"""SQLite persistence for the offline desktop application."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .constants import FOUNDER_NAME, ORGANIZATION_NAME, REGION_NAME

SCHEMA_VERSION = 2


class Database:
    """Owns the local SQLite database and schema lifecycle."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS parcels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    village TEXT NOT NULL,
                    area_ha REAL NOT NULL CHECK (area_ha > 0),
                    soil_type TEXT NOT NULL DEFAULT '',
                    water_access TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS campaigns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parcel_id INTEGER NOT NULL REFERENCES parcels(id) ON DELETE RESTRICT,
                    name TEXT NOT NULL,
                    crop TEXT NOT NULL,
                    variety TEXT NOT NULL DEFAULT '',
                    area_ha REAL NOT NULL CHECK (area_ha > 0),
                    planting_date TEXT,
                    expected_harvest_date TEXT,
                    status TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_campaigns_parcel
                    ON campaigns(parcel_id);
                CREATE INDEX IF NOT EXISTS idx_campaigns_status
                    ON campaigns(status);

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parcel_id INTEGER REFERENCES parcels(id) ON DELETE SET NULL,
                    campaign_id INTEGER REFERENCES campaigns(id) ON DELETE SET NULL,
                    title TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    due_date TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'À FAIRE',
                    estimated_cost REAL NOT NULL DEFAULT 0 CHECK (estimated_cost >= 0),
                    notes TEXT NOT NULL DEFAULT '',
                    completed_at TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_due_status
                    ON tasks(status, due_date);

                CREATE TABLE IF NOT EXISTS stock_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    category TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    current_quantity REAL NOT NULL DEFAULT 0 CHECK (current_quantity >= 0),
                    minimum_quantity REAL NOT NULL DEFAULT 0 CHECK (minimum_quantity >= 0),
                    unit_cost REAL NOT NULL DEFAULT 0 CHECK (unit_cost >= 0),
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS stock_movements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER NOT NULL REFERENCES stock_items(id) ON DELETE RESTRICT,
                    movement_type TEXT NOT NULL CHECK (movement_type IN ('ENTRÉE', 'SORTIE')),
                    quantity REAL NOT NULL CHECK (quantity > 0),
                    balance_after REAL NOT NULL CHECK (balance_after >= 0),
                    movement_date TEXT NOT NULL,
                    reference TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_stock_movements_item_date
                    ON stock_movements(item_id, movement_date DESC);

                CREATE TABLE IF NOT EXISTS finance_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id INTEGER REFERENCES campaigns(id) ON DELETE SET NULL,
                    kind TEXT NOT NULL CHECK (kind IN ('DÉPENSE', 'RECETTE')),
                    category TEXT NOT NULL,
                    amount REAL NOT NULL CHECK (amount > 0),
                    transaction_date TEXT NOT NULL,
                    description TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_finance_date
                    ON finance_transactions(transaction_date DESC);

                CREATE TABLE IF NOT EXISTS plant_lots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    species TEXT NOT NULL,
                    variety TEXT NOT NULL DEFAULT '',
                    quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
                    minimum_quantity INTEGER NOT NULL DEFAULT 0 CHECK (minimum_quantity >= 0),
                    unit_price REAL NOT NULL DEFAULT 0 CHECK (unit_price >= 0),
                    age_months INTEGER NOT NULL DEFAULT 0 CHECK (age_months >= 0),
                    location TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(species, variety, location)
                );

                CREATE TABLE IF NOT EXISTS plant_movements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lot_id INTEGER NOT NULL REFERENCES plant_lots(id) ON DELETE RESTRICT,
                    movement_type TEXT NOT NULL CHECK (movement_type IN ('ENTRÉE', 'SORTIE')),
                    quantity INTEGER NOT NULL CHECK (quantity > 0),
                    balance_after INTEGER NOT NULL CHECK (balance_after >= 0),
                    movement_date TEXT NOT NULL,
                    reference TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parcel_id INTEGER REFERENCES parcels(id) ON DELETE SET NULL,
                    campaign_id INTEGER REFERENCES campaigns(id) ON DELETE SET NULL,
                    observed_at TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    photo_path TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_observations_date
                    ON observations(observed_at DESC);

                CREATE TABLE IF NOT EXISTS news_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    link TEXT NOT NULL,
                    published_at TEXT,
                    summary TEXT NOT NULL DEFAULT '',
                    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(source_key, link)
                );

                CREATE INDEX IF NOT EXISTS idx_news_items_published
                    ON news_items(published_at DESC);

                CREATE TABLE IF NOT EXISTS weather_forecasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    location_key TEXT NOT NULL,
                    forecast_date TEXT NOT NULL,
                    temperature_min REAL,
                    temperature_max REAL,
                    precipitation_mm REAL,
                    precipitation_probability REAL,
                    weather_code INTEGER,
                    wind_speed_max REAL,
                    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(location_key, forecast_date)
                );

                CREATE INDEX IF NOT EXISTS idx_weather_location_date
                    ON weather_forecasts(location_key, forecast_date);
                """
            )
            settings = {
                "organization_name": ORGANIZATION_NAME,
                "founder_name": FOUNDER_NAME,
                "region_name": REGION_NAME,
            }
            connection.executemany(
                "INSERT OR IGNORE INTO app_settings(key, value) VALUES (?, ?)",
                settings.items(),
            )
            connection.execute(
                """
                INSERT INTO app_settings(key, value) VALUES ('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(SCHEMA_VERSION),),
            )
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def healthcheck(self) -> dict[str, object]:
        self.initialize()
        with self.connection() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = [
                row["name"]
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                    ORDER BY name
                    """
                )
            ]
        return {
            "database": str(self.path),
            "schema_version": version,
            "tables": tables,
        }

    def backup_to(self, destination: str | Path) -> Path:
        self.initialize()
        target = Path(destination).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        source_connection = sqlite3.connect(self.path)
        target_connection = sqlite3.connect(target)
        try:
            source_connection.backup(target_connection)
        finally:
            target_connection.close()
            source_connection.close()
        return target

