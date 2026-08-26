import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from database.core.setup import create_tables
from database.repositories.site_controls import get_operations_settings
from utils.security import hash_password
from web.application import app


BOOTSTRAP_ENV = {
    "THE_SMOKE_ADMIN_USERNAME": "operator",
    "THE_SMOKE_ADMIN_PASSWORD_HASH": hash_password("operator-pass"),
    "THE_SMOKE_MAINTENANCE": "0",
}


class OperationsControlTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            Path(self.temp.name) / "game.db",
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()
        self.client = app.test_client()
        self.environment = patch.dict("os.environ", BOOTSTRAP_ENV)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def sign_in(self):
        return self.client.post(
            "/admin/login",
            data={"username": "operator", "password": "operator-pass"},
        )

    def test_default_settings_keep_game_and_registration_open(self):
        settings = get_operations_settings()

        self.assertFalse(settings.maintenance_active())
        self.assertTrue(settings.registration_open)
        self.assertEqual(self.client.get("/login").status_code, 200)
        self.assertEqual(self.client.get("/register").status_code, 200)

    def test_admin_can_schedule_custom_maintenance(self):
        self.sign_in()
        now = datetime.now(timezone.utc)
        response = self.client.post(
            "/admin/operations",
            data={
                "maintenance_enabled": "1",
                "maintenance_starts_at": (
                    now - timedelta(minutes=5)
                ).strftime("%Y-%m-%dT%H:%M"),
                "maintenance_ends_at": (
                    now + timedelta(hours=1)
                ).strftime("%Y-%m-%dT%H:%M"),
                "maintenance_title": "London is changing",
                "maintenance_message": "New streets are being opened.",
                "registration_open": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        public = self.client.get("/login")
        self.assertEqual(public.status_code, 503)
        self.assertIn(b"London is changing", public.data)
        self.assertIn(b"New streets are being opened", public.data)
        self.assertEqual(self.client.get("/admin").status_code, 200)
        self.assertEqual(self.client.get("/healthz").status_code, 200)

    def test_admin_can_pause_registration_and_publish_notice(self):
        self.sign_in()
        self.client.post(
            "/admin/operations",
            data={
                "maintenance_title": "Maintenance in progress",
                "maintenance_message": "Please check back shortly.",
                "announcement_enabled": "1",
                "announcement_message": "Crime rewards are doubled tonight.",
            },
        )

        settings = get_operations_settings()
        self.assertFalse(settings.registration_open)
        self.assertTrue(settings.announcement_enabled)
        registration = self.client.get("/register")
        self.assertEqual(registration.status_code, 403)
        self.assertIn(b"Registrations temporarily paused", registration.data)

    def test_invalid_maintenance_window_is_rejected(self):
        self.sign_in()
        response = self.client.post(
            "/admin/operations",
            data={
                "maintenance_enabled": "1",
                "maintenance_starts_at": "2026-08-27T12:00",
                "maintenance_ends_at": "2026-08-27T11:00",
                "maintenance_title": "Maintenance",
                "maintenance_message": "Brief interruption.",
                "registration_open": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(get_operations_settings().maintenance_enabled)


if __name__ == "__main__":
    unittest.main()
