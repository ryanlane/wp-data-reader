from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .app import WPReaderApp
from .db import connect
from .importer import ensure_fts_backfilled


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wp-data-reader",
        description="Browse, search, and export posts/pages from WordPress SQL dumps.",
    )
    parser.add_argument(
        "dumps", nargs="+", type=Path,
        help="One or more mysqldump/phpMyAdmin .sql dump files to load.",
    )
    parser.add_argument(
        "--db", type=Path, default=None,
        help="Path to the SQLite cache file (default: .wp_data_reader_cache.sqlite3 "
             "next to the first dump file).",
    )
    parser.add_argument(
        "--rebuild", action="store_true",
        help="Force re-import of all dump files even if unchanged.",
    )
    parser.add_argument(
        "--jobs", type=int, default=None,
        help="Max dump files to import in parallel (default: one process per "
             "CPU core, capped at the number of files).",
    )
    parser.add_argument(
        "--uploads-dir", type=Path, default=None,
        help="Local directory mirroring wp-content/uploads (e.g. from a "
             "recovered backup), used to open image/media links against a "
             "local file instead of the original (possibly dead) site. "
             "Remembered for this dump set after the first run.",
    )
    args = parser.parse_args(argv)

    for p in args.dumps:
        if not p.is_file():
            print(f"error: not a file: {p}", file=sys.stderr)
            return 1
    if args.uploads_dir is not None and not args.uploads_dir.is_dir():
        print(f"error: not a directory: {args.uploads_dir}", file=sys.stderr)
        return 1

    db_path = args.db or (args.dumps[0].parent / ".wp_data_reader_cache.sqlite3")
    # Creates the schema (and enables WAL) up front, synchronously, before
    # any worker process/thread touches the same file.
    conn = connect(db_path)
    ensure_fts_backfilled(conn)

    app = WPReaderApp(conn, db_path=db_path, dump_paths=args.dumps,
                       force_reimport=args.rebuild, max_workers=args.jobs,
                       uploads_dir=args.uploads_dir)
    app.run()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
