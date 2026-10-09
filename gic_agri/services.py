"""Application services and business rules."""

from __future__ import annotations

import csv
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .constants import (
    CAMPAIGN_STATUSES,
    FINANCE_KINDS,
    MOVEMENT_TYPES,
    TASK_PRIORITIES,
    TASK_STATUSES,
)
from .database import Database
from .validators import (
    ValidationError,
    existing_optional_file,
    iso_date,
    non_negative_float,
    non_negative_int,
    optional_text,
    positive_float,
    required_text,
)


def _dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


class AgricultureService:
    """Coordinates validation, transactions and domain calculations."""

    EXPORT_TABLES = (
        "parcels",
        "campaigns",
        "tasks",
        "stock_items",
        "stock_movements",
        "finance_transactions",
        "plant_lots",
        "plant_movements",
        "observations",
    )

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()

    @staticmethod
    def _resolve_context(
        connection: sqlite3.Connection,
        parcel_id: int | None,
        campaign_id: int | None,
    ) -> tuple[int | None, int | None]:
        resolved_parcel_id = parcel_id
        if campaign_id is not None:
            campaign = connection.execute(
                "SELECT parcel_id FROM campaigns WHERE id = ?",
                (campaign_id,),
            ).fetchone()
            if campaign is None:
                raise ValidationError("La campagne sélectionnée est introuvable.")
            campaign_parcel_id = int(campaign["parcel_id"])
            if (
                resolved_parcel_id is not None
                and resolved_parcel_id != campaign_parcel_id
            ):
                raise ValidationError(
                    "La campagne sélectionnée n'appartient pas à cette parcelle."
                )
            resolved_parcel_id = campaign_parcel_id
        elif resolved_parcel_id is not None:
            parcel = connection.execute(
                "SELECT 1 FROM parcels WHERE id = ?",
                (resolved_parcel_id,),
            ).fetchone()
            if parcel is None:
                raise ValidationError("La parcelle sélectionnée est introuvable.")
        return resolved_parcel_id, campaign_id

    def create_parcel(
        self,
        *,
        name: object,
        village: object,
        area_ha: object,
        soil_type: object = "",
        water_access: object = "",
        notes: object = "",
    ) -> int:
        values = (
            required_text(name, "Nom de la parcelle"),
            required_text(village, "Village"),
            positive_float(area_ha, "Superficie"),
            optional_text(soil_type, max_length=120),
            optional_text(water_access, max_length=120),
            optional_text(notes),
        )
        try:
            with self.database.connection() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO parcels(
                        name, village, area_ha, soil_type, water_access, notes
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                return int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise ValidationError(
                "Une parcelle portant ce nom existe déjà."
            ) from exc

    def list_parcels(self, *, active_only: bool = False) -> list[dict[str, Any]]:
        where = "WHERE active = 1" if active_only else ""
        with self.database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT id, name, village, area_ha, soil_type, water_access,
                       notes, active, created_at
                FROM parcels
                {where}
                ORDER BY active DESC, name COLLATE NOCASE
                """
            ).fetchall()
        return _dicts(rows)

    def create_campaign(
        self,
        *,
        parcel_id: int,
        name: object,
        crop: object,
        variety: object,
        area_ha: object,
        planting_date: object,
        expected_harvest_date: object,
        status: object,
        notes: object = "",
    ) -> int:
        campaign_status = required_text(status, "Statut")
        if campaign_status not in CAMPAIGN_STATUSES:
            raise ValidationError("Le statut de campagne est invalide.")
        area = positive_float(area_ha, "Superficie cultivée")
        planting = iso_date(planting_date, "Date de plantation", required=False)
        harvest = iso_date(
            expected_harvest_date, "Récolte prévue", required=False
        )
        if planting and harvest and harvest < planting:
            raise ValidationError(
                "La date de récolte prévue doit suivre la date de plantation."
            )
        with self.database.connection() as connection:
            parcel = connection.execute(
                "SELECT area_ha FROM parcels WHERE id = ? AND active = 1",
                (parcel_id,),
            ).fetchone()
            if parcel is None:
                raise ValidationError("La parcelle sélectionnée est introuvable.")
            if area > float(parcel["area_ha"]):
                raise ValidationError(
                    "La superficie cultivée dépasse celle de la parcelle."
                )
            cursor = connection.execute(
                """
                INSERT INTO campaigns(
                    parcel_id, name, crop, variety, area_ha, planting_date,
                    expected_harvest_date, status, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    parcel_id,
                    required_text(name, "Nom de la campagne"),
                    required_text(crop, "Culture"),
                    optional_text(variety, max_length=120),
                    area,
                    planting,
                    harvest,
                    campaign_status,
                    optional_text(notes),
                ),
            )
            return int(cursor.lastrowid)

    def list_campaigns(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT c.id, c.name, c.crop, c.variety, c.area_ha,
                       c.planting_date, c.expected_harvest_date, c.status,
                       c.notes, p.id AS parcel_id, p.name AS parcel_name,
                       p.village
                FROM campaigns c
                JOIN parcels p ON p.id = c.parcel_id
                ORDER BY
                    CASE c.status
                        WHEN 'ACTIVE' THEN 0
                        WHEN 'PLANIFIÉE' THEN 1
                        ELSE 2
                    END,
                    c.created_at DESC
                """
            ).fetchall()
        return _dicts(rows)

    def create_task(
        self,
        *,
        title: object,
        task_type: object,
        due_date: object,
        priority: object,
        parcel_id: int | None = None,
        campaign_id: int | None = None,
        estimated_cost: object = 0,
        notes: object = "",
    ) -> int:
        task_priority = required_text(priority, "Priorité")
        if task_priority not in TASK_PRIORITIES:
            raise ValidationError("La priorité est invalide.")
        with self.database.connection() as connection:
            resolved_parcel_id, resolved_campaign_id = self._resolve_context(
                connection, parcel_id, campaign_id
            )
            cursor = connection.execute(
                """
                INSERT INTO tasks(
                    parcel_id, campaign_id, title, task_type, due_date,
                    priority, estimated_cost, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved_parcel_id,
                    resolved_campaign_id,
                    required_text(title, "Tâche"),
                    required_text(task_type, "Type de tâche"),
                    iso_date(due_date, "Échéance"),
                    task_priority,
                    non_negative_float(estimated_cost, "Coût estimé"),
                    optional_text(notes),
                ),
            )
            return int(cursor.lastrowid)

    def list_tasks(
        self, *, pending_only: bool = False, limit: int | None = None
    ) -> list[dict[str, Any]]:
        where = "WHERE t.status = 'À FAIRE'" if pending_only else ""
        limit_sql = "LIMIT ?" if limit is not None else ""
        parameters: tuple[Any, ...] = (limit,) if limit is not None else ()
        with self.database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT t.id, t.title, t.task_type, t.due_date, t.priority,
                       t.status, t.estimated_cost, t.notes,
                       p.name AS parcel_name, c.name AS campaign_name
                FROM tasks t
                LEFT JOIN parcels p ON p.id = t.parcel_id
                LEFT JOIN campaigns c ON c.id = t.campaign_id
                {where}
                ORDER BY
                    CASE t.status WHEN 'À FAIRE' THEN 0 ELSE 1 END,
                    t.due_date,
                    CASE t.priority
                        WHEN 'URGENTE' THEN 0
                        WHEN 'HAUTE' THEN 1
                        WHEN 'NORMALE' THEN 2
                        ELSE 3
                    END
                {limit_sql}
                """,
                parameters,
            ).fetchall()
        return _dicts(rows)

    def set_task_status(self, task_id: int, status: str) -> None:
        if status not in TASK_STATUSES:
            raise ValidationError("Le statut de tâche est invalide.")
        completed_at = date.today().isoformat() if status == "TERMINÉE" else None
        with self.database.connection() as connection:
            cursor = connection.execute(
                "UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?",
                (status, completed_at, task_id),
            )
            if cursor.rowcount != 1:
                raise ValidationError("La tâche sélectionnée est introuvable.")

    def create_stock_item(
        self,
        *,
        name: object,
        category: object,
        unit: object,
        current_quantity: object = 0,
        minimum_quantity: object = 0,
        unit_cost: object = 0,
        notes: object = "",
    ) -> int:
        quantity = non_negative_float(current_quantity, "Quantité initiale")
        try:
            with self.database.connection() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO stock_items(
                        name, category, unit, current_quantity,
                        minimum_quantity, unit_cost, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        required_text(name, "Article"),
                        required_text(category, "Catégorie"),
                        required_text(unit, "Unité"),
                        quantity,
                        non_negative_float(minimum_quantity, "Seuil minimum"),
                        non_negative_float(unit_cost, "Coût unitaire"),
                        optional_text(notes),
                    ),
                )
                item_id = int(cursor.lastrowid)
                if quantity > 0:
                    connection.execute(
                        """
                        INSERT INTO stock_movements(
                            item_id, movement_type, quantity, balance_after,
                            movement_date, reference, notes
                        ) VALUES (?, 'ENTRÉE', ?, ?, ?, 'Stock initial', '')
                        """,
                        (item_id, quantity, quantity, date.today().isoformat()),
                    )
                return item_id
        except sqlite3.IntegrityError as exc:
            raise ValidationError(
                "Un article portant ce nom existe déjà."
            ) from exc

    def list_stock_items(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT id, name, category, unit, current_quantity,
                       minimum_quantity, unit_cost, notes, updated_at,
                       CASE
                           WHEN current_quantity <= minimum_quantity THEN 1
                           ELSE 0
                       END AS low_stock
                FROM stock_items
                ORDER BY low_stock DESC, name COLLATE NOCASE
                """
            ).fetchall()
        return _dicts(rows)

    def record_stock_movement(
        self,
        *,
        item_id: int,
        movement_type: str,
        quantity: object,
        movement_date: object,
        reference: object = "",
        notes: object = "",
    ) -> float:
        if movement_type not in MOVEMENT_TYPES:
            raise ValidationError("Le type de mouvement est invalide.")
        amount = positive_float(quantity, "Quantité")
        movement_day = iso_date(movement_date, "Date du mouvement")
        with self.database.connection() as connection:
            item = connection.execute(
                "SELECT current_quantity FROM stock_items WHERE id = ?",
                (item_id,),
            ).fetchone()
            if item is None:
                raise ValidationError("L'article sélectionné est introuvable.")
            delta = amount if movement_type == "ENTRÉE" else -amount
            balance = float(item["current_quantity"]) + delta
            if balance < 0:
                raise ValidationError(
                    "La sortie demandée dépasse le stock disponible."
                )
            connection.execute(
                """
                UPDATE stock_items
                SET current_quantity = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (balance, item_id),
            )
            connection.execute(
                """
                INSERT INTO stock_movements(
                    item_id, movement_type, quantity, balance_after,
                    movement_date, reference, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    movement_type,
                    amount,
                    balance,
                    movement_day,
                    optional_text(reference, max_length=160),
                    optional_text(notes),
                ),
            )
        return balance

    def create_finance_transaction(
        self,
        *,
        kind: object,
        category: object,
        amount: object,
        transaction_date: object,
        description: object,
        campaign_id: int | None = None,
    ) -> int:
        transaction_kind = required_text(kind, "Type")
        if transaction_kind not in FINANCE_KINDS:
            raise ValidationError("Le type financier est invalide.")
        with self.database.connection() as connection:
            if campaign_id is not None:
                campaign = connection.execute(
                    "SELECT 1 FROM campaigns WHERE id = ?",
                    (campaign_id,),
                ).fetchone()
                if campaign is None:
                    raise ValidationError(
                        "La campagne sélectionnée est introuvable."
                    )
            cursor = connection.execute(
                """
                INSERT INTO finance_transactions(
                    campaign_id, kind, category, amount,
                    transaction_date, description
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    campaign_id,
                    transaction_kind,
                    required_text(category, "Catégorie"),
                    positive_float(amount, "Montant"),
                    iso_date(transaction_date, "Date"),
                    required_text(description, "Description", max_length=500),
                ),
            )
            return int(cursor.lastrowid)

    def list_finance_transactions(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT f.id, f.kind, f.category, f.amount,
                       f.transaction_date, f.description,
                       c.name AS campaign_name
                FROM finance_transactions f
                LEFT JOIN campaigns c ON c.id = f.campaign_id
                ORDER BY f.transaction_date DESC, f.id DESC
                """
            ).fetchall()
        return _dicts(rows)

    def finance_summary(self) -> dict[str, float]:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN kind = 'RECETTE' THEN amount END), 0)
                        AS revenue,
                    COALESCE(SUM(CASE WHEN kind = 'DÉPENSE' THEN amount END), 0)
                        AS expense
                FROM finance_transactions
                """
            ).fetchone()
        revenue = float(row["revenue"])
        expense = float(row["expense"])
        return {"revenue": revenue, "expense": expense, "balance": revenue - expense}

    def create_plant_lot(
        self,
        *,
        species: object,
        variety: object = "",
        quantity: object = 0,
        minimum_quantity: object = 0,
        unit_price: object = 0,
        age_months: object = 0,
        location: object = "",
        notes: object = "",
    ) -> int:
        initial_quantity = non_negative_int(quantity, "Quantité initiale")
        try:
            with self.database.connection() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO plant_lots(
                        species, variety, quantity, minimum_quantity,
                        unit_price, age_months, location, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        required_text(species, "Espèce"),
                        optional_text(variety, max_length=120),
                        initial_quantity,
                        non_negative_int(minimum_quantity, "Seuil minimum"),
                        non_negative_float(unit_price, "Prix unitaire"),
                        non_negative_int(age_months, "Âge"),
                        optional_text(location, max_length=160),
                        optional_text(notes),
                    ),
                )
                lot_id = int(cursor.lastrowid)
                if initial_quantity > 0:
                    connection.execute(
                        """
                        INSERT INTO plant_movements(
                            lot_id, movement_type, quantity, balance_after,
                            movement_date, reference, notes
                        ) VALUES (?, 'ENTRÉE', ?, ?, ?, 'Stock initial', '')
                        """,
                        (
                            lot_id,
                            initial_quantity,
                            initial_quantity,
                            date.today().isoformat(),
                        ),
                    )
                return lot_id
        except sqlite3.IntegrityError as exc:
            raise ValidationError(
                "Ce lot de plants existe déjà pour cet emplacement."
            ) from exc

    def list_plant_lots(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT id, species, variety, quantity, minimum_quantity,
                       unit_price, age_months, location, notes, updated_at,
                       CASE WHEN quantity <= minimum_quantity THEN 1 ELSE 0 END
                           AS low_stock
                FROM plant_lots
                ORDER BY low_stock DESC, species COLLATE NOCASE, variety
                """
            ).fetchall()
        return _dicts(rows)

    def record_plant_movement(
        self,
        *,
        lot_id: int,
        movement_type: str,
        quantity: object,
        movement_date: object,
        reference: object = "",
        notes: object = "",
    ) -> int:
        if movement_type not in MOVEMENT_TYPES:
            raise ValidationError("Le type de mouvement est invalide.")
        amount = non_negative_int(quantity, "Quantité")
        if amount == 0:
            raise ValidationError("La quantité doit être supérieure à zéro.")
        movement_day = iso_date(movement_date, "Date du mouvement")
        with self.database.connection() as connection:
            lot = connection.execute(
                "SELECT quantity FROM plant_lots WHERE id = ?",
                (lot_id,),
            ).fetchone()
            if lot is None:
                raise ValidationError("Le lot de plants est introuvable.")
            delta = amount if movement_type == "ENTRÉE" else -amount
            balance = int(lot["quantity"]) + delta
            if balance < 0:
                raise ValidationError(
                    "La sortie demandée dépasse le nombre de plants disponibles."
                )
            connection.execute(
                """
                UPDATE plant_lots
                SET quantity = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (balance, lot_id),
            )
            connection.execute(
                """
                INSERT INTO plant_movements(
                    lot_id, movement_type, quantity, balance_after,
                    movement_date, reference, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lot_id,
                    movement_type,
                    amount,
                    balance,
                    movement_day,
                    optional_text(reference, max_length=160),
                    optional_text(notes),
                ),
            )
        return balance

    def create_observation(
        self,
        *,
        observed_at: object,
        category: object,
        description: object,
        parcel_id: int | None = None,
        campaign_id: int | None = None,
        photo_path: object = "",
    ) -> int:
        with self.database.connection() as connection:
            resolved_parcel_id, resolved_campaign_id = self._resolve_context(
                connection, parcel_id, campaign_id
            )
            cursor = connection.execute(
                """
                INSERT INTO observations(
                    parcel_id, campaign_id, observed_at,
                    category, description, photo_path
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved_parcel_id,
                    resolved_campaign_id,
                    iso_date(observed_at, "Date d'observation"),
                    required_text(category, "Catégorie"),
                    required_text(description, "Observation", max_length=2_000),
                    existing_optional_file(photo_path, "Photo"),
                ),
            )
            return int(cursor.lastrowid)

    def list_observations(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT o.id, o.observed_at, o.category, o.description,
                       o.photo_path, p.name AS parcel_name,
                       c.name AS campaign_name
                FROM observations o
                LEFT JOIN parcels p ON p.id = o.parcel_id
                LEFT JOIN campaigns c ON c.id = o.campaign_id
                ORDER BY o.observed_at DESC, o.id DESC
                """
            ).fetchall()
        return _dicts(rows)

    def dashboard_summary(self) -> dict[str, Any]:
        today = date.today().isoformat()
        horizon = (date.today() + timedelta(days=14)).isoformat()
        with self.database.connection() as connection:
            counts = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM parcels WHERE active = 1)
                        AS parcels,
                    (SELECT COUNT(*) FROM campaigns WHERE status = 'ACTIVE')
                        AS active_campaigns,
                    (SELECT COUNT(*) FROM tasks WHERE status = 'À FAIRE')
                        AS pending_tasks,
                    (
                        SELECT COUNT(*) FROM stock_items
                        WHERE current_quantity <= minimum_quantity
                    ) + (
                        SELECT COUNT(*) FROM plant_lots
                        WHERE quantity <= minimum_quantity
                    ) AS alerts
                """
            ).fetchone()
            upcoming = connection.execute(
                """
                SELECT t.id, t.title, t.due_date, t.priority,
                       p.name AS parcel_name
                FROM tasks t
                LEFT JOIN parcels p ON p.id = t.parcel_id
                WHERE t.status = 'À FAIRE'
                  AND t.due_date BETWEEN ? AND ?
                ORDER BY t.due_date, t.priority DESC
                LIMIT 8
                """,
                (today, horizon),
            ).fetchall()
            low_stock = connection.execute(
                """
                SELECT name, current_quantity AS quantity, unit
                FROM stock_items
                WHERE current_quantity <= minimum_quantity
                ORDER BY name
                LIMIT 8
                """
            ).fetchall()
        summary = dict(counts)
        summary["finance"] = self.finance_summary()
        summary["upcoming_tasks"] = _dicts(upcoming)
        summary["low_stock"] = _dicts(low_stock)
        return summary

    def export_csv(self, destination: str | Path) -> Path:
        folder = Path(destination).expanduser().resolve()
        folder.mkdir(parents=True, exist_ok=True)
        with self.database.connection() as connection:
            for table in self.EXPORT_TABLES:
                cursor = connection.execute(f"SELECT * FROM {table} ORDER BY id")
                output = folder / f"{table}.csv"
                with output.open("w", newline="", encoding="utf-8-sig") as handle:
                    writer = csv.writer(handle, delimiter=";")
                    writer.writerow(column[0] for column in cursor.description)
                    writer.writerows(cursor.fetchall())
        return folder

    def seed_demo_data(self) -> bool:
        if self.list_parcels():
            return False
        parcel_id = self.create_parcel(
            name="Parcelle de démonstration",
            village="Mbandjock",
            area_ha=2.5,
            soil_type="Sol à renseigner",
            water_access="Pluie",
            notes="Exemple à modifier ou compléter.",
        )
        planting = date.today() - timedelta(days=30)
        harvest = date.today() + timedelta(days=240)
        campaign_id = self.create_campaign(
            parcel_id=parcel_id,
            name=f"Manioc {date.today().year}",
            crop="Manioc",
            variety="À renseigner",
            area_ha=1.5,
            planting_date=planting.isoformat(),
            expected_harvest_date=harvest.isoformat(),
            status="ACTIVE",
            notes="Campagne de démonstration.",
        )
        self.create_task(
            title="Faire le tour de la parcelle",
            task_type="Observation",
            due_date=(date.today() + timedelta(days=2)).isoformat(),
            priority="NORMALE",
            parcel_id=parcel_id,
            campaign_id=campaign_id,
            notes="Observer la croissance et noter les anomalies.",
        )
        self.create_stock_item(
            name="Sacs de conditionnement",
            category="Emballages",
            unit="unité",
            current_quantity=25,
            minimum_quantity=10,
            unit_cost=250,
        )
        self.create_plant_lot(
            species="Citronnier",
            variety="À renseigner",
            quantity=20,
            minimum_quantity=5,
            unit_price=0,
            age_months=0,
            location="Pépinière principale",
            notes="Compléter l'âge et le prix.",
        )
        return True
