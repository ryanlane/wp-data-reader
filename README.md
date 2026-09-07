# wp-data-reader

A terminal UI for browsing, searching, and exporting posts and pages from
WordPress SQL dumps (mysqldump / phpMyAdmin `.sql` files) — no MySQL server
required.

## Usage

```sh
uv run wp-data-reader path/to/dump1.sql path/to/dump2.sql ...
```

The first run parses the dump(s) into a local SQLite cache
(`.wp_data_reader_cache.sqlite3`, next to the first dump file by default;
override with `--db`). Later runs re-import automatically only if a dump
file's size or mtime changed. Force a full re-import with `--rebuild`.

A single dump file can contain more than one WordPress install if it uses
multiple table prefixes (e.g. `wp_`, `AT_`); each prefix is treated as its
own "site" and can be selected independently in the UI.

## In the TUI

- `/` — focus the search box (full-text search over title/content/excerpt)
- Site / Type dropdowns — narrow the list to one imported site and/or post type
- `e` — export the selected post/page as a standalone HTML file
- `m` — export the selected post/page as Markdown (with YAML front matter)
- `q` — quit

Exports include an "embedded media" appendix that resolves images and
NextGEN Gallery shortcodes (`[singlepic]`, `[nggallery]`) back to their
original filename/path under `wp-content/uploads`, using the attachment and
gallery tables in the dump — including images that only appear in the
content as a resized variant, or gallery shortcodes with no filename at all.

## How it works

- `dumpparser.py` — a lightweight scanner for `CREATE TABLE` / `INSERT INTO`
  statements (handles both the "with column list" and "bare VALUES" dump
  styles), with a hand-rolled tokenizer for row values.
- `importer.py` / `db.py` — loads `posts`, `postmeta`, `terms`,
  `term_taxonomy`, `term_relationships`, `users`, and NextGEN gallery tables
  into a local SQLite cache, with an FTS5 index over post content.
- `content.py` — reconstructs rendered HTML from raw `post_content`
  (replicating WordPress's `wpautop` for classic-editor content), converts
  it to Markdown for display/export, and resolves embedded media.
- `app.py` — the Textual TUI.
