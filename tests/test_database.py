from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from gic_agri.database import Database
from gic_agri.services import AgricultureService


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.database = Database(self.root / "source.db")
        self.service = AgricultureService(self.database)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_schema_and_brand_settings_are_initialized(self) -> None:
        health = self.database.healthcheck()

        self.assertEqual(health["schema_version"], 2)
        self.assertIn("parcels", health["tables"])
        self.assertIn("observations", health["tables"])
        self.assertIn("news_items", health["tables"])
        self.assertIn("weather_forecasts", health["tables"])

        with self.database.connection() as connection:
            settings = dict(
                connection.execute("SELECT key, value FROM app_settings").fetchall()
            )

        self.assertEqual(settings["organization_name"], "GIC INNOVATION")
        self.assertEqual(settings["founder_name"], "Famille Blang")
        self.assertEqual(settings["region_name"], "Haute-Sanaga")
        self.assertEqual(settings["schema_version"], "2")

    def test_schema_version_upgrades_on_pre_existing_database(self) -> None:
        with self.database.connection() as connection:
            connection.execute(
                "UPDATE app_settings SET value = '1' WHERE key = 'schema_version'"
            )

        self.database.initialize()

        health = self.database.healthcheck()
        self.assertEqual(health["schema_version"], 2)
        with self.database.connection() as connection:
            stored_version = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'schema_version'"
            ).fetchone()[0]
        self.assertEqual(stored_version, "2")

    def test_backup_contains_committed_data(self) -> None:
        self.service.create_parcel(
            name="Parcelle A",
            village="Mbandjock",
            area_ha=1.25,
        )
        backup_path = self.database.backup_to(self.root / "backup.db")

        with closing(sqlite3.connect(backup_path)) as connection:
            count = connection.execute("SELECT COUNT(*) FROM parcels").fetchone()[0]

        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
