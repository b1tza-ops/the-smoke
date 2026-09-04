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
from game.crime import CRIMES
from game.gym.definitions import GYMS
from game.handbook import GUIDES, RULES, get_guide, inline, sections
from game.handbook.blocks import Bullets, Note, Steps, Table, Text
from game.handbook.guides import GUIDES_BY_SLUG, SECTION_ORDER
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

    def test_every_opponent_is_listed_at_its_real_energy_cost(self):
        # The guide said "every fight costs 10 energy" for as long as
        # that was true and then afterwards. Opponents charge their own
        # cost now, so read them back out of the table.
        from game.combat.npc import OPPONENTS

        text = self.guide("fighting")

        for opponent in OPPONENTS:
            with self.subTest(opponent=opponent.key):
                self.assertIn(str(opponent.energy_cost), text)
                self.assertIn(
                    f"£{opponent.cash_min}\u2013{opponent.cash_max}",
                    text,
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


def table_with(guide, first_header):
    for block in guide.blocks:
        if isinstance(block, Table) and block.headers[0] == first_header:
            return block
    raise AssertionError(
        f"{guide.slug} has no table starting {first_header!r}"
    )


class NewGuideAccuracyTests(unittest.TestCase):
    """Three systems shipped without a guide, and now have one.

    Jobs, the item market and the daily contract board were all live
    and all undocumented -- the handbook mentioned the contract board
    nowhere at all. These pin the figures those guides quote to the
    catalogues they came from, so the tables cannot drift the way the
    housing one did.
    """

    def test_the_job_table_lists_every_role_at_the_right_pay(self):
        from game.jobs.definitions import CAREERS

        table = table_with(GUIDES_BY_SLUG["jobs-and-shifts"], "Role")
        listed = {row[0]: row for row in table.rows}
        roles = [role for career in CAREERS for role in career.roles]

        self.assertEqual(len(listed), len(roles))

        for role in roles:
            with self.subTest(role=role.key):
                row = listed.get(role.name)
                self.assertIsNotNone(row, f"{role.name} is not listed")
                self.assertEqual(row[1], f"£{role.salary:,}")
                self.assertEqual(row[2], str(role.energy_cost))

    def test_the_job_guide_quotes_the_real_shift_length(self):
        from game.jobs.service import SHIFT_SECONDS

        hours = SHIFT_SECONDS // 3600
        prose = " ".join(all_strings(GUIDES_BY_SLUG["jobs-and-shifts"]))

        self.assertIn(f"{hours} hours", prose.replace("three", "3"))

    def test_the_best_paid_role_is_the_one_the_guide_recommends(self):
        """The advice, not just the table.

        The guide tells a new player to join London Transport and an
        established one to aim at Hackney Security. Both claims are
        arithmetic, so both can go stale.
        """
        from game.jobs.definitions import CAREERS

        by_name = {career.name: career for career in CAREERS}
        entry_pay = {
            name: career.roles[0].salary
            for name, career in by_name.items()
            if career.roles[0].required_level == 1
        }
        best_entry = max(entry_pay, key=entry_pay.get)
        best_top = max(
            by_name,
            key=lambda name: by_name[name].roles[-1].salary,
        )

        self.assertEqual(best_entry, "London Transport")
        self.assertEqual(best_top, "Hackney Security")

    def test_the_careers_that_need_a_district_are_named_as_such(self):
        from game.jobs.definitions import CAREERS

        table = table_with(GUIDES_BY_SLUG["jobs-and-shifts"], "Career")
        listed = {row[0]: row[1] for row in table.rows}

        self.assertEqual(len(listed), len(CAREERS))

        for career in CAREERS:
            with self.subTest(career=career.key):
                want = (
                    DISTRICTS_BY_KEY[career.required_district].name
                    if career.required_district
                    else "Anywhere"
                )
                self.assertEqual(listed[career.name], want)

    def test_the_contract_table_lists_the_whole_pool(self):
        from game.combat.contracts import CONTRACT_POOL

        table = table_with(GUIDES_BY_SLUG["daily-contracts"], "Contract")
        listed = {row[0]: row[2] for row in table.rows}

        self.assertEqual(len(listed), len(CONTRACT_POOL))

        for contract in CONTRACT_POOL:
            with self.subTest(contract=contract.key):
                pays = listed.get(contract.name)
                self.assertIsNotNone(pays)
                self.assertIn(f"£{contract.cash_reward:,}", pays)
                self.assertIn(f"{contract.xp_reward} XP", pays)

    def test_the_contract_guide_quotes_the_board_size(self):
        from game.combat.contracts import (
            DAILY_CONTRACT_COUNT,
            MINIMUM_SOLO_CONTRACTS,
        )

        prose = " ".join(
            all_strings(GUIDES_BY_SLUG["daily-contracts"])
        ).lower()

        self.assertEqual(DAILY_CONTRACT_COUNT, 3)
        self.assertEqual(MINIMUM_SOLO_CONTRACTS, 2)
        self.assertIn("three contracts a day", prose)
        self.assertIn("at least two of your three", prose)

    def test_the_jail_section_quotes_the_real_breakout_odds(self):
        """Both jail numbers were written for a game that grew past them.

        Bail charged a flat fee per level and the breakout capped at
        85% for anyone with a combined 60 in speed and dexterity, which
        is everybody. The guide describes the repaired versions, so it
        has to move if they move again.
        """
        from database.repositories.jail import (
            BREAKOUT_FLOOR,
            BREAKOUT_NERVE_COST,
            BREAKOUT_RANGE,
        )

        prose = " ".join(
            all_strings(GUIDES_BY_SLUG["crime-and-jail"])
        )

        self.assertIn(f"{BREAKOUT_NERVE_COST} nerve", prose)
        self.assertIn(
            f"{BREAKOUT_FLOOR}\u2013{BREAKOUT_FLOOR + BREAKOUT_RANGE}%",
            prose,
        )

    def test_the_market_guide_quotes_the_real_commission(self):
        from game.economy.fence import FENCE_RATE
        from game.economy.market import (
            COMMISSION_RATE,
            MAXIMUM_LISTING_QUANTITY,
        )

        prose = " ".join(
            all_strings(GUIDES_BY_SLUG["the-item-market"])
        ).lower()

        self.assertIn(
            f"commission is {int(COMMISSION_RATE * 100)}%", prose
        )
        self.assertIn(f"{int(FENCE_RATE * 100)}% of value", prose)
        self.assertIn("twenty", prose)
        self.assertEqual(MAXIMUM_LISTING_QUANTITY, 20)


class FreshnessTests(unittest.TestCase):
    """`lastmod` has to be true, or it is worse than absent.

    Google reads `lastmod` and ignores `priority` and `changefreq`, so
    the sitemap carries the one that is used. But its guidance is
    equally explicit that a date which is always "now", or which moves
    on every deploy, gets the field ignored for the whole site -- which
    rules out a file modification time, since a git checkout stamps
    every file at deploy.

    So each date is written down with a fingerprint of the guide beside
    it, and this recomputes the fingerprint. Edit a guide without
    moving its date and this fails, which is what makes the date honest
    rather than remembered.
    """

    def test_every_guide_has_a_date(self):
        from game.handbook.freshness import GUIDE_FRESHNESS

        missing = sorted(
            guide.slug for guide in GUIDES
            if guide.slug not in GUIDE_FRESHNESS
        )

        self.assertEqual(
            missing,
            [],
            "these guides have no last-changed date: "
            + ", ".join(missing),
        )

    def test_no_date_is_claimed_for_a_guide_that_is_gone(self):
        from game.handbook.freshness import GUIDE_FRESHNESS

        slugs = {guide.slug for guide in GUIDES}
        orphans = sorted(set(GUIDE_FRESHNESS) - slugs)

        self.assertEqual(orphans, [])

    def test_a_changed_guide_must_carry_a_changed_date(self):
        from game.handbook.freshness import (
            GUIDE_FRESHNESS,
            fingerprint,
        )

        stale = []

        for guide in GUIDES:
            recorded = GUIDE_FRESHNESS.get(guide.slug)
            if recorded is None:
                continue

            _date, recorded_print = recorded
            now = fingerprint(guide)

            if now != recorded_print:
                stale.append(f'"{guide.slug}": ("<today>", "{now}")')

        self.assertEqual(
            stale,
            [],
            "these guides changed without their date moving. Paste "
            "today's date and the new fingerprint into "
            "game/handbook/freshness.py:\n  " + "\n  ".join(stale),
        )

    def test_the_fingerprint_notices_a_single_edited_word(self):
        """Otherwise the guard above proves nothing."""
        from dataclasses import replace

        from game.handbook.blocks import Text
        from game.handbook.freshness import fingerprint

        guide = GUIDES[0]
        edited = replace(
            guide,
            blocks=guide.blocks + (Text("One more sentence."),),
        )
        retitled = replace(guide, title=guide.title + "!")

        self.assertNotEqual(fingerprint(guide), fingerprint(edited))
        self.assertNotEqual(fingerprint(guide), fingerprint(retitled))

    def test_the_fingerprint_is_stable_across_runs(self):
        from game.handbook.freshness import fingerprint

        for guide in GUIDES:
            with self.subTest(guide=guide.slug):
                self.assertEqual(
                    fingerprint(guide), fingerprint(guide)
                )

    def test_the_dates_are_dates(self):
        from datetime import date

        from game.handbook.freshness import GUIDE_FRESHNESS

        for slug, (when, _print) in GUIDE_FRESHNESS.items():
            with self.subTest(guide=slug):
                self.assertEqual(
                    date.fromisoformat(when).isoformat(), when
                )


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

    def resolves(self, path):
        """Whether a link lands somewhere real.

        A guide may link to another guide, and `/forum/<slug>` is one
        route rather than one per guide, so those are checked against
        the catalogue instead of the URL map -- which also catches a
        link to a guide that has been renamed or removed.
        """
        if path in self.routes:
            return True

        prefix = "/forum/"
        return (
            path.startswith(prefix)
            and path[len(prefix):] in GUIDES_BY_SLUG
        )

    def test_every_internal_link_resolves(self):
        pattern = re.compile(r"\[[^\]]+\]\((/[A-Za-z0-9/_\-]*)\)")
        found = 0
        for text in self.all_prose():
            for path in pattern.findall(str(text)):
                found += 1
                with self.subTest(path=path):
                    self.assertTrue(
                        self.resolves(path),
                        f"{path} goes nowhere",
                    )
        self.assertGreater(found, 0, "no links found to check")

    def test_a_link_to_a_missing_guide_is_caught(self):
        self.assertFalse(self.resolves("/forum/no-such-guide"))
        self.assertTrue(self.resolves("/forum/the-casino"))


class HousingGuideTests(unittest.TestCase):
    """The guide quotes figures, so the figures have to be the real ones.

    A wiki that drifts from the game is worse than no wiki: players
    plan around it. These pin the housing page's numbers and pictures
    to what the code actually does.
    """

    def setUp(self):
        self.guide = get_guide("housing")

    def rows_of(self, headers_start):
        for block in self.guide.blocks:
            if isinstance(block, Table) and block.headers[0] == headers_start:
                return block.rows
        self.fail(f"no table starting {headers_start!r}")

    def test_the_ladder_matches_the_residences(self):
        from game.housing import RESIDENCES
        from game.housing.service import recovery_bonus

        quoted = {
            row[0]: (row[1], row[2], row[3])
            for row in self.rows_of("Home")
        }

        self.assertEqual(len(quoted), len(RESIDENCES))

        for home in RESIDENCES:
            with self.subTest(residence=home.key):
                price, energy, nerve = quoted[home.name]

                self.assertEqual(
                    price,
                    "Free" if not home.purchase_price
                    else f"£{home.purchase_price:,}",
                )
                for shown, actual in (
                    (energy, recovery_bonus(home, (), "energy")),
                    (nerve, recovery_bonus(home, (), "nerve")),
                ):
                    self.assertEqual(
                        shown,
                        "—" if not actual else f"+{actual}%",
                    )

    def test_the_rent_table_matches_the_residences(self):
        from game.housing import RESIDENCES
        from game.housing.service import daily_upkeep

        quoted = {}
        for block in self.guide.blocks:
            if isinstance(block, Table) and block.headers == (
                "Home",
                "Rent a day",
            ):
                quoted = {row[0]: row[1] for row in block.rows}
                break

        self.assertEqual(len(quoted), len(RESIDENCES))

        for home in RESIDENCES:
            with self.subTest(residence=home.key):
                rent = daily_upkeep(home)
                self.assertEqual(
                    quoted[home.name],
                    "Free" if not rent else f"£{rent:,}",
                )

    def test_it_promises_arrears_never_take_anything(self):
        # The guide has to be straight about this or the first player
        # who falls behind assumes they have lost the house.
        prose = " ".join(
            str(getattr(block, "text", ""))
            for block in self.guide.blocks
        )

        self.assertIn("not evicted", prose)

    def test_the_fittings_match_the_catalogue(self):
        from game.housing import FACILITIES

        quoted = {
            row[0]: row[1] for row in self.rows_of("Fitting")
        }

        self.assertEqual(len(quoted), len(FACILITIES))

        for name, price, _effect in FACILITIES.values():
            with self.subTest(fitting=name):
                self.assertEqual(quoted[name], f"£{price:,}")

    def test_the_storage_table_matches_the_residences(self):
        from game.housing import RESIDENCES

        quoted = {row[0]: row[1] for row in self.rows_of("Home") if False}
        for block in self.guide.blocks:
            if isinstance(block, Table) and block.headers == ("Home", "Carries"):
                quoted = {row[0]: row[1] for row in block.rows}
                break

        self.assertEqual(len(quoted), len(RESIDENCES))

        for home in RESIDENCES:
            with self.subTest(residence=home.key):
                self.assertEqual(
                    quoted[home.name],
                    f"{home.storage_capacity} items",
                )

    def test_every_picture_it_shows_exists(self):
        from pathlib import Path as _Path

        from game.handbook.blocks import Gallery
        from utils.images import is_renderable_image

        static = (
            _Path(__file__).resolve().parents[2] / "web" / "static"
        )
        shown = [
            filename
            for block in self.guide.blocks
            if isinstance(block, Gallery)
            for filename, _caption in block.images
        ]

        self.assertTrue(shown, "the guide shows no pictures at all")

        missing = [
            filename
            for filename in shown
            if not is_renderable_image(static / filename)
        ]

        self.assertEqual(missing, [], f"unrenderable: {missing}")

    def test_nothing_on_the_property_page_is_decoration_any_more(self):
        """Checked against the code, not against the guide.

        Every figure a property advertises used to have a chance of
        being read by nothing: safe capacity was, then garage space
        was, then comfort and the swimming pool. Each was found by a
        reader noticing the guide's own apology rather than by
        anything failing.

        So this asserts the behaviour instead of the prose: each
        advertised number must visibly change something. A figure added
        to `ResidenceDefinition` tomorrow and wired to nothing does not
        fail here -- but a figure quietly *unwired* does.
        """
        from game.housing.service import (
            RESIDENCES,
            gym_gain_bonus,
            recovery_bonus,
        )
        from game.housing.safe import capacity_for
        from game.vehicles.service import garage_capacity

        bottom, top = RESIDENCES[0], RESIDENCES[-1]

        for label, read in (
            ("energy", lambda home: recovery_bonus(home, (), "energy")),
            ("nerve", lambda home: recovery_bonus(home, (), "nerve")),
            ("comfort",
             lambda home: recovery_bonus(home, (), "happiness")),
            ("safe", lambda home: capacity_for(home.key)),
            ("garage", lambda home: garage_capacity(home.key)),
            ("storage", lambda home: home.storage_capacity),
        ):
            with self.subTest(figure=label):
                self.assertGreater(
                    read(top),
                    read(bottom),
                    f"{label} is advertised and reads the same at "
                    "both ends of the ladder",
                )

        self.assertGreater(
            gym_gain_bonus(("pool",)),
            0,
            "the swimming pool is sold for £8,000 and does nothing",
        )

    def test_it_stops_calling_a_figure_dead_once_it_is_wired_up(self):
        """The other half of the same rule.

        Safe capacity sat on the not-wired-up list after the safe
        shipped, so the same page both explained the interest rate and
        said the number did nothing. Garage space would have done the
        same the day vehicles landed. A guide that contradicts itself
        is worse than one that is merely behind, so both are pinned
        here: the moment a figure starts working, it comes off the
        list.
        """
        prose = " ".join(
            str(item)
            for block in self.guide.blocks
            if isinstance(block, Bullets)
            for item in block.items
        )

        for wired in (
            "Safe capacity",
            "Garage space",
            "has no effect",
            "decoration",
        ):
            with self.subTest(attribute=wired):
                self.assertNotIn(wired, prose)


class CrimeGuideTests(unittest.TestCase):
    """The crime table drifted once already.

    It carried three-day and five-day sentences, and prose explaining
    that the big jobs are worth £12 an hour, for as long as that was
    true and then afterwards. Pin the column to the crimes.
    """

    def jail_column(self):
        guide = get_guide("crime-and-jail")

        for block in guide.blocks:
            if isinstance(block, Table) and "Jail if caught" in block.headers:
                index = block.headers.index("Jail if caught")
                return {row[0]: row[index] for row in block.rows}

        self.fail("no crime table with a jail column")

    def test_the_jail_column_matches_the_crimes(self):
        from game.crime import CRIMES

        shown = self.jail_column()
        by_minutes = {}

        for crime in CRIMES:
            minutes = crime.jail_seconds // 60
            by_minutes[crime.jail_chance, minutes] = crime.key

        for label, cell in shown.items():
            with self.subTest(crime=label):
                chance, sentence = cell.split(", ")
                chance = int(chance.rstrip("%"))
                minutes = (
                    60 if sentence == "1 hour"
                    else int(sentence.split()[0])
                )

                self.assertIn(
                    (chance, minutes),
                    by_minutes,
                    f"{label} shows {cell}, which no crime has",
                )

    def test_it_no_longer_promises_multi_day_sentences(self):
        for cell in self.jail_column().values():
            with self.subTest(cell=cell):
                self.assertNotIn("day", cell)

    def test_it_explains_heat(self):
        # Heat is the cost of a big score now. A guide that omits it
        # leaves players thinking the top crimes are free money.
        prose = " ".join(
            str(getattr(block, "text", ""))
            for block in get_guide("crime-and-jail").blocks
        )

        self.assertIn("wanted level", prose)


if __name__ == "__main__":
    unittest.main()
