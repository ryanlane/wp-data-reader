"""SQLite cache schema and query helpers."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS imported_files (
    path TEXT PRIMARY KEY,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT NOT NULL,
    prefix TEXT NOT NULL,
    label TEXT NOT NULL,
    UNIQUE(source_file, prefix)
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL,
    wp_id INTEGER NOT NULL,
    post_author INTEGER,
    post_date TEXT,
    post_date_gmt TEXT,
    post_title TEXT,
    post_name TEXT,
    post_content TEXT,
    post_excerpt TEXT,
    post_status TEXT,
    post_type TEXT,
    post_parent INTEGER,
    guid TEXT,
    menu_order INTEGER,
    comment_status TEXT,
    ping_status TEXT,
    post_password TEXT,
    post_modified TEXT,
    post_modified_gmt TEXT,
    post_mime_type TEXT,
    comment_count INTEGER,
    UNIQUE(site_id, wp_id)
);
CREATE INDEX IF NOT EXISTS idx_posts_site_type_status ON posts(site_id, post_type, post_status);
CREATE INDEX IF NOT EXISTS idx_posts_parent ON posts(site_id, post_parent);

CREATE TABLE IF NOT EXISTS postmeta (
    site_id INTEGER NOT NULL,
    post_wp_id INTEGER NOT NULL,
    meta_key TEXT,
    meta_value TEXT
);
CREATE INDEX IF NOT EXISTS idx_postmeta_lookup ON postmeta(site_id, post_wp_id, meta_key);

CREATE TABLE IF NOT EXISTS terms (
    site_id INTEGER NOT NULL,
    term_id INTEGER NOT NULL,
    name TEXT,
    slug TEXT
);
CREATE INDEX IF NOT EXISTS idx_terms ON terms(site_id, term_id);

CREATE TABLE IF NOT EXISTS term_taxonomy (
    site_id INTEGER NOT NULL,
    term_taxonomy_id INTEGER NOT NULL,
    term_id INTEGER,
    taxonomy TEXT,
    description TEXT,
    parent INTEGER,
    count INTEGER
);
CREATE INDEX IF NOT EXISTS idx_term_taxonomy ON term_taxonomy(site_id, term_taxonomy_id);

CREATE TABLE IF NOT EXISTS term_relationships (
    site_id INTEGER NOT NULL,
    object_id INTEGER NOT NULL,
    term_taxonomy_id INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_term_rel ON term_relationships(site_id, object_id);

CREATE TABLE IF NOT EXISTS users (
    site_id INTEGER NOT NULL,
    wp_id INTEGER NOT NULL,
    user_login TEXT,
    display_name TEXT,
    user_email TEXT,
    user_nicename TEXT
);
CREATE INDEX IF NOT EXISTS idx_users ON users(site_id, wp_id);

CREATE TABLE IF NOT EXISTS ngg_pictures (
    site_id INTEGER NOT NULL,
    pid INTEGER NOT NULL,
    galleryid INTEGER,
    filename TEXT,
    description TEXT,
    alttext TEXT
);
CREATE INDEX IF NOT EXISTS idx_ngg_pictures ON ngg_pictures(site_id, pid);

CREATE TABLE IF NOT EXISTS ngg_gallery (
    site_id INTEGER NOT NULL,
    gid INTEGER NOT NULL,
    name TEXT,
    slug TEXT,
    path TEXT
);
CREATE INDEX IF NOT EXISTS idx_ngg_gallery ON ngg_gallery(site_id, gid);

CREATE VIRTUAL TABLE IF NOT EXISTS posts_fts USING fts5(
    post_title, post_content, post_excerpt,
    tokenize='porter unicode61'
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def rebuild_fts(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM posts_fts")
    conn.execute(
        "INSERT INTO posts_fts(rowid, post_title, post_content, post_excerpt) "
        "SELECT id, post_title, post_content, post_excerpt FROM posts"
    )
    conn.commit()
