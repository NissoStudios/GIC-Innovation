from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from gic_agri.constants import HAUTE_SANAGA_LOCATIONS
from gic_agri.database import Database
from gic_agri.network import NetworkError
from gic_agri.weather import WeatherService, describe_weather_code

def _build_sample_payload(start: date) -> dict:
    """Build an Open-Meteo-like payload starting from *start*, not a fixed
    calendar date, so the test stays valid regardless of when it runs."""

    dates = [(start + timedelta(days=offset)).isoformat() for offset in range(3)]
    return {
        "daily": {
            "time": dates,
            "weathercode": [80, 61, 0],
            "temperature_2m_max": [27.0, 26.0, 29.0],
            "temperature_2m_min": [21.0, 21.0, 20.0],
            "precipitation_sum": [15.0, 5.0, 0.0],
            "precipitation_probability_max": [80, 40, 10],
            "wind_speed_10m_max": [12.0, 10.0, 8.0],
        }
    }


class WeatherCodeLabelTests(unittest.TestCase):
    def test_known_code_returns_french_label(self) -> None:
        self.assertEqual(describe_weather_code(95), "Orage")

    def test_unknown_code_returns_generic_label(self) -> None:
        self.assertEqual(describe_weather_code(12345), "Code météo 12345")

    def test_none_returns_unknown(self) -> None:
        self.assertEqual(describe_weather_code(None), "Inconnu")


class WeatherServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temporary_directory.name) / "weather.db")
        self.service = WeatherService(self.database)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_fetch_and_cache_stores_every_daily_row(self) -> None:
        payload = _build_sample_payload(date.today())
        with patch("gic_agri.weather.fetch_json", return_value=payload):
            fetched = self.service.fetch_and_cache("nanga_eboko", days=3)

        self.assertEqual(fetched, 3)
        cached = self.service.list_cached_forecast("nanga_eboko")
        self.assertEqual(len(cached), 3)
        self.assertEqual(cached[0]["forecast_date"], date.today().isoformat())
        self.assertEqual(cached[0]["weather_code"], 80)
        self.assertAlmostEqual(cached[0]["precipitation_mm"], 15.0)
        self.assertIsNotNone(self.service.last_updated("nanga_eboko"))

    def test_fetch_and_cache_rejects_unknown_location(self) -> None:
        with self.assertRaises(ValueError):
            self.service.fetch_and_cache("localite_inexistante")

    def test_refresh_all_locations_degrades_gracefully_offline(self) -> None:
        with patch(
            "gic_agri.weather.fetch_json",
            side_effect=NetworkError("connexion indisponible"),
        ):
            results = self.service.refresh_all_locations()

        self.assertEqual(set(results.keys()), set(HAUTE_SANAGA_LOCATIONS.keys()))
        self.assertTrue(all(value == -1 for value in results.values()))

    def test_list_cached_forecast_excludes_stale_rows(self) -> None:
        stale_date = (date.today() - timedelta(days=10)).isoformat()
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO weather_forecasts(
                    location_key, forecast_date, temperature_min,
                    temperature_max, precipitation_mm,
                    precipitation_probability, weather_code, wind_speed_max
                ) VALUES ('nanga_eboko', ?, 20, 28, 0, 5, 0, 6)
                """,
                (stale_date,),
            )

        fresh_payload = {
            "daily": {
                "time": [date.today().isoformat()],
                "weathercode": [3],
                "temperature_2m_max": [28.0],
                "temperature_2m_min": [21.0],
                "precipitation_sum": [2.0],
                "precipitation_probability_max": [20],
                "wind_speed_10m_max": [9.0],
            }
        }
        with patch("gic_agri.weather.fetch_json", return_value=fresh_payload):
            self.service.fetch_and_cache("nanga_eboko", days=1)

        cached = self.service.list_cached_forecast("nanga_eboko")
        dates = [row["forecast_date"] for row in cached]
        self.assertNotIn(stale_date, dates)
        self.assertIn(date.today().isoformat(), dates)


if __name__ == "__main__":
    unittest.main()
