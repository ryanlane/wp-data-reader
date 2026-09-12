"""Query helpers that assemble a post together with all of its metadata."""
from __future__ import annotations

import calendar
import re
import sqlite3
from dataclasses import dataclass, field


@dataclass
class Term:
    taxonomy: str
    name: str
    slug: str


@dataclass
class PostRecord:
    row_id: int
    site_id: int
    wp_id: int
    site_label: str
    title: str
    name: str
    content: str
    excerpt: str
    status: str
    post_type: str
    date: str
    modified: str
    author: str
    guid: str
    parent: int
    password: str = ""
    meta: dict[str, list[str]] = field(default_factory=dict)
    terms: list[Term] = field(default_factory=list)

    @property
    def display_title(self) -> str:
        return self.title.strip() or f"(untitled {self.post_type} #{self.wp_id})"

    def terms_by_taxonomy(self, taxonomy: str) -> list[Term]:
        return [t for t in self.terms if t.taxonomy == taxonomy]


def list_sites(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM sites ORDER BY label").fetchall()


def list_post_types(conn: sqlite3.Connection, site_ids: list[int] | None) -> list[str]:
    if site_ids is None:
        rows = conn.execute(
            "SELECT DISTINCT post_type FROM posts ORDER BY post_type"
        ).fetchall()
    else:
        placeholders = ",".join("?" * len(site_ids))
        rows = conn.execute(
            f"SELECT DISTINCT post_type FROM posts WHERE site_id IN ({placeholders}) ORDER BY post_type",
            site_ids,
        ).fetchall()
    return [r["post_type"] for r in rows]


def list_statuses(conn: sqlite3.Connection, site_ids: list[int] | None) -> list[str]:
    if site_ids is None:
        rows = conn.execute(
            "SELECT DISTINCT post_status FROM posts ORDER BY post_status"
        ).fetchall()
    else:
        placeholders = ",".join("?" * len(site_ids))
        rows = conn.execute(
            f"SELECT DISTINCT post_status FROM posts WHERE site_id IN ({placeholders}) ORDER BY post_status",
            site_ids,
        ).fetchall()
    return [r["post_status"] for r in rows]


def list_terms(conn: sqlite3.Connection, site_ids: list[int] | None, taxonomy: str) -> list[tuple[str, str]]:
    """Distinct (name, slug) pairs for a taxonomy, for populating a filter dropdown."""
    if site_ids is None:
        rows = conn.execute(
            """SELECT DISTINCT te.name AS name, te.slug AS slug
               FROM term_taxonomy tt
               JOIN terms te ON te.site_id = tt.site_id AND te.term_id = tt.term_id
               WHERE tt.taxonomy = ?
               ORDER BY te.name""",
            (taxonomy,),
        ).fetchall()
    else:
        placeholders = ",".join("?" * len(site_ids))
        rows = conn.execute(
            f"""SELECT DISTINCT te.name AS name, te.slug AS slug
               FROM term_taxonomy tt
               JOIN terms te ON te.site_id = tt.site_id AND te.term_id = tt.term_id
               WHERE tt.site_id IN ({placeholders}) AND tt.taxonomy = ?
               ORDER BY te.name""",
            (*site_ids, taxonomy),
        ).fetchall()
    return [(r["name"], r["slug"]) for r in rows]


_PARTIAL_DATE_RE = re.compile(r"^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?$")


def resolve_date_bound(value: str, *, end: bool) -> str | None:
    """Expand a possibly-partial date ("2012", "2012-12", or "2012-12-15")
    into a full "YYYY-MM-DD HH:MM:SS" bound. ``end`` picks the last vs. first
    instant of whatever period the given precision implies, so "2012" as a
    lower bound starts at Jan 1 and as an upper bound reaches Dec 31."""
    value = value.strip()
    if not value:
        return None
    m = _PARTIAL_DATE_RE.match(value)
    if not m:
        return None
    year = int(m.group(1))
    month = int(m.group(2)) if m.group(2) else None
    day = int(m.group(3)) if m.group(3) else None

    if month is None:
        month, day = (12, 31) if end else (1, 1)
    elif day is None:
        day = calendar.monthrange(year, month)[1] if end else 1

    time_part = "23:59:59" if end else "00:00:00"
    return f"{year:04d}-{month:02d}-{day:02d} {time_part}"


def query_posts(
    conn: sqlite3.Connection,
    site_ids: list[int] | None = None,
    post_types: list[str] | None = None,
    statuses: list[str] | None = None,
    search: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[sqlite3.Row]:
    clauses = []
    params: list = []

    if search:
        base = (
            "SELECT p.* FROM posts p "
            "JOIN posts_fts f ON f.rowid = p.id "
            "WHERE posts_fts MATCH ?"
        )
        params.append(search)
    else:
        base = "SELECT p.* FROM posts p WHERE 1=1"

    if site_ids:
        clauses.append(f"p.site_id IN ({','.join('?' * len(site_ids))})")
        params.extend(site_ids)
    if post_types:
        clauses.append(f"p.post_type IN ({','.join('?' * len(post_types))})")
        params.extend(post_types)
    if statuses:
        clauses.append(f"p.post_status IN ({','.join('?' * len(statuses))})")
        params.extend(statuses)
    for taxonomy, slug in (("category", category), ("post_tag", tag)):
        if slug:
            clauses.append(
                "EXISTS (SELECT 1 FROM term_relationships tr "
                "JOIN term_taxonomy tt ON tt.site_id = tr.site_id AND tt.term_taxonomy_id = tr.term_taxonomy_id "
                "JOIN terms te ON te.site_id = tr.site_id AND te.term_id = tt.term_id "
                "WHERE tr.site_id = p.site_id AND tr.object_id = p.wp_id "
                "AND tt.taxonomy = ? AND te.slug = ?)"
            )
            params.extend([taxonomy, slug])
    # A lone value in either field pins to just that period (e.g. "2018" ->
    # all of 2018) rather than leaving the other side unbounded; filling in
    # both with different values gives a genuine range.
    effective_from = date_from or date_to
    effective_to = date_to or date_from
    if effective_from:
        resolved = resolve_date_bound(effective_from, end=False)
        if resolved:
            clauses.append("p.post_date >= ?")
            params.append(resolved)
    if effective_to:
        resolved = resolve_date_bound(effective_to, end=True)
        if resolved:
            clauses.append("p.post_date <= ?")
            params.append(resolved)

    sql = base + ("" if not clauses else " AND " + " AND ".join(clauses))
    sql += " ORDER BY p.post_date DESC"
    return conn.execute(sql, params).fetchall()


def load_post(conn: sqlite3.Connection, row_id: int) -> PostRecord:
    p = conn.execute("SELECT * FROM posts WHERE id=?", (row_id,)).fetchone()
    site = conn.execute("SELECT label FROM sites WHERE id=?", (p["site_id"],)).fetchone()

    author_row = conn.execute(
        "SELECT display_name, user_login FROM users WHERE site_id=? AND wp_id=?",
        (p["site_id"], p["post_author"]),
    ).fetchone()
    author = (author_row["display_name"] or author_row["user_login"]) if author_row else str(p["post_author"])

    meta: dict[str, list[str]] = {}
    for m in conn.execute(
        "SELECT meta_key, meta_value FROM postmeta WHERE site_id=? AND post_wp_id=? ORDER BY meta_key",
        (p["site_id"], p["wp_id"]),
    ):
        if m["meta_key"] is None:
            continue
        meta.setdefault(m["meta_key"], []).append(m["meta_value"])

    terms: list[Term] = []
    for t in conn.execute(
        """SELECT tt.taxonomy AS taxonomy, te.name AS name, te.slug AS slug
           FROM term_relationships tr
           JOIN term_taxonomy tt ON tt.site_id = tr.site_id AND tt.term_taxonomy_id = tr.term_taxonomy_id
           JOIN terms te ON te.site_id = tr.site_id AND te.term_id = tt.term_id
           WHERE tr.site_id = ? AND tr.object_id = ?
           ORDER BY tt.taxonomy, te.name""",
        (p["site_id"], p["wp_id"]),
    ):
        terms.append(Term(t["taxonomy"], t["name"], t["slug"]))

    return PostRecord(
        row_id=p["id"],
        site_id=p["site_id"],
        wp_id=p["wp_id"],
        site_label=site["label"] if site else "",
        title=p["post_title"] or "",
        name=p["post_name"] or "",
        content=p["post_content"] or "",
        excerpt=p["post_excerpt"] or "",
        status=p["post_status"] or "",
        post_type=p["post_type"] or "",
        date=p["post_date"] or "",
        modified=p["post_modified"] or "",
        author=author,
        guid=p["guid"] or "",
        parent=p["post_parent"] or 0,
        password=p["post_password"] or "",
        meta=meta,
        terms=terms,
    )
