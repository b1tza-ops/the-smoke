"""Money on somebody's head.

The reason this exists is that The Smoke had a great deal of content and
almost no reason to care that other players existed. A bounty is the
cheapest fix: it works asynchronously, so two people who are never
online together can still matter to each other.

Most of what follows is about the money, because a bounty is escrowed
cash sitting in a table waiting to move. There are exactly three ways
out of that table -- collected, lapsed, or never -- and every test here
is checking that the fourth way, whatever it would have been, does not
exist.
"""

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from database.core.setup import create_tables
from game.combat.bounties import (
    BOUNTY_LIFETIME_DAYS,
    BOUNTY_MAXIMUM,
    BOUNTY_MINIMUM,
    MAXIMUM_OPEN_BOUNTIES,
    BountyError,
    collectable,
    posting_fee,
    seconds_left,
    total_cost,
    validate_stake,
)
from game.player.regeneration import format_timestamp


class BountyArithmeticTests(unittest.TestCase):
    def test_the_fixer_rounds_in_his_own_favour(self):
        # £501 at 10% is £50.10. The house does not eat the tenpence.
        self.assertEqual(posting_fee(501), 51)

    def test_the_cut_is_paid_on_top_of_the_stake(self):
        self.assertEqual(total_cost(10_000), 11_000)

    def test_the_stake_is_what_is_collected_not_the_cost(self):
        """The fee is a sink, not part of the prize.

        If the hunter collected the fee too, the board would put money
        into the economy rather than taking it out.
        """
        self.assertLess(10_000, total_cost(10_000))

    def test_a_bounty_too_small_to_bother_with_is_refused(self):
        with self.assertRaises(BountyError):
            validate_stake(BOUNTY_MINIMUM - 1)

    def test_one_bounty_cannot_carry_a_fortune(self):
        with self.assertRaises(BountyError):
            validate_stake(BOUNTY_MAXIMUM + 1)

    def test_pennies_and_booleans_are_not_money(self):
        for nonsense in (1_000.5, True, "1000", None):
            with self.assertRaises(BountyError):
                validate_stake(nonsense)

    def test_a_lapsed_bounty_never_reports_negative_time(self):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        self.assertEqual(seconds_left(now - timedelta(days=3), now), 0)

    def test_time_left_counts_down_to_the_expiry(self):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        self.assertEqual(
            seconds_left(now + timedelta(hours=2), now), 7_200
        )

    def test_you_cannot_collect_your_own_money(self):
        bounties = [
            {"id": 1, "poster_id": 7, "amount": 1_000},
            {"id": 2, "poster_id": 9, "amount": 2_000},
        ]

        payable, skipped = collectable(bounties, claimer_id=7)

        self.assertEqual(
            [entry["id"] for entry in payable], [2]
        )
        self.assertEqual([entry["id"] for entry in skipped], [1])

    def test_your_own_bounty_does_not_block_everybody_elses(self):
        """Skipping rather than refusing, on purpose.

        Refusing the whole payout would make a £500 bounty of your own a
        way to make everybody else's uncollectable by you -- a grief
        tactic dressed as a rule.
        """
        bounties = [{"id": 1, "poster_id": 7, "amount": 50_000}]
        payable, _ = collectable(bounties, claimer_id=9)

        self.assertEqual(
            [entry["id"] for entry in payable], [1]
        )


class BountyBoardTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "bounty.db"
        self.database_patch = patch(
            "database.core.connection.DB_PATH", self.database_path
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        self.now = datetime.now(timezone.utc)
        self.poster_user, self.poster = self.make("poster", money=100_000)
        self.target_user, self.target = self.make("target", money=5_000)
        self.hunter_user, self.hunter = self.make("hunter", money=0)

    # ------------------------------------------------------- fixtures

    def make(self, name, established=True, **columns):
        from database.repositories.players import create_player
        from database.repositories.users import create_user

        user_id = create_user(name, f"{name}@example.com", "hash")
        create_player(user_id, name)
        connection = sqlite3.connect(self.database_path)
        with connection:
            if columns:
                connection.execute(
                    "UPDATE players SET "
                    + ", ".join(f"{key} = ?" for key in columns)
                    + ", current_district = 'camden' WHERE user_id = ?",
                    (*columns.values(), user_id),
                )
            if established:
                connection.execute(
                    "UPDATE users SET created_at = '2026-01-01' "
                    "WHERE id = ?",
                    (user_id,),
                )
        player_id = connection.execute(
            "SELECT id FROM players WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        connection.close()
        return user_id, player_id

    def money(self, player_id):
        connection = sqlite3.connect(self.database_path)
        row = connection.execute(
            "SELECT money FROM players WHERE id = ?", (player_id,)
        ).fetchone()
        connection.close()
        return row[0]

    def statuses(self):
        connection = sqlite3.connect(self.database_path)
        rows = connection.execute(
            "SELECT status FROM player_bounties ORDER BY id"
        ).fetchall()
        connection.close()
        return [row[0] for row in rows]

    def notices(self, player_id):
        connection = sqlite3.connect(self.database_path)
        rows = connection.execute(
            "SELECT message FROM pvp_notifications WHERE player_id = ?",
            (player_id,),
        ).fetchall()
        connection.close()
        return [row[0] for row in rows]

    def post(self, amount=10_000, user_id=None, target=None, now=None):
        from database.repositories.bounties import post_bounty

        return post_bounty(
            user_id if user_id is not None else self.poster_user,
            target if target is not None else self.target,
            amount,
            now=now,
        )

    def won_fight(self, attacker, defender, multiplier=1.0, now=None):
        """A victory sitting in the log, waiting to be settled."""
        moment = now or self.now
        connection = sqlite3.connect(self.database_path)
        with connection:
            cursor = connection.execute(
                """
                INSERT INTO player_pvp_attacks (
                    attacker_id, defender_id, approach, outcome,
                    reward_multiplier, created_at
                ) VALUES (?, ?, 'defensive', 'victory', ?, ?)
                """,
                (attacker, defender, multiplier, format_timestamp(moment)),
            )
            attack_id = cursor.lastrowid
        connection.close()
        return attack_id

    # -------------------------------------------------------- posting

    def test_the_stake_and_the_cut_both_leave_the_wallet(self):
        self.post(10_000)

        self.assertEqual(self.money(self.poster), 100_000 - 11_000)

    def test_the_board_shows_what_was_put_up_not_what_it_cost(self):
        from database.repositories.bounties import get_board

        self.post(10_000)
        board = get_board(self.poster)

        self.assertEqual(len(board), 1)
        self.assertEqual(board[0]["total"], 10_000)
        self.assertEqual(board[0]["name"], "target")
        self.assertTrue(board[0]["yours"])

    def test_a_bounty_you_cannot_afford_moves_nothing(self):
        """Enough for the stake is not enough. The cut is real money."""
        broke_user, broke = self.make("broke", money=10_500)

        with self.assertRaises(BountyError):
            self.post(10_000, user_id=broke_user)

        self.assertEqual(self.money(broke), 10_500)
        self.assertEqual(self.statuses(), [])

    def test_somebody_with_no_character_cannot_post(self):
        from database.repositories.users import create_user

        stranger = create_user("stranger", "stranger@example.com", "hash")

        with self.assertRaises(BountyError):
            self.post(10_000, user_id=stranger)

    def test_you_cannot_price_your_own_head(self):
        with self.assertRaises(BountyError):
            self.post(10_000, target=self.poster)

        self.assertEqual(self.money(self.poster), 100_000)

    def test_a_new_player_cannot_be_named(self):
        """The same 72 hours that protect them from fights and burglars.

        A price on a head is worse than either: it is an open invitation
        to everybody at once.
        """
        _, fresh = self.make("fresh", established=False, money=0)

        with self.assertRaises(BountyError):
            self.post(10_000, target=fresh)

    def test_a_name_nobody_answers_to_finds_nobody(self):
        from database.repositories.bounties import find_target

        self.assertIsNone(find_target("nobody at all"))
        self.assertIsNone(find_target(""))
        self.assertIsNone(find_target("   "))

    def test_a_name_is_matched_however_it_is_typed(self):
        from database.repositories.bounties import find_target

        self.assertEqual(find_target("TARGET"), self.target)
        self.assertEqual(find_target("  target  "), self.target)

    def test_nobody_may_paper_the_whole_board(self):
        targets = [
            self.make(f"mark{index}")[1]
            for index in range(MAXIMUM_OPEN_BOUNTIES + 1)
        ]

        for target in targets[:MAXIMUM_OPEN_BOUNTIES]:
            self.post(BOUNTY_MINIMUM, target=target)

        with self.assertRaises(BountyError):
            self.post(BOUNTY_MINIMUM, target=targets[-1])

        self.assertEqual(len(self.statuses()), MAXIMUM_OPEN_BOUNTIES)

    def test_the_target_is_told_there_is_a_price_on_them(self):
        self.post(10_000)

        self.assertTrue(any(
            "10,000" in message and "poster" in message
            for message in self.notices(self.target)
        ))

    # ------------------------------------------------------- lapsing

    def test_an_uncollected_bounty_returns_the_stake_but_not_the_cut(self):
        from database.repositories.bounties import sweep

        self.post(10_000, now=self.now)
        later = self.now + timedelta(days=BOUNTY_LIFETIME_DAYS, seconds=1)

        sweep(now=later)

        self.assertEqual(self.money(self.poster), 100_000 - 1_000)
        self.assertEqual(self.statuses(), ["expired"])

    def test_a_stake_is_only_ever_handed_back_once(self):
        """The obvious way to mint money: refund a lapsed bounty twice.

        The sweep runs on every page view, so this is not a
        hypothetical -- it is what happens the second time anybody
        opens the board.
        """
        from database.repositories.bounties import sweep

        self.post(10_000, now=self.now)
        later = self.now + timedelta(days=BOUNTY_LIFETIME_DAYS, seconds=1)

        for _ in range(4):
            sweep(now=later)

        self.assertEqual(self.money(self.poster), 100_000 - 1_000)

    def test_a_lapsed_bounty_is_off_the_board_before_it_is_settled(self):
        """Reading is not what refunds it, so reading must not need to.

        The board would otherwise advertise a head that nobody can
        collect on, for as long as it took somebody to open the page.
        """
        from database.repositories.bounties import (
            bounty_on,
            get_board,
        )

        self.post(10_000, now=self.now)
        later = self.now + timedelta(days=BOUNTY_LIFETIME_DAYS, seconds=1)

        self.assertEqual(get_board(self.poster, now=later), [])
        self.assertEqual(bounty_on(self.target, now=later), 0)
        self.assertEqual(self.statuses(), ["open"])

    def test_a_lapsed_bounty_pays_nobody(self):
        from database.repositories.pvp import settle_aftermath

        self.post(10_000, now=self.now)
        later = self.now + timedelta(days=BOUNTY_LIFETIME_DAYS, seconds=1)
        attack = self.won_fight(self.hunter, self.target, now=later)

        settle_aftermath(
            attack, self.hunter, "hospitalise", now=later
        )

        self.assertEqual(self.money(self.hunter), 0)
        self.assertEqual(self.statuses(), ["expired"])

    def test_a_bounty_still_in_date_is_left_alone_by_the_sweep(self):
        from database.repositories.bounties import sweep

        self.post(10_000, now=self.now)
        sweep(now=self.now + timedelta(days=6))

        self.assertEqual(self.statuses(), ["open"])
        self.assertEqual(self.money(self.poster), 100_000 - 11_000)

    # ------------------------------------------------------ collecting

    def test_a_hospital_bed_collects_the_money(self):
        from database.repositories.pvp import settle_aftermath

        self.post(10_000)
        attack = self.won_fight(self.hunter, self.target)

        aftermath = settle_aftermath(
            attack, self.hunter, "hospitalise", now=self.now
        )

        self.assertEqual(aftermath.bounty_collected, 10_000)
        self.assertEqual(aftermath.bounty_count, 1)
        self.assertEqual(self.money(self.hunter), 10_000)
        self.assertEqual(self.statuses(), ["claimed"])

    def test_going_through_their_pockets_leaves_the_price_standing(self):
        """Mug or hospitalise, and now the choice actually costs you.

        Before bounties, mugging strictly dominated: it paid and the
        other two did not. This is the test that the new answer is a
        real fork rather than a second way to get the same money.
        """
        from database.repositories.pvp import settle_aftermath

        self.post(10_000)
        attack = self.won_fight(self.hunter, self.target)

        aftermath = settle_aftermath(
            attack, self.hunter, "mug", now=self.now
        )

        self.assertEqual(aftermath.bounty_collected, 0)
        self.assertEqual(self.statuses(), ["open"])
        self.assertLess(self.money(self.hunter), 10_000)

    def test_walking_away_collects_nothing(self):
        from database.repositories.pvp import settle_aftermath

        self.post(10_000)
        attack = self.won_fight(self.hunter, self.target)

        settle_aftermath(attack, self.hunter, "leave", now=self.now)

        self.assertEqual(self.money(self.hunter), 0)
        self.assertEqual(self.statuses(), ["open"])

    def test_every_price_on_one_head_is_collected_at_once(self):
        from database.repositories.pvp import settle_aftermath

        other_user, _ = self.make("rival", money=100_000)
        self.post(10_000)
        self.post(2_500, user_id=other_user)
        attack = self.won_fight(self.hunter, self.target)

        aftermath = settle_aftermath(
            attack, self.hunter, "hospitalise", now=self.now
        )

        self.assertEqual(aftermath.bounty_collected, 12_500)
        self.assertEqual(aftermath.bounty_count, 2)
        self.assertEqual(self.statuses(), ["claimed", "claimed"])

    def test_hunting_your_own_target_pays_you_nothing(self):
        """Otherwise a bounty is a laundry: post, collect, repeat.

        The stake would come straight back and the only cost would be
        the fee, which is cheaper than the item market's commission.
        """
        from database.repositories.pvp import settle_aftermath

        self.post(10_000)
        attack = self.won_fight(self.poster, self.target)

        aftermath = settle_aftermath(
            attack, self.poster, "hospitalise", now=self.now
        )

        self.assertEqual(aftermath.bounty_collected, 0)
        self.assertEqual(self.money(self.poster), 100_000 - 11_000)
        self.assertEqual(self.statuses(), ["open"])

    def test_somebody_elses_bounty_is_still_collectable_by_you(self):
        from database.repositories.pvp import settle_aftermath

        rival_user, _ = self.make("rival", money=100_000)
        self.post(10_000)
        self.post(5_000, user_id=rival_user)
        attack = self.won_fight(self.poster, self.target)

        aftermath = settle_aftermath(
            attack, self.poster, "hospitalise", now=self.now
        )

        self.assertEqual(aftermath.bounty_collected, 5_000)
        self.assertEqual(sorted(self.statuses()), ["claimed", "open"])

    def test_the_money_is_only_moved_it_is_never_made(self):
        """Post, collect, and count the whole economy either side.

        The only pound that may go missing is the fixer's cut, which is
        the point of the fee.
        """
        from database.repositories.pvp import settle_aftermath

        before = sum(
            self.money(player)
            for player in (self.poster, self.target, self.hunter)
        )

        self.post(10_000)
        attack = self.won_fight(self.hunter, self.target)
        settle_aftermath(attack, self.hunter, "hospitalise", now=self.now)

        after = sum(
            self.money(player)
            for player in (self.poster, self.target, self.hunter)
        )

        self.assertEqual(before - after, posting_fee(10_000))

    def test_both_sides_are_told_who_collected(self):
        from database.repositories.pvp import settle_aftermath

        self.post(10_000)
        attack = self.won_fight(self.hunter, self.target)
        settle_aftermath(attack, self.hunter, "hospitalise", now=self.now)

        self.assertTrue(any(
            "hunter" in message and "10,000" in message
            for message in self.notices(self.poster)
        ))
        self.assertTrue(any(
            "hunter" in message
            for message in self.notices(self.target)
        ))

    def test_a_settled_fight_cannot_be_settled_again(self):
        """The refresh case, which is how a payout gets taken twice."""
        from database.repositories.pvp import settle_aftermath
        from game.combat.pvp import PvpError

        rival_user, _ = self.make("rival", money=100_000)
        self.post(10_000)
        attack = self.won_fight(self.hunter, self.target)
        settle_aftermath(attack, self.hunter, "hospitalise", now=self.now)

        self.post(7_500, user_id=rival_user)
        with self.assertRaises(PvpError):
            settle_aftermath(
                attack, self.hunter, "hospitalise", now=self.now
            )

        self.assertEqual(self.money(self.hunter), 10_000)

    # -------------------------------------------------------- reading

    def test_the_fight_list_can_see_what_a_head_is_worth(self):
        from database.repositories.bounties import (
            bounty_on,
            open_bounty_totals,
        )

        self.post(10_000)

        self.assertEqual(bounty_on(self.target), 10_000)
        self.assertEqual(bounty_on(self.hunter), 0)
        self.assertEqual(
            open_bounty_totals([self.target, self.hunter]),
            {self.target: {"total": 10_000, "bounties": 1}},
        )

    def test_an_empty_list_of_heads_asks_the_database_nothing(self):
        from database.repositories.bounties import open_bounty_totals

        self.assertEqual(open_bounty_totals([]), {})

    def test_the_board_puts_the_dearest_head_first(self):
        from database.repositories.bounties import get_board

        cheap = self.make("cheap")[1]
        self.post(BOUNTY_MINIMUM, target=cheap)
        self.post(50_000, target=self.target)

        board = get_board(self.poster)

        self.assertEqual(
            [entry["name"] for entry in board], ["target", "cheap"]
        )

    def test_your_own_postings_are_listed_back_to_you(self):
        from database.repositories.bounties import bounties_posted_by

        self.post(10_000)
        mine = bounties_posted_by(self.poster)

        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["amount"], 10_000)
        self.assertEqual(mine[0]["status"], "open")


class BountyPageTests(unittest.TestCase):
    """The board through the actual routes.

    The repository tests above prove the money moves correctly. This
    proves a player can reach it: the page renders, the form posts, and
    every refusal comes back as a sentence rather than a 500.
    """

    def setUp(self):
        from web.application import app

        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "pages.db"
        self.database_patch = patch(
            "database.core.connection.DB_PATH", self.database_path
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        presence = patch("web.application.mark_player_online")
        presence.start()
        self.addCleanup(presence.stop)

        self.hunter = self.register("hunter")
        self.mark = self.register("mark")

        app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = self.hunter

    def register(self, name):
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
                "UPDATE players SET money = 100000, "
                "current_district = 'camden' WHERE user_id = ?",
                (user_id,),
            )
        connection.close()
        return user_id

    def wallet(self, user_id):
        connection = sqlite3.connect(self.database_path)
        row = connection.execute(
            "SELECT money FROM players WHERE user_id = ?", (user_id,)
        ).fetchone()
        connection.close()
        return row[0]

    def put_up(self, name="mark", amount="10000"):
        return self.client.post(
            "/pvp/bounties", data={"name": name, "amount": amount}
        ).data.decode()

    def test_the_board_opens(self):
        response = self.client.get("/pvp/bounties")

        self.assertEqual(response.status_code, 200)

    def test_posting_from_the_form_takes_the_money(self):
        body = self.put_up()

        self.assertIn("is on mark", body)
        self.assertEqual(self.wallet(self.hunter), 100_000 - 11_000)

    def test_a_posted_bounty_shows_on_the_board_and_the_fight_list(self):
        self.put_up()

        self.assertIn("£10,000", self.client.get("/pvp/bounties").data.decode())
        self.assertIn("on their head", self.client.get("/pvp").data.decode())

    def test_every_refusal_is_a_sentence_not_a_crash(self):
        for name, amount, expected in (
            ("nobody at all", "10000", "goes by"),
            ("", "10000", "Name somebody"),
            ("hunter", "10000", "your own head"),
            ("mark", "12", "gets out of bed"),
            ("mark", "999999999", "is the most"),
            ("mark", "not a number", "whole number"),
            ("mark", "", "whole number"),
        ):
            with self.subTest(name=name, amount=amount):
                body = self.put_up(name, amount)

                self.assertIn(expected, body)
                self.assertEqual(self.wallet(self.hunter), 100_000)

    def test_the_fight_list_offers_to_price_a_head(self):
        body = self.client.get("/pvp").data.decode()

        self.assertIn("Put a price on their head", body)

    def test_the_board_needs_a_login(self):
        with self.client.session_transaction() as session:
            session.clear()

        response = self.client.get("/pvp/bounties")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])


if __name__ == "__main__":
    unittest.main()
