from types import SimpleNamespace
import unittest

from game.gym import (
    GYMS,
    GYMS_BY_KEY,
    STAT_SCALE,
    WEIGHT_CLASS_ENERGY,
    calculate_training_gain,
    gain_per_train,
    happiness_cost,
    train,
    training_outcome,
)

MAX_HAPPINESS = 100


class GymWeightClassTests(unittest.TestCase):
    def test_every_gym_has_a_known_weight_class(self):
        for gym in GYMS:
            with self.subTest(gym=gym.key):
                self.assertIn(gym.weight_class, WEIGHT_CLASS_ENERGY)

    def test_energy_cost_matches_the_weight_class(self):
        for gym in GYMS:
            with self.subTest(gym=gym.key):
                self.assertEqual(
                    gym.energy_per_train,
                    WEIGHT_CLASS_ENERGY[gym.weight_class],
                )

    def test_every_trainable_stat_names_an_exercise(self):
        for gym in GYMS:
            for stat in ("strength", "defence", "speed", "dexterity"):
                if not gym.trains(stat):
                    continue

                with self.subTest(gym=gym.key, stat=stat):
                    self.assertIn(stat, gym.exercises)
                    self.assertTrue(gym.exercises[stat])

    def test_soho_mixes_weight_classes(self):
        # The gym page has to cope with more than one energy cost at a
        # time, which is only true because Soho is deliberately mixed.
        soho = {
            gym.energy_per_train
            for gym in GYMS
            if gym.district == "soho"
        }

        self.assertGreater(len(soho), 1)


class TrainingEconomyTests(unittest.TestCase):
    def setUp(self):
        self.camden = GYMS_BY_KEY["camden_community"]
        self.elite = GYMS_BY_KEY["hackney_the_lock"]

    def test_a_batch_equals_the_same_trains_taken_one_at_a_time(self):
        batch = training_outcome(
            self.camden,
            "strength",
            energy=self.camden.energy_per_train * 12,
            stat_value=500,
            happiness=MAX_HAPPINESS,
            max_happiness=MAX_HAPPINESS,
        )

        happiness = MAX_HAPPINESS
        stat_value = 500
        singles = 0.0

        for _ in range(12):
            one = training_outcome(
                self.camden,
                "strength",
                energy=self.camden.energy_per_train,
                stat_value=stat_value,
                happiness=happiness,
                max_happiness=MAX_HAPPINESS,
            )
            singles += one.stat_gain
            happiness -= one.happiness_spent
            stat_value += one.stat_gain

        self.assertEqual(batch.trains, 12)
        self.assertEqual(round(singles, 2), batch.stat_gain)
        self.assertEqual(happiness, MAX_HAPPINESS - batch.happiness_spent)

    def test_happiness_is_spent_in_proportion_to_energy(self):
        """Half the energy spent, rounded up -- as in Torn.

        So weight class decides how big each commitment is, not how
        efficiently the gym burns happiness.
        """
        light = training_outcome(
            self.camden,
            "strength",
            energy=self.camden.energy_per_train * 4,
            happiness=MAX_HAPPINESS,
            max_happiness=MAX_HAPPINESS,
        )
        heavy = training_outcome(
            self.elite,
            "strength",
            energy=self.elite.energy_per_train * 4,
            happiness=MAX_HAPPINESS,
            max_happiness=MAX_HAPPINESS,
        )

        self.assertEqual(light.energy_spent, 20)
        self.assertEqual(heavy.energy_spent, 100)
        self.assertEqual(light.happiness_spent, 4 * happiness_cost(5))
        self.assertEqual(heavy.happiness_spent, 4 * happiness_cost(25))
        self.assertEqual(light.happiness_spent, 12)
        self.assertEqual(heavy.happiness_spent, 52)

    def test_every_weight_class_costs_the_same_happiness_per_bar(self):
        # A full 150-energy bar costs about the same happiness however
        # it is broken up, within the rounding on each train.
        spends = {
            gym.key: training_outcome(
                gym,
                "strength",
                energy=150,
                happiness=1000,
                max_happiness=1000,
            ).happiness_spent
            for gym in GYMS
            if gym.trains("strength")
        }

        self.assertLessEqual(max(spends.values()) - min(spends.values()), 15)
        for key, spent in spends.items():
            with self.subTest(gym=key):
                self.assertGreaterEqual(spent, 75)

    def test_happiness_floors_at_zero_rather_than_going_negative(self):
        outcome = training_outcome(
            self.camden,
            "strength",
            energy=self.camden.energy_per_train * 4,
            happiness=7,
            max_happiness=MAX_HAPPINESS,
        )

        self.assertEqual(outcome.happiness_spent, 7)
        self.assertGreater(outcome.stat_gain, 0)

    def test_the_elite_gym_gains_more_for_the_same_energy(self):
        starting = {"happiness": MAX_HAPPINESS, "max_happiness": MAX_HAPPINESS}

        camden = training_outcome(
            self.camden, "strength", energy=150, **starting
        )
        elite = training_outcome(
            self.elite, "strength", energy=150, **starting
        )

        # Same energy, but the elite gym sustains its happiness and has
        # the better multiplier, so it wins twice over.
        self.assertGreater(elite.stat_gain, camden.stat_gain)


