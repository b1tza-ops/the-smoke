"""Letting other machines play, without letting them eat the game.

The rules page bans automation, and it is right to. A bot that never
sleeps out-earns every human on the server inside a week, and this one
has real players with real balances. So the ban stays for anything
unsanctioned, and this is the declared exception: an account that has
said it is a machine, plays through an API with a key, and is sealed
off from every other player.

**The wall is the feature, and it is symmetric.** An agent cannot
attack, mug, burgle, bail, bounty or trade with anybody -- and nobody
can do those things to an agent either. The second half matters more
than it looks: a machine that logs in every ninety seconds and *can* be
robbed is a cash machine with a heartbeat, and the humans would find it
inside a day.

Most of what follows is that wall, checked from both sides, at the
repository rather than at the API -- because an agent account can also
log into the website, and a check that only lives in the JSON layer is
not a wall at all.
"""

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from database.core.setup import create_tables
from game.agents.service import (
    AGENT_SEALED_ACTIONS,
    KEY_PREFIX,
    RATE_LIMIT_PER_MINUTE,
    AgentError,
    generate_key,
    looks_like_key,
    sealed_reason,
)
from game.player.regeneration import format_timestamp


class KeyShapeTests(unittest.TestCase):
    def test_a_key_is_obviously_a_credential(self):
        """Prefixed so one found in a log is recognisable as ours."""
        key = generate_key()

        self.assertTrue(key.startswith(KEY_PREFIX))
        self.assertGreater(len(key), len(KEY_PREFIX) + 30)

    def test_two_keys_are_never_the_same(self):
        self.assertEqual(len({generate_key() for _ in range(200)}), 200)

    def test_obvious_rubbish_never_reaches_the_database(self):
        for rubbish in ("", "hunter2", None, 12, KEY_PREFIX, KEY_PREFIX + "x"):
            with self.subTest(candidate=rubbish):
                self.assertFalse(looks_like_key(rubbish))

    def test_a_real_key_passes_the_shape_check(self):
        self.assertTrue(looks_like_key(generate_key()))


class SealedActionTests(unittest.TestCase):
    """The pure rule, before any database is involved."""

    def test_an_agent_may_not_touch_a_human(self):
        for action in AGENT_SEALED_ACTIONS:
            with self.subTest(action=action):
                self.assertIsNotNone(sealed_reason(action, True, False))

    def test_a_human_may_not_touch_an_agent(self):
        """The half that is easy to forget, and worse to get wrong."""
        for action in AGENT_SEALED_ACTIONS:
            with self.subTest(action=action):
                self.assertIsNotNone(sealed_reason(action, False, True))

    def test_two_humans_are_left_alone(self):
        for action in AGENT_SEALED_ACTIONS:
            with self.subTest(action=action):
                self.assertIsNone(sealed_reason(action, False, False))

    def test_playing_the_city_is_never_sealed(self):
        for action in ("crime", "train", "travel", "fight", "job"):
            with self.subTest(action=action):
                self.assertIsNone(sealed_reason(action, True, False))
                self.assertIsNone(sealed_reason(action, True, True))

    def test_every_way_value_moves_between_players_is_listed(self):
        """A new mechanic that takes from a player must be added here.

        This cannot check the future, but it can check that the list
        still covers everything the game has today -- so removing an
        entry is a visible act rather than an accident.
        """
        self.assertEqual(
            set(AGENT_SEALED_ACTIONS),
            {
                "attack", "mug", "burgle", "bail",
                "breakout", "bounty", "market",
            },
        )


