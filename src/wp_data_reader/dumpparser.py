"""Streaming-ish parser for phpMyAdmin/mysqldump SQL dump files.

We don't need a full SQL engine here: every INSERT statement in these dumps
explicitly lists its column names, so we only need to recognise
``INSERT INTO `table` (`col`, ...) VALUES (...), (...);`` statements for a
handful of table suffixes we care about, and decode the row tuples.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterator

# Table suffixes we import, longest first so e.g. `_term_taxonomy` isn't
# mistaken for `_terms`.
WANTED_SUFFIXES = sorted(
    [
        "postmeta",
        "posts",
        "term_taxonomy",
        "term_relationships",
        "termmeta",
        "terms",
        "users",
        "ngg_pictures",
        "ngg_gallery",
    ],
    key=len,
    reverse=True,
)

_STMT_RE = re.compile(
    r"CREATE\s+TABLE\s+`([^`]+)`\s*\("
    r"|INSERT\s+INTO\s+`([^`]+)`\s*(?:\(([^)]*)\))?\s*VALUES",
    re.IGNORECASE,
)

_ESCAPES = {
    "0": "\0",
    "'": "'",
    '"': '"',
    "b": "\b",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "Z": "\x1a",
    "\\": "\\",
    "%": "%",
    "_": "_",
}


@dataclass(frozen=True)
class TableRef:
    """A recognised `{prefix}_{suffix}` table name."""

    full_name: str
    prefix: str
    suffix: str


def match_table(name: str) -> TableRef | None:
    for suffix in WANTED_SUFFIXES:
        marker = "_" + suffix
        if name.endswith(marker):
            prefix = name[: -len(marker)]
            if prefix:
                return TableRef(name, prefix, suffix)
    return None


def _num(raw: str):
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _parse_row(text: str, pos: int) -> tuple[list, int]:
    """Parse one ``(v1, v2, ...)`` tuple starting at ``text[pos] == '('``."""
    assert text[pos] == "("
    pos += 1
    n = len(text)
    tokens: list = []
    buf: list[str] = []

    def flush_unquoted():
        if buf:
            raw = "".join(buf)
            tokens.append(None if raw == "NULL" else _num(raw))
            buf.clear()

    while True:
        c = text[pos]
        if c == "'":
            pos += 1
            s: list[str] = []
            while True:
                c2 = text[pos]
                if c2 == "\\":
                    nxt = text[pos + 1]
                    s.append(_ESCAPES.get(nxt, nxt))
                    pos += 2
                    continue
                if c2 == "'":
                    if pos + 1 < n and text[pos + 1] == "'":
                        s.append("'")
                        pos += 2
                        continue
                    pos += 1
                    break
                s.append(c2)
                pos += 1
            tokens.append("".join(s))
        elif c.isspace():
            pos += 1
        elif c == ",":
            flush_unquoted()
            pos += 1
        elif c == ")":
            flush_unquoted()
            pos += 1
            return tokens, pos
        else:
            buf.append(c)
            pos += 1


def _skip_balanced_parens(text: str, pos: int) -> int:
    """``pos`` points just after an opening '(' (depth already 1). Returns the
    index just after the matching closing ')', skipping over quoted strings."""
    depth = 1
    n = len(text)
    while depth > 0 and pos < n:
        c = text[pos]
        if c == "'":
            pos += 1
            while pos < n and text[pos] != "'":
                pos += 2 if text[pos] == "\\" else 1
            pos += 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        pos += 1
    return pos


def _split_top_level(body: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    i = 0
    n = len(body)
    while i < n:
        c = body[i]
        if c == "'":
            buf.append(c)
            i += 1
            while i < n and body[i] != "'":
                if body[i] == "\\":
                    buf.append(body[i])
                    buf.append(body[i + 1] if i + 1 < n else "")
                    i += 2
                    continue
                buf.append(body[i])
                i += 1
            if i < n:
                buf.append(body[i])
                i += 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    if buf:
        parts.append("".join(buf))
    return parts


def _parse_create_table_columns(text: str, body_start: int) -> tuple[list[str], int]:
    """``body_start`` is the index just after the CREATE TABLE's opening '('.
    Returns (column_names, index just after the closing ')')."""
    end = _skip_balanced_parens(text, body_start)
    body = text[body_start:end - 1]
    columns = []
    for part in _split_top_level(body):
        s = part.strip()
        if s.startswith("`"):
            close = s.index("`", 1)
            columns.append(s[1:close])
    return columns, end


def _iter_row_chunks(text: str, pos: int, chunk_size: int) -> Iterator[tuple[list[list], int]]:
    """Parse the row tuples of a VALUES section, yielding them in chunks of
    up to ``chunk_size`` rows (each paired with the text position reached so
    far) so large tables can be written and reported on incrementally
    instead of only after the whole INSERT statement has been parsed."""
    n = len(text)
    chunk: list[list] = []
    while pos < n:
        while pos < n and text[pos].isspace():
            pos += 1
        if pos >= n or text[pos] != "(":
            break
        row, pos = _parse_row(text, pos)
        chunk.append(row)
        if len(chunk) >= chunk_size:
            yield chunk, pos
            chunk = []
        while pos < n and text[pos].isspace():
            pos += 1
        if pos < n and text[pos] == ",":
            pos += 1
            continue
        if pos < n and text[pos] == ";":
            pos += 1
        break
    if chunk:
        yield chunk, pos


@dataclass(frozen=True)
class InsertBatch:
    table: TableRef
    columns: list[str]
    rows: list[list]
    fraction: float  # 0..1 progress through the source text at this point


def iter_inserts(text: str, chunk_size: int = 3000) -> Iterator[InsertBatch]:
    """Yield chunks of rows from every recognised INSERT statement.

    Dumps vary: some INSERTs list column names explicitly, others
    (``INSERT INTO `t` VALUES (...)``) rely on the table's declared column
    order, so we also track CREATE TABLE definitions as we scan. Large
    INSERTs (the common case for `posts`/`postmeta`) are yielded in chunks
    rather than all at once, so a caller can write and report progress
    incrementally instead of blocking until an entire table is parsed.
    """
    table_columns: dict[str, list[str]] = {}
    total = max(len(text), 1)
    pos = 0
    while True:
        m = _STMT_RE.search(text, pos)
        if not m:
            return
        if m.group(1) is not None:
            # CREATE TABLE `name` (
            columns, pos = _parse_create_table_columns(text, m.end())
            table_columns[m.group(1)] = columns
            continue

        table_name = m.group(2)
        explicit_cols = m.group(3)
        if explicit_cols is not None:
            columns = [c.strip().strip("`") for c in explicit_cols.split(",")]
            table_columns[table_name] = columns
        else:
            columns = table_columns.get(table_name)

        ref = match_table(table_name) if columns is not None else None

        for rows, end in _iter_row_chunks(text, m.end(), chunk_size):
            pos = end
            if ref is not None and columns is not None:
                yield InsertBatch(ref, columns, rows, pos / total)
