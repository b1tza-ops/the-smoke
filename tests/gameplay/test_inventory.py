from types import SimpleNamespace
import unittest

from game.inventory import (
    INVENTORY_SLOT_CAPACITY,
    InsufficientItemError,
    InvalidQuantityError,
    InventoryFullError,
    ItemLimitError,
    ItemNotUsableError,
    ResourceAlreadyFullError,
    add_item,
    remove_item,
    use_item,
)


class InventoryTests(unittest.TestCase):
    def make_player(self, **overrides):
        values = {
            "inventory": {},
            "health": 100,
            "energy": 100,
            "max_energy": 100,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_items_can_be_added_and_removed(self):
        player = self.make_player()

        added = add_item(
            player,
            "lockpick",
            quantity=3,
        )
        removed = remove_item(
            player,
            "lockpick",
            quantity=2,
        )

        self.assertEqual(added.quantity_after, 3)
        self.assertEqual(removed.quantity_after, 1)
        self.assertEqual(player.inventory, {"lockpick": 1})

    def test_quantities_must_be_positive_whole_numbers(self):
        player = self.make_player()

        for quantity in (0, -1, True, 1.5):
            with self.subTest(quantity=quantity):
                with self.assertRaises(
                    InvalidQuantityError
                ):
                    add_item(
                        player,
                        "lockpick",
                        quantity,
                    )

    def test_stack_and_non_stack_limits_are_enforced(self):
        player = self.make_player()

        with self.assertRaises(ItemLimitError):
            add_item(
                player,
                "energy_drink",
                quantity=6,
            )

        add_item(player, "kitchen_knife")

        with self.assertRaises(ItemLimitError):
            add_item(player, "kitchen_knife")

    def test_cannot_remove_more_than_owned(self):
        player = self.make_player(
            inventory={"lockpick": 1},
        )

        with self.assertRaises(
            InsufficientItemError
        ):
            remove_item(
                player,
                "lockpick",
                quantity=2,
            )

        self.assertEqual(
            player.inventory,
            {"lockpick": 1},
        )

    def test_first_aid_restores_health_and_is_consumed(self):
        player = self.make_player(
            inventory={"first_aid_kit": 1},
            health=80,
        )

        result = use_item(
            player,
            "first_aid_kit",
        )

        self.assertEqual(result.amount_restored, 20)
        self.assertEqual(player.health, 100)
        self.assertEqual(player.inventory, {})

    def test_energy_drink_respects_maximum_energy(self):
        player = self.make_player(
            inventory={"energy_drink": 2},
            energy=90,
        )

        result = use_item(
            player,
            "energy_drink",
        )

        self.assertEqual(result.amount_restored, 10)
        self.assertEqual(player.energy, 100)
        self.assertEqual(
            player.inventory,
            {"energy_drink": 1},
        )

    def test_full_resource_does_not_consume_item(self):
        player = self.make_player(
            inventory={"first_aid_kit": 1},
        )

        with self.assertRaises(
            ResourceAlreadyFullError
        ):
            use_item(
                player,
                "first_aid_kit",
            )

        self.assertEqual(
            player.inventory,
            {"first_aid_kit": 1},
        )

    def test_weapon_cannot_be_consumed(self):
        player = self.make_player(
            inventory={"kitchen_knife": 1},
        )

        with self.assertRaises(ItemNotUsableError):
            use_item(
                player,
                "kitchen_knife",
            )

    def test_inventory_capacity_counts_item_slots(self):
        inventory = {
            f"placeholder_{number}": 1
            for number in range(
                INVENTORY_SLOT_CAPACITY
            )
        }
        player = self.make_player(
            inventory=inventory,
        )

        with self.assertRaises(InventoryFullError):
            add_item(
                player,
                "lockpick",
            )


if __name__ == "__main__":
    unittest.main()
