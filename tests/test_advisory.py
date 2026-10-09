from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from gic_agri.advisory import AdvisoryService
from gic_agri.database import Database
from gic_agri.services import AgricultureService
from gic_agri.weather import WeatherService


class AdvisoryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temporary_directory.name) / "advisory.db")
        self.agriculture_service = AgricultureService(self.database)
        self.weather_service = WeatherService(self.database)
        self.advisory_service = AdvisoryService(
            self.agriculture_service, self.weather_service
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _create_parcel(self) -> int:
        return self.agriculture_service.create_parcel(
            name="Parcelle de test",
            village="Nanga-Eboko",
            area_ha=5,
        )

    def _insert_forecast(self, daily_precipitation_mm: list[float]) -> None:
        with self.database.connection() as connection:
            for offset, rain in enumerate(daily_precipitation_mm):
                forecast_date = (date.today() + timedelta(days=offset)).isoformat()
                connection.execute(
                    """
                    INSERT INTO weather_forecasts(
                        location_key, forecast_date, temperature_min,
                        temperature_max, precipitation_mm,
                        precipitation_probability, weather_code, wind_speed_max
                    ) VALUES ('nanga_eboko', ?, 20, 28, ?, 50, 61, 10)
                    """,
                    (forecast_date, rain),
                )

    def test_campaign_within_regional_window_is_marked_as_consistent(self) -> None:
        parcel_id = self._create_parcel()
        self.agriculture_service.create_campaign(
            parcel_id=parcel_id,
            name="Campagne manioc",
            crop="Manioc",
            variety="",
            area_ha=1,
            planting_date="2026-03-15",
            expected_harvest_date="2026-12-15",
            status="ACTIVE",
        )
        self._insert_forecast([10, 10, 10, 10, 10, 10, 10])

        recommendations = self.advisory_service.generate_recommendations()

        calendar_notes = [
            item for item in recommendations if "Campagne manioc" in item["title"]
        ]
        self.assertEqual(len(calendar_notes), 1)
        self.assertEqual(calendar_notes[0]["level"], "info")
        self.assertIn("période cohérente", calendar_notes[0]["title"])

    def test_campaign_outside_regional_window_raises_attention(self) -> None:
        parcel_id = self._create_parcel()
        self.agriculture_service.create_campaign(
            parcel_id=parcel_id,
            name="Campagne maïs tardive",
            crop="Maïs",
            variety="",
            area_ha=1,
            planting_date="2026-11-10",
            expected_harvest_date="2027-03-10",
            status="PLANIFIÉE",
        )
        self._insert_forecast([10, 10, 10, 10, 10, 10, 10])

        recommendations = self.advisory_service.generate_recommendations()

        calendar_notes = [
            item
            for item in recommendations
            if "Campagne maïs tardive" in item["title"]
        ]
        self.assertEqual(len(calendar_notes), 1)
        self.assertEqual(calendar_notes[0]["level"], "attention")
        self.assertIn("période à vérifier", calendar_notes[0]["title"])

    def test_low_rainfall_forecast_triggers_drought_attention(self) -> None:
        self._insert_forecast([0, 0, 1, 0, 0, 0, 0])

        recommendations = self.advisory_service.generate_recommendations()

        drought_notes = [
            item for item in recommendations if "sécheresse" in item["title"].lower()
        ]
        self.assertEqual(len(drought_notes), 1)
        self.assertEqual(drought_notes[0]["level"], "attention")
        self.assertIn("Open-Meteo", drought_notes[0]["source"])

    def test_heavy_rainfall_forecast_triggers_waterlogging_attention(self) -> None:
        self._insert_forecast([25, 10, 5, 5, 5, 5, 5])

        recommendations = self.advisory_service.generate_recommendations()

        rain_notes = [
            item for item in recommendations if "Fortes pluies" in item["title"]
        ]
        self.assertEqual(len(rain_notes), 1)
        self.assertEqual(rain_notes[0]["level"], "attention")

    def test_moderate_rainfall_forecast_is_informational(self) -> None:
        self._insert_forecast([3, 3, 3, 3, 3, 3, 3])

        recommendations = self.advisory_service.generate_recommendations()

        normal_notes = [
            item for item in recommendations if "proches de la normale" in item["title"]
        ]
        self.assertEqual(len(normal_notes), 1)
        self.assertEqual(normal_notes[0]["level"], "info")

    def test_missing_forecast_reports_unavailable_data_as_info(self) -> None:
        recommendations = self.advisory_service.generate_recommendations()

        unavailable_notes = [
            item
            for item in recommendations
            if "non disponibles" in item["title"].lower()
        ]
        self.assertEqual(len(unavailable_notes), 1)
        self.assertEqual(unavailable_notes[0]["level"], "info")

    def test_low_stock_and_overdue_task_trigger_operational_alerts(self) -> None:
        self.agriculture_service.create_stock_item(
            name="Sacs de conditionnement",
            category="Emballages",
            unit="unité",
            current_quantity=1,
            minimum_quantity=10,
        )
        self.agriculture_service.create_task(
            title="Travail en retard",
            task_type="Observation",
            due_date=(date.today() - timedelta(days=3)).isoformat(),
            priority="HAUTE",
        )
        self._insert_forecast([3, 3, 3, 3, 3, 3, 3])

        recommendations = self.advisory_service.generate_recommendations()

        titles = [item["title"] for item in recommendations]
        self.assertTrue(any("Stocks sous le seuil minimum" in title for title in titles))
        self.assertTrue(any("Travaux en retard" in title for title in titles))

        overdue_note = next(
            item for item in recommendations if item["title"] == "Travaux en retard"
        )
        self.assertEqual(overdue_note["level"], "urgent")

    def test_recommendations_are_sorted_urgent_first(self) -> None:
        self.agriculture_service.create_task(
            title="Travail en retard",
            task_type="Observation",
            due_date=(date.today() - timedelta(days=1)).isoformat(),
            priority="HAUTE",
        )
        self._insert_forecast([0, 0, 0, 0, 0, 0, 0])

        recommendations = self.advisory_service.generate_recommendations()
        levels = [item["level"] for item in recommendations]

        self.assertEqual(levels, sorted(levels, key={"urgent": 0, "attention": 1, "info": 2}.get))
        self.assertEqual(levels[0], "urgent")


if __name__ == "__main__":
    unittest.main()
