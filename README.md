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

If the site the dump came from is no longer online, image/media links in
post content will 404. If you have a local copy of `wp-content/uploads`
(e.g. from a backup), point `--uploads-dir` at it and any link whose file
exists there opens (or copies) a `file://` URL to it instead of the
original, dead one — matched using the same original-filename resolution
the export media appendix uses, so a resized reference like
`IMG_4354-550x412.jpg` still finds `IMG_4354.jpg` if that's what you have:

```sh
uv run wp-data-reader path/to/dump.sql --uploads-dir path/to/wp-content/uploads
```

Remembered next to the cache after the first run, so later runs don't need
the flag repeated.

## In the TUI

- `/` — focus the search box (full-text search over title/content/excerpt,
  debounced so fast typing doesn't re-query on every keystroke); matches are
  highlighted in the content view
- `f` — open the Filters dialog. The first time a dump set's cache already
  has data (e.g. a later run against unchanged dumps), this opens
  automatically before the table appears, so you can choose scope up front
  instead of everything loading at once:
  - Sites / Content types — checkboxes, so you can include more than one at
    once; Posts and Pages are checked by default, since a WordPress
    install's `posts` table is usually mostly revisions and plugin
    bookkeeping rows otherwise
  - Status — publish, draft, pending, private, ...
  - Category / Tag dropdowns, populated from that taxonomy's terms
  - From / To date fields, accepting `YYYY`, `YYYY-MM`, or `YYYY-MM-DD`.
    Filling in just one field matches only that period (e.g. `2018` alone
    shows everything from 2018; `2018-02-08` alone shows just that day).
    Filling in both gives a range (e.g. `2012-12` to `2013-02` covers
    December 2012 through February 2013)

  Choices are saved next to the SQLite cache (`<cache>.filters.json`) and
  reused on the next run against the same dump set.
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

### If copying to the clipboard doesn't work

`y` and "Copy URL" (in the link-click dialog) use `xclip`/`xsel`/`wl-copy` if
one is installed, since some terminals and multiplexers block the OSC 52
escape sequence that terminal apps otherwise rely on for clipboard access.
If none of those are installed, install one for your session type:

```sh
sudo apt install xclip   # or xsel — X11
sudo apt install wl-clipboard   # Wayland
```

If none of those can be installed (e.g. no access to the display server —
over plain SSH without X/Wayland forwarding) it falls back to the OSC 52
terminal escape sequence, which some terminals/multiplexers block by
default:

- Inside `tmux`, add `set -s set-clipboard on` to `.tmux.conf`.
- Check your terminal emulator's settings for an OSC 52 / "clipboard from
  remote application" permission.

Separately, selecting text with the mouse to copy it natively (rather than
using `y`) may need **Shift+drag** — the TUI captures plain mouse drags for
its own UI, which otherwise pre-empts your terminal emulator's own text
selection.

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
- `config.py` — reads/writes saved settings (Filters selection,
  `--uploads-dir`) in `<cache>.filters.json`, next to the SQLite cache.
