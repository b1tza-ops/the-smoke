"""The last two figures on the property page that did nothing.

Housing has advertised five numbers since it shipped. Three of them
were real -- energy recovery, nerve recovery, and the safe. Two were
not: **comfort**, printed on every property and read by nothing, and
the swimming pool's **+2% gym gains**, sold for £8,000 and applied
nowhere. The housing guide said so out loud, in a section headed "What
is not working yet".

Comfort now drives happiness recovery, which is the quiet way a good
address pays for itself: happiness is what the gym spends alongside
energy, so a comfortable home buys more trains rather than bigger ones.
The pool does what the shop says.

These check the arithmetic, and then check it again through a real
database and a real training batch -- because a bonus that exists in a
formula and never reaches the player is the same dead number in a
different place.
"""

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from database.core.setup import create_tables
from game.gym.definitions import GYMS_BY_KEY
from game.gym.formula import training_outcome
from game.housing.service import (
    COMFORT_HAPPINESS_PERCENT,
    FACILITY_COMFORT,
    FACILITY_GYM_GAIN,
    RESIDENCES,
    RESIDENCES_BY_KEY,
    HousingError,
    comfort_for,
    gym_gain_bonus,
    recovery_bonus,
)
from game.player.regeneration import (
    HAPPINESS_POINTS_PER_TICK,
    HAPPINESS_TICK_SECONDS,
    format_timestamp,
)


class ComfortTests(unittest.TestCase):
    def test_a_tent_is_comfortable_enough_to_be_worth_nothing(self):
        """Level with its 0% energy and nerve bonuses.

        The bottom of the ladder is the baseline everything else is
        measured against; if it paid something the ladder would start
        one rung up.
        """
        tent = RESIDENCES_BY_KEY["tent"]

        self.assertEqual(recovery_bonus(tent, (), "happiness"), 0)

    def test_comfort_climbs_with_the_ladder(self):
        for cheaper, dearer in zip(RESIDENCES, RESIDENCES[1:]):
            with self.subTest(rung=dearer.key):
                self.assertGreater(
                    recovery_bonus(dearer, (), "happiness"),
                    recovery_bonus(cheaper, (), "happiness"),
                )

    def test_the_top_of_the_ladder_sits_beside_its_other_bonuses(self):
        """36% happiness against 40% energy and 35% nerve.

        A third meter that ran away from the other two would quietly
        become the only reason to climb.
        """
        penthouse = RESIDENCES_BY_KEY["penthouse"]

        self.assertEqual(
            recovery_bonus(penthouse, (), "happiness"), 36
        )
        self.assertLessEqual(
            recovery_bonus(penthouse, (), "happiness"),
            recovery_bonus(penthouse, (), "energy"),
        )

    def test_the_fittings_add_the_comfort_the_shop_advertises(self):
        flat = RESIDENCES_BY_KEY["council_flat"]
        fitted = comfort_for(flat, ("interior", "open_bar"))

        self.assertEqual(
            fitted,
            flat.comfort
            + FACILITY_COMFORT["interior"]
            + FACILITY_COMFORT["open_bar"],
        )
        self.assertEqual(
            recovery_bonus(flat, ("interior", "open_bar"), "happiness"),
            (fitted - 1) * COMFORT_HAPPINESS_PERCENT,
        )

    def test_a_fitting_that_is_not_about_comfort_changes_nothing(self):
        flat = RESIDENCES_BY_KEY["council_flat"]

        self.assertEqual(
            recovery_bonus(flat, ("hot_tub", "sauna"), "happiness"),
            recovery_bonus(flat, (), "happiness"),
        )

    def test_no_home_at_all_is_not_a_crash(self):
        self.assertEqual(comfort_for(None, ()), 0)
        self.assertEqual(recovery_bonus(None, (), "happiness"), 0)
        self.assertEqual(recovery_bonus(None, None, "happiness"), 0)

    def test_an_unknown_resource_is_still_refused(self):
        with self.assertRaises(HousingError):
            recovery_bonus(RESIDENCES[0], (), "charisma")


