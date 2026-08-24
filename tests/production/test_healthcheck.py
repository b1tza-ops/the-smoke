import unittest
from unittest.mock import Mock, patch

from web.application import app


class HealthcheckTests(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
        )
        self.client = app.test_client()

    @patch("web.application.get_connection")
    def test_healthcheck_queries_database(
        self,
        get_connection,
    ):
        connection = Mock()
        connection.execute.return_value.fetchone.return_value = (1,)
        get_connection.return_value = connection

        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"status": "ok"},
        )
        connection.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
