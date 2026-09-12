"""Export a post/page to a standalone HTML or Markdown file."""
from __future__ import annotations

from html import escape
from pathlib import Path

from .content import MediaIndex, MediaRef, find_media_refs, html_to_markdown, prepare_html, rewrite_uploads_links
from .models import PostRecord

_HTML_TEMPLATE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
 body {{ max-width: 46rem; margin: 2rem auto; padding: 0 1rem;
        font-family: Georgia, serif; line-height: 1.6; color: #222; }}
 .meta {{ color: #666; font-size: 0.9rem; margin-bottom: 2rem; }}
 .meta dt {{ font-weight: bold; float: left; clear: left; width: 9rem; }}
 .meta dd {{ margin-left: 9rem; }}
 img {{ max-width: 100%; }}
 blockquote {{ border-left: 3px solid #ccc; margin-left: 0; padding-left: 1rem; color: #555; }}
 .media-appendix {{ margin-top: 2rem; border-top: 1px solid #ccc; padding-top: 1rem;
                     font-size: 0.85rem; color: #555; }}
</style>
</head>
<body>
<h1>{title}</h1>
<dl class="meta">
{meta_rows}
</dl>
<article>
{content}
</article>
{media_appendix}
</body>
</html>
"""


def _meta_rows(post: PostRecord) -> str:
    rows = [
        ("Author", post.author),
        ("Date", post.date),
        ("Modified", post.modified),
        ("Status", post.status),
        ("Type", post.post_type),
        ("Slug", post.name),
        ("Site", post.site_label),
    ]
    cats = ", ".join(t.name for t in post.terms_by_taxonomy("category"))
    tags = ", ".join(t.name for t in post.terms_by_taxonomy("post_tag"))
    if cats:
        rows.append(("Categories", cats))
    if tags:
        rows.append(("Tags", tags))
    return "\n".join(
        f"<dt>{escape(k)}</dt><dd>{escape(str(v))}</dd>" for k, v in rows if v
    )


def _media_html(refs: list[MediaRef]) -> str:
    if not refs:
        return ""
    items = []
    for r in refs:
        target = r.resolved_path or r.as_referenced
        items.append(f"<li><code>{escape(r.as_referenced)}</code> &rarr; <code>{escape(str(target))}</code>"
                     f"{' (' + escape(r.note) + ')' if r.note else ''}</li>")
    return "<div class=\"media-appendix\"><strong>Embedded media (original uploads paths)</strong><ul>" + "".join(items) + "</ul></div>"


def _media_markdown(refs: list[MediaRef]) -> str:
    if not refs:
        return ""
    lines = ["", "---", "", "**Embedded media (original uploads paths)**", ""]
    for r in refs:
        target = r.resolved_path or r.as_referenced
        note = f" _{r.note}_" if r.note else ""
        lines.append(f"- `{r.as_referenced}` -> `{target}`{note}")
    return "\n".join(lines)


def export_html(
    post: PostRecord, media_refs: list[MediaRef], dest: Path,
    *, uploads_dir: Path | None = None, media_index: MediaIndex | None = None,
) -> Path:
    html_body = prepare_html(post.content)
    if uploads_dir is not None:
        html_body = rewrite_uploads_links(html_body, uploads_dir, media_index)
    doc = _HTML_TEMPLATE.format(
        title=escape(post.display_title),
        meta_rows=_meta_rows(post),
        content=html_body,
        media_appendix=_media_html(media_refs),
    )
    dest.write_text(doc, encoding="utf-8")
    return dest


def export_markdown(
    post: PostRecord, media_refs: list[MediaRef], dest: Path,
    *, uploads_dir: Path | None = None, media_index: MediaIndex | None = None,
) -> Path:
    front_matter = [
        "---",
        f"title: {post.display_title!r}",
        f"author: {post.author!r}",
        f"date: {post.date!r}",
        f"modified: {post.modified!r}",
        f"status: {post.status!r}",
        f"type: {post.post_type!r}",
        f"slug: {post.name!r}",
        f"site: {post.site_label!r}",
    ]
    cats = [t.name for t in post.terms_by_taxonomy("category")]
    tags = [t.name for t in post.terms_by_taxonomy("post_tag")]
    if cats:
        front_matter.append(f"categories: {cats!r}")
    if tags:
        front_matter.append(f"tags: {tags!r}")
    front_matter.append("---\n")

    body_html = prepare_html(post.content)
    if uploads_dir is not None:
        body_html = rewrite_uploads_links(body_html, uploads_dir, media_index)
    body = html_to_markdown(body_html)
    doc = "\n".join(front_matter) + f"\n# {post.display_title}\n\n{body}\n" + _media_markdown(media_refs)
    dest.write_text(doc, encoding="utf-8")
    return dest


def default_filename(post: PostRecord, ext: str) -> str:
    stem = post.name or f"{post.post_type}-{post.wp_id}"
    return f"{stem}.{ext}"


def build_media_refs(conn, post: PostRecord):
    from .content import MediaIndex
    index = MediaIndex(conn, post.site_id)
    return find_media_refs(post.content, index)
