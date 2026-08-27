from dataclasses import dataclass
from datetime import datetime, timezone

from database.core.connection import get_connection


DEFAULT_TITLE = "Maintenance in progress"
DEFAULT_MESSAGE = (
    "We are making The Smoke safer and more reliable. "
    "Please check back shortly."
)


@dataclass(frozen=True)
class OperationsSettings:
    maintenance_enabled: bool
    maintenance_starts_at: str | None
    maintenance_ends_at: str | None
    maintenance_title: str
    maintenance_message: str
    registration_open: bool
    announcement_enabled: bool
    announcement_message: str
    updated_at: str

    def maintenance_active(self, now=None):
        if not self.maintenance_enabled:
            return False
        now = now or datetime.now(timezone.utc)
        starts = _parse_utc(self.maintenance_starts_at)
        ends = _parse_utc(self.maintenance_ends_at)
        return bool(starts and ends and starts <= now < ends)


def _parse_utc(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def get_operations_settings():
    connection = get_connection()
    try:
        row = connection.execute(
            """
            SELECT maintenance_enabled, maintenance_starts_at,
                   maintenance_ends_at, maintenance_title,
                   maintenance_message, registration_open,
                   announcement_enabled, announcement_message,
                   updated_at
            FROM operations_settings WHERE id = 1
            """
        ).fetchone()
        if row is None:
            raise RuntimeError("Operations settings row is missing.")
        return OperationsSettings(
            bool(row[0]), row[1], row[2], row[3], row[4],
            bool(row[5]), bool(row[6]), row[7], row[8],
        )
    finally:
        connection.close()


def update_operations_settings(
    *, maintenance_enabled, maintenance_starts_at,
    maintenance_ends_at, maintenance_title, maintenance_message,
    registration_open, announcement_enabled, announcement_message,
):
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            UPDATE operations_settings
            SET maintenance_enabled = ?, maintenance_starts_at = ?,
                maintenance_ends_at = ?, maintenance_title = ?,
                maintenance_message = ?, registration_open = ?,
                announcement_enabled = ?, announcement_message = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
            (
                int(maintenance_enabled), maintenance_starts_at,
                maintenance_ends_at, maintenance_title,
                maintenance_message, int(registration_open),
                int(announcement_enabled), announcement_message,
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
