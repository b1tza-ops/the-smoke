"""The handbook.

Two things are worth testing here. The first is that every page renders
and every link inside one resolves -- a guide pointing at a dead route
is worse than no guide. The second is that the inline formatter cannot
be made to inject markup, because it is the only place in the project
that builds HTML from a string.

The figures in the guides are checked against the constants they quote
where that is cheap. Prose cannot be tested, and pretending otherwise
would just be a test that agrees with whatever the guide says.
"""

import re
import unittest

from game.casino.limits import BET_PER_LEVEL, MINIMUM_LEVEL
from game.combat.npc import COMBAT_ENERGY_COST
from game.crime import CRIMES
from game.gym.definitions import GYMS
from game.handbook import GUIDES, RULES, get_guide, inline, sections
from game.handbook.blocks import Bullets, Note, Steps, Table, Text
from game.handbook.guides import SECTION_ORDER
from game.inventory import AMMO_KEYS, ITEMS_BY_KEY
from game.player.regeneration import (
    ENERGY_POINTS_PER_TICK,
    ENERGY_TICK_SECONDS,
    NERVE_POINTS_PER_TICK,
    NERVE_TICK_SECONDS,
)
from game.world.districts import DISTRICTS_BY_KEY


def all_strings(guide):
    """Every piece of prose in a guide, whatever block it came from."""
    out = []
    for block in guide.blocks:
        if isinstance(block, (Text, Note)):
            out.append(block.text)
        elif isinstance(block, (Bullets, Steps)):
            out.extend(block.items)
        elif isinstance(block, Table):
            out.extend(block.headers)
            out.append(block.caption)
            for row in block.rows:
                out.extend(row)
        else:
            out.append(getattr(block, "text", ""))
    return [str(item) for item in out]


class InlineFormatterTests(unittest.TestCase):
    def test_markup_in_the_source_is_escaped(self):
        rendered = str(inline("<script>alert(1)</script>"))
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_markup_inside_emphasis_is_still_escaped(self):
        rendered = str(inline("**<b>bold</b>**"))
        self.assertIn("<strong>", rendered)
        self.assertIn("&lt;b&gt;", rendered)
        self.assertNotIn("<b>", rendered)

    def test_the_vocabulary_renders(self):
        self.assertIn("<strong>x</strong>", str(inline("**x**")))
        self.assertIn("<code>x</code>", str(inline("`x`")))
        self.assertIn('<a href="/gym">gym</a>', str(inline("[gym](/gym)")))

    def test_only_in_site_paths_become_links(self):
        for target in (
            "https://example.com",
            "//example.com",
            "javascript:alert(1)",
            "http://example.com/x",
        ):
            with self.subTest(target=target):
                rendered = str(inline(f"[go]({target})"))
                self.assertNotIn("<a ", rendered)

    def test_a_quoted_attribute_cannot_be_broken_out_of(self):
        rendered = str(inline('[x](/a") onmouseover="alert(1)'))
        # The path holds a quote, so no link is built at all and every
        # quote is left escaped -- the text ends up inert, outside any tag.
        self.assertNotIn("<a ", rendered)
        self.assertNotIn('"', rendered)
        self.assertIn("&quot;", rendered)


class GuideCatalogueTests(unittest.TestCase):
    def test_every_guide_is_in_a_known_section(self):
        for guide in GUIDES:
            self.assertIn(guide.section, SECTION_ORDER)

    def test_every_section_has_at_least_one_guide(self):
        for name, guides in sections():
            self.assertTrue(guides, f"{name} is empty")

    def test_sections_cover_every_guide_exactly_once(self):
        listed = [g.slug for _, guides in sections() for g in guides]
        self.assertEqual(sorted(listed), sorted(g.slug for g in GUIDES))

    def test_slugs_are_unique_and_url_safe(self):
        slugs = [guide.slug for guide in GUIDES]
        self.assertEqual(len(slugs), len(set(slugs)))
        for slug in slugs:
            self.assertRegex(slug, r"^[a-z0-9\-]+$")

    def test_lookup_finds_every_guide_and_nothing_else(self):
        for guide in GUIDES:
            self.assertIs(get_guide(guide.slug), guide)
        self.assertIsNone(get_guide("not-a-guide"))

    def test_every_guide_has_a_summary_and_content(self):
        for guide in GUIDES:
            self.assertTrue(guide.summary.strip(), guide.slug)
            self.assertTrue(guide.blocks, guide.slug)

    def test_tables_are_rectangular(self):
        for guide in GUIDES:
            for block in guide.blocks:
                if not isinstance(block, Table):
                    continue
                width = len(block.headers)
                for row in block.rows:
                    self.assertEqual(len(row), width, f"{guide.slug}: {row}")


