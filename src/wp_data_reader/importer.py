"""Import mysqldump/phpMyAdmin SQL dumps into the local SQLite cache."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
import sqlite3
import time
from pathlib import Path
from typing import Callable, Iterator

from .db import connect, rebuild_fts
from .dumpparser import InsertBatch, iter_inserts

# (path, table_name, fraction) -> None, called as each chunk of an INSERT
# statement is written, so progress can be reported at sub-table granularity.
ProgressCallback = Callable[[Path, str, float], None]

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
            cur = conn.execute(
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
            # Populated inline (rather than a separate rebuild-at-the-end pass)
            # so search works against posts as soon as they land, not only
            # once the whole import finishes.
            conn.execute(
                "INSERT INTO posts_fts(rowid, post_title, post_content, post_excerpt) VALUES (?,?,?,?)",
                (cur.lastrowid, d.get("post_title"), d.get("post_content"), d.get("post_excerpt")),
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


def import_dump_file(conn: sqlite3.Connection, path: Path, on_progress: ProgressCallback | None = None) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    source_file = str(path)
    # Chunk boundaries (~3000 rows) give smooth progress granularity, but
    # committing that often across several concurrent processes sharing one
    # SQLite file causes heavy write-lock contention (each commit briefly
    # takes the single writer lock). Commit on a time budget instead, so
    # progress is still reported every chunk but disk writes/lock churn stay
    # proportional to wall-clock time, not row count.
    last_commit = time.monotonic()
    for batch in iter_inserts(text):
        _import_batch(conn, source_file, batch)
        if time.monotonic() - last_commit >= 0.5:
            conn.commit()
            last_commit = time.monotonic()
        if on_progress:
            on_progress(path, batch.table.full_name, batch.fraction)
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
        post_ids = [r["id"] for r in conn.execute("SELECT id FROM posts WHERE site_id=?", (sid,))]
        if post_ids:
            conn.executemany("DELETE FROM posts_fts WHERE rowid=?", [(pid,) for pid in post_ids])
        for table in (
            "posts", "postmeta", "terms", "term_taxonomy",
            "term_relationships", "users", "ngg_pictures", "ngg_gallery",
        ):
            conn.execute(f"DELETE FROM {table} WHERE site_id=?", (sid,))
        conn.execute("DELETE FROM sites WHERE id=?", (sid,))
    conn.execute("DELETE FROM imported_files WHERE path=?", (source_file,))
    conn.execute("DELETE FROM import_progress WHERE path=?", (source_file,))
    conn.commit()


def import_all(
    conn: sqlite3.Connection, paths: list[Path], force: bool = False,
    on_progress: ProgressCallback | None = None,
) -> None:
    """Import files one at a time on the current connection/thread."""
    for path in paths:
        if force or needs_import(conn, path):
            forget_file(conn, path)
            import_dump_file(conn, path, on_progress=on_progress)
            mark_imported(conn, path)


def _write_progress(conn: sqlite3.Connection, path: str, table_name: str | None,
                     fraction: float, status: str, error: str | None = None) -> None:
    conn.execute(
        """INSERT INTO import_progress(path, table_name, fraction, status, error, updated_at)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(path) DO UPDATE SET
            table_name=excluded.table_name, fraction=excluded.fraction,
            status=excluded.status, error=excluded.error, updated_at=excluded.updated_at""",
        (path, table_name, fraction, status, error, time.time()),
    )


def ensure_fts_backfilled(conn: sqlite3.Connection) -> None:
    """posts_fts is populated as part of merging imported data in; this only
    backfills a cache built before that existed (posts present, index empty)."""
    posts = conn.execute("SELECT count(*) c FROM posts").fetchone()["c"]
    indexed = conn.execute("SELECT count(*) c FROM posts_fts").fetchone()["c"]
    if posts > 0 and indexed == 0:
        rebuild_fts(conn)


# --- Parallel import ------------------------------------------------------
#
# SQLite allows only one writer at a time. Committing to one shared db file
# from several concurrent processes (even with a generous busy_timeout)
# serializes them so heavily that it's *slower* than importing sequentially
# (measured: 5 files went from ~45s sequential to ~55-60s "parallel" that
# way). Instead, each file is parsed and imported into its own private
# "shard" database, entirely uncontended, which is where the real multi-core
# win comes from; the small, already-parsed shards are then merged into the
# main db with a handful of fast bulk `INSERT ... SELECT`s.

def shard_db_paths(shard_dir: Path, paths: list[Path]) -> dict[str, Path]:
    """Deterministic mapping from dump path to its private shard db, shared
    between the orchestrator and anything (e.g. a progress poller) that
    needs to know where a given file's shard lives before/while it runs."""
    return {str(p): shard_dir / f"shard_{i}.sqlite3" for i, p in enumerate(paths)}


