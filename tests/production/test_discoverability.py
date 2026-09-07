"""Can a search engine — or a person — find out what this site is?

Searching for play.the-smoke.com returned nothing but an AI summary
claiming the domain did not resolve. It resolves fine; Google simply had
nothing indexed, and the site gave it very little to work with:

  * `/` answered 302 to /login, so the one URL people search for and
    link to had no content of its own. A crawler found a password field.
  * There was no robots.txt and no sitemap.xml anywhere, so the eleven
    guides -- the only substantial prose on the site -- were advertised
    by nothing.
  * No canonical tags and no Open Graph, so sharing a link anywhere
    produced a bare URL with no title, description or preview.

None of this makes Google index the site; only submitting the domain and
earning inbound links does that. It does mean that when a crawler shows
up, there is something to read. These hold that.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.core.setup import create_tables
from game.handbook import GUIDES


class DiscoverabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            Path(self.temp_dir.name) / "seo.db",
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        from web.application import app

        self.client = app.test_client()

    def get(self, path):
        return self.client.get(path)

    # ------------------------------------------------ the front door

    def test_the_bare_domain_serves_a_page_rather_than_a_redirect(self):
        response = self.get("/")

        self.assertEqual(
            response.status_code,
            200,
            "a logged-out visitor is being bounced somewhere instead of "
            "being told what this site is",
        )

    def test_the_landing_page_says_what_the_game_is(self):
        page = self.get("/").get_data(as_text=True)

        self.assertIn("<h1", page)
        self.assertIn("The Smoke", page)
        self.assertIn("London", page)
        self.assertIn('name="description"', page)

    def test_the_landing_page_links_to_every_guide(self):
        page = self.get("/").get_data(as_text=True)

        for guide in GUIDES:
            with self.subTest(guide=guide.slug):
                self.assertIn(f"/forum/{guide.slug}", page)

    def test_a_signed_in_player_still_gets_the_game(self):
        """It must only replace the redirect for logged-out visitors.

        With a real account, not a made-up session id: pointing the
        session at a user who does not exist makes this 500, which is
        "not the landing page" for entirely the wrong reason.
        """
        from database.repositories.players import create_player
        from database.repositories.users import create_user

        user_id = create_user("player", "player@example.com", "hash")
        create_player(user_id, "Player")

        with self.client.session_transaction() as session:
            session["user_id"] = user_id

        response = self.get("/")

        self.assertIn(response.status_code, (302, 200))
        if response.status_code == 200:
            self.assertNotIn(
                'id="landing-title"',
                response.get_data(as_text=True),
                "a signed-in player was served the marketing page",
            )

    # -------------------------------------------------------- robots

    def test_robots_is_served_and_points_at_the_sitemap(self):
        response = self.get("/robots.txt")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/plain")
        self.assertIn("Sitemap:", body)
        self.assertIn("/sitemap.xml", body)

    def test_robots_keeps_crawlers_out_of_the_private_half(self):
        body = self.get("/robots.txt").get_data(as_text=True)

        for path in ("/admin", "/logout", "/reset-password"):
            with self.subTest(path=path):
                self.assertIn(f"Disallow: {path}", body)

    def test_robots_does_not_accidentally_block_the_whole_site(self):
        # One stray line here would undo everything else in this file.
        body = self.get("/robots.txt").get_data(as_text=True)

        self.assertNotIn("Disallow: /\n", body)
        self.assertIn("Allow: /", body)

    # ------------------------------------------------------- sitemap

    def test_the_sitemap_lists_every_guide(self):
        body = self.get("/sitemap.xml").get_data(as_text=True)

        for guide in GUIDES:
            with self.subTest(guide=guide.slug):
                self.assertIn(f"/forum/{guide.slug}", body)

    def test_the_sitemap_is_well_formed_xml(self):
        from xml.etree import ElementTree

        response = self.get("/sitemap.xml")

        self.assertEqual(response.mimetype, "application/xml")

        root = ElementTree.fromstring(response.get_data(as_text=True))
        namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

        locations = [
            element.text
            for element in root.iter(f"{namespace}loc")
        ]

        self.assertEqual(len(locations), len(GUIDES) + 5)
        for location in locations:
            self.assertTrue(location.startswith("http"), location)

    def test_every_entry_carries_the_hint_google_reads(self):
        """`lastmod` is used; `priority` and `changefreq` are not.

        The sitemap sent the two Google discards and omitted the one it
        reads. Every URL now carries a date, and the dates are held
        honest by a fingerprint -- see game/handbook/freshness.py, and
        `FreshnessTests` for the guard.
        """
        from xml.etree import ElementTree

        body = self.get("/sitemap.xml").get_data(as_text=True)
        root = ElementTree.fromstring(body)
        namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

        urls = list(root.iter(f"{namespace}url"))
        dates = list(root.iter(f"{namespace}lastmod"))

        self.assertEqual(len(dates), len(urls))
        self.assertNotIn("<priority>", body)
        self.assertNotIn("<changefreq>", body)

    def test_the_dates_are_valid_and_not_in_the_future(self):
        """A date Google cannot parse is worse than no date at all."""
        from datetime import date
        from xml.etree import ElementTree

        root = ElementTree.fromstring(
            self.get("/sitemap.xml").get_data(as_text=True)
        )
        namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

        for element in root.iter(f"{namespace}lastmod"):
            with self.subTest(lastmod=element.text):
                stamped = date.fromisoformat(element.text)

                self.assertEqual(stamped.isoformat(), element.text)
                self.assertLessEqual(stamped, date.today())

    def test_a_guide_carries_its_own_date_not_the_site_wide_one(self):
        """Otherwise every page claims to change whenever any does.

        Google's stated response to a lastmod that moves for the whole
        site at once is to stop trusting the field entirely.
        """
        from xml.etree import ElementTree

        from game.handbook.freshness import GUIDE_FRESHNESS

        root = ElementTree.fromstring(
            self.get("/sitemap.xml").get_data(as_text=True)
        )
        namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

        by_location = {
            element.findtext(f"{namespace}loc"):
                element.findtext(f"{namespace}lastmod")
            for element in root.iter(f"{namespace}url")
        }

        for guide in GUIDES:
            with self.subTest(guide=guide.slug):
                url = next(
                    location for location in by_location
                    if location.endswith(f"/forum/{guide.slug}")
                )

                self.assertEqual(
                    by_location[url],
                    GUIDE_FRESHNESS[guide.slug][0],
                )

    def test_the_sitemap_never_offers_a_private_page(self):
        body = self.get("/sitemap.xml").get_data(as_text=True)

        for path in ("/admin", "/logout", "/dashboard", "/bank"):
            with self.subTest(path=path):
                self.assertNotIn(f"<loc>{path}", body)
                self.assertNotIn(f"{path}</loc>", body)

    # ------------------------------------- sharing and duplicate URLs

    def test_the_public_pages_declare_a_canonical_url(self):
        for path in ("/", "/forum", "/rules", f"/forum/{GUIDES[0].slug}"):
            with self.subTest(path=path):
                page = self.get(path).get_data(as_text=True)
                self.assertIn('rel="canonical"', page)

    def test_a_shared_link_carries_a_title_and_a_description(self):
        for path in ("/", "/forum", "/rules", f"/forum/{GUIDES[0].slug}"):
            with self.subTest(path=path):
                page = self.get(path).get_data(as_text=True)
                self.assertIn('property="og:title"', page)
                self.assertIn('property="og:description"', page)

    def test_nothing_public_is_marked_noindex(self):
        for path in ("/", "/forum", "/rules"):
            with self.subTest(path=path):
                page = self.get(path).get_data(as_text=True)
                self.assertNotIn("noindex", page)


if __name__ == "__main__":
    unittest.main()