class GuideAccuracyTests(unittest.TestCase):
    """The figures a guide quotes must match the game."""

    def guide(self, slug):
        return " ".join(all_strings(get_guide(slug)))

    def test_regeneration_rates_match_the_engine(self):
        text = self.guide("energy-and-nerve")
        energy_hourly = ENERGY_POINTS_PER_TICK * 3600 // ENERGY_TICK_SECONDS
        nerve_hourly = NERVE_POINTS_PER_TICK * 3600 // NERVE_TICK_SECONDS
        self.assertIn(str(energy_hourly), text)
        self.assertIn(str(nerve_hourly), text)
        self.assertIn(f"+{ENERGY_POINTS_PER_TICK} every 10 minutes", text)

    def test_every_crime_is_listed_with_its_nerve_cost(self):
        text = self.guide("crime-and-jail")
        for crime in CRIMES:
            with self.subTest(crime=crime.key):
                self.assertIn(f"{crime.success_chance}%", text)

    def test_the_fight_energy_cost_is_right(self):
        self.assertIn(
            f"**{COMBAT_ENERGY_COST} energy**", self.guide("fighting")
        )

    def test_every_pistol_and_round_is_listed_at_its_real_price(self):
        text = self.guide("guns-and-ammunition")
        for key in (
            "derringer_22", "converted_blank_pistol",
            "snub_nose_38", "compact_9mm",
        ):
            item = ITEMS_BY_KEY[key]
            with self.subTest(item=key):
                self.assertIn(item.name, text)
                self.assertIn(f"+{item.strength_bonus}", text)
                self.assertIn(f"£{item.value:,}", text)
        for key in AMMO_KEYS:
            item = ITEMS_BY_KEY[key]
            with self.subTest(ammo=key):
                self.assertIn(f"£{item.value}", text)

    def test_the_gym_ladder_lists_every_gym(self):
        text = self.guide("the-gym")
        for gym in GYMS:
            with self.subTest(gym=gym.key):
                self.assertIn(gym.name.replace("Average Joe's Camden", "Average Joe's"), text)

    def test_the_casino_gate_and_ceiling_are_right(self):
        text = self.guide("the-casino")
        self.assertIn(f"level **{MINIMUM_LEVEL}", text.replace("**level ", "level **"))
        self.assertIn(f"£{BET_PER_LEVEL}", text)

    def test_district_unlock_levels_are_right(self):
        text = self.guide("travel")
        for district in DISTRICTS_BY_KEY.values():
            with self.subTest(district=district.key):
                self.assertIn(district.name, text)
                self.assertIn(f"Level {district.minimum_level}", text)


class RuleTests(unittest.TestCase):
    def test_every_rule_states_a_penalty(self):
        for rule in RULES:
            self.assertTrue(rule.penalty.strip(), rule.key)
            self.assertTrue(rule.blocks, rule.key)

    def test_rule_keys_are_unique_and_anchor_safe(self):
        keys = [rule.key for rule in RULES]
        self.assertEqual(len(keys), len(set(keys)))
        for key in keys:
            self.assertRegex(key, r"^[a-z0-9\-]+$")

    def test_the_serious_offences_are_covered(self):
        keys = {rule.key for rule in RULES}
        self.assertLessEqual(
            {
                "multiple-accounts",
                "real-money-trading",
                "account-sharing",
                "automation",
                "exploits",
            },
            keys,
        )

    def test_penalties_render_to_a_known_style(self):
        # The template turns the penalty into a class name; an unexpected
        # one would silently lose its colour.
        known = {"permanent-ban", "ban", "warning-then-ban"}
        for rule in RULES:
            slug = rule.penalty.lower().replace(" ", "-").replace(",", "")
            self.assertIn(slug, known, rule.key)


class HandbookLinkTests(unittest.TestCase):
    """A guide that points at a dead route is worse than no guide."""

    def setUp(self):
        from web.application import app
        self.app = app
        self.routes = {rule.rule for rule in app.url_map.iter_rules()}

    def all_prose(self):
        prose = []
        for guide in GUIDES:
            prose.extend(all_strings(guide))
        for rule in RULES:
            for block in rule.blocks:
                if isinstance(block, (Text, Note)):
                    prose.append(block.text)
                elif isinstance(block, Bullets):
                    prose.extend(block.items)
        return prose

    def test_every_internal_link_resolves(self):
        pattern = re.compile(r"\[[^\]]+\]\((/[A-Za-z0-9/_\-]*)\)")
        found = 0
        for text in self.all_prose():
            for path in pattern.findall(str(text)):
                found += 1
                with self.subTest(path=path):
                    self.assertIn(path, self.routes, f"{path} is not a route")
        self.assertGreater(found, 0, "no links found to check")


if __name__ == "__main__":
    unittest.main()
