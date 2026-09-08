"""A seal must refuse, and refusing is not crashing.

`refuse_if_sealed` was added to seven paths in one go -- attacking,
burgling, posting and claiming bounties, bail, and both sides of the
market -- and it raises `AgentError`, which is not any of the domain
errors those routes were already catching. Every one of them let it
through to the 500 handler.

The result was a live outage that looked nothing like an agent problem:
an owner whose own account had been made an agent pressed Attack on an
ordinary player and got "Something went wrong". So did anybody aiming
at an agent. Nothing in the suite noticed, because every agent test
called the repositories directly, where raising is the correct
behaviour, and no test drove the pages where it had to be caught.

That is the gap these tests close. They are deliberately about status
codes rather than messages: the message is a nicety, whereas a 500 on a
core action is the difference between a game that says no and a game
that looks broken.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.core.connection import get_connection
from database.core.setup import create_tables
from database.repositories.agents import issue_key
from database.repositories.players import create_player, get_player_by_user_id
from database.repositories.users import create_user
from game.player import Player
from web.application import app


class SealedActionPageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            Path(self.temp.name) / "game.db",
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        app.config.update(TESTING=True, SECRET_KEY="test-secret")
        # Without this a raised AgentError is swallowed into a 500 page
        # and the test passes on the strength of the thing it is meant
        # to be catching.
        app.config["PROPAGATE_EXCEPTIONS"] = True
        self.addCleanup(app.config.pop, "PROPAGATE_EXCEPTIONS", None)

        self.agent_user = create_user("bot", "bot@example.com", "hash")
        create_player(self.agent_user, "Bot")
        self.human_user = create_user("human", "human@example.com", "hash")
        create_player(self.human_user, "Human")

        connection = get_connection()
        with connection:
            connection.execute(
                "UPDATE users SET created_at = DATETIME('now', '-30 days')"
            )
            connection.execute(
                """
                UPDATE players
                SET level = 10, money = 900000, health = 200,
                    max_health = 200, energy = 100, nerve = 20,
                    current_district = 'camden'
                """
            )
        connection.close()

        self.agent = Player(*get_player_by_user_id(self.agent_user))
        self.human = Player(*get_player_by_user_id(self.human_user))
        issue_key(self.agent_user, "Sealed for tests")

    def post(self, actor_user_id, path, data):
        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user_id"] = actor_user_id
            return client.post(path, data=data, follow_redirects=True)

    def sealed_actions(self, target):
        """Every page action the seal stands in front of."""
        return (
            ("attack", "/pvp", {"target_id": str(target.id)}),
            (
                "burgle",
                "/pvp",
                {"action": "burgle", "target_id": str(target.id)},
            ),
            (
                "post a bounty",
                "/pvp/bounties",
                {"name": target.name.lower(), "amount": "10000"},
            ),
            (
                "pay bail",
                "/jail",
                {
                    "action": "pay_bail",
                    "target_player_id": str(target.id),
                },
            ),
        )

    def test_an_agent_is_refused_rather_than_crashed(self):
        for label, path, data in self.sealed_actions(self.human):
            with self.subTest(action=label):
                response = self.post(self.agent_user, path, data)
                self.assertLess(
                    response.status_code, 500,
                    f"an agent doing '{label}' brought the page down",
                )

    def test_aiming_at_an_agent_is_refused_rather_than_crashed(self):
        """The other direction, and the one a real player will hit.

        An ordinary player has no idea which accounts are agents, so
        this is the path that turns somebody else's configuration into
        an error page in front of a paying player.
        """
        for label, path, data in self.sealed_actions(self.agent):
            with self.subTest(action=label):
                response = self.post(self.human_user, path, data)
                self.assertLess(
                    response.status_code, 500,
                    f"'{label}' against an agent brought the page down",
                )

    def test_the_refusal_says_why(self):
        response = self.post(
            self.agent_user, "/pvp", {"target_id": str(self.human.id)}
        )
        self.assertIn("agent", response.get_data(as_text=True).lower())

    def test_two_ordinary_players_are_not_affected(self):
        """The seal must not be catching anybody it was not aimed at."""
        second = create_user("other", "other@example.com", "hash")
        create_player(second, "Other")
        connection = get_connection()
        with connection:
            connection.execute(
                "UPDATE users SET created_at = DATETIME('now', '-30 days')"
            )
            connection.execute(
                """
                UPDATE players
                SET level = 10, money = 900000, health = 200,
                    max_health = 200, energy = 100, nerve = 20,
                    current_district = 'camden'
                WHERE user_id = ?
                """,
                (second,),
            )
        connection.close()

        response = self.post(
            self.human_user,
            "/pvp/bounties",
            {"name": "other", "amount": "10000"},
        )
        body = response.get_data(as_text=True)
        self.assertLess(response.status_code, 500)
        self.assertNotIn("Agents play the city", body)


class SealBackstopTests(unittest.TestCase):
    """The floor under the six `except` clauses.

    Widening each route fixes the routes that exist today. The handler
    is what covers the eighth sealed action somebody adds in a year,
    when nobody remembers this file.
    """

    def test_the_application_handles_agent_errors_itself(self):
        from game.agents.service import AgentError

        self.assertIn(
            AgentError,
            app.error_handler_spec[None][None],
            "AgentError has no application-wide handler",
        )


if __name__ == "__main__":
    unittest.main()
