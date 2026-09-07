"""Turn raw wp_posts.post_content into displayable HTML / Markdown, and
resolve embedded media (images, NextGEN gallery shortcodes) back to the
filenames WordPress actually stored in wp-content/uploads."""
from __future__ import annotations

from dataclasses import dataclass
import re

from markdownify import markdownify

_BLOCK_TAG_RE = re.compile(
    r"^\s*<(p|div|ul|ol|li|blockquote|h[1-6]|table|thead|tbody|tr|td|th|"
    r"pre|form|fieldset|hr|figure|figcaption|iframe|script|style|section|"
    r"article|aside|header|footer|nav)\b",
    re.IGNORECASE,
)


def is_gutenberg(content: str) -> bool:
    return "<!-- wp:" in content


def wpautop(text: str) -> str:
    """A pragmatic subset of WordPress's wpautop(): wraps loose text blocks
    (separated by blank lines) in <p> tags and turns single newlines into
    <br />, while leaving blocks that already start with a block-level tag
    alone."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    blocks = re.split(r"\n\s*\n", text)
    out = []
    for block in blocks:
        block = block.strip("\n")
        if not block.strip():
            continue
        if _BLOCK_TAG_RE.match(block):
            out.append(block)
        else:
            out.append("<p>" + block.replace("\n", "<br />\n") + "</p>")
    return "\n\n".join(out)


def prepare_html(post_content: str) -> str:
    """Best-effort rendering of post_content as it would appear on the site."""
    if is_gutenberg(post_content):
        # Strip block comments, keep the inner markup which is already HTML.
        return re.sub(r"<!--\s*/?wp:[^>]*-->", "", post_content).strip()
    if _BLOCK_TAG_RE.search(post_content[:200]) and "<p" in post_content[:2000]:
        return post_content
    return wpautop(post_content)


def html_to_markdown(html: str) -> str:
    return markdownify(html, heading_style="ATX", bullets="-").strip()


# --- Media resolution -------------------------------------------------

_SIZE_SUFFIX_RE = re.compile(r"-\d+x\d+(?=\.\w+$)")
_UPLOADS_SRC_RE = re.compile(
    r"""(?:src|href)=["']([^"']*wp-content/uploads/([^"']+))["']""",
    re.IGNORECASE,
)
_SINGLEPIC_RE = re.compile(r"\[singlepic\s+id=(\d+)[^\]]*\]", re.IGNORECASE)
_NGGALLERY_RE = re.compile(r"\[nggallery\s+id=(\d+)[^\]]*\]", re.IGNORECASE)
_GALLERY_IDS_RE = re.compile(r"\[gallery[^\]]*\bids=[\"']([\d,\s]+)[\"'][^\]]*\]", re.IGNORECASE)


def normalize_basename(name: str) -> str:
    name = name.rsplit("/", 1)[-1]
    return _SIZE_SUFFIX_RE.sub("", name).lower()


@dataclass
class MediaRef:
    kind: str  # "image", "gallery-image", "gallery"
    as_referenced: str  # what appeared in the content
    resolved_path: str | None  # best-known uploads-relative path, if resolved
    note: str = ""


class MediaIndex:
    """Per-site lookup of attachment filenames and NextGEN gallery pictures,
    used to resolve embedded media back to their original filenames."""

    def __init__(self, conn, site_id: int):
        self.site_id = site_id
        self.by_normalized_basename: dict[str, str] = {}
        self.by_wp_id: dict[int, str] = {}

        rows = conn.execute(
            """SELECT p.wp_id AS wp_id, p.guid AS guid,
                      (SELECT meta_value FROM postmeta pm
                       WHERE pm.site_id = p.site_id AND pm.post_wp_id = p.wp_id
                         AND pm.meta_key = '_wp_attached_file') AS attached_file
               FROM posts p
               WHERE p.site_id = ? AND p.post_type = 'attachment'""",
            (site_id,),
        ).fetchall()
        for r in rows:
            rel = r["attached_file"] or (r["guid"] or "").rsplit("wp-content/uploads/", 1)[-1]
            if not rel:
                continue
            self.by_wp_id[r["wp_id"]] = rel
            self.by_normalized_basename[normalize_basename(rel)] = rel

        self.ngg_pictures = {
            r["pid"]: (r["filename"], r["galleryid"])
            for r in conn.execute(
                "SELECT pid, filename, galleryid FROM ngg_pictures WHERE site_id=?",
                (site_id,),
            )
        }
        self.ngg_galleries = {
            r["gid"]: r["path"]
            for r in conn.execute(
                "SELECT gid, path FROM ngg_gallery WHERE site_id=?", (site_id,)
            )
        }

    def resolve_upload_ref(self, ref_path: str) -> MediaRef:
        norm = normalize_basename(ref_path)
        original = self.by_normalized_basename.get(norm)
        if original and original.lower() != ref_path.lstrip("/").lower():
            return MediaRef("image", ref_path, original, "resolved to original upload")
        return MediaRef("image", ref_path, original or ref_path, "" if original else "not found in attachments table")

    def resolve_singlepic(self, pid: int) -> MediaRef:
        pic = self.ngg_pictures.get(pid)
        if not pic:
            return MediaRef("gallery-image", f"singlepic id={pid}", None, "not found in wp_ngg_pictures")
        filename, gallery_id = pic
        gallery_path = self.ngg_galleries.get(gallery_id)
        resolved = f"{gallery_path}/{filename}" if gallery_path else filename
        return MediaRef("gallery-image", f"singlepic id={pid}", resolved, "resolved via NextGEN gallery")

    def resolve_nggallery(self, gid: int) -> MediaRef:
        gallery_path = self.ngg_galleries.get(gid)
        count = sum(1 for _, g in self.ngg_pictures.values() if g == gid)
        return MediaRef(
            "gallery", f"nggallery id={gid}", gallery_path,
            f"resolved gallery folder ({count} pictures)" if gallery_path else "gallery not found",
        )

    def resolve_gallery_ids(self, ids: list[int]) -> list[MediaRef]:
        refs = []
        for wp_id in ids:
            rel = self.by_wp_id.get(wp_id)
            refs.append(
                MediaRef("image", f"gallery attachment id={wp_id}", rel,
                          "resolved via attachment id" if rel else "attachment not found")
            )
        return refs


def find_media_refs(content: str, index: MediaIndex) -> list[MediaRef]:
    refs: list[MediaRef] = []
    for m in _UPLOADS_SRC_RE.finditer(content):
        refs.append(index.resolve_upload_ref(m.group(2)))
    for m in _SINGLEPIC_RE.finditer(content):
        refs.append(index.resolve_singlepic(int(m.group(1))))
    for m in _NGGALLERY_RE.finditer(content):
        refs.append(index.resolve_nggallery(int(m.group(1))))
    for m in _GALLERY_IDS_RE.finditer(content):
        ids = [int(x) for x in re.findall(r"\d+", m.group(1))]
        refs.extend(index.resolve_gallery_ids(ids))
    return refs