class SwimmingPoolTests(unittest.TestCase):
    def test_only_the_pool_moves_training(self):
        self.assertEqual(gym_gain_bonus(("pool",)), 2)
        self.assertEqual(gym_gain_bonus(("hot_tub", "sauna")), 0)
        self.assertEqual(gym_gain_bonus(()), 0)
        self.assertEqual(gym_gain_bonus(None), 0)

    def test_the_pool_adds_exactly_what_the_shop_says(self):
        """Measured where rounding is noise rather than the answer.

        `stat_gain` is rounded to two places, so on a gain of 1.05 a 2%
        bonus is 0.021 and lands on 1.07 -- a ratio of 1.019, not 1.02.
        That is the rounding, not the bonus, so the claim is checked at
        a stat where the gain is large enough for two decimal places to
        be noise.
        """
        gym = GYMS_BY_KEY["camden_community"]
        plain = training_outcome(
            gym, "strength", 5, stat_value=200_000,
            happiness=100, max_happiness=100,
        )
        with_pool = training_outcome(
            gym, "strength", 5, stat_value=200_000,
            happiness=100, max_happiness=100,
            home_bonus_percent=FACILITY_GYM_GAIN["pool"],
        )

        self.assertAlmostEqual(
            with_pool.stat_gain / plain.stat_gain,
            1 + FACILITY_GYM_GAIN["pool"] / 100,
            places=5,
        )

    def test_a_small_gain_never_loses_the_bonus_entirely(self):
        """Rounding may shave it; it may not swallow it.

        A new player training their first strength point should still
        be able to see that the pool did something.
        """
        gym = GYMS_BY_KEY["camden_community"]
        plain = training_outcome(
            gym, "strength", 5, stat_value=0,
            happiness=100, max_happiness=100,
        )
        with_pool = training_outcome(
            gym, "strength", 5, stat_value=0,
            happiness=100, max_happiness=100, home_bonus_percent=2,
        )

        self.assertGreater(with_pool.stat_gain, plain.stat_gain)

    def test_it_is_worth_the_same_share_at_every_gym(self):
        """A flat multiplier, not a flat number.

        Applied to the gym's own figure it would be worth nothing at
        Camden and a fortune at The Lock, which is the opposite of what
        an £8,000 fitting should do.
        """
        for key in ("camden_community", "soho_london_elite",
                    "hackney_the_lock"):
            with self.subTest(gym=key):
                gym = GYMS_BY_KEY[key]
                plain = training_outcome(
                    gym, "strength", gym.energy_per_train,
                    stat_value=200_000,
                    happiness=200, max_happiness=200,
                )
                boosted = training_outcome(
                    gym, "strength", gym.energy_per_train,
                    stat_value=200_000,
                    happiness=200, max_happiness=200,
                    home_bonus_percent=2,
                )

                self.assertAlmostEqual(
                    boosted.stat_gain / plain.stat_gain, 1.02, places=4
                )

    def test_it_never_costs_extra_happiness(self):
        gym = GYMS_BY_KEY["camden_community"]
        plain = training_outcome(
            gym, "strength", 25, stat_value=100,
            happiness=100, max_happiness=100,
        )
        boosted = training_outcome(
            gym, "strength", 25, stat_value=100,
            happiness=100, max_happiness=100, home_bonus_percent=2,
        )

        self.assertEqual(
            boosted.happiness_spent, plain.happiness_spent
        )
        self.assertEqual(boosted.energy_spent, plain.energy_spent)

    def test_a_negative_bonus_cannot_be_used_to_shrink_a_gain(self):
        gym = GYMS_BY_KEY["camden_community"]
        plain = training_outcome(
            gym, "strength", 5, stat_value=100,
            happiness=100, max_happiness=100,
        )
        nonsense = training_outcome(
            gym, "strength", 5, stat_value=100,
            happiness=100, max_happiness=100, home_bonus_percent=-50,
        )

        self.assertEqual(nonsense.stat_gain, plain.stat_gain)


