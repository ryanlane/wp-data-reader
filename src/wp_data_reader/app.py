from __future__ import annotations

import shutil
import sqlite3
import tempfile
import webbrowser
from pathlib import Path

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import (
    Button, DataTable, Footer, Header, Input, Label, Markdown, ProgressBar, Select, Static,
)

from .content import (
    apply_highlight_markers, extract_search_terms, highlight_html,
    html_to_markdown, prepare_html,
)
from .export import build_media_refs, default_filename, export_html, export_markdown
from .db import connect as connect_db
from .importer import file_fingerprint, import_all_parallel, needs_import, shard_db_paths
from .models import (
    PostRecord, list_post_types, list_sites, list_statuses, list_terms, load_post, query_posts,
)

ALL = "__all__"
POSTS_AND_PAGES = "__posts_and_pages__"

STATUS_STYLES = {
    "publish": "bold black on green",
    "private": "bold white on red",
    "draft": "bold black on yellow",
    "pending": "bold black on yellow",
    "future": "bold white on blue",
    "trash": "bold white on grey42",
    "auto-draft": "dim white on grey30",
    "inherit": "dim white on grey30",
}


class ExportModal(ModalScreen[None]):
    """Prompt for a destination path, then write the file."""

    DEFAULT_CSS = """
    ExportModal {
        align: center middle;
    }
    #export-box {
        width: 70%;
        max-width: 90;
        height: auto;
        border: thick $accent;
        background: $panel;
        padding: 1 2;
    }
    #export-actions {
        height: auto;
        margin-top: 1;
    }
    #export-actions Button {
        margin-right: 1;
    }
    """

    def __init__(self, conn: sqlite3.Connection, post: PostRecord, fmt: str) -> None:
        super().__init__()
        self.conn = conn
        self.post = post
        self.fmt = fmt

    def compose(self) -> ComposeResult:
        default_path = str(Path.cwd() / default_filename(self.post, self.fmt))
        with Vertical(id="export-box"):
            yield Label(f"Export '{self.post.display_title}' as {self.fmt.upper()}")
            yield Input(value=default_path, id="export-path")
            with Horizontal(id="export-actions"):
                yield Button("Save", id="export-save", variant="primary")
                yield Button("Cancel", id="export-cancel")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    @on(Input.Submitted, "#export-path")
    @on(Button.Pressed, "#export-save")
    def do_export(self) -> None:
        dest = Path(self.query_one("#export-path", Input).value.strip()).expanduser()
        refs = build_media_refs(self.conn, self.post)
        if self.fmt == "html":
            export_html(self.post, refs, dest)
        else:
            export_markdown(self.post, refs, dest)
        self.app.notify(f"Exported to {dest}")
        self.dismiss(None)

    @on(Button.Pressed, "#export-cancel")
    def cancel_pressed(self) -> None:
        self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


