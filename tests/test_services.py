from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from gic_agri.database import Database
from gic_agri.services import AgricultureService
from gic_agri.validators import ValidationError


class AgricultureServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.service = AgricultureService(Database(self.root / "test.db"))

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _create_parcel_and_campaign(self) -> tuple[int, int]:
        parcel_id = self.service.create_parcel(
            name="Parcelle Manioc",
            village="Nkoteng",
            area_ha="2,5",
            soil_type="À observer",
        )
        campaign_id = self.service.create_campaign(
            parcel_id=parcel_id,
            name="Campagne principale",
            crop="Manioc",
            variety="Locale",
            area_ha=2,
            planting_date="2026-03-10",
            expected_harvest_date="2026-12-10",
            status="ACTIVE",
        )
        return parcel_id, campaign_id

    def test_end_to_end_dashboard_and_finance(self) -> None:
        parcel_id, campaign_id = self._create_parcel_and_campaign()
        self.service.create_task(
            title="Observer les feuilles",
            task_type="Observation",
            due_date=(date.today() + timedelta(days=1)).isoformat(),
            priority="HAUTE",
            parcel_id=parcel_id,
            campaign_id=campaign_id,
            estimated_cost=0,
        )
        self.service.create_stock_item(
            name="Sacs",
            category="Emballages",
            unit="unité",
            current_quantity=4,
            minimum_quantity=5,
            unit_cost=250,
        )
        self.service.create_plant_lot(
            species="Avocatier",
            variety="Locale",
            quantity=3,
            minimum_quantity=5,
            unit_price=2_000,
            age_months=6,
            location="Pépinière A",
        )
        self.service.create_finance_transaction(
            kind="DÉPENSE",
            category="Main-d'œuvre",
            amount=10_000,
            transaction_date=date.today().isoformat(),
            description="Préparation de la parcelle",
            campaign_id=campaign_id,
        )
        self.service.create_finance_transaction(
            kind="RECETTE",
            category="Vente de récolte",
            amount=18_000,
            transaction_date=date.today().isoformat(),
            description="Vente test",
            campaign_id=campaign_id,
        )
        self.service.create_observation(
            observed_at=date.today().isoformat(),
            category="Croissance",
            description="Développement régulier.",
            parcel_id=parcel_id,
            campaign_id=campaign_id,
        )

        summary = self.service.dashboard_summary()

        self.assertEqual(summary["parcels"], 1)
        self.assertEqual(summary["active_campaigns"], 1)
        self.assertEqual(summary["pending_tasks"], 1)
        self.assertEqual(summary["alerts"], 2)
        self.assertEqual(summary["finance"]["balance"], 8_000)
        self.assertEqual(len(summary["upcoming_tasks"]), 1)
        self.assertEqual(len(self.service.list_observations()), 1)

    def test_campaign_cannot_exceed_parcel_area(self) -> None:
        parcel_id = self.service.create_parcel(
            name="Petite parcelle",
            village="Mbandjock",
            area_ha=1,
        )

        with self.assertRaisesRegex(ValidationError, "dépasse"):
            self.service.create_campaign(
                parcel_id=parcel_id,
                name="Campagne trop grande",
                crop="Maïs",
                variety="",
                area_ha=1.5,
                planting_date="2026-03-01",
                expected_harvest_date="2026-07-01",
                status="ACTIVE",
            )

    def test_campaign_context_infers_and_protects_parcel(self) -> None:
        _parcel_id, campaign_id = self._create_parcel_and_campaign()
        other_parcel_id = self.service.create_parcel(
            name="Autre parcelle",
            village="Mbandjock",
            area_ha=1,
        )

        self.service.create_task(
            title="Tâche liée à la campagne",
            task_type="Observation",
            due_date=date.today().isoformat(),
            priority="NORMALE",
            campaign_id=campaign_id,
        )
        task = self.service.list_tasks()[0]
        self.assertEqual(task["parcel_name"], "Parcelle Manioc")

        with self.assertRaisesRegex(ValidationError, "n'appartient pas"):
            self.service.create_observation(
                observed_at=date.today().isoformat(),
                category="Croissance",
                description="Association incohérente.",
                parcel_id=other_parcel_id,
                campaign_id=campaign_id,
            )

    def test_stock_exit_cannot_create_negative_balance(self) -> None:
        item_id = self.service.create_stock_item(
            name="Aliment croissance",
            category="Aliments pour animaux",
            unit="kg",
            current_quantity=10,
            minimum_quantity=2,
        )

        with self.assertRaisesRegex(ValidationError, "dépasse"):
            self.service.record_stock_movement(
                item_id=item_id,
                movement_type="SORTIE",
                quantity=11,
                movement_date=date.today().isoformat(),
            )

        item = self.service.list_stock_items()[0]
        self.assertEqual(item["current_quantity"], 10)

    def test_plant_sale_updates_balance(self) -> None:
        lot_id = self.service.create_plant_lot(
            species="Citronnier",
            variety="",
            quantity=20,
            minimum_quantity=5,
            unit_price=1_500,
            age_months=4,
            location="Pépinière",
        )

        balance = self.service.record_plant_movement(
            lot_id=lot_id,
            movement_type="SORTIE",
            quantity=7,
            movement_date=date.today().isoformat(),
            reference="Client test",
        )

        self.assertEqual(balance, 13)
        self.assertEqual(self.service.list_plant_lots()[0]["quantity"], 13)

    def test_export_csv_creates_all_expected_files(self) -> None:
        self._create_parcel_and_campaign()
        destination = self.service.export_csv(self.root / "export")

        exported = {path.name for path in destination.glob("*.csv")}
        self.assertEqual(
            exported,
            {f"{table}.csv" for table in self.service.EXPORT_TABLES},
        )
        parcel_content = (destination / "parcels.csv").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn("Parcelle Manioc", parcel_content)


if __name__ == "__main__":
    unittest.main()
