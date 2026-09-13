"""Generates the tiny, entirely fictional WordPress SQL dump used to take
the README screenshots (a made-up backyard-birding blog, no real people or
places). Not needed to use wp-data-reader itself — only to regenerate the
sample dump or the screenshots.

Usage: uv run python docs/screenshots/make_sample_dump.py
Writes: docs/screenshots/sample-blog.sql
"""
from __future__ import annotations

from pathlib import Path

PREFIX = "wp_"


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def sql_str(v) -> str:
    if v is None:
        return "NULL"
    return f"'{esc(str(v))}'"


users = [
    # ID, user_login, display_name, user_email, user_nicename
    (2, "sam", "Sam Whitfield", "sam@example.test", "sam-whitfield"),
]

categories = [
    # term_id, name, slug
    (10, "Sightings", "sightings"),
    (11, "Backyard Setup", "backyard-setup"),
    (12, "Gear", "gear"),
]
tags = [
    (20, "cardinals", "cardinals"),
    (21, "warblers", "warblers"),
    (22, "feeders", "feeders"),
    (23, "migration", "migration"),
    (24, "photography", "photography"),
]

# term_taxonomy_id assignment: categories at 100+i, tags at 200+i.
cat_tt = {c[0]: 100 + i for i, c in enumerate(categories)}
tag_tt = {t[0]: 200 + i for i, t in enumerate(tags)}

posts = [
    dict(
        id=101, type="post", status="publish", author=2,
        title="A Pair of Cardinals Moved Into the Hedge",
        slug="cardinals-in-the-hedge",
        date="2023-03-04 07:40:00",
        cats=[10], tags=[20],
        excerpt="They've been back every morning for a week now, right on schedule.",
        content="""<p>A pair of cardinals has taken up residence in the hedge along the back
fence, and they've been back every morning for about a week now &mdash; right on
schedule, usually just after sunrise.</p>
<p>The male does a slow, deliberate circuit of the feeder before ever landing,
which I assume is either caution or theater. Possibly both.</p>
<h2>Notes</h2>
<ul>
<li>Prefers the platform feeder over the tube feeder, consistently</li>
<li>Female is noticeably more relaxed around the window than the male</li>
<li>No sign of a nest yet, but it's early in the season</li>
</ul>""",
    ),
    dict(
        id=102, type="post", status="publish", author=2,
        title="Warbler Migration Is Picking Up",
        slug="warbler-migration-picking-up",
        date="2023-04-18 08:15:00",
        cats=[10], tags=[21, 23],
        excerpt="Three new warbler species in the yard this week alone.",
        content="""<p>Migration is properly underway &mdash; three new warbler species have shown
up in the yard this week alone, all just passing through on their way
further north.</p>
<p>Yellow-rumped were the first to arrive, as usual, followed by a single
very lost-looking Blackburnian that stayed for exactly one afternoon.</p>
<p>Binoculars have basically lived on the kitchen table since Tuesday.</p>""",
    ),
    dict(
        id=103, type="post", status="publish", author=2,
        title="Setting Up a Second Feeder Without Starting a Turf War",
        slug="second-feeder-without-turf-war",
        date="2023-05-02 09:00:00",
        cats=[11, 12], tags=[22],
        excerpt="Two feeders, positioned carefully, mostly kept the peace.",
        content="""<p>Adding a second feeder always risks turning the yard into contested
territory, so I put some thought into placement before hanging it.</p>
<p>Keeping the new feeder well out of sight-line from the first one, on the
far side of the maple, mostly kept the peace. There's still the occasional
dispute, but nothing like the chaos of the one time I hung them side by
side.</p>""",
    ),
    dict(
        id=104, type="post", status="draft", author=2,
        title="Draft: Photographing Fast Little Birds (unfinished)",
        slug="photographing-fast-birds-draft",
        date="2023-06-10 15:00:00",
        cats=[12], tags=[24],
        excerpt="",
        content="""<p>Notes so far: shutter speed matters more than I expected, chickadees do
not sit still for anyone. Need better photos before this is postable.</p>""",
    ),
    dict(
        id=105, type="post", status="publish", author=2,
        title="The Best Photo I've Gotten So Far",
        slug="best-photo-so-far",
        date="2023-07-22 10:30:00",
        cats=[10], tags=[24, 20],
        excerpt="A cardinal, mid-hop, caught in decent light for once.",
        content="""<p>After months of blurry, half-obscured attempts, I finally caught one
worth keeping: the male cardinal, mid-hop off the platform feeder, in
actually decent morning light.</p>
<img src="http://backyardbirding.test/wp-content/uploads/2023/07/cardinal-hop-300x200.jpg" alt="cardinal mid-hop off the feeder" />
<p>Framed it. It's on the wall now, which is probably a little much for a
bird photo, but here we are.</p>""",
    ),
    dict(
        id=106, type="post", status="private", author=2,
        title="Private Notes: Neighbor's Cat (private)",
        slug="neighbors-cat-notes",
        date="2023-08-01 12:00:00",
        cats=[11], tags=[],
        excerpt="",
        content="""<p>Private notes, not for the public site &mdash; the neighbor's cat has been in
the yard twice this week. Need to mention it, gently, before it becomes a
bigger conversation than it needs to be.</p>""",
    ),
    dict(
        id=110, type="page", status="publish", author=2,
        title="About",
        slug="about",
        date="2023-01-01 12:00:00",
        cats=[], tags=[],
        excerpt="",
        content="""<p>Backyard Birding is a small, occasional log of whatever shows up at the
feeders, written by Sam Whitfield. No expertise claimed &mdash; just a pair of
binoculars and more patience than the average chickadee deserves.</p>""",
    ),
]

