"""Weather forecast integration for the Haute-Sanaga, based on Open-Meteo.

Open-Meteo (https://open-meteo.com) was chosen because it is free, requires
no API key or account, and publishes its forecast model and update
frequency openly — important properties for a tool meant to run reliably
for a small agricultural organization without a paid subscription. The
integration was verified manually against live coordinates for Nanga-Eboko
before being wired into the application (see README, section « Sources »).

Forecasts are cached locally so the application keeps showing the last
known data when Internet access is unavailable; each cached row keeps a
timestamp of when it was actually fetched.
"""

from __future__ import annotations

import urllib.parse
from datetime import date
from typing import Any

from .constants import HAUTE_SANAGA_LOCATIONS
from .database import Database
from .network import fetch_json

FORECAST_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
DEFAULT_FORECAST_DAYS = 7

# World Meteorological Organization weather interpretation codes, as used by
# Open-Meteo. See https://open-meteo.com/en/docs for the authoritative list.
WEATHER_CODE_LABELS: dict[int, str] = {
    0: "Ciel dégagé",
    1: "Généralement dégagé",
    2: "Partiellement nuageux",
    3: "Ciel couvert",
    45: "Brouillard",
    48: "Brouillard givrant",
    51: "Bruine légère",
    53: "Bruine modérée",
    55: "Bruine dense",
    56: "Bruine verglaçante légère",
    57: "Bruine verglaçante dense",
    61: "Pluie légère",
    63: "Pluie modérée",
    65: "Pluie forte",
    66: "Pluie verglaçante légère",
    67: "Pluie verglaçante forte",
    71: "Neige légère",
    73: "Neige modérée",
    75: "Neige forte",
    77: "Grains de neige",
    80: "Averses légères",
    81: "Averses modérées",
    82: "Averses violentes",
    85: "Averses de neige légères",
    86: "Averses de neige fortes",
    95: "Orage",
    96: "Orage avec grêle légère",
    99: "Orage avec grêle forte",
}


def describe_weather_code(code: int | None) -> str:
    """Return a short French description for an Open-Meteo weather code."""

    if code is None:
        return "Inconnu"
    try:
        return WEATHER_CODE_LABELS.get(int(code), f"Code météo {code}")
    except (TypeError, ValueError):
        return "Inconnu"


def _series(daily: dict[str, Any], key: str, index: int) -> float | None:
    values = daily.get(key)
    if not values or index >= len(values):
        return None
    value = values[index]
    return None if value is None else float(value)


class WeatherService:
    """Fetches, caches and reads back weather forecasts for Haute-Sanaga."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()

    @staticmethod
    def list_locations() -> dict[str, dict[str, Any]]:
        return HAUTE_SANAGA_LOCATIONS

    def fetch_and_cache(
        self, location_key: str, *, days: int = DEFAULT_FORECAST_DAYS
    ) -> int:
        """Fetch the forecast for *location_key* and store it locally.

        Returns the number of daily rows retrieved. Raises
        :class:`gic_agri.network.NetworkError` if the request fails, and
        ``ValueError`` if *location_key* is not a known Haute-Sanaga
        location.
        """

        if location_key not in HAUTE_SANAGA_LOCATIONS:
            raise ValueError(f"Localité inconnue : {location_key}")
        location = HAUTE_SANAGA_LOCATIONS[location_key]
        query = urllib.parse.urlencode(
            {
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "daily": ",".join(
                    (
                        "weathercode",
                        "temperature_2m_max",
                        "temperature_2m_min",
                        "precipitation_sum",
                        "precipitation_probability_max",
                        "wind_speed_10m_max",
                    )
                ),
                "forecast_days": days,
                "timezone": "Africa/Douala",
            }
        )
        payload = fetch_json(f"{FORECAST_ENDPOINT}?{query}")
        daily = payload.get("daily", {}) if isinstance(payload, dict) else {}
        dates: list[str] = daily.get("time", [])
        rows = [
            (
                location_key,
                forecast_date,
                _series(daily, "temperature_2m_min", index),
                _series(daily, "temperature_2m_max", index),
                _series(daily, "precipitation_sum", index),
                _series(daily, "precipitation_probability_max", index),
                _series(daily, "weathercode", index),
                _series(daily, "wind_speed_10m_max", index),
            )
            for index, forecast_date in enumerate(dates)
        ]
        with self.database.connection() as connection:
            connection.executemany(
                """
                INSERT INTO weather_forecasts(
                    location_key, forecast_date, temperature_min,
                    temperature_max, precipitation_mm,
                    precipitation_probability, weather_code,
                    wind_speed_max, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(location_key, forecast_date) DO UPDATE SET
                    temperature_min = excluded.temperature_min,
                    temperature_max = excluded.temperature_max,
                    precipitation_mm = excluded.precipitation_mm,
                    precipitation_probability = excluded.precipitation_probability,
                    weather_code = excluded.weather_code,
                    wind_speed_max = excluded.wind_speed_max,
                    fetched_at = CURRENT_TIMESTAMP
                """,
                rows,
            )
        return len(rows)

    def list_cached_forecast(self, location_key: str) -> list[dict[str, Any]]:
        """Return cached forecast rows for *location_key*, oldest first.

        Only rows from yesterday onward are returned so a forecast that
        was never refreshed does not silently show stale past days.
        """

        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT forecast_date, temperature_min, temperature_max,
                       precipitation_mm, precipitation_probability,
                       weather_code, wind_speed_max, fetched_at
                FROM weather_forecasts
                WHERE location_key = ? AND forecast_date >= date('now', '-1 day')
                ORDER BY forecast_date
                """,
                (location_key,),
            ).fetchall()
        return [dict(row) for row in rows]

    def last_updated(self, location_key: str) -> str | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT MAX(fetched_at) AS fetched_at
                FROM weather_forecasts
                WHERE location_key = ?
                """,
                (location_key,),
            ).fetchone()
        return row["fetched_at"] if row and row["fetched_at"] else None

    def refresh_all_locations(self, *, days: int = DEFAULT_FORECAST_DAYS) -> dict[str, int]:
        """Refresh every known Haute-Sanaga location; never raises.

        Returns a mapping of ``location_key`` to the number of rows fetched,
        or ``-1`` for locations that failed (network unavailable, etc.).
        """

        results: dict[str, int] = {}
        for location_key in HAUTE_SANAGA_LOCATIONS:
            try:
                results[location_key] = self.fetch_and_cache(location_key, days=days)
            except Exception:  # noqa: BLE001 - degrade gracefully per location
                results[location_key] = -1
        return results


__all__ = [
    "WeatherService",
    "describe_weather_code",
    "WEATHER_CODE_LABELS",
    "DEFAULT_FORECAST_DAYS",
]
