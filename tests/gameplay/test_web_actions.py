import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from web.application import app


class WebGameplayTests(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
        )
        self.presence_patch = patch(
            "web.application.mark_player_online"
        )
        self.presence_patch.start()
        self.addCleanup(self.presence_patch.stop)
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = 7

    def make_player(self):
        return SimpleNamespace(
            current_district="camden",
            current_gym_key="camden_community",
            unlocked_gyms={"camden_community"},
            energy=100,
            max_energy=100,
            nerve=20,
            max_nerve=20,
            money=500,
            level=1,
            travel_destination=None,
            travel_until=None,
            wanted_level=0,
            last_wanted_update=None,
            jail_until=None,
            hospital_until=None,
        )

    @patch(
        "web.application.render_template",
        return_value="gym rendered",
    )
    @patch("web.application.save_player")
    @patch(
        "web.application.get_district_gyms",
        return_value=(),
    )
    @patch(
        "web.application.get_training_block",
        return_value=None,
    )
    @patch(
        "web.application.get_unlocked_gyms",
        return_value={"camden_community"},
    )
    @patch(
        "web.application.train",
        return_value=True,
    )
    @patch(
        "web.application.calculate_training_gain",
        return_value=2,
    )
    @patch("web.application.select_gym")
    @patch("web.application.update_player_status")
    @patch("web.application.update_travel")
    @patch("web.application.Player")
    @patch(
        "web.application.get_player_by_user_id",
        return_value=(1,),
    )
    def test_gym_training_is_saved(
        self,
        get_player_by_user_id,
        player_class,
        update_travel,
        update_player_status,
        select_gym,
        calculate_training_gain,
        train,
        get_unlocked_gyms,
        get_training_block,
        get_district_gyms,
        save_player,
        render_template,
    ):
        player = self.make_player()
        player_class.return_value = player

        response = self.client.post(
            "/gym",
            data={
                "action": "train",
                "gym_key": "camden_community",
                "stat": "strength",
                "trains": "2",
            },
        )

        self.assertEqual(response.status_code, 200)
        train.assert_called_once_with(
            player,
            "strength",
            energy=20,
            gym_key="camden_community",
        )
        save_player.assert_called_once_with(player)



    @patch(
        "web.application.render_template",
        return_value="character rendered",
    )
    @patch(
        "web.application.get_residence",
        return_value=Mock(name="Tent"),
    )
    @patch("web.application.save_player")
    @patch("web.application.update_player_status")
    @patch("web.application.update_travel")
    @patch("web.application.Player")
    @patch(
        "web.application.get_player_by_user_id",
        return_value=(1,),
    )
    def test_character_page_updates_and_saves_player(
        self,
        get_player_by_user_id,
        player_class,
        update_travel,
        update_player_status,
        save_player,
        get_residence,
        render_template,
    ):
        player = self.make_player()
        player.xp = 0
        player.bank_balance = 0
        player.residence_key = "tent"
        player.job_role_key = None
        player.jail_until = None
        player.hospital_until = None
        player_class.return_value = player

        response = self.client.get("/character")

        self.assertEqual(response.status_code, 200)
        save_player.assert_called_once_with(player)


    @patch(
        "web.application.render_template",
        return_value="travel rendered",
    )
    @patch("web.application.get_active_travel")
    @patch("web.application.save_player")
    @patch("web.application.start_travel")
    @patch("web.application.update_player_status")
    @patch("web.application.update_travel")
    @patch("web.application.Player")
    @patch(
        "web.application.get_player_by_user_id",
        return_value=(1,),
    )
    def test_web_travel_departure_is_saved(
        self,
        get_player_by_user_id,
        player_class,
        update_travel,
        update_player_status,
        start_travel,
        save_player,
        get_active_travel,
        render_template,
    ):
        player = self.make_player()
        player_class.return_value = player
        update_travel.return_value = False
        get_active_travel.return_value = Mock(
            destination_key="brixton",
            remaining_seconds=600,
        )
        start_travel.return_value = Mock(
            destination_key="brixton",
            cost=35,
        )

        response = self.client.post(
            "/travel",
            data={"destination_key": "brixton"},
        )

        self.assertEqual(response.status_code, 200)
        start_travel.assert_called_once_with(
            player,
            "brixton",
        )
        save_player.assert_called_once_with(player)


    @patch(
        "web.application.render_template",
        return_value="crimes rendered",
    )
    @patch("web.application.save_player")
    @patch("web.application.commit_crime")
    @patch("web.application.update_player_status")
    @patch("web.application.update_travel")
    @patch("web.application.Player")
    @patch(
        "web.application.get_player_by_user_id",
        return_value=(1,),
    )
    def test_crime_attempt_is_saved(
        self,
        get_player_by_user_id,
        player_class,
        update_travel,
        update_player_status,
        commit_crime,
        save_player,
        render_template,
    ):
        player = self.make_player()
        player_class.return_value = player
        commit_crime.return_value = Mock(
            attempted=True,
            success=True,
        )

        response = self.client.post(
            "/crimes",
            data={"crime_key": "camden_shoplift"},
        )

        self.assertEqual(response.status_code, 200)
        commit_crime.assert_called_once()
        save_player.assert_called_once_with(player)
        self.assertEqual(
            render_template.call_args.kwargs[
                "attempted_crime_key"
            ],
            "camden_shoplift",
        )


if __name__ == "__main__":
    unittest.main()
