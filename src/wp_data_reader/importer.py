"""Import mysqldump/phpMyAdmin SQL dumps into the local SQLite cache."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .dumpparser import InsertBatch, iter_inserts

POST_COLUMNS = [
    "ID", "post_author", "post_date", "post_date_gmt", "post_content",
    "post_title", "post_excerpt", "post_status", "comment_status",
    "ping_status", "post_password", "post_name", "post_modified",
    "post_modified_gmt", "post_parent", "guid", "menu_order", "post_type",
    "post_mime_type", "comment_count",
]


def _site_id(conn: sqlite3.Connection, source_file: str, prefix: str) -> int:
    label = f"{Path(source_file).stem} [{prefix}]"
    conn.execute(
        "INSERT OR IGNORE INTO sites(source_file, prefix, label) VALUES (?, ?, ?)",
        (source_file, prefix, label),
    )
    row = conn.execute(
        "SELECT id FROM sites WHERE source_file=? AND prefix=?",
        (source_file, prefix),
    ).fetchone()
    return row["id"]


def _row_dict(batch: InsertBatch, row: list) -> dict:
    return dict(zip(batch.columns, row))


def _import_batch(conn: sqlite3.Connection, source_file: str, batch: InsertBatch) -> None:
    site_id = _site_id(conn, source_file, batch.table.prefix)
    suffix = batch.table.suffix

    if suffix == "posts":
        for row in batch.rows:
            d = _row_dict(batch, row)
            conn.execute(
                """INSERT OR REPLACE INTO posts
                (site_id, wp_id, post_author, post_date, post_date_gmt, post_title,
                 post_name, post_content, post_excerpt, post_status, post_type,
                 post_parent, guid, menu_order, comment_status, ping_status,
                 post_password, post_modified, post_modified_gmt, post_mime_type,
                 comment_count)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    site_id, d.get("ID"), d.get("post_author"), d.get("post_date"),
                    d.get("post_date_gmt"), d.get("post_title"), d.get("post_name"),
                    d.get("post_content"), d.get("post_excerpt"), d.get("post_status"),
                    d.get("post_type"), d.get("post_parent"), d.get("guid"),
                    d.get("menu_order"), d.get("comment_status"), d.get("ping_status"),
                    d.get("post_password"), d.get("post_modified"),
                    d.get("post_modified_gmt"), d.get("post_mime_type"),
                    d.get("comment_count"),
                ),
            )
    elif suffix == "postmeta":
        conn.executemany(
            "INSERT INTO postmeta(site_id, post_wp_id, meta_key, meta_value) VALUES (?,?,?,?)",
            [
                (site_id, _row_dict(batch, r).get("post_id"),
                 _row_dict(batch, r).get("meta_key"), _row_dict(batch, r).get("meta_value"))
                for r in batch.rows
            ],
        )
    elif suffix == "terms":
        conn.executemany(
            "INSERT INTO terms(site_id, term_id, name, slug) VALUES (?,?,?,?)",
            [
                (site_id, d.get("term_id"), d.get("name"), d.get("slug"))
                for d in (_row_dict(batch, r) for r in batch.rows)
            ],
        )
    elif suffix == "term_taxonomy":
        conn.executemany(
            """INSERT INTO term_taxonomy
            (site_id, term_taxonomy_id, term_id, taxonomy, description, parent, count)
            VALUES (?,?,?,?,?,?,?)""",
            [
                (site_id, d.get("term_taxonomy_id"), d.get("term_id"), d.get("taxonomy"),
                 d.get("description"), d.get("parent"), d.get("count"))
                for d in (_row_dict(batch, r) for r in batch.rows)
            ],
        )
    elif suffix == "term_relationships":
        conn.executemany(
            "INSERT INTO term_relationships(site_id, object_id, term_taxonomy_id) VALUES (?,?,?)",
            [
                (site_id, d.get("object_id"), d.get("term_taxonomy_id"))
                for d in (_row_dict(batch, r) for r in batch.rows)
            ],
        )
    elif suffix == "users":
        conn.executemany(
            """INSERT INTO users(site_id, wp_id, user_login, display_name, user_email, user_nicename)
            VALUES (?,?,?,?,?,?)""",
            [
                (site_id, d.get("ID"), d.get("user_login"), d.get("display_name"),
                 d.get("user_email"), d.get("user_nicename"))
                for d in (_row_dict(batch, r) for r in batch.rows)
            ],
        )
    elif suffix == "ngg_pictures":
        conn.executemany(
            """INSERT INTO ngg_pictures(site_id, pid, galleryid, filename, description, alttext)
            VALUES (?,?,?,?,?,?)""",
            [
                (site_id, d.get("pid"), d.get("galleryid"), d.get("filename"),
                 d.get("description"), d.get("alttext"))
                for d in (_row_dict(batch, r) for r in batch.rows)
            ],
        )
    elif suffix == "ngg_gallery":
        conn.executemany(
            "INSERT INTO ngg_gallery(site_id, gid, name, slug, path) VALUES (?,?,?,?,?)",
            [
                (site_id, d.get("gid"), d.get("name"), d.get("slug"), d.get("path"))
                for d in (_row_dict(batch, r) for r in batch.rows)
            ],
        )
    # termmeta currently unused for display; skipped.


def import_dump_file(conn: sqlite3.Connection, path: Path, on_progress=None) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    source_file = str(path)
    for i, batch in enumerate(iter_inserts(text)):
        _import_batch(conn, source_file, batch)
        if on_progress and i % 20 == 0:
            on_progress(path, batch.table.full_name)
    conn.commit()


def file_fingerprint(path: Path) -> tuple[int, float]:
    st = path.stat()
    return (st.st_size, st.st_mtime)


def needs_import(conn: sqlite3.Connection, path: Path) -> bool:
    size, mtime = file_fingerprint(path)
    row = conn.execute(
        "SELECT size, mtime FROM imported_files WHERE path=?", (str(path),)
    ).fetchone()
    return row is None or row["size"] != size or row["mtime"] != mtime


def mark_imported(conn: sqlite3.Connection, path: Path) -> None:
    size, mtime = file_fingerprint(path)
    conn.execute(
        "INSERT OR REPLACE INTO imported_files(path, size, mtime) VALUES (?,?,?)",
        (str(path), size, mtime),
    )
    conn.commit()


def forget_file(conn: sqlite3.Connection, path: Path) -> None:
    source_file = str(path)
    site_ids = [
        r["id"] for r in conn.execute(
            "SELECT id FROM sites WHERE source_file=?", (source_file,)
        )
    ]
    for sid in site_ids:
        for table in (
            "posts", "postmeta", "terms", "term_taxonomy",
            "term_relationships", "users", "ngg_pictures", "ngg_gallery",
        ):
            conn.execute(f"DELETE FROM {table} WHERE site_id=?", (sid,))
        conn.execute("DELETE FROM sites WHERE id=?", (sid,))
    conn.execute("DELETE FROM imported_files WHERE path=?", (source_file,))
    conn.commit()


def import_all(conn: sqlite3.Connection, paths: list[Path], force: bool = False, on_progress=None) -> None:
    for path in paths:
        if force:
            forget_file(conn, path)
        elif not needs_import(conn, path):
            continue
        else:
            forget_file(conn, path)  # re-import cleanly if it changed
        import_dump_file(conn, path, on_progress=on_progress)
        mark_imported(conn, path)
