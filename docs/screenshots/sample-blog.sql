-- Fake WordPress dump for wp-data-reader screenshots/testing.
-- Entirely fictional: no real people, places, or content.

CREATE TABLE `wp_users` (`ID` bigint, `user_login` varchar(60), `display_name` varchar(250), `user_email` varchar(100), `user_nicename` varchar(50));
INSERT INTO `wp_users` (`ID`, `user_login`, `display_name`, `user_email`, `user_nicename`) VALUES (2, 'sam', 'Sam Whitfield', 'sam@example.test', 'sam-whitfield');

CREATE TABLE `wp_terms` (`term_id` bigint, `name` varchar(200), `slug` varchar(200));
INSERT INTO `wp_terms` (`term_id`, `name`, `slug`) VALUES (10, 'Sightings', 'sightings'), (11, 'Backyard Setup', 'backyard-setup'), (12, 'Gear', 'gear'), (20, 'cardinals', 'cardinals'), (21, 'warblers', 'warblers'), (22, 'feeders', 'feeders'), (23, 'migration', 'migration'), (24, 'photography', 'photography');

CREATE TABLE `wp_term_taxonomy` (`term_taxonomy_id` bigint, `term_id` bigint, `taxonomy` varchar(32), `description` longtext, `parent` bigint, `count` bigint);
INSERT INTO `wp_term_taxonomy` (`term_taxonomy_id`, `term_id`, `taxonomy`, `description`, `parent`, `count`) VALUES (100, 10, 'category', '', 0, 0), (101, 11, 'category', '', 0, 0), (102, 12, 'category', '', 0, 0), (200, 20, 'post_tag', '', 0, 0), (201, 21, 'post_tag', '', 0, 0), (202, 22, 'post_tag', '', 0, 0), (203, 23, 'post_tag', '', 0, 0), (204, 24, 'post_tag', '', 0, 0);