def import_file_to_shard(shard_db_path: str, path_str: str) -> tuple[str, str | None]:
    """Entry point run in a worker *process*: parse+import one dump file into
    its own fresh, uncontended shard database. Progress is written into that
    shard's own ``import_progress`` row (pollable independently by the
    caller). Returns ``(path, error)``; ``error`` is ``None`` on success."""
    path = Path(path_str)
    conn = connect(Path(shard_db_path))
    try:
        def _progress(p: Path, table_name: str, fraction: float) -> None:
            _write_progress(conn, str(p), table_name, fraction, "importing")

        import_dump_file(conn, path, on_progress=_progress)
        _write_progress(conn, path_str, None, 1.0, "done")
        conn.commit()
        return (path_str, None)
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        conn.rollback()
        _write_progress(conn, path_str, None, 0.0, "error", str(exc))
        conn.commit()
        return (path_str, str(exc))
    finally:
        conn.close()


_MERGE_TABLES: list[tuple[str, list[str]]] = [
    ("posts", [
        "wp_id", "post_author", "post_date", "post_date_gmt", "post_title", "post_name",
        "post_content", "post_excerpt", "post_status", "post_type", "post_parent", "guid",
        "menu_order", "comment_status", "ping_status", "post_password", "post_modified",
        "post_modified_gmt", "post_mime_type", "comment_count",
    ]),
    ("postmeta", ["post_wp_id", "meta_key", "meta_value"]),
    ("terms", ["term_id", "name", "slug"]),
    ("term_taxonomy", ["term_taxonomy_id", "term_id", "taxonomy", "description", "parent", "count"]),
    ("term_relationships", ["object_id", "term_taxonomy_id"]),
    ("users", ["wp_id", "user_login", "display_name", "user_email", "user_nicename"]),
    ("ngg_pictures", ["pid", "galleryid", "filename", "description", "alttext"]),
    ("ngg_gallery", ["gid", "name", "slug", "path"]),
]


def merge_shard(main_conn: sqlite3.Connection, shard_path: Path) -> None:
    """Copy one shard database's imported rows into the main db, remapping
    each shard-local site_id to the (newly allocated, if needed) site_id in
    the main db. posts_fts is rebuilt once by the caller after all shards
    are merged, rather than per-row here."""
    main_conn.execute("ATTACH DATABASE ? AS shard", (str(shard_path),))
    try:
        site_id_map: dict[int, int] = {}
        for srow in main_conn.execute("SELECT * FROM shard.sites"):
            main_conn.execute(
                "INSERT OR IGNORE INTO sites(source_file, prefix, label) VALUES (?,?,?)",
                (srow["source_file"], srow["prefix"], srow["label"]),
            )
            new_id = main_conn.execute(
                "SELECT id FROM sites WHERE source_file=? AND prefix=?",
                (srow["source_file"], srow["prefix"]),
            ).fetchone()["id"]
            site_id_map[srow["id"]] = new_id

        main_conn.execute("DROP TABLE IF EXISTS temp.site_map")
        main_conn.execute("CREATE TEMP TABLE site_map(old_id INTEGER PRIMARY KEY, new_id INTEGER)")
        main_conn.executemany("INSERT INTO temp.site_map VALUES (?,?)", site_id_map.items())

        for table, cols in _MERGE_TABLES:
            col_list = ", ".join(cols)
            selected = ", ".join(f"s.{c}" for c in cols)
            main_conn.execute(
                f"""INSERT INTO {table} (site_id, {col_list})
                    SELECT sm.new_id, {selected}
                    FROM shard.{table} s JOIN temp.site_map sm ON sm.old_id = s.site_id"""
            )
        main_conn.commit()  # DETACH fails if a transaction touching it is still open
    finally:
        main_conn.execute("DETACH DATABASE shard")


def import_all_parallel(
    db_path: Path, paths: list[Path], shard_dir: Path, max_workers: int | None = None,
) -> Iterator[tuple[str, str | None]]:
    """Parse+import every file in its own OS process (real parallelism for
    this CPU-bound work, unlike threads), merging each into the main db as
    it finishes, and yield ``(path, error)`` as it does. The caller is
    responsible for having already decided *which* files need importing
    (e.g. via :func:`needs_import`) and for cleaning up ``shard_dir``
    afterwards. Per-file progress while still in flight is available by
    polling that file's shard db (see :func:`shard_db_paths`)."""
    main_conn = connect(db_path)
    shards = shard_db_paths(shard_dir, paths)
    try:
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(import_file_to_shard, str(shards[str(p)]), str(p)): p
                for p in paths
            }
            for future in as_completed(futures):
                path = futures[future]
                path_str, error = future.result()
                if error is None:
                    merge_shard(main_conn, shards[path_str])
                    mark_imported(main_conn, path)
                    main_conn.commit()
                yield (path_str, error)

        rebuild_fts(main_conn)
    finally:
        main_conn.close()