class WalledOffTests(unittest.TestCase):
    """The wall where it actually lives: on the transaction.

    Checked through the repositories rather than the API, because an
    agent's account can still log into the website. A rule enforced
    only in the JSON layer would be a suggestion.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "agents.db"
        self.database_patch = patch(
            "database.core.connection.DB_PATH", self.database_path
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        self.bot_user, self.bot = self.make("botty")
        self.human_user, self.human = self.make("human")
        self.other_user, self.other = self.make("other")

        from database.repositories.agents import issue_key

        self.key = issue_key(self.bot_user, "Test agent")

    def make(self, name):
        from database.repositories.players import create_player
        from database.repositories.users import create_user

        user_id = create_user(name, f"{name}@example.com", "hash")
        create_player(user_id, name)
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                "UPDATE users SET created_at = '2026-01-01' WHERE id = ?",
                (user_id,),
            )
            connection.execute(
                "UPDATE players SET money = 100000, level = 10, "
                "nerve = 50, energy = 100, current_district = 'camden', "
                "residence_key = 'council_flat' WHERE user_id = ?",
                (user_id,),
            )
        player_id = connection.execute(
            "SELECT id FROM players WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        connection.close()
        return user_id, player_id

    def jail(self, player_id):
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                "UPDATE players SET jail_until = ? WHERE id = ?",
                (
                    format_timestamp(
                        datetime.now(timezone.utc) + timedelta(hours=1)
                    ),
                    player_id,
                ),
            )
        connection.close()

    # ----------------------------------------------- attacks and theft

    def test_an_agent_cannot_attack_a_human(self):
        from database.repositories.pvp import reserve_pvp_attack

        with self.assertRaises(AgentError):
            reserve_pvp_attack(self.bot, self.human)

    def test_a_human_cannot_attack_an_agent(self):
        from database.repositories.pvp import reserve_pvp_attack

        with self.assertRaises(AgentError):
            reserve_pvp_attack(self.human, self.bot)

    def test_two_humans_can_still_attack_each_other(self):
        """The wall must not have gone up around everybody."""
        from database.repositories.pvp import reserve_pvp_attack

        self.assertIsNotNone(
            reserve_pvp_attack(self.human, self.other)
        )

    def test_an_agent_never_appears_in_the_target_list(self):
        from database.repositories.pvp import get_pvp_targets

        names = {
            target["name"]
            for target in get_pvp_targets(self.human, "camden")
        }

        self.assertIn("other", names)
        self.assertNotIn("botty", names)

    def test_an_agent_cannot_burgle_and_cannot_be_burgled(self):
        from database.repositories.safe import burgle

        with self.assertRaises(AgentError):
            burgle(self.bot_user, self.human)

        with self.assertRaises(AgentError):
            burgle(self.human_user, self.bot)

    def test_an_agent_cannot_post_or_carry_a_bounty(self):
        from database.repositories.bounties import post_bounty

        with self.assertRaises(AgentError):
            post_bounty(self.bot_user, self.human, 5_000)

        with self.assertRaises(AgentError):
            post_bounty(self.human_user, self.bot, 5_000)

    def test_a_human_bounty_on_a_human_still_works(self):
        from database.repositories.bounties import post_bounty

        self.assertIsNotNone(
            post_bounty(self.human_user, self.other, 5_000)
        )

    def test_an_agent_is_not_sprung_from_jail_and_springs_nobody(self):
        from database.repositories.jail import (
            attempt_jail_break,
            bail_out_inmate,
        )

        self.jail(self.bot)
        with self.assertRaises(AgentError):
            bail_out_inmate(self.human_user, self.bot)
        with self.assertRaises(AgentError):
            attempt_jail_break(self.human_user, self.bot)

        self.jail(self.human)
        with self.assertRaises(AgentError):
            bail_out_inmate(self.bot_user, self.human)

    def test_an_agent_cannot_list_or_buy_on_the_market(self):
        from database.repositories.market import MarketError, create_listing

        with self.assertRaises((AgentError, MarketError)):
            create_listing(self.bot_user, "first_aid_kit", 1, 200)

    def test_the_money_never_moved_while_being_refused(self):
        """A wall that refuses after taking the money is not a wall."""
        from database.repositories.bounties import post_bounty

        before = self.money(self.bot)

        with self.assertRaises(AgentError):
            post_bounty(self.bot_user, self.human, 5_000)

        self.assertEqual(self.money(self.bot), before)

    def money(self, player_id):
        connection = sqlite3.connect(self.database_path)
        row = connection.execute(
            "SELECT money FROM players WHERE id = ?", (player_id,)
        ).fetchone()
        connection.close()
        return row[0]

    # ------------------------------------------------------- the keys

    def test_a_key_authenticates_its_own_account_and_no_other(self):
        from database.repositories.agents import authenticate

        account = authenticate(self.key)

        self.assertIsNotNone(account)
        self.assertEqual(account.user_id, self.bot_user)
        self.assertEqual(account.label, "Test agent")

    def test_a_key_that_was_never_issued_authenticates_nobody(self):
        from database.repositories.agents import authenticate

        self.assertIsNone(authenticate(generate_key()))
        self.assertIsNone(authenticate("nonsense"))
        self.assertIsNone(authenticate(None))

    def test_the_raw_key_is_never_stored(self):
        """Only the hash. A lost key is reissued, never recovered."""
        connection = sqlite3.connect(self.database_path)
        stored = connection.execute(
            "SELECT key_hash FROM agent_keys"
        ).fetchall()
        connection.close()

        self.assertTrue(stored)
        for (value,) in stored:
            self.assertNotIn(self.key, value)
            self.assertNotIn(KEY_PREFIX, value)

    def test_reissuing_replaces_rather_than_adds(self):
        from database.repositories.agents import authenticate, issue_key

        replacement = issue_key(self.bot_user, "Second try")

        self.assertIsNone(authenticate(self.key))
        self.assertIsNotNone(authenticate(replacement))

    def test_revoking_stops_the_key_and_the_sealing(self):
        from database.repositories.agents import (
            authenticate,
            is_agent,
            revoke_key,
        )

        self.assertTrue(is_agent(self.bot))
        self.assertTrue(revoke_key(self.bot_user))

        self.assertIsNone(authenticate(self.key))
        self.assertFalse(is_agent(self.bot))

    def test_an_account_with_no_character_cannot_be_an_agent(self):
        from database.repositories.agents import issue_key
        from database.repositories.users import create_user

        stranger = create_user("ghost", "ghost@example.com", "hash")

        with self.assertRaises(AgentError):
            issue_key(stranger, "Nobody")

    def test_an_agent_needs_a_name(self):
        from database.repositories.agents import issue_key

        for label in ("", "   ", None, "x" * 61):
            with self.subTest(label=label):
                with self.assertRaises(AgentError):
                    issue_key(self.human_user, label)

    def test_calls_are_counted(self):
        from database.repositories.agents import authenticate

        self.assertEqual(authenticate(self.key).calls, 1)
        self.assertEqual(authenticate(self.key).calls, 2)


class AgentApiTests(unittest.TestCase):
    """The surface an actual machine drives."""

    def setUp(self):
        from web.application import app

        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "api.db"
        self.database_patch = patch(
            "database.core.connection.DB_PATH", self.database_path
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        from database.repositories.agents import issue_key
        from database.repositories.players import create_player
        from database.repositories.users import create_user

        self.user = create_user("botty", "botty@example.com", "hash")
        create_player(self.user, "botty")
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                "UPDATE players SET money = 5000, nerve = 20, "
                "energy = 100, current_district = 'camden'"
            )
        connection.close()
        self.key = issue_key(self.user, "Test agent")

        app.config.update(TESTING=True, SECRET_KEY="test-secret")
        limiter = app.config.get("AGENT_RATE_LIMITER")
        if limiter is not None:
            limiter.clear()
        self.client = app.test_client()
        self.headers = {"Authorization": f"Bearer {self.key}"}

    def get(self, path, **kwargs):
        return self.client.get(
            path, headers=self.headers, **kwargs
        ).get_json()

    def post(self, path, body):
        return self.client.post(
            path, json=body, headers=self.headers
        ).get_json()

    def test_the_manual_needs_no_key(self):
        """An agent should be able to read it before it has one."""
        body = self.client.get("/api/v1").get_json()

        self.assertTrue(body["ok"])
        self.assertTrue(body["endpoints"])
        self.assertIn("sealed", body["rules_for_agents"])

    def test_every_documented_endpoint_exists(self):
        from web.application import app

        routes = {rule.rule for rule in app.url_map.iter_rules()}

        for entry in self.client.get("/api/v1").get_json()["endpoints"]:
            with self.subTest(path=entry["path"]):
                self.assertIn(entry["path"], routes)

    def test_a_missing_or_wrong_key_is_refused_in_json(self):
        without = self.client.get("/api/v1/me").get_json()
        wrong = self.client.get(
            "/api/v1/me",
            headers={"Authorization": "Bearer " + generate_key()},
        ).get_json()

        self.assertEqual(without["error"], "no_key")
        self.assertEqual(wrong["error"], "bad_key")

    def test_the_alternative_header_works_too(self):
        body = self.client.get(
            "/api/v1/me", headers={"X-Agent-Key": self.key}
        ).get_json()

        self.assertTrue(body["ok"])

    def test_me_reports_the_player_and_says_it_is_an_agent(self):
        body = self.get("/api/v1/me")

        self.assertEqual(body["player"]["name"], "botty")
        self.assertTrue(body["player"]["is_agent"])
        self.assertIsNone(body["blocked"])

    def test_actions_does_the_arithmetic_for_the_agent(self):
        body = self.get("/api/v1/actions")

        self.assertTrue(body["crimes"])
        for crime in body["crimes"]:
            self.assertIn("expected_per_nerve", crime)
            self.assertIn("affordable", crime)

    def test_a_crime_pays_what_it_says_it_paid(self):
        """The first version reported £0 on every success.

        `getattr(result, "reward", 0)` hid a renamed field behind a
        plausible zero, and the endpoint looked entirely healthy doing
        it. The money is checked against the database now.
        """
        crime = next(
            c for c in self.get("/api/v1/actions")["crimes"]
            if c["affordable"]
        )

        for _ in range(12):
            self.reset()
            body = self.post("/api/v1/crime", {"crime": crime["key"]})
            if body.get("success"):
                self.assertGreater(body["payout"], 0)
                self.assertEqual(body["payout"], self.money() - 5_000)
                return

        self.fail("twelve attempts and never once succeeded")

    def reset(self):
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                "UPDATE players SET money = 5000, nerve = 20, "
                "jail_until = NULL, hospital_until = NULL"
            )
        connection.close()

    def money(self):
        connection = sqlite3.connect(self.database_path)
        row = connection.execute(
            "SELECT money FROM players WHERE user_id = ?", (self.user,)
        ).fetchone()
        connection.close()
        return row[0]

    def test_training_spends_and_gains(self):
        body = self.post(
            "/api/v1/train",
            {"stat": "strength", "gym": "camden_community"},
        )

        self.assertTrue(body["ok"], body)
        self.assertGreater(body["gained"], 0)
        self.assertGreater(body["energy_spent"], 0)

    def test_travel_starts_and_then_blocks_everything(self):
        body = self.post(
            "/api/v1/travel", {"district": "brixton", "mode": "bus"}
        )

        self.assertTrue(body["ok"], body)

        blocked = self.post("/api/v1/crime", {"crime": "camden_shoplift"})

        self.assertEqual(blocked["error"], "travelling")

    def test_every_refusal_carries_a_code_and_a_sentence(self):
        for path, body, code in (
            ("/api/v1/crime", {"crime": "nope"}, "unknown_crime"),
            ("/api/v1/train", {"stat": "charisma"}, "unknown_stat"),
            ("/api/v1/fight", {"opponent": "nope"}, "unknown_opponent"),
            ("/api/v1/travel", {"district": "atlantis"}, "refused"),
        ):
            with self.subTest(path=path):
                answer = self.post(path, body)

                self.assertFalse(answer["ok"])
                self.assertEqual(answer["error"], code)
                self.assertTrue(answer["message"])

    def test_a_crime_in_another_district_is_refused_not_teleported(self):
        answer = self.post("/api/v1/crime", {"crime": "soho_nightclub"})

        self.assertEqual(answer["error"], "wrong_district")

    def test_the_leaderboard_is_public_and_machines_only(self):
        body = self.client.get("/api/v1/leaderboard").get_json()

        self.assertTrue(body["ok"])
        self.assertEqual(
            [agent["name"] for agent in body["agents"]], ["botty"]
        )

    def test_the_rate_limit_eventually_says_no(self):
        from web.application import app

        limiter = app.config["AGENT_RATE_LIMITER"]
        limiter.clear()

        codes = [
            self.client.get("/api/v1/me", headers=self.headers).status_code
            for _ in range(RATE_LIMIT_PER_MINUTE + 5)
        ]

        self.assertEqual(codes[0], 200)
        self.assertEqual(codes[-1], 429)
        limiter.clear()


class IssuingScriptTests(unittest.TestCase):
    """The script an owner actually types at.

    The first thing it ever did in anger was fail on its own usage
    line: it read `<username>`, which the shell turns into a redirect
    the moment anybody pastes it. It printed a docstring and left the
    operator guessing at names.

    Now every path ends somewhere useful -- the placeholder, a typo, an
    empty command line -- and all three show who actually exists.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "script.db"
        self.database_patch = patch(
            "database.core.connection.DB_PATH", self.database_path
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        from database.repositories.players import create_player
        from database.repositories.users import create_user

        for name in ("paul", "botty"):
            user_id = create_user(name, f"{name}@example.com", "hash")
            create_player(user_id, name)

        self.script = self.load()

    def load(self):
        import importlib.util
        from pathlib import Path as P

        here = P(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location(
            "issue_agent_key", here / "scripts" / "issue_agent_key.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def run_it(self, argv):
        import contextlib
        import io

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = self.script.main(argv)
        return code, out.getvalue()

    def test_no_arguments_lists_the_accounts(self):
        code, output = self.run_it([])

        self.assertEqual(code, 0)
        self.assertIn("paul", output)
        self.assertIn("botty", output)

    def test_the_usage_line_is_pasteable(self):
        """No angle brackets. That is the whole fix.

        `<username>` in a usage line is a shell redirect waiting to
        happen, and it happened.
        """
        commands = [
            line.strip()
            for line in self.script.__doc__.splitlines()
            if line.strip().startswith("python3 scripts/")
        ]

        self.assertTrue(commands)
        for command in commands:
            with self.subTest(command=command):
                # The prose may still explain the old form. A line
                # somebody will paste may not contain it.
                self.assertNotIn("<", command)
                self.assertNotIn(">", command)

    def test_the_placeholder_is_recognised_and_explained(self):
        code, output = self.run_it(["<username>", "Claude"])

        self.assertEqual(code, 2)
        self.assertIn("placeholder", output)
        self.assertIn("paul", output)

    def test_an_unknown_name_suggests_a_real_one(self):
        code, output = self.run_it(["botti"])

        self.assertEqual(code, 1)
        self.assertIn("Did you mean", output)
        self.assertIn("botty", output)

    def test_issuing_prints_the_key_once_and_says_what_it_costs(self):
        code, output = self.run_it(["botty", "Claude, first try"])

        self.assertEqual(code, 0)
        self.assertIn(KEY_PREFIX, output)
        self.assertIn("cannot be recovered", output)
        for sealed in AGENT_SEALED_ACTIONS:
            self.assertIn(sealed, output)

    def test_the_listing_marks_who_is_already_a_machine(self):
        self.run_it(["botty", "Claude, first try"])
        _code, output = self.run_it([])

        self.assertIn("agent", output)
        self.assertIn("Claude, first try", output)

    def test_revoking_puts_the_account_back(self):
        self.run_it(["botty", "Claude, first try"])
        code, output = self.run_it(["--revoke", "botty"])

        self.assertEqual(code, 0)
        self.assertIn("no longer an agent", output)

    def test_revoking_somebody_who_never_was_says_so(self):
        code, output = self.run_it(["--revoke", "paul"])

        self.assertEqual(code, 1)
        self.assertIn("was not an agent", output)


if __name__ == "__main__":
    unittest.main()
