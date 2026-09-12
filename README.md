# wp-data-reader

A terminal UI for browsing, searching, and exporting posts and pages from
WordPress SQL dumps (mysqldump / phpMyAdmin `.sql` files) — no MySQL server
required.

## Install

This project uses [uv](https://docs.astral.sh/uv/) to manage the Python
environment and dependencies. If you don't have it yet, see the
[installation instructions](https://docs.astral.sh/uv/getting-started/installation/)
(a single install script for macOS/Linux/Windows, or via `pipx`/Homebrew/etc).

## Usage

```sh
uv run wp-data-reader path/to/dump1.sql path/to/dump2.sql ...
```

The first run parses the dump(s) into a local SQLite cache
(`.wp_data_reader_cache.sqlite3`, next to the first dump file by default;
override with `--db`). Later runs re-import automatically only if a dump
file's size or mtime changed. Force a full re-import with `--rebuild`.
Multiple dump files are parsed in parallel (one OS process per file, capped
at your CPU count by default — override with `--jobs`); the UI comes up
immediately with a progress bar and fills in with posts from each site as
soon as that file finishes, rather than blocking until everything is done.

A single dump file can contain more than one WordPress install if it uses
multiple table prefixes (e.g. `wp_`, `AT_`); each prefix is treated as its
own "site" and can be selected independently in the UI.

## In the TUI

- `/` — focus the search box (full-text search over title/content/excerpt,
  debounced so fast typing doesn't re-query on every keystroke); matches are
  highlighted in the content view
- Site / Type / Status dropdowns — narrow the list to one imported site,
  post type, and/or status (publish, draft, pending, private, ...). Type
  defaults to "Posts & Pages", since a WordPress install's `posts` table is
  usually mostly revisions and plugin bookkeeping rows — pick "All types"
  to see those too
- With Type set to "Posts & Pages", two more filter rows appear:
  - Category / Tag dropdowns, populated from that taxonomy's terms on the
    selected site
  - From / To date fields, accepting `YYYY`, `YYYY-MM`, or `YYYY-MM-DD`.
    Filling in just one field matches only that period (e.g. `2018` alone
    shows everything from 2018; `2018-02-08` alone shows just that day).
    Filling in both gives a range (e.g. `2012-12` to `2013-02` covers
    December 2012 through February 2013)
- `d` — toggle showing the date before the title in the list (on by
  default) and collapse the Type/Status/Date columns, so the date is
  visible without needing a very wide window
- `y` — copy the currently highlighted search matches to the clipboard
- Clicking a link in the content view asks whether to open it in your
  browser or copy the URL, rather than opening it immediately
- `e` — export the selected post/page as a standalone HTML file
- `m` — export the selected post/page as Markdown (with YAML front matter)
  — the export dialog's Save/Cancel buttons support both mouse clicks and
  Tab/Shift+Tab to move focus between the path field and the buttons
- `q` — quit

Exports include an "embedded media" appendix that resolves images and
NextGEN Gallery shortcodes (`[singlepic]`, `[nggallery]`) back to their
original filename/path under `wp-content/uploads`, using the attachment and
gallery tables in the dump — including images that only appear in the
content as a resized variant, or gallery shortcodes with no filename at all.

## How it works

- `dumpparser.py` — a lightweight scanner for `CREATE TABLE` / `INSERT INTO`
  statements (handles both the "with column list" and "bare VALUES" dump
  styles), with a hand-rolled tokenizer for row values, yielding rows in
  chunks so large tables can be imported and reported on incrementally.
- `importer.py` / `db.py` — loads `posts`, `postmeta`, `terms`,
  `term_taxonomy`, `term_relationships`, `users`, and NextGEN gallery tables
  into a local SQLite cache, with an FTS5 index over post content. Each dump
  file is parsed and imported into its own private, uncontended "shard" db
  in a worker process (SQLite only allows one writer at a time, so sharing
  a single file across processes serializes them instead of speeding
  anything up), then merged into the main cache with a few bulk SQL copies.
- `content.py` — reconstructs rendered HTML from raw `post_content`
  (replicating WordPress's `wpautop` for classic-editor content), converts
  it to Markdown for display/export, and resolves embedded media.
- `app.py` — the Textual TUI.