# One image attachment (child of post 105), so the local-uploads-dir /
# embedded-media features have something to resolve in screenshots.
attachment = dict(
    id=201, type="attachment", status="inherit", author=2,
    title="cardinal-hop", slug="cardinal-hop",
    date="2023-07-20 10:00:00",
    guid="http://backyardbirding.test/wp-content/uploads/2023/07/cardinal-hop.jpg",
)

post_cols = [
    "ID", "post_author", "post_date", "post_date_gmt", "post_content",
    "post_title", "post_excerpt", "post_status", "comment_status",
    "ping_status", "post_password", "post_name", "post_modified",
    "post_modified_gmt", "post_parent", "guid", "menu_order", "post_type",
    "post_mime_type", "comment_count",
]


def build() -> str:
    lines = [
        "-- Fake WordPress dump for wp-data-reader screenshots/testing.",
        "-- Entirely fictional: no real people, places, or content.\n",
    ]

    lines.append(
        f"CREATE TABLE `{PREFIX}users` (`ID` bigint, `user_login` varchar(60), "
        "`display_name` varchar(250), `user_email` varchar(100), `user_nicename` varchar(50));"
    )
    vals = ", ".join(
        f"({u[0]}, {sql_str(u[1])}, {sql_str(u[2])}, {sql_str(u[3])}, {sql_str(u[4])})"
        for u in users
    )
    lines.append(
        f"INSERT INTO `{PREFIX}users` (`ID`, `user_login`, `display_name`, "
        f"`user_email`, `user_nicename`) VALUES {vals};\n"
    )

    lines.append(f"CREATE TABLE `{PREFIX}terms` (`term_id` bigint, `name` varchar(200), `slug` varchar(200));")
    vals = ", ".join(f"({t[0]}, {sql_str(t[1])}, {sql_str(t[2])})" for t in categories + tags)
    lines.append(f"INSERT INTO `{PREFIX}terms` (`term_id`, `name`, `slug`) VALUES {vals};\n")

    lines.append(
        f"CREATE TABLE `{PREFIX}term_taxonomy` (`term_taxonomy_id` bigint, `term_id` bigint, "
        "`taxonomy` varchar(32), `description` longtext, `parent` bigint, `count` bigint);"
    )
    rows = [f"({cat_tt[c[0]]}, {c[0]}, 'category', '', 0, 0)" for c in categories]
    rows += [f"({tag_tt[t[0]]}, {t[0]}, 'post_tag', '', 0, 0)" for t in tags]
    lines.append(
        f"INSERT INTO `{PREFIX}term_taxonomy` (`term_taxonomy_id`, `term_id`, `taxonomy`, "
        f"`description`, `parent`, `count`) VALUES {', '.join(rows)};\n"
    )

    lines.append(f"CREATE TABLE `{PREFIX}posts` (" + ", ".join(f"`{c}` longtext" for c in post_cols) + ");")

    post_rows = []
    term_rel_rows = []
    for p in posts:
        guid = f"http://backyardbirding.test/{'?p=' + str(p['id']) if p['type'] == 'post' else p['slug']}"
        row = [
            p["id"], p["author"], p["date"], p["date"], p["content"],
            p["title"], p["excerpt"], p["status"], "open", "open", "",
            p["slug"], p["date"], p["date"], 0, guid, 0, p["type"], "", 0,
        ]
        post_rows.append("(" + ", ".join(str(v) if isinstance(v, int) else sql_str(v) for v in row) + ")")
        for term_id in p["cats"]:
            term_rel_rows.append(f"({p['id']}, {cat_tt[term_id]}, 0)")
        for term_id in p["tags"]:
            term_rel_rows.append(f"({p['id']}, {tag_tt[term_id]}, 0)")

    a = attachment
    a_row = [
        a["id"], a["author"], a["date"], a["date"], "",
        a["title"], "", a["status"], "open", "closed", "",
        a["slug"], a["date"], a["date"], 105, a["guid"], 0, a["type"], "image/jpeg", 0,
    ]
    post_rows.append("(" + ", ".join(str(v) if isinstance(v, int) else sql_str(v) for v in a_row) + ")")

    lines.append(
        f"INSERT INTO `{PREFIX}posts` (" + ", ".join(f"`{c}`" for c in post_cols)
        + f") VALUES {', '.join(post_rows)};\n"
    )

    lines.append(f"CREATE TABLE `{PREFIX}term_relationships` (`object_id` bigint, `term_taxonomy_id` bigint, `term_order` int);")
    lines.append(
        f"INSERT INTO `{PREFIX}term_relationships` (`object_id`, `term_taxonomy_id`, `term_order`) "
        f"VALUES {', '.join(term_rel_rows)};\n"
    )

    lines.append(f"CREATE TABLE `{PREFIX}postmeta` (`meta_id` bigint, `post_id` bigint, `meta_key` varchar(255), `meta_value` longtext);")
    postmeta_rows = [
        f"(1, {a['id']}, '_wp_attached_file', '2023/07/cardinal-hop.jpg')",
        "(2, 105, '_thumbnail_id', '201')",
    ]
    lines.append(
        f"INSERT INTO `{PREFIX}postmeta` (`meta_id`, `post_id`, `meta_key`, `meta_value`) "
        f"VALUES {', '.join(postmeta_rows)};\n"
    )

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    out = Path(__file__).parent / "sample-blog.sql"
    out.write_text(build())
    print(f"wrote {out}")
