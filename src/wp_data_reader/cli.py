from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .app import WPReaderApp
from .db import connect, rebuild_fts
from .importer import import_all


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
    args = parser.parse_args(argv)

    for p in args.dumps:
        if not p.is_file():
            print(f"error: not a file: {p}", file=sys.stderr)
            return 1

    db_path = args.db or (args.dumps[0].parent / ".wp_data_reader_cache.sqlite3")
    conn = connect(db_path)

    def on_progress(path: Path, table: str) -> None:
        print(f"\rImporting {path.name}: {table}" + " " * 10, end="", file=sys.stderr)

    import_all(conn, args.dumps, force=args.rebuild, on_progress=on_progress)
    print(file=sys.stderr)
    rebuild_fts(conn)

    app = WPReaderApp(conn)
    app.run()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