class LinkActionModal(ModalScreen[None]):
    """Ask what to do with a link clicked in the content view, rather than
    silently opening it (a personal blog can link almost anywhere)."""

    DEFAULT_CSS = """
    LinkActionModal {
        align: center middle;
    }
    #link-box {
        width: 80%;
        max-width: 100;
        height: auto;
        border: thick $accent;
        background: $panel;
        padding: 1 2;
    }
    #link-url {
        color: $text-muted;
        margin-bottom: 1;
    }
    #link-actions {
        height: auto;
    }
    #link-actions Button {
        margin-right: 1;
    }
    """

    BINDINGS = [
        ("o", "open", "Open in browser"),
        ("c", "copy", "Copy URL"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url

    def compose(self) -> ComposeResult:
        with Vertical(id="link-box"):
            yield Label("Link clicked")
            yield Static(self.url, id="link-url")
            with Horizontal(id="link-actions"):
                yield Button("Open in browser", id="link-open", variant="primary")
                yield Button("Copy URL", id="link-copy")
                yield Button("Cancel", id="link-cancel")

    @on(Button.Pressed, "#link-open")
    def open_pressed(self) -> None:
        self.action_open()

    @on(Button.Pressed, "#link-copy")
    def copy_pressed(self) -> None:
        self.action_copy()

    @on(Button.Pressed, "#link-cancel")
    def cancel_pressed(self) -> None:
        self.action_cancel()

    def action_open(self) -> None:
        webbrowser.open(self.url)
        self.app.notify(f"Opened {self.url}")
        self.dismiss(None)

    def action_copy(self) -> None:
        self.app.copy_to_clipboard(self.url)
        self.app.notify("URL copied to clipboard")
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class WPReaderApp(App):
    TITLE = "WP Data Reader"
    CSS = """
    #sidebar {
        width: 42%;
        border-right: solid $accent;
    }
    #filters {
        height: auto;
        padding: 0 1;
    }
    #filters .filter-row {
        height: auto;
    }
    #filters .filter-row.hidden {
        display: none;
    }
    #detail {
        padding: 1 2;
    }
    #meta-panel {
        height: auto;
        border-bottom: solid $accent-darken-1;
        padding-bottom: 1;
        margin-bottom: 1;
    }
    #content-view MarkdownBlock > .code_inline {
        background: $warning 60%;
        color: $text;
        text-style: bold;
    }
    #import-status {
        height: auto;
        padding: 0 1;
        background: $panel;
        border-bottom: solid $accent-darken-1;
    }
    #import-status.hidden {
        display: none;
    }
    #import-label {
        color: $text-muted;
    }
    #import-spinner {
        width: auto;
        margin-right: 1;
        color: $accent;
        text-style: bold;
    }
    """
    SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    BINDINGS = [
        ("/", "focus_search", "Search"),
        ("e", "export_html", "Export HTML"),
        ("m", "export_markdown", "Export Markdown"),
        ("y", "copy_highlights", "Copy highlights"),
        ("d", "toggle_date_in_title", "Toggle date in title"),
        ("escape", "clear_search", "Clear search"),
        ("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        conn: sqlite3.Connection,
        db_path: Path | None = None,
        dump_paths: list[Path] | None = None,
        force_reimport: bool = False,
        max_workers: int | None = None,
    ) -> None:
        super().__init__()
        self.conn = conn
        self.db_path = db_path
        self.dump_paths = dump_paths or []
        self.force_reimport = force_reimport
        self.max_workers = max_workers
        self.current_post: PostRecord | None = None
        self._progress_timer: Timer | None = None
        self._spinner_timer: Timer | None = None
        self._spinner_index = 0
        self._search_timer: Timer | None = None
        self._date_timer: Timer | None = None
        self._highlighted_matches: list[str] = []
        self._show_date_in_title = True
        self._known_site_count = 0
        self._type_user_selected = False
        self._suppress_type_change = False
        self._import_weights: dict[str, float] = {}
        self._import_paths: list[str] = []
        self._shard_paths: dict[str, Path] = {}
        self._shard_dir: Path | None = None
        self._shard_conns: dict[str, sqlite3.Connection] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="import-status", classes="hidden"):
            yield Static("", id="import-spinner")
            yield Static("", id="import-label")
            yield ProgressBar(id="import-bar", total=100, show_eta=False)
        with Horizontal():
            with Vertical(id="sidebar"):
                with Vertical(id="filters"):
                    with Horizontal(classes="filter-row"):
                        yield Select([], id="site-select", prompt="Site")
                        yield Select([], id="type-select", prompt="Type")
                        yield Select([], id="status-select", prompt="Status")
                    with Horizontal(id="taxonomy-filters", classes="filter-row hidden"):
                        yield Select([], id="category-select", prompt="Category")
                        yield Select([], id="tag-select", prompt="Tag")
                    with Horizontal(id="date-filters", classes="filter-row hidden"):
                        yield Input(placeholder="From (YYYY[-MM[-DD]])", id="date-from")
                        yield Input(placeholder="To (YYYY[-MM[-DD]])", id="date-to")
                yield Input(placeholder="Search title/content... (press /)", id="search")
                yield DataTable(id="post-table", cursor_type="row", zebra_stripes=True)
            with VerticalScroll(id="detail"):
                yield Static(id="meta-panel")
                yield Markdown(id="content-view", open_links=False)
        yield Footer()

    def on_mount(self) -> None:
        self._configure_table_columns()

        self._refresh_site_options()
        self._refresh_type_options()
        self._refresh_status_options()
        self._refresh_taxonomy_options()
        self.refresh_posts()

        files_to_import = [
            p for p in self.dump_paths
            if self.force_reimport or needs_import(self.conn, p)
        ]
        if files_to_import and self.db_path is not None:
            self._start_import(files_to_import)

    # --- Background import ---------------------------------------------

    def _start_import(self, files: list[Path]) -> None:
        assert self.db_path is not None
        total_bytes = sum(file_fingerprint(p)[0] for p in files) or 1
        self._import_weights = {str(p): file_fingerprint(p)[0] / total_bytes for p in files}
        self._import_paths = [str(p) for p in files]
        self._known_site_count = self.conn.execute("SELECT count(*) c FROM sites").fetchone()["c"]

        self._shard_dir = Path(tempfile.mkdtemp(prefix="wp-data-reader-import-"))
        self._shard_paths = shard_db_paths(self._shard_dir, files)
        self._shard_conns = {}

        status = self.query_one("#import-status", Horizontal)
        status.remove_class("hidden")
        self.query_one("#import-label", Static).update(
            f"Importing {len(files)} dump file(s)…"
        )

        self.run_worker(lambda: self._import_worker(files), exclusive=True, thread=True)
        self._progress_timer = self.set_interval(0.4, self._poll_import_progress)
        self._spinner_index = 0
        self._spinner_timer = self.set_interval(0.1, self._tick_spinner)

    def _tick_spinner(self) -> None:
        self._spinner_index = (self._spinner_index + 1) % len(self.SPINNER_FRAMES)
        self.query_one("#import-spinner", Static).update(self.SPINNER_FRAMES[self._spinner_index])

    def _import_worker(self, files: list[Path]) -> None:
        """Runs in a background thread (see ``thread=True`` above): drives
        the process pool synchronously, then hands the result back to the
        UI thread. Blocking here is fine — it isn't the UI thread."""
        assert self.db_path is not None and self._shard_dir is not None
        errors: list[str] = []
        results = list(import_all_parallel(
            self.db_path, files, shard_dir=self._shard_dir, max_workers=self.max_workers,
        ))
        for path, error in results:
            if error:
                errors.append(f"{Path(path).name}: {error}")
        # Blocks until the main thread's _finish_import has run (and closed
        # any shard connections it opened), so it's safe to clean up here
        # afterwards without racing the progress poller.
        self.call_from_thread(self._finish_import, errors)
        shutil.rmtree(self._shard_dir, ignore_errors=True)

    def _shard_conn(self, path: str) -> sqlite3.Connection | None:
        conn = self._shard_conns.get(path)
        if conn is not None:
            return conn
        shard_path = self._shard_paths[path]
        if not shard_path.exists():
            return None
        conn = connect_db(shard_path)
        self._shard_conns[path] = conn
        return conn

    def _poll_import_progress(self) -> None:
        overall = 0.0
        done = 0
        current_label = ""
        for path in self._import_paths:
            weight = self._import_weights[path]
            conn = self._shard_conn(path)
            row = (
                conn.execute(
                    "SELECT table_name, fraction, status FROM import_progress WHERE path=?", (path,)
                ).fetchone()
                if conn is not None else None
            )
            if row is None:
                continue
            if row["status"] in ("done", "error"):
                overall += weight
                done += 1
            else:
                overall += weight * float(row["fraction"] or 0.0)
                current_label = f"{Path(path).name}: {row['table_name'] or '…'}"

        self.query_one("#import-bar", ProgressBar).update(progress=overall * 100)
        label = f"Importing {len(self._import_paths)} file(s), {done} done"
        if current_label:
            label += f" — {current_label}"
        self.query_one("#import-label", Static).update(label)

        site_count = self.conn.execute("SELECT count(*) c FROM sites").fetchone()["c"]
        if site_count != self._known_site_count:
            self._known_site_count = site_count
            self._refresh_site_options()
            self._refresh_type_options()
            self._refresh_status_options()
            self._refresh_taxonomy_options()
            self.refresh_posts()

    def _finish_import(self, errors: list[str]) -> None:
        for conn in self._shard_conns.values():
            conn.close()
        self._shard_conns = {}
        if self._progress_timer is not None:
            self._progress_timer.stop()
            self._progress_timer = None
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None
        self.query_one("#import-status", Horizontal).add_class("hidden")
        self._refresh_site_options()
        self._refresh_type_options()
        self._refresh_status_options()
        self._refresh_taxonomy_options()
        self.refresh_posts()
        if errors:
            self.notify("Import finished with errors:\n" + "\n".join(errors), severity="error", timeout=10)
        else:
            self.notify("Import complete.")

    def _refresh_site_options(self) -> None:
        current = self.query_one("#site-select", Select).value
        sites = list_sites(self.conn)
        site_select = self.query_one("#site-select", Select)
        site_select.set_options(
            [("All sites", ALL)] + [(s["label"], str(s["id"])) for s in sites]
        )
        valid_values = {ALL, *(str(s["id"]) for s in sites)}
        site_select.value = current if current in valid_values else ALL

    def _current_site_id(self) -> int | None:
        val = self.query_one("#site-select", Select).value
        if val in (ALL, Select.BLANK, None):
            return None
        return int(val)  # type: ignore[arg-type]

    def _refresh_type_options(self) -> None:
        current = self.query_one("#type-select", Select).value
        types = list_post_types(self.conn, self._current_site_id())
        options = [("All types", ALL)]
        has_posts_or_pages = "post" in types or "page" in types
        if has_posts_or_pages:
            options.append(("Posts & Pages", POSTS_AND_PAGES))
        options += [(t, t) for t in types]

        type_select = self.query_one("#type-select", Select)
        self._suppress_type_change = True
        type_select.set_options(options)
        valid_values = {ALL, *(t for t in types)} | ({POSTS_AND_PAGES} if has_posts_or_pages else set())
        if self._type_user_selected and current in valid_values:
            type_select.value = current
        else:
            # A plugin's internal post types (revisions, attachments, gallery
            # bookkeeping, ...) usually dwarf actual content and aren't what
            # anyone wants to browse by default. Until the user picks
            # something themselves, keep re-evaluating this on every refresh
            # (site change, or a new site landing mid-import) rather than
            # locking in whatever was true the first time this ran — during
            # a progressive import that first pass may briefly see no
            # posts/pages yet (only plugin bookkeeping rows so far).
            type_select.value = POSTS_AND_PAGES if has_posts_or_pages else ALL
        self._suppress_type_change = False
        self._update_filter_visibility()

    def _refresh_status_options(self) -> None:
        current = self.query_one("#status-select", Select).value
        statuses = list_statuses(self.conn, self._current_site_id())
        status_select = self.query_one("#status-select", Select)
        status_select.set_options([("All statuses", ALL)] + [(s, s) for s in statuses])
        valid_values = {ALL, *statuses}
        status_select.value = current if current in valid_values else ALL

    def _refresh_taxonomy_options(self) -> None:
        site_id = self._current_site_id()
        for select_id, taxonomy, label in (
            ("category-select", "category", "categories"),
            ("tag-select", "post_tag", "tags"),
        ):
            select = self.query_one(f"#{select_id}", Select)
            current = select.value
            terms = list_terms(self.conn, site_id, taxonomy)
            select.set_options([(f"All {label}", ALL)] + [(name, slug) for name, slug in terms])
            valid_values = {ALL, *(slug for _, slug in terms)}
            select.value = current if current in valid_values else ALL

    def _update_filter_visibility(self) -> None:
        show = self.query_one("#type-select", Select).value == POSTS_AND_PAGES
        self.query_one("#taxonomy-filters", Horizontal).set_class(not show, "hidden")
        self.query_one("#date-filters", Horizontal).set_class(not show, "hidden")

    @on(Select.Changed, "#site-select")
    def site_changed(self) -> None:
        self._refresh_type_options()
        self._refresh_status_options()
        self._refresh_taxonomy_options()
        self.refresh_posts()

    @on(Select.Changed, "#type-select")
    def type_changed(self) -> None:
        if not self._suppress_type_change:
            self._type_user_selected = True
        self._update_filter_visibility()
        self.refresh_posts()

    @on(Select.Changed, "#status-select")
    def status_changed(self) -> None:
        self.refresh_posts()

    @on(Select.Changed, "#category-select")
    @on(Select.Changed, "#tag-select")
    def taxonomy_changed(self) -> None:
        self.refresh_posts()

    @on(Input.Changed, "#date-from")
    @on(Input.Changed, "#date-to")
    def date_changed(self) -> None:
        if self._date_timer is not None:
            self._date_timer.stop()
        self._date_timer = self.set_timer(0.3, self._run_debounced_dates)

    def _run_debounced_dates(self) -> None:
        self._date_timer = None
        self.refresh_posts()

    @on(Input.Submitted, "#date-from")
    @on(Input.Submitted, "#date-to")
    def date_submitted(self) -> None:
        if self._date_timer is not None:
            self._date_timer.stop()
            self._date_timer = None
        self.refresh_posts()

    @on(Input.Changed, "#search")
    def search_changed(self) -> None:
        # Debounced: querying + re-rendering on every keystroke makes fast
        # typing/backspacing feel laggy. Wait for a short pause instead.
        if self._search_timer is not None:
            self._search_timer.stop()
        self._search_timer = self.set_timer(0.3, self._run_debounced_search)

    def _run_debounced_search(self) -> None:
        self._search_timer = None
        self.refresh_posts()

    @on(Input.Submitted, "#search")
    def search_submitted(self) -> None:
        # Enter runs it immediately, skipping the debounce wait.
        if self._search_timer is not None:
            self._search_timer.stop()
            self._search_timer = None
        self.refresh_posts()

    def _configure_table_columns(self) -> None:
        table = self.query_one("#post-table", DataTable)
        table.clear(columns=True)
        if self._show_date_in_title:
            # Drop the separate Type/Status/Date columns so Title gets the
            # full row width — otherwise a long title truncates before the
            # date concatenated onto its end ever becomes visible.
            table.add_columns("Title")
        else:
            table.add_columns("Title", "Type", "Status", "Date")

    def _title_cell(self, row: sqlite3.Row) -> str:
        title = (row["post_title"] or "").strip() or f"(untitled #{row['wp_id']})"
        if self._show_date_in_title:
            date = (row["post_date"] or "")[:10]
            if date:
                title = f"{date}  —  {title}"
        return title

    def refresh_posts(self) -> None:
        site_id = self._current_site_id()
        type_val = self.query_one("#type-select", Select).value
        if type_val in (ALL, Select.BLANK, None):
            post_types = None
        elif type_val == POSTS_AND_PAGES:
            post_types = ["post", "page"]
        else:
            post_types = [type_val]
        search = self.query_one("#search", Input).value.strip()

        status_val = self.query_one("#status-select", Select).value
        statuses = None if status_val in (ALL, Select.BLANK, None) else [status_val]

        category = tag = date_from = date_to = None
        if type_val == POSTS_AND_PAGES:
            category_val = self.query_one("#category-select", Select).value
            category = None if category_val in (ALL, Select.BLANK, None) else category_val
            tag_val = self.query_one("#tag-select", Select).value
            tag = None if tag_val in (ALL, Select.BLANK, None) else tag_val
            date_from = self.query_one("#date-from", Input).value.strip() or None
            date_to = self.query_one("#date-to", Input).value.strip() or None

        rows = query_posts(
            self.conn,
            site_id=site_id,
            post_types=post_types,
            statuses=statuses,
            search=(search + "*") if search else None,
            category=category,
            tag=tag,
            date_from=date_from,
            date_to=date_to,
        )
        table = self.query_one("#post-table", DataTable)
        table.clear()
        self._row_ids = [r["id"] for r in rows]
        # add_rows (bulk) rather than one add_row() call per post: with tens
        # of thousands of rows the per-row version visibly blocks the UI.
        if self._show_date_in_title:
            table.add_rows((self._title_cell(r),) for r in rows)
        else:
            table.add_rows(
                (self._title_cell(r), r["post_type"], r["post_status"], (r["post_date"] or "")[:10])
                for r in rows
            )
        if rows:
            table.move_cursor(row=0)
            self.show_post(self._row_ids[0])
        else:
            self.current_post = None
            self.query_one("#meta-panel", Static).update("No posts match.")
            self.query_one("#content-view", Markdown).update("")

    @on(DataTable.RowHighlighted, "#post-table")
    def row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.cursor_row is None or event.cursor_row >= len(self._row_ids):
            return
        self.show_post(self._row_ids[event.cursor_row])

    def show_post(self, row_id: int) -> None:
        post = load_post(self.conn, row_id)
        self.current_post = post
        self.query_one("#meta-panel", Static).update(self._meta_panel(post))
        html = prepare_html(post.content)
        search = self.query_one("#search", Input).value.strip()
        terms = extract_search_terms(search)
        self._highlighted_matches = []
        if terms:
            html, self._highlighted_matches = highlight_html(html, terms)
        md = html_to_markdown(html)
        if terms:
            md = apply_highlight_markers(md)
        self.query_one("#content-view", Markdown).update(md)

    def _meta_panel(self, post: PostRecord) -> Group:
        header = Text(post.display_title, style="bold")
        header.append("  ")
        header.append(
            f" {post.status.upper()} ",
            style=STATUS_STYLES.get(post.status, "bold white on grey35"),
        )
        if post.password:
            header.append(" PASSWORD PROTECTED ", style="bold black on dark_orange")

        subtitle = Text(f"{post.post_type} · {post.site_label}", style="dim")

        cats = ", ".join(t.name for t in post.terms_by_taxonomy("category"))
        tags = ", ".join(t.name for t in post.terms_by_taxonomy("post_tag"))
        interesting_meta = {
            k: v for k, v in post.meta.items()
            if not k.startswith("_") or k in ("_wp_page_template",)
        }
        meta_line = "  ".join(f"{k}={v[0]!r}" for k, v in list(interesting_meta.items())[:6])

        table = Table.grid(padding=(0, 2))
        table.add_column(style="dim", justify="right", no_wrap=True)
        table.add_column(ratio=1)

        def add(label: str, value: str) -> None:
            if value:
                table.add_row(label, value)

        add("Author", post.author)
        add("Date", post.date)
        add("Modified", post.modified)
        add("Slug", post.name)
        add("Categories", cats)
        add("Tags", tags)
        if meta_line:
            add("Custom fields", meta_line)
        add("Meta keys", str(len(post.meta)))

        return Group(header, subtitle, Text(""), table)

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_clear_search(self) -> None:
        search = self.query_one("#search", Input)
        if self.focused is search and search.value:
            search.value = ""
        else:
            self.query_one("#post-table", DataTable).focus()

    def action_toggle_date_in_title(self) -> None:
        table = self.query_one("#post-table", DataTable)
        cursor_row = table.cursor_row
        self._show_date_in_title = not self._show_date_in_title
        self._configure_table_columns()
        self.refresh_posts()
        # refresh_posts() re-queries with the same filters, so row order is
        # unchanged; restore the prior selection instead of jumping to the
        # top just because the title text changed.
        if cursor_row is not None and 0 <= cursor_row < len(self._row_ids):
            table.move_cursor(row=cursor_row)

    def action_copy_highlights(self) -> None:
        if not self._highlighted_matches:
            self.notify("No highlighted search matches to copy.", severity="warning")
            return
        self.copy_to_clipboard("\n".join(self._highlighted_matches))
        self.notify(f"Copied {len(self._highlighted_matches)} highlighted match(es) to clipboard.")

    def action_export_html(self) -> None:
        if self.current_post:
            self.push_screen(ExportModal(self.conn, self.current_post, "html"))

    def action_export_markdown(self) -> None:
        if self.current_post:
            self.push_screen(ExportModal(self.conn, self.current_post, "md"))

    @on(Markdown.LinkClicked)
    def link_clicked(self, event: Markdown.LinkClicked) -> None:
        self.push_screen(LinkActionModal(event.href))