class HappinessThroughTheDatabaseTests(unittest.TestCase):
    """The bonus has to survive the trip through the loader.

    The formula was never the hard part. Happiness was the one meter
    whose regeneration did not consult the player's home at all, so it
    ticked at the same rate in a tent and a penthouse -- which is why
    this is checked through `get_player_by_user_id` rather than against
    `recovery_bonus`.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "home.db"
        self.database_patch = patch(
            "database.core.connection.DB_PATH", self.database_path
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        # `get_player_by_user_id` reads the real clock -- it takes no
        # `now`. A fixed moment here would leave the stored timestamp
        # months in the past and every meter arriving full.
        self.moment = datetime.now(timezone.utc)

    def make(self, name, residence_key, facilities=()):
        from database.repositories.players import create_player
        from database.repositories.users import create_user

        user_id = create_user(name, f"{name}@example.com", "hash")
        create_player(user_id, name)
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                """
                UPDATE players
                SET residence_key = ?, happiness = 0,
                    last_happiness_update = ?
                WHERE user_id = ?
                """,
                (
                    residence_key,
                    format_timestamp(
                        self.moment - timedelta(hours=3)
                    ),
                    user_id,
                ),
            )
            player_id = connection.execute(
                "SELECT id FROM players WHERE user_id = ?", (user_id,)
            ).fetchone()[0]
            for key in facilities:
                connection.execute(
                    "INSERT INTO player_housing_facilities "
                    "(player_id, facility_key) VALUES (?, ?)",
                    (player_id, key),
                )
        connection.close()
        return user_id

    def happiness(self, user_id):
        from database.repositories.players import get_player_by_user_id

        return get_player_by_user_id(user_id)[33]

    def test_a_penthouse_refills_happiness_faster_than_a_tent(self):
        rough = self.make("rough", "tent")
        posh = self.make("posh", "penthouse")

        self.assertGreater(self.happiness(posh), self.happiness(rough))

    def test_a_tent_ticks_at_the_undiscounted_rate(self):
        rough = self.make("rough", "tent")
        expected = (
            3 * 3600 // HAPPINESS_TICK_SECONDS
        ) * HAPPINESS_POINTS_PER_TICK

        self.assertEqual(
            self.happiness(rough),
            min(expected, 100),
        )

    def test_the_comfort_fittings_beat_the_same_address_without_them(self):
        plain = self.make("plain", "council_flat")
        fitted = self.make(
            "fitted", "council_flat", ("interior", "open_bar")
        )

        self.assertGreater(
            self.happiness(fitted), self.happiness(plain)
        )

    def test_a_hot_tub_does_nothing_for_happiness(self):
        """It is the energy fitting, and it must stay that way.

        Every fitting doing everything would make the choice between
        them meaningless.
        """
        plain = self.make("plain", "council_flat")
        tubbed = self.make("tubbed", "council_flat", ("hot_tub",))

        self.assertEqual(
            self.happiness(tubbed), self.happiness(plain)
        )


class GymPageTests(unittest.TestCase):
    """The pool has to reach the training itself, not just the preview.

    A bonus shown on the page and not applied when the button is
    pressed is worse than no bonus: the player can see they were
    short-changed.
    """

    def setUp(self):
        from web.application import app

        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "gym.db"
        self.database_patch = patch(
            "database.core.connection.DB_PATH", self.database_path
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        presence = patch("web.application.mark_player_online")
        presence.start()
        self.addCleanup(presence.stop)

        from database.repositories.players import create_player
        from database.repositories.users import create_user

        self.user = create_user("lifter", "lifter@example.com", "hash")
        create_player(self.user, "lifter")
        self.set(
            money=500_000, level=20, residence_key="penthouse",
            current_district="camden", energy=100, happiness=100,
            strength=100,
        )

        app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = self.user

    def set(self, **columns):
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                "UPDATE players SET "
                + ", ".join(f"{key} = ?" for key in columns)
                + " WHERE user_id = ?",
                (*columns.values(), self.user),
            )
        connection.close()

    def strength(self):
        connection = sqlite3.connect(self.database_path)
        row = connection.execute(
            "SELECT strength FROM players WHERE user_id = ?",
            (self.user,),
        ).fetchone()
        connection.close()
        return row[0]

    def train_once(self):
        before = self.strength()
        self.client.post(
            "/gym",
            data={
                "action": "train",
                "gym_key": "camden_community",
                "stat": "strength",
                "trains": "1",
            },
        )
        return self.strength() - before

    def test_the_pool_is_worth_more_at_the_weights(self):
        without = self.train_once()

        self.set(energy=100, happiness=100, strength=100)
        self.client.post(
            "/housing/manage", data={"facility_key": "pool"}
        )
        self.set(energy=100, happiness=100, strength=100)
        with_pool = self.train_once()

        self.assertGreater(with_pool, without)
        self.assertAlmostEqual(with_pool / without, 1.02, places=2)


if __name__ == "__main__":
    unittest.main()