CREATE TABLE `wp_posts` (`ID` longtext, `post_author` longtext, `post_date` longtext, `post_date_gmt` longtext, `post_content` longtext, `post_title` longtext, `post_excerpt` longtext, `post_status` longtext, `comment_status` longtext, `ping_status` longtext, `post_password` longtext, `post_name` longtext, `post_modified` longtext, `post_modified_gmt` longtext, `post_parent` longtext, `guid` longtext, `menu_order` longtext, `post_type` longtext, `post_mime_type` longtext, `comment_count` longtext);
INSERT INTO `wp_posts` (`ID`, `post_author`, `post_date`, `post_date_gmt`, `post_content`, `post_title`, `post_excerpt`, `post_status`, `comment_status`, `ping_status`, `post_password`, `post_name`, `post_modified`, `post_modified_gmt`, `post_parent`, `guid`, `menu_order`, `post_type`, `post_mime_type`, `comment_count`) VALUES (101, 2, '2023-03-04 07:40:00', '2023-03-04 07:40:00', '<p>A pair of cardinals has taken up residence in the hedge along the back
fence, and they\'ve been back every morning for about a week now &mdash; right on
schedule, usually just after sunrise.</p>
<p>The male does a slow, deliberate circuit of the feeder before ever landing,
which I assume is either caution or theater. Possibly both.</p>
<h2>Notes</h2>
<ul>
<li>Prefers the platform feeder over the tube feeder, consistently</li>
<li>Female is noticeably more relaxed around the window than the male</li>
<li>No sign of a nest yet, but it\'s early in the season</li>
</ul>', 'A Pair of Cardinals Moved Into the Hedge', 'They\'ve been back every morning for a week now, right on schedule.', 'publish', 'open', 'open', '', 'cardinals-in-the-hedge', '2023-03-04 07:40:00', '2023-03-04 07:40:00', 0, 'http://backyardbirding.test/?p=101', 0, 'post', '', 0), (102, 2, '2023-04-18 08:15:00', '2023-04-18 08:15:00', '<p>Migration is properly underway &mdash; three new warbler species have shown
up in the yard this week alone, all just passing through on their way
further north.</p>
<p>Yellow-rumped were the first to arrive, as usual, followed by a single
very lost-looking Blackburnian that stayed for exactly one afternoon.</p>
<p>Binoculars have basically lived on the kitchen table since Tuesday.</p>', 'Warbler Migration Is Picking Up', 'Three new warbler species in the yard this week alone.', 'publish', 'open', 'open', '', 'warbler-migration-picking-up', '2023-04-18 08:15:00', '2023-04-18 08:15:00', 0, 'http://backyardbirding.test/?p=102', 0, 'post', '', 0), (103, 2, '2023-05-02 09:00:00', '2023-05-02 09:00:00', '<p>Adding a second feeder always risks turning the yard into contested
territory, so I put some thought into placement before hanging it.</p>
<p>Keeping the new feeder well out of sight-line from the first one, on the
far side of the maple, mostly kept the peace. There\'s still the occasional
dispute, but nothing like the chaos of the one time I hung them side by
side.</p>', 'Setting Up a Second Feeder Without Starting a Turf War', 'Two feeders, positioned carefully, mostly kept the peace.', 'publish', 'open', 'open', '', 'second-feeder-without-turf-war', '2023-05-02 09:00:00', '2023-05-02 09:00:00', 0, 'http://backyardbirding.test/?p=103', 0, 'post', '', 0), (104, 2, '2023-06-10 15:00:00', '2023-06-10 15:00:00', '<p>Notes so far: shutter speed matters more than I expected, chickadees do
not sit still for anyone. Need better photos before this is postable.</p>', 'Draft: Photographing Fast Little Birds (unfinished)', '', 'draft', 'open', 'open', '', 'photographing-fast-birds-draft', '2023-06-10 15:00:00', '2023-06-10 15:00:00', 0, 'http://backyardbirding.test/?p=104', 0, 'post', '', 0), (105, 2, '2023-07-22 10:30:00', '2023-07-22 10:30:00', '<p>After months of blurry, half-obscured attempts, I finally caught one
worth keeping: the male cardinal, mid-hop off the platform feeder, in
actually decent morning light.</p>
<img src="http://backyardbirding.test/wp-content/uploads/2023/07/cardinal-hop-300x200.jpg" alt="cardinal mid-hop off the feeder" />
<p>Framed it. It\'s on the wall now, which is probably a little much for a
bird photo, but here we are.</p>', 'The Best Photo I\'ve Gotten So Far', 'A cardinal, mid-hop, caught in decent light for once.', 'publish', 'open', 'open', '', 'best-photo-so-far', '2023-07-22 10:30:00', '2023-07-22 10:30:00', 0, 'http://backyardbirding.test/?p=105', 0, 'post', '', 0), (106, 2, '2023-08-01 12:00:00', '2023-08-01 12:00:00', '<p>Private notes, not for the public site &mdash; the neighbor\'s cat has been in
the yard twice this week. Need to mention it, gently, before it becomes a
bigger conversation than it needs to be.</p>', 'Private Notes: Neighbor\'s Cat (private)', '', 'private', 'open', 'open', '', 'neighbors-cat-notes', '2023-08-01 12:00:00', '2023-08-01 12:00:00', 0, 'http://backyardbirding.test/?p=106', 0, 'post', '', 0), (110, 2, '2023-01-01 12:00:00', '2023-01-01 12:00:00', '<p>Backyard Birding is a small, occasional log of whatever shows up at the
feeders, written by Sam Whitfield. No expertise claimed &mdash; just a pair of
binoculars and more patience than the average chickadee deserves.</p>', 'About', '', 'publish', 'open', 'open', '', 'about', '2023-01-01 12:00:00', '2023-01-01 12:00:00', 0, 'http://backyardbirding.test/about', 0, 'page', '', 0), (201, 2, '2023-07-20 10:00:00', '2023-07-20 10:00:00', '', 'cardinal-hop', '', 'inherit', 'open', 'closed', '', 'cardinal-hop', '2023-07-20 10:00:00', '2023-07-20 10:00:00', 105, 'http://backyardbirding.test/wp-content/uploads/2023/07/cardinal-hop.jpg', 0, 'attachment', 'image/jpeg', 0);

CREATE TABLE `wp_term_relationships` (`object_id` bigint, `term_taxonomy_id` bigint, `term_order` int);
INSERT INTO `wp_term_relationships` (`object_id`, `term_taxonomy_id`, `term_order`) VALUES (101, 100, 0), (101, 200, 0), (102, 100, 0), (102, 201, 0), (102, 203, 0), (103, 101, 0), (103, 102, 0), (103, 202, 0), (104, 102, 0), (104, 204, 0), (105, 100, 0), (105, 204, 0), (105, 200, 0), (106, 101, 0);

CREATE TABLE `wp_postmeta` (`meta_id` bigint, `post_id` bigint, `meta_key` varchar(255), `meta_value` longtext);
INSERT INTO `wp_postmeta` (`meta_id`, `post_id`, `meta_key`, `meta_value`) VALUES (1, 201, '_wp_attached_file', '2023/07/cardinal-hop.jpg'), (2, 105, '_thumbnail_id', '201');