class TrainingSpendsHappinessTests(unittest.TestCase):
    def make_player(self, **overrides):
        values = {
            "level": 30,
            "money": 0,
            "energy": 150,
            "max_energy": 150,
            "happiness": MAX_HAPPINESS,
            "max_happiness": MAX_HAPPINESS,
            "strength": 10,
            "defence": 10,
            "speed": 10,
            "dexterity": 10,
            "current_district": "camden",
            "current_gym_key": "camden_community",
            "unlocked_gyms": {"camden_community"},
            "travel_destination": None,
            "travel_until": None,
            "wanted_level": 0,
            "last_wanted_update": None,
            "jail_until": None,
            "hospital_until": None,
            "last_energy_update": None,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_training_deducts_energy_and_happiness(self):
        player = self.make_player()

        outcome = train(player, "strength", energy=25)

        # 25 energy at Camden is five trains of 5, costing 3 happiness
        # each -- half the energy, rounded up.
        self.assertEqual(outcome.trains, 5)
        self.assertEqual(player.energy, 125)
        self.assertEqual(player.happiness, MAX_HAPPINESS - 15)
        self.assertEqual(
            player.strength,
            round(10 + outcome.stat_gain, 2),
        )

    def test_the_preview_matches_what_training_awards(self):
        player = self.make_player(happiness=30)

        preview = calculate_training_gain(
            "camden_community",
            "strength",
            energy=25,
            player=player,
        )
        outcome = train(player, "strength", energy=25)

        self.assertEqual(preview, outcome.stat_gain)

    def test_training_still_works_with_no_happiness_left(self):
        player = self.make_player(happiness=0)

        outcome = train(player, "strength", energy=25)

        self.assertEqual(player.happiness, 0)
        self.assertGreater(outcome.stat_gain, 0)


class StatScaledGainTests(unittest.TestCase):
    """Gain grows with the stat being trained, as it does in Torn.

    A flat gain is transformative at 10 strength and invisible at
    5,000; scaling keeps training worth the energy at every size.
    """

    def setUp(self):
        self.camden = GYMS_BY_KEY["camden_community"]
        self.elite = GYMS_BY_KEY["hackney_the_lock"]

    def one_train(self, gym, stat_value):
        return training_outcome(
            gym,
            "strength",
            gym.energy_per_train,
            stat_value=stat_value,
        ).stat_gain

    def test_a_beginner_gains_exactly_what_they_used_to(self):
        # The floor is set so the opening experience is unchanged.
        self.assertEqual(self.one_train(self.camden, 10), 1.0)
        # 25 energy at x4.0 -- the top of the roster, in one commitment.
        self.assertEqual(self.one_train(self.elite, 10), 20.1)

    def test_gain_doubles_at_the_scaling_point(self):
        self.assertEqual(
            self.one_train(self.camden, STAT_SCALE),
            self.one_train(self.camden, 0) * 2,
        )
        self.assertEqual(
            self.one_train(self.elite, STAT_SCALE),
            self.one_train(self.elite, 0) * 2,
        )

    def test_gain_keeps_rising_with_the_stat(self):
        gains = [
            self.one_train(self.elite, stat_value)
            for stat_value in (0, 500, 1000, 5000, 10000)
        ]

        self.assertEqual(gains, sorted(gains))
        self.assertEqual(len(set(gains)), len(gains))

    def test_scaling_is_linear_in_the_stat(self):
        base = self.one_train(self.camden, 0)

        for stat_value in (1000, 4000, 9000):
            with self.subTest(stat_value=stat_value):
                self.assertAlmostEqual(
                    self.one_train(self.camden, stat_value),
                    base * (1 + stat_value / STAT_SCALE),
                    places=2,
                )

    def test_the_stat_rises_within_a_long_batch(self):
        """Later trains in a batch are worth more than the first.

        The stat they scale from has grown by then -- which is also
        why a batch is simulated one train at a time.
        """
        singles = self.one_train(self.camden, 5000) * 30
        batch = training_outcome(
            self.camden,
            "strength",
            energy=150,
            stat_value=5000,
        ).stat_gain

        self.assertGreater(batch, singles)

    def test_the_gym_multiplier_still_applies_on_top(self):
        # Against the unrounded rate, since a single train's gain is
        # rounded to two places before it reaches the player.
        for stat_value in (10, 2000, 8000):
            with self.subTest(stat_value=stat_value):
                # Per point of energy, the top gym is worth four times.
                self.assertAlmostEqual(
                    gain_per_train(self.elite, "strength", stat_value)
                    / self.elite.energy_per_train,
                    gain_per_train(self.camden, "strength", stat_value)
                    / self.camden.energy_per_train
                    * 4,
                    places=9,
                )


class HappinessCostTests(unittest.TestCase):
    def test_a_train_costs_half_its_energy_rounded_up(self):
        self.assertEqual(happiness_cost(5), 3)
        self.assertEqual(happiness_cost(10), 5)
        self.assertEqual(happiness_cost(25), 13)

    def test_the_cost_never_exceeds_the_energy(self):
        for energy in range(1, 151):
            with self.subTest(energy=energy):
                cost = happiness_cost(energy)
                self.assertGreaterEqual(cost, energy / 2)
                self.assertLessEqual(cost, energy)


if __name__ == "__main__":
    unittest.main()
