from __future__ import annotations

import sqlite3
from pathlib import Path

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    DataTable, Footer, Header, Input, Label, Markdown, Select, Static,
)

from .content import html_to_markdown, prepare_html
from .export import build_media_refs, default_filename, export_html, export_markdown
from .models import PostRecord, list_post_types, list_sites, load_post, query_posts

ALL = "__all__"

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
            yield Static("[Enter] save   [Escape] cancel", classes="hint")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    @on(Input.Submitted)
    def do_export(self, event: Input.Submitted) -> None:
        dest = Path(event.value.strip()).expanduser()
        refs = build_media_refs(self.conn, self.post)
        if self.fmt == "html":
            export_html(self.post, refs, dest)
        else:
            export_markdown(self.post, refs, dest)
        self.app.notify(f"Exported to {dest}")
        self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
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
    #detail {
        padding: 1 2;
    }
    #meta-panel {
        height: auto;
        border-bottom: solid $accent-darken-1;
        padding-bottom: 1;
        margin-bottom: 1;
    }
    """
    BINDINGS = [
        ("/", "focus_search", "Search"),
        ("e", "export_html", "Export HTML"),
        ("m", "export_markdown", "Export Markdown"),
        ("escape", "clear_search", "Clear search"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, conn: sqlite3.Connection) -> None:
        super().__init__()
        self.conn = conn
        self.current_post: PostRecord | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="sidebar"):
                with Horizontal(id="filters"):
                    yield Select([], id="site-select", prompt="Site")
                    yield Select([], id="type-select", prompt="Type")
                yield Input(placeholder="Search title/content... (press /)", id="search")
                yield DataTable(id="post-table", cursor_type="row", zebra_stripes=True)
            with VerticalScroll(id="detail"):
                yield Static(id="meta-panel")
                yield Markdown(id="content-view")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#post-table", DataTable)
        table.add_columns("Title", "Type", "Status", "Date")

        sites = list_sites(self.conn)
        site_select = self.query_one("#site-select", Select)
        site_select.set_options(
            [("All sites", ALL)] + [(s["label"], str(s["id"])) for s in sites]
        )
        site_select.value = ALL

        self._refresh_type_options()
        self.refresh_posts()

    def _current_site_id(self) -> int | None:
        val = self.query_one("#site-select", Select).value
        if val in (ALL, Select.BLANK, None):
            return None
        return int(val)  # type: ignore[arg-type]

    def _refresh_type_options(self) -> None:
        types = list_post_types(self.conn, self._current_site_id())
        type_select = self.query_one("#type-select", Select)
        type_select.set_options([("All types", ALL)] + [(t, t) for t in types])
        type_select.value = ALL

    @on(Select.Changed, "#site-select")
    def site_changed(self) -> None:
        self._refresh_type_options()
        self.refresh_posts()

    @on(Select.Changed, "#type-select")
    def type_changed(self) -> None:
        self.refresh_posts()

    @on(Input.Changed, "#search")
    def search_changed(self) -> None:
        self.refresh_posts()

    def refresh_posts(self) -> None:
        site_id = self._current_site_id()
        type_val = self.query_one("#type-select", Select).value
        post_types = None if type_val in (ALL, Select.BLANK, None) else [type_val]
        search = self.query_one("#search", Input).value.strip()

        rows = query_posts(
            self.conn,
            site_id=site_id,
            post_types=post_types,
            search=(search + "*") if search else None,
        )
        table = self.query_one("#post-table", DataTable)
        table.clear()
        self._row_ids = []
        for r in rows:
            title = (r["post_title"] or "").strip() or f"(untitled #{r['wp_id']})"
            table.add_row(title, r["post_type"], r["post_status"], (r["post_date"] or "")[:10])
            self._row_ids.append(r["id"])
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
        md = html_to_markdown(html)
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

    def action_export_html(self) -> None:
        if self.current_post:
            self.push_screen(ExportModal(self.conn, self.current_post, "html"))

    def action_export_markdown(self) -> None:
        if self.current_post:
            self.push_screen(ExportModal(self.conn, self.current_post, "md"))
