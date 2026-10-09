"""Tkinter user interface for the offline GIC INNOVATION application."""

from __future__ import annotations

import logging
import traceback
import webbrowser
from datetime import date, datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from .advisory import AdvisoryService
from .constants import (
    CAMPAIGN_STATUSES,
    CROPS,
    DEFAULT_WEATHER_LOCATION,
    FINANCE_CATEGORIES,
    FINANCE_KINDS,
    FRUIT_SPECIES,
    MOVEMENT_TYPES,
    OBSERVATION_CATEGORIES,
    ORGANIZATION_NAME,
    REGION_NAME,
    STOCK_CATEGORIES,
    STOCK_UNITS,
    TASK_PRIORITIES,
    TASK_TYPES,
)
from .network import NetworkError
from .news import NewsService
from .services import AgricultureService
from .validators import ValidationError
from .weather import WeatherService, describe_weather_code


GREEN = "#075b2a"
DARK_GREEN = "#063b20"
LIGHT_GREEN = "#eaf5ed"
LIME = "#8dc63f"
ORANGE = "#e57800"
CREAM = "#f8faf5"
MUTED = "#66736b"
NONE_OPTION = "— Aucun —"


def money(value: float) -> str:
    return f"{float(value):,.0f} FCFA".replace(",", " ")


def number(value: float, decimals: int = 2) -> str:
    formatted = f"{float(value):,.{decimals}f}".replace(",", " ")
    return formatted.rstrip("0").rstrip(",").rstrip(".")


def optional_number(value: Any, *, decimals: int = 1, suffix: str = "") -> str:
    if value is None:
        return "—"
    try:
        return f"{number(float(value), decimals)}{suffix}"
    except (TypeError, ValueError):
        return "—"


def option(row_id: int, label: str) -> str:
    return f"{row_id} | {label}"


def option_id(value: str, label: str, *, required: bool = False) -> int | None:
    text = str(value or "").strip()
    if not text or text == NONE_OPTION:
        if required:
            raise ValidationError(f"Veuillez sélectionner {label}.")
        return None
    try:
        return int(text.split("|", 1)[0].strip())
    except (ValueError, IndexError) as exc:
        raise ValidationError(f"La sélection « {label} » est invalide.") from exc


class FormDialog(tk.Toplevel):
    """Small reusable modal form."""

    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        fields: list[dict[str, Any]],
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.result: dict[str, str] | None = None
        self.fields = fields
        self.widgets: dict[str, Any] = {}

        outer = ttk.Frame(self, padding=18)
        outer.grid(sticky="nsew")
        outer.columnconfigure(1, weight=1)

        first_focus: tk.Widget | None = None
        row = 0
        for field in fields:
            ttk.Label(outer, text=field["label"]).grid(
                row=row, column=0, sticky="nw", padx=(0, 12), pady=6
            )
            field_type = field.get("type", "entry")
            default = str(field.get("default", ""))

            if field_type == "text":
                widget = tk.Text(
                    outer,
                    width=46,
                    height=field.get("height", 4),
                    wrap="word",
                    relief="solid",
                    borderwidth=1,
                )
                widget.insert("1.0", default)
                widget.grid(row=row, column=1, sticky="ew", pady=6)
                self.widgets[field["name"]] = widget
            elif field_type == "combo":
                variable = tk.StringVar(value=default)
                widget = ttk.Combobox(
                    outer,
                    textvariable=variable,
                    values=field.get("options", ()),
                    state="readonly",
                    width=43,
                )
                widget.grid(row=row, column=1, sticky="ew", pady=6)
                self.widgets[field["name"]] = variable
            elif field_type == "file":
                variable = tk.StringVar(value=default)
                holder = ttk.Frame(outer)
                holder.grid(row=row, column=1, sticky="ew", pady=6)
                holder.columnconfigure(0, weight=1)
                widget = ttk.Entry(holder, textvariable=variable, width=38)
                widget.grid(row=0, column=0, sticky="ew")
                ttk.Button(
                    holder,
                    text="Parcourir…",
                    command=lambda var=variable: self._select_file(var),
                ).grid(row=0, column=1, padx=(8, 0))
                self.widgets[field["name"]] = variable
            else:
                variable = tk.StringVar(value=default)
                widget = ttk.Entry(outer, textvariable=variable, width=46)
                widget.grid(row=row, column=1, sticky="ew", pady=6)
                self.widgets[field["name"]] = variable

            if first_focus is None and isinstance(widget, tk.Widget):
                first_focus = widget
            row += 1

        actions = ttk.Frame(outer)
        actions.grid(row=row, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(actions, text="Annuler", command=self.destroy).pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(
            actions,
            text="Enregistrer",
            style="Primary.TButton",
            command=self._save,
        ).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.update_idletasks()
        self._center(parent.winfo_toplevel())
        self.grab_set()
        if first_focus is not None:
            first_focus.focus_set()

    def _center(self, parent: tk.Misc) -> None:
        width = self.winfo_reqwidth()
        height = self.winfo_reqheight()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 2)
        self.geometry(f"+{x}+{y}")

    def _select_file(self, variable: tk.StringVar) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="Sélectionner une photo",
            filetypes=(
                ("Images", "*.jpg *.jpeg *.png *.webp"),
                ("Tous les fichiers", "*.*"),
            ),
        )
        if selected:
            variable.set(selected)

    def _save(self) -> None:
        values: dict[str, str] = {}
        for field in self.fields:
            widget = self.widgets[field["name"]]
            if isinstance(widget, tk.Text):
                value = widget.get("1.0", "end").strip()
            else:
                value = widget.get().strip()
            if field.get("required") and not value:
                messagebox.showwarning(
                    "Champ obligatoire",
                    f"Le champ « {field['label']} » est obligatoire.",
                    parent=self,
                )
                return
            values[field["name"]] = value
        self.result = values
        self.destroy()

    @classmethod
    def ask(
        cls,
        parent: tk.Misc,
        title: str,
        fields: list[dict[str, Any]],
    ) -> dict[str, str] | None:
        dialog = cls(parent, title, fields)
        parent.wait_window(dialog)
        return dialog.result


def build_tree(
    parent: tk.Misc,
    columns: list[tuple[str, str, int]],
    *,
    height: int = 18,
) -> ttk.Treeview:
    tree = ttk.Treeview(
        parent,
        columns=[item[0] for item in columns],
        show="headings",
        height=height,
        selectmode="browse",
    )
    for key, label, width in columns:
        tree.heading(key, text=label)
        anchor = "e" if key in {"area", "quantity", "amount", "price", "age"} else "w"
        tree.column(key, width=width, anchor=anchor, stretch=key not in {"id"})
    tree.tag_configure("alert", background="#fff0e6", foreground="#8d3100")
    tree.tag_configure("done", foreground="#6f7a73")
    return tree


def selected_id(tree: ttk.Treeview, label: str) -> int:
    selection = tree.selection()
    if not selection:
        raise ValidationError(f"Veuillez sélectionner {label}.")
    values = tree.item(selection[0], "values")
    if not values:
        raise ValidationError(f"La sélection « {label} » est invalide.")
    return int(values[0])


class DashboardTab(ttk.Frame):
    def __init__(self, parent: tk.Misc, service: AgricultureService) -> None:
        super().__init__(parent, padding=18)
        self.service = service
        self.card_values: dict[str, tk.StringVar] = {}

        cards = ttk.Frame(self)
        cards.pack(fill="x", pady=(0, 18))
        for index, (key, title, color) in enumerate(
            (
                ("parcels", "Parcelles actives", GREEN),
                ("campaigns", "Campagnes actives", "#2d7e46"),
                ("tasks", "Travaux à faire", ORANGE),
                ("alerts", "Alertes de stock", "#a63c24"),
                ("balance", "Solde enregistré", "#2f6577"),
            )
        ):
            cards.columnconfigure(index, weight=1)
            card = tk.Frame(cards, bg=color, padx=18, pady=15)
            card.grid(row=0, column=index, sticky="nsew", padx=5)
            tk.Label(
                card,
                text=title,
                bg=color,
                fg="white",
                font=("Segoe UI", 10, "bold"),
            ).pack(anchor="w")
            variable = tk.StringVar(value="0")
            tk.Label(
                card,
                textvariable=variable,
                bg=color,
                fg="white",
                font=("Segoe UI", 22, "bold"),
            ).pack(anchor="w", pady=(7, 0))
            self.card_values[key] = variable

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True)

        tasks_frame = ttk.LabelFrame(
            body, text="Travaux des 14 prochains jours", padding=10
        )
        stock_frame = ttk.LabelFrame(body, text="Stocks à surveiller", padding=10)
        body.add(tasks_frame, weight=3)
        body.add(stock_frame, weight=2)

        self.tasks_tree = build_tree(
            tasks_frame,
            [
                ("date", "Échéance", 105),
                ("title", "Travail", 250),
                ("parcel", "Parcelle", 160),
                ("priority", "Priorité", 90),
            ],
            height=16,
        )
        self.tasks_tree.pack(fill="both", expand=True)

        self.stock_tree = build_tree(
            stock_frame,
            [
                ("name", "Article", 220),
                ("quantity", "Disponible", 110),
                ("unit", "Unité", 80),
            ],
            height=16,
        )
        self.stock_tree.pack(fill="both", expand=True)

        ttk.Label(
            self,
            text=(
                "Les alertes locales sont calculées à partir de vos données. "
                "Aucune intelligence artificielle n'est activée dans cette version."
            ),
            foreground=MUTED,
        ).pack(anchor="w", pady=(12, 0))

    def refresh(self) -> None:
        summary = self.service.dashboard_summary()
        finance = summary["finance"]
        self.card_values["parcels"].set(str(summary["parcels"]))
        self.card_values["campaigns"].set(str(summary["active_campaigns"]))
        self.card_values["tasks"].set(str(summary["pending_tasks"]))
        self.card_values["alerts"].set(str(summary["alerts"]))
        self.card_values["balance"].set(money(finance["balance"]))

        self.tasks_tree.delete(*self.tasks_tree.get_children())
        for row in summary["upcoming_tasks"]:
            self.tasks_tree.insert(
                "",
                "end",
                values=(
                    row["due_date"],
                    row["title"],
                    row["parcel_name"] or "—",
                    row["priority"],
                ),
            )

        self.stock_tree.delete(*self.stock_tree.get_children())
        for row in summary["low_stock"]:
            self.stock_tree.insert(
                "",
                "end",
                values=(row["name"], number(row["quantity"]), row["unit"]),
                tags=("alert",),
            )


class DataTab(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        app: "MainWindow",
        title: str,
        description: str,
        columns: list[tuple[str, str, int]],
    ) -> None:
        super().__init__(parent, padding=18)
        self.app = app
        self.service = app.service

        heading = ttk.Frame(self)
        heading.pack(fill="x", pady=(0, 12))
        ttk.Label(heading, text=title, style="Heading.TLabel").pack(anchor="w")
        ttk.Label(heading, text=description, foreground=MUTED).pack(
            anchor="w", pady=(3, 0)
        )

        self.toolbar = ttk.Frame(self)
        self.toolbar.pack(fill="x", pady=(0, 10))
        ttk.Button(self.toolbar, text="Actualiser", command=self.refresh).pack(
            side="right"
        )

        table_holder = ttk.Frame(self)
        table_holder.pack(fill="both", expand=True)
        self.tree = build_tree(table_holder, columns)
        scrollbar = ttk.Scrollbar(
            table_holder, orient="vertical", command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def add_button(
        self,
        text: str,
        command: Callable[[], None],
        *,
        primary: bool = False,
    ) -> None:
        ttk.Button(
            self.toolbar,
            text=text,
            command=command,
            style="Primary.TButton" if primary else "TButton",
        ).pack(side="left", padx=(0, 8))

    def refresh(self) -> None:
        raise NotImplementedError


class ParcelsTab(DataTab):
    def __init__(self, parent: tk.Misc, app: "MainWindow") -> None:
        super().__init__(
            parent,
            app,
            "Parcelles",
            "Enregistrez les parcelles et leur localisation dans la Haute-Sanaga.",
            [
                ("id", "ID", 55),
                ("name", "Nom", 210),
                ("village", "Village", 170),
                ("area", "Superficie (ha)", 120),
                ("soil", "Type de sol", 150),
                ("water", "Accès à l'eau", 150),
                ("active", "État", 90),
            ],
        )
        self.add_button("Nouvelle parcelle", self.create, primary=True)

    def create(self) -> None:
        values = FormDialog.ask(
            self,
            "Nouvelle parcelle",
            [
                {"name": "name", "label": "Nom", "required": True},
                {"name": "village", "label": "Village", "required": True},
                {
                    "name": "area",
                    "label": "Superficie (ha)",
                    "required": True,
                },
                {"name": "soil", "label": "Type de sol"},
                {"name": "water", "label": "Accès à l'eau"},
                {"name": "notes", "label": "Notes", "type": "text"},
            ],
        )
        if values is None:
            return
        self.app.perform(
            lambda: self.service.create_parcel(
                name=values["name"],
                village=values["village"],
                area_ha=values["area"],
                soil_type=values["soil"],
                water_access=values["water"],
                notes=values["notes"],
            ),
            "Parcelle enregistrée.",
        )

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for row in self.service.list_parcels():
            self.tree.insert(
                "",
                "end",
                values=(
                    row["id"],
                    row["name"],
                    row["village"],
                    number(row["area_ha"]),
                    row["soil_type"] or "—",
                    row["water_access"] or "—",
                    "Active" if row["active"] else "Inactive",
                ),
            )


class CampaignsTab(DataTab):
    def __init__(self, parent: tk.Misc, app: "MainWindow") -> None:
        super().__init__(
            parent,
            app,
            "Campagnes culturales",
            "Associez une culture, une superficie et des dates à chaque parcelle.",
            [
                ("id", "ID", 55),
                ("name", "Campagne", 190),
                ("parcel", "Parcelle", 170),
                ("crop", "Culture", 125),
                ("variety", "Variété", 130),
                ("area", "Surface (ha)", 105),
                ("planting", "Plantation", 105),
                ("harvest", "Récolte prévue", 110),
                ("status", "Statut", 100),
            ],
        )
        self.add_button("Nouvelle campagne", self.create, primary=True)

    def create(self) -> None:
        parcels = self.service.list_parcels(active_only=True)
        if not parcels:
            messagebox.showwarning(
                "Parcelle requise",
                "Enregistrez d'abord une parcelle active.",
                parent=self,
            )
            return
        parcel_options = [
            option(row["id"], f"{row['name']} — {row['village']}") for row in parcels
        ]
        values = FormDialog.ask(
            self,
            "Nouvelle campagne",
            [
                {
                    "name": "parcel",
                    "label": "Parcelle",
                    "type": "combo",
                    "options": parcel_options,
                    "default": parcel_options[0],
                    "required": True,
                },
                {"name": "name", "label": "Nom de la campagne", "required": True},
                {
                    "name": "crop",
                    "label": "Culture",
                    "type": "combo",
                    "options": CROPS,
                    "default": CROPS[0],
                    "required": True,
                },
                {"name": "variety", "label": "Variété"},
                {
                    "name": "area",
                    "label": "Superficie cultivée (ha)",
                    "required": True,
                },
                {
                    "name": "planting",
                    "label": "Date de plantation",
                    "default": date.today().isoformat(),
                },
                {"name": "harvest", "label": "Récolte prévue"},
                {
                    "name": "status",
                    "label": "Statut",
                    "type": "combo",
                    "options": CAMPAIGN_STATUSES,
                    "default": "ACTIVE",
                    "required": True,
                },
                {"name": "notes", "label": "Notes", "type": "text"},
            ],
        )
        if values is None:
            return
        self.app.perform(
            lambda: self.service.create_campaign(
                parcel_id=option_id(values["parcel"], "une parcelle", required=True),
                name=values["name"],
                crop=values["crop"],
                variety=values["variety"],
                area_ha=values["area"],
                planting_date=values["planting"],
                expected_harvest_date=values["harvest"],
                status=values["status"],
                notes=values["notes"],
            ),
            "Campagne enregistrée.",
        )

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for row in self.service.list_campaigns():
            self.tree.insert(
                "",
                "end",
                values=(
                    row["id"],
                    row["name"],
                    row["parcel_name"],
                    row["crop"],
                    row["variety"] or "—",
                    number(row["area_ha"]),
                    row["planting_date"] or "—",
                    row["expected_harvest_date"] or "—",
                    row["status"],
                ),
            )


class TasksTab(DataTab):
    def __init__(self, parent: tk.Misc, app: "MainWindow") -> None:
        super().__init__(
            parent,
            app,
            "Travaux et calendrier",
            "Planifiez les opérations et marquez-les comme terminées.",
            [
                ("id", "ID", 55),
                ("date", "Échéance", 105),
                ("title", "Travail", 240),
                ("type", "Type", 155),
                ("parcel", "Parcelle", 155),
                ("campaign", "Campagne", 155),
                ("priority", "Priorité", 90),
                ("status", "Statut", 100),
                ("cost", "Coût estimé", 120),
            ],
        )
        self.add_button("Nouveau travail", self.create, primary=True)
        self.add_button("Marquer terminé", self.complete)

    def create(self) -> None:
        parcels = self.service.list_parcels(active_only=True)
        campaigns = self.service.list_campaigns()
        parcel_options = [NONE_OPTION] + [
            option(row["id"], row["name"]) for row in parcels
        ]
        campaign_options = [NONE_OPTION] + [
            option(row["id"], row["name"]) for row in campaigns
        ]
        values = FormDialog.ask(
            self,
            "Nouveau travail",
            [
                {"name": "title", "label": "Travail", "required": True},
                {
                    "name": "type",
                    "label": "Type",
                    "type": "combo",
                    "options": TASK_TYPES,
                    "default": TASK_TYPES[0],
                    "required": True,
                },
                {
                    "name": "due",
                    "label": "Échéance",
                    "default": date.today().isoformat(),
                    "required": True,
                },
                {
                    "name": "priority",
                    "label": "Priorité",
                    "type": "combo",
                    "options": TASK_PRIORITIES,
                    "default": "NORMALE",
                    "required": True,
                },
                {
                    "name": "parcel",
                    "label": "Parcelle",
                    "type": "combo",
                    "options": parcel_options,
                    "default": NONE_OPTION,
                },
                {
                    "name": "campaign",
                    "label": "Campagne",
                    "type": "combo",
                    "options": campaign_options,
                    "default": NONE_OPTION,
                },
                {"name": "cost", "label": "Coût estimé", "default": "0"},
                {"name": "notes", "label": "Notes", "type": "text"},
            ],
        )
        if values is None:
            return
        self.app.perform(
            lambda: self.service.create_task(
                title=values["title"],
                task_type=values["type"],
                due_date=values["due"],
                priority=values["priority"],
                parcel_id=option_id(values["parcel"], "une parcelle"),
                campaign_id=option_id(values["campaign"], "une campagne"),
                estimated_cost=values["cost"],
                notes=values["notes"],
            ),
            "Travail planifié.",
        )

    def complete(self) -> None:
        self.app.perform(
            lambda: self.service.set_task_status(
                selected_id(self.tree, "un travail"), "TERMINÉE"
            ),
            "Travail marqué comme terminé.",
        )

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        today = date.today().isoformat()
        for row in self.service.list_tasks():
            tags: tuple[str, ...] = ()
            if row["status"] == "TERMINÉE":
                tags = ("done",)
            elif row["status"] == "À FAIRE" and row["due_date"] < today:
                tags = ("alert",)
            self.tree.insert(
                "",
                "end",
                values=(
                    row["id"],
                    row["due_date"],
                    row["title"],
                    row["task_type"],
                    row["parcel_name"] or "—",
                    row["campaign_name"] or "—",
                    row["priority"],
                    row["status"],
                    money(row["estimated_cost"]),
                ),
                tags=tags,
            )


class StockTab(DataTab):
    def __init__(self, parent: tk.Misc, app: "MainWindow") -> None:
        super().__init__(
            parent,
            app,
            "Stocks",
            "Suivez les intrants, aliments, récoltes, emballages et matériels.",
            [
                ("id", "ID", 55),
                ("name", "Article", 220),
                ("category", "Catégorie", 180),
                ("quantity", "Disponible", 105),
                ("unit", "Unité", 80),
                ("minimum", "Seuil", 90),
                ("price", "Coût unitaire", 120),
                ("state", "État", 105),
            ],
        )
        self.add_button("Nouvel article", self.create, primary=True)
        self.add_button("Entrée", lambda: self.movement("ENTRÉE"))
        self.add_button("Sortie", lambda: self.movement("SORTIE"))

    def create(self) -> None:
        values = FormDialog.ask(
            self,
            "Nouvel article",
            [
                {"name": "name", "label": "Article", "required": True},
                {
                    "name": "category",
                    "label": "Catégorie",
                    "type": "combo",
                    "options": STOCK_CATEGORIES,
                    "default": STOCK_CATEGORIES[0],
                    "required": True,
                },
                {
                    "name": "unit",
                    "label": "Unité",
                    "type": "combo",
                    "options": STOCK_UNITS,
                    "default": STOCK_UNITS[0],
                    "required": True,
                },
                {"name": "quantity", "label": "Quantité initiale", "default": "0"},
                {"name": "minimum", "label": "Seuil minimum", "default": "0"},
                {"name": "cost", "label": "Coût unitaire", "default": "0"},
                {"name": "notes", "label": "Notes", "type": "text"},
            ],
        )
        if values is None:
            return
        self.app.perform(
            lambda: self.service.create_stock_item(
                name=values["name"],
                category=values["category"],
                unit=values["unit"],
                current_quantity=values["quantity"],
                minimum_quantity=values["minimum"],
                unit_cost=values["cost"],
                notes=values["notes"],
            ),
            "Article enregistré.",
        )

    def movement(self, movement_type: str) -> None:
        try:
            item_id = selected_id(self.tree, "un article")
        except ValidationError as exc:
            messagebox.showwarning("Sélection requise", str(exc), parent=self)
            return
        values = FormDialog.ask(
            self,
            f"{movement_type.title()} de stock",
            [
                {"name": "quantity", "label": "Quantité", "required": True},
                {
                    "name": "date",
                    "label": "Date",
                    "default": date.today().isoformat(),
                    "required": True,
                },
                {"name": "reference", "label": "Référence"},
                {"name": "notes", "label": "Notes", "type": "text"},
            ],
        )
        if values is None:
            return
        self.app.perform(
            lambda: self.service.record_stock_movement(
                item_id=item_id,
                movement_type=movement_type,
                quantity=values["quantity"],
                movement_date=values["date"],
                reference=values["reference"],
                notes=values["notes"],
            ),
            "Mouvement de stock enregistré.",
        )

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for row in self.service.list_stock_items():
            self.tree.insert(
                "",
                "end",
                values=(
                    row["id"],
                    row["name"],
                    row["category"],
                    number(row["current_quantity"]),
                    row["unit"],
                    number(row["minimum_quantity"]),
                    money(row["unit_cost"]),
                    "À réapprovisionner" if row["low_stock"] else "Disponible",
                ),
                tags=("alert",) if row["low_stock"] else (),
            )


class FinanceTab(DataTab):
    def __init__(self, parent: tk.Misc, app: "MainWindow") -> None:
        super().__init__(
            parent,
            app,
            "Finances",
            "Enregistrez les recettes et dépenses pour suivre la marge réelle.",
            [
                ("id", "ID", 55),
                ("date", "Date", 105),
                ("kind", "Type", 90),
                ("category", "Catégorie", 170),
                ("amount", "Montant", 130),
                ("campaign", "Campagne", 170),
                ("description", "Description", 300),
            ],
        )
        self.add_button("Nouvelle opération", self.create, primary=True)
        self.summary_var = tk.StringVar()
        ttk.Label(
            self.toolbar,
            textvariable=self.summary_var,
            foreground=GREEN,
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left", padx=(16, 0))

    def create(self) -> None:
        campaigns = self.service.list_campaigns()
        campaign_options = [NONE_OPTION] + [
            option(row["id"], row["name"]) for row in campaigns
        ]
        values = FormDialog.ask(
            self,
            "Nouvelle opération financière",
            [
                {
                    "name": "kind",
                    "label": "Type",
                    "type": "combo",
                    "options": FINANCE_KINDS,
                    "default": "DÉPENSE",
                    "required": True,
                },
                {
                    "name": "category",
                    "label": "Catégorie",
                    "type": "combo",
                    "options": FINANCE_CATEGORIES,
                    "default": FINANCE_CATEGORIES[0],
                    "required": True,
                },
                {"name": "amount", "label": "Montant", "required": True},
                {
                    "name": "date",
                    "label": "Date",
                    "default": date.today().isoformat(),
                    "required": True,
                },
                {
                    "name": "campaign",
                    "label": "Campagne",
                    "type": "combo",
                    "options": campaign_options,
                    "default": NONE_OPTION,
                },
                {
                    "name": "description",
                    "label": "Description",
                    "type": "text",
                    "required": True,
                },
            ],
        )
        if values is None:
            return
        self.app.perform(
            lambda: self.service.create_finance_transaction(
                kind=values["kind"],
                category=values["category"],
                amount=values["amount"],
                transaction_date=values["date"],
                description=values["description"],
                campaign_id=option_id(values["campaign"], "une campagne"),
            ),
            "Opération financière enregistrée.",
        )

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for row in self.service.list_finance_transactions():
            self.tree.insert(
                "",
                "end",
                values=(
                    row["id"],
                    row["transaction_date"],
                    row["kind"],
                    row["category"],
                    money(row["amount"]),
                    row["campaign_name"] or "—",
                    row["description"],
                ),
                tags=("alert",) if row["kind"] == "DÉPENSE" else (),
            )
        summary = self.service.finance_summary()
        self.summary_var.set(
            f"Recettes : {money(summary['revenue'])}  •  "
            f"Dépenses : {money(summary['expense'])}  •  "
            f"Solde : {money(summary['balance'])}"
        )


class PlantsTab(DataTab):
    def __init__(self, parent: tk.Misc, app: "MainWindow") -> None:
        super().__init__(
            parent,
            app,
            "Plants fruitiers",
            "Gérez les lots disponibles à la pépinière et les sorties de vente.",
            [
                ("id", "ID", 55),
                ("species", "Espèce", 135),
                ("variety", "Variété", 135),
                ("quantity", "Disponible", 100),
                ("minimum", "Seuil", 80),
                ("price", "Prix unitaire", 120),
                ("age", "Âge (mois)", 90),
                ("location", "Emplacement", 170),
                ("state", "État", 105),
            ],
        )
        self.add_button("Nouveau lot", self.create, primary=True)
        self.add_button("Entrée", lambda: self.movement("ENTRÉE"))
        self.add_button("Vente / sortie", lambda: self.movement("SORTIE"))

    def create(self) -> None:
        values = FormDialog.ask(
            self,
            "Nouveau lot de plants",
            [
                {
                    "name": "species",
                    "label": "Espèce",
                    "type": "combo",
                    "options": FRUIT_SPECIES,
                    "default": FRUIT_SPECIES[0],
                    "required": True,
                },
                {"name": "variety", "label": "Variété"},
                {"name": "quantity", "label": "Quantité initiale", "default": "0"},
                {"name": "minimum", "label": "Seuil minimum", "default": "0"},
                {"name": "price", "label": "Prix unitaire", "default": "0"},
                {"name": "age", "label": "Âge en mois", "default": "0"},
                {"name": "location", "label": "Emplacement"},
                {"name": "notes", "label": "Notes", "type": "text"},
            ],
        )
        if values is None:
            return
        self.app.perform(
            lambda: self.service.create_plant_lot(
                species=values["species"],
                variety=values["variety"],
                quantity=values["quantity"],
                minimum_quantity=values["minimum"],
                unit_price=values["price"],
                age_months=values["age"],
                location=values["location"],
                notes=values["notes"],
            ),
            "Lot de plants enregistré.",
        )

    def movement(self, movement_type: str) -> None:
        try:
            lot_id = selected_id(self.tree, "un lot de plants")
        except ValidationError as exc:
            messagebox.showwarning("Sélection requise", str(exc), parent=self)
            return
        values = FormDialog.ask(
            self,
            "Entrée de plants" if movement_type == "ENTRÉE" else "Vente / sortie",
            [
                {"name": "quantity", "label": "Nombre de plants", "required": True},
                {
                    "name": "date",
                    "label": "Date",
                    "default": date.today().isoformat(),
                    "required": True,
                },
                {"name": "reference", "label": "Client / référence"},
                {"name": "notes", "label": "Notes", "type": "text"},
            ],
        )
        if values is None:
            return
        self.app.perform(
            lambda: self.service.record_plant_movement(
                lot_id=lot_id,
                movement_type=movement_type,
                quantity=values["quantity"],
                movement_date=values["date"],
                reference=values["reference"],
                notes=values["notes"],
            ),
            "Mouvement de plants enregistré.",
        )

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for row in self.service.list_plant_lots():
            self.tree.insert(
                "",
                "end",
                values=(
                    row["id"],
                    row["species"],
                    row["variety"] or "—",
                    row["quantity"],
                    row["minimum_quantity"],
                    money(row["unit_price"]),
                    row["age_months"],
                    row["location"] or "—",
                    "Stock faible" if row["low_stock"] else "Disponible",
                ),
                tags=("alert",) if row["low_stock"] else (),
            )


class ObservationsTab(DataTab):
    def __init__(self, parent: tk.Misc, app: "MainWindow") -> None:
        super().__init__(
            parent,
            app,
            "Observations terrain",
            "Conservez les constats et photos qui pourront alimenter un futur assistant IA.",
            [
                ("id", "ID", 55),
                ("date", "Date", 105),
                ("category", "Catégorie", 155),
                ("parcel", "Parcelle", 155),
                ("campaign", "Campagne", 155),
                ("description", "Observation", 330),
                ("photo", "Photo", 180),
            ],
        )
        self.add_button("Nouvelle observation", self.create, primary=True)
        self.add_button("Ouvrir la photo", self.open_photo)

    def create(self) -> None:
        parcels = self.service.list_parcels(active_only=True)
        campaigns = self.service.list_campaigns()
        parcel_options = [NONE_OPTION] + [
            option(row["id"], row["name"]) for row in parcels
        ]
        campaign_options = [NONE_OPTION] + [
            option(row["id"], row["name"]) for row in campaigns
        ]
        values = FormDialog.ask(
            self,
            "Nouvelle observation",
            [
                {
                    "name": "date",
                    "label": "Date",
                    "default": date.today().isoformat(),
                    "required": True,
                },
                {
                    "name": "category",
                    "label": "Catégorie",
                    "type": "combo",
                    "options": OBSERVATION_CATEGORIES,
                    "default": OBSERVATION_CATEGORIES[0],
                    "required": True,
                },
                {
                    "name": "parcel",
                    "label": "Parcelle",
                    "type": "combo",
                    "options": parcel_options,
                    "default": NONE_OPTION,
                },
                {
                    "name": "campaign",
                    "label": "Campagne",
                    "type": "combo",
                    "options": campaign_options,
                    "default": NONE_OPTION,
                },
                {
                    "name": "description",
                    "label": "Observation",
                    "type": "text",
                    "height": 6,
                    "required": True,
                },
                {"name": "photo", "label": "Photo", "type": "file"},
            ],
        )
        if values is None:
            return
        self.app.perform(
            lambda: self.service.create_observation(
                observed_at=values["date"],
                category=values["category"],
                description=values["description"],
                parcel_id=option_id(values["parcel"], "une parcelle"),
                campaign_id=option_id(values["campaign"], "une campagne"),
                photo_path=values["photo"],
            ),
            "Observation enregistrée.",
        )

    def open_photo(self) -> None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning(
                "Sélection requise",
                "Veuillez sélectionner une observation.",
                parent=self,
            )
            return
        values = self.tree.item(selection[0], "values")
        photo = str(values[6])
        if not photo or photo == "—":
            messagebox.showinfo(
                "Aucune photo",
                "Cette observation ne contient pas de photo.",
                parent=self,
            )
            return
        path = Path(photo)
        if not path.is_file():
            messagebox.showerror(
                "Photo introuvable",
                f"Le fichier n'existe plus :\n{path}",
                parent=self,
            )
            return
        webbrowser.open(path.as_uri())

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for row in self.service.list_observations():
            self.tree.insert(
                "",
                "end",
                values=(
                    row["id"],
                    row["observed_at"],
                    row["category"],
                    row["parcel_name"] or "—",
                    row["campaign_name"] or "—",
                    row["description"],
                    row["photo_path"] or "—",
                ),
            )


class NewsTab(ttk.Frame):
    """Curated agricultural news filtered from authentic Cameroonian sources."""

    def __init__(self, parent: tk.Misc, app: "MainWindow") -> None:
        super().__init__(parent, padding=18)
        self.app = app
        self.news_service = app.news_service
        self._headline_links: dict[str, str] = {}
        self._source_urls: dict[str, str] = {}

        heading = ttk.Frame(self)
        heading.pack(fill="x", pady=(0, 6))
        ttk.Label(heading, text="Actualités agricoles", style="Heading.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            heading,
            text=(
                "Sélection de sources camerounaises authentiques : institutions "
                "officielles, recherche agricole et presse économique. Une "
                "connexion Internet est nécessaire pour actualiser ; les articles "
                "déjà récupérés restent consultables hors connexion."
            ),
            foreground=MUTED,
            wraplength=980,
            justify="left",
        ).pack(anchor="w", pady=(3, 0))

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(10, 10))
        ttk.Button(
            toolbar,
            text="Actualiser les actualités",
            style="Primary.TButton",
            command=self.refresh_online,
        ).pack(side="left")
        ttk.Button(
            toolbar,
            text="Ouvrir l'article sélectionné",
            command=self.open_selected_article,
        ).pack(side="left", padx=(8, 0))
        self.status_var = tk.StringVar(
            value="Aucune actualisation effectuée pour l'instant."
        )
        ttk.Label(toolbar, textvariable=self.status_var, foreground=MUTED).pack(
            side="left", padx=(16, 0)
        )

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True)

        sources_frame = ttk.LabelFrame(body, text="Sources suivies", padding=10)
        headlines_frame = ttk.LabelFrame(
            body, text="Dernières publications récupérées", padding=10
        )
        body.add(sources_frame, weight=2)
        body.add(headlines_frame, weight=3)

        self.sources_tree = build_tree(
            sources_frame,
            [
                ("name", "Source", 250),
                ("category", "Catégorie", 170),
                ("feed", "Flux auto.", 80),
            ],
            height=14,
        )
        self.sources_tree.pack(fill="both", expand=True)
        ttk.Button(
            sources_frame,
            text="Ouvrir le site de la source sélectionnée",
            command=self.open_selected_source,
        ).pack(fill="x", pady=(8, 0))

        self.headlines_tree = build_tree(
            headlines_frame,
            [
                ("date", "Date", 95),
                ("source", "Source", 150),
                ("title", "Titre", 420),
            ],
            height=14,
        )
        self.headlines_tree.pack(fill="both", expand=True)

    def refresh_online(self) -> None:
        result = self.app.perform(
            self.news_service.refresh_all, "Actualités mises à jour."
        )
        if result is not None:
            ok = sum(1 for value in result.values() if value >= 0)
            failed = sum(1 for value in result.values() if value < 0)
            if failed:
                self.status_var.set(
                    f"{ok} source(s) mise(s) à jour, {failed} indisponible(s) "
                    "pour l'instant."
                )
            elif ok:
                self.status_var.set(f"{ok} source(s) mise(s) à jour avec succès.")
            else:
                self.status_var.set("Aucune source à flux automatique à mettre à jour.")
        self.refresh()

    def open_selected_article(self) -> None:
        selection = self.headlines_tree.selection()
        if not selection:
            messagebox.showinfo(
                "Sélection requise",
                "Veuillez sélectionner un article dans la liste.",
                parent=self,
            )
            return
        link = self._headline_links.get(selection[0])
        if link:
            webbrowser.open(link)

    def open_selected_source(self) -> None:
        selection = self.sources_tree.selection()
        if not selection:
            messagebox.showinfo(
                "Sélection requise",
                "Veuillez sélectionner une source dans la liste.",
                parent=self,
            )
            return
        url = self._source_urls.get(selection[0])
        if url:
            webbrowser.open(url)

    def refresh(self) -> None:
        self.sources_tree.delete(*self.sources_tree.get_children())
        self._source_urls.clear()
        for source in self.news_service.list_sources():
            item_id = self.sources_tree.insert(
                "",
                "end",
                values=(
                    source["name"],
                    source["category"],
                    "Oui" if source.get("feed_url") else "Non",
                ),
            )
            self._source_urls[item_id] = source["site_url"]

        source_names = {
            source["key"]: source["name"] for source in self.news_service.list_sources()
        }
        self.headlines_tree.delete(*self.headlines_tree.get_children())
        self._headline_links.clear()
        for item in self.news_service.list_cached_items():
            item_id = self.headlines_tree.insert(
                "",
                "end",
                values=(
                    item["published_at"] or "—",
                    source_names.get(item["source_key"], item["source_key"]),
                    item["title"],
                ),
            )
            self._headline_links[item_id] = item["link"]


class WeatherTab(ttk.Frame):
    """Seven-day forecast for Haute-Sanaga communes, based on Open-Meteo."""

    def __init__(self, parent: tk.Misc, app: "MainWindow") -> None:
        super().__init__(parent, padding=18)
        self.app = app
        self.weather_service = app.weather_service
        locations = self.weather_service.list_locations()
        self.location_labels: dict[str, str] = {
            key: str(value["label"]) for key, value in locations.items()
        }
        self.location_lookup: dict[str, str] = {
            label: key for key, label in self.location_labels.items()
        }

        heading = ttk.Frame(self)
        heading.pack(fill="x", pady=(0, 6))
        ttk.Label(heading, text="Météo — Haute-Sanaga", style="Heading.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            heading,
            text=(
                "Prévisions sur 7 jours (source : Open-Meteo, gratuite et sans "
                "clé). Une connexion Internet est nécessaire pour actualiser ; la "
                "dernière prévision récupérée reste consultable hors connexion."
            ),
            foreground=MUTED,
            wraplength=980,
            justify="left",
        ).pack(anchor="w", pady=(3, 0))

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(10, 10))
        ttk.Label(toolbar, text="Localité :").pack(side="left")
        self.location_var = tk.StringVar(
            value=self.location_labels[DEFAULT_WEATHER_LOCATION]
        )
        self.location_combo = ttk.Combobox(
            toolbar,
            textvariable=self.location_var,
            values=list(self.location_labels.values()),
            state="readonly",
            width=26,
        )
        self.location_combo.pack(side="left", padx=(8, 16))
        self.location_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self.refresh()
        )
        ttk.Button(
            toolbar,
            text="Actualiser la météo",
            style="Primary.TButton",
            command=self.refresh_online,
        ).pack(side="left")
        ttk.Button(
            toolbar,
            text="Bulletins officiels ONACC",
            command=lambda: webbrowser.open("https://onacc.cm/fr/bulletins"),
        ).pack(side="left", padx=(8, 0))
        self.status_var = tk.StringVar(
            value="Aucune prévision enregistrée pour l'instant."
        )
        ttk.Label(toolbar, textvariable=self.status_var, foreground=MUTED).pack(
            side="left", padx=(16, 0)
        )

        table_holder = ttk.Frame(self)
        table_holder.pack(fill="both", expand=True)
        self.tree = build_tree(
            table_holder,
            [
                ("date", "Date", 105),
                ("condition", "Condition", 200),
                ("tmin", "Min (°C)", 85),
                ("tmax", "Max (°C)", 85),
                ("rain", "Pluie (mm)", 95),
                ("prob", "Probabilité", 95),
                ("wind", "Vent max (km/h)", 125),
            ],
            height=12,
        )
        self.tree.pack(fill="both", expand=True)

    def _current_location_key(self) -> str:
        return self.location_lookup.get(self.location_var.get(), DEFAULT_WEATHER_LOCATION)

    def refresh_online(self) -> None:
        location_key = self._current_location_key()
        result = self.app.perform(
            lambda: self.weather_service.fetch_and_cache(location_key),
            "Prévisions météo mises à jour.",
        )
        if result is not None:
            self.status_var.set(f"{result} jour(s) de prévision récupéré(s).")
        self.refresh()

    def refresh(self) -> None:
        location_key = self._current_location_key()
        self.tree.delete(*self.tree.get_children())
        for day in self.weather_service.list_cached_forecast(location_key):
            self.tree.insert(
                "",
                "end",
                values=(
                    day["forecast_date"],
                    describe_weather_code(day["weather_code"]),
                    optional_number(day["temperature_min"]),
                    optional_number(day["temperature_max"]),
                    optional_number(day["precipitation_mm"]),
                    optional_number(day["precipitation_probability"], suffix="%"),
                    optional_number(day["wind_speed_max"]),
                ),
            )
        last_updated = self.weather_service.last_updated(location_key)
        self.status_var.set(
            f"Dernière mise à jour : {last_updated}"
            if last_updated
            else "Aucune prévision enregistrée pour cette localité."
        )


class AdvisoryTab(ttk.Frame):
    """Rule-based agricultural advisory assistant (explainable, not a black box)."""

    def __init__(self, parent: tk.Misc, app: "MainWindow") -> None:
        super().__init__(parent, padding=18)
        self.app = app
        self.advisory_service = app.advisory_service
        self._explanations: dict[str, str] = {}

        locations = app.weather_service.list_locations()
        self.location_labels: dict[str, str] = {
            key: str(value["label"]) for key, value in locations.items()
        }
        self.location_lookup: dict[str, str] = {
            label: key for key, label in self.location_labels.items()
        }

        heading = ttk.Frame(self)
        heading.pack(fill="x", pady=(0, 6))
        ttk.Label(heading, text="Assistant agricole", style="Heading.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            heading,
            text=(
                "Système d'aide à la décision basé sur des règles agronomiques et "
                "météorologiques (calendrier régional des saisons des pluies, "
                "prévisions Open-Meteo, suivi de stock et de travaux). Ce n'est "
                "pas un diagnostic automatique : chaque recommandation indique sa "
                "règle d'origine et doit être confrontée aux bulletins "
                "ONACC/MINADER et, en cas de doute, à l'avis d'un agronome, d'un "
                "technicien ou d'un vétérinaire."
            ),
            foreground=MUTED,
            wraplength=980,
            justify="left",
        ).pack(anchor="w", pady=(3, 0))

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(10, 10))
        ttk.Label(toolbar, text="Localité météo :").pack(side="left")
        self.location_var = tk.StringVar(
            value=self.location_labels[DEFAULT_WEATHER_LOCATION]
        )
        self.location_combo = ttk.Combobox(
            toolbar,
            textvariable=self.location_var,
            values=list(self.location_labels.values()),
            state="readonly",
            width=26,
        )
        self.location_combo.pack(side="left", padx=(8, 16))
        self.location_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self.refresh()
        )
        ttk.Button(
            toolbar,
            text="Actualiser les recommandations",
            style="Primary.TButton",
            command=self.refresh,
        ).pack(side="left")

        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True)

        list_frame = ttk.Frame(body)
        detail_frame = ttk.LabelFrame(
            body, text="Explication de la recommandation sélectionnée", padding=10
        )
        body.add(list_frame, weight=3)
        body.add(detail_frame, weight=2)

        self.tree = build_tree(
            list_frame,
            [
                ("level", "Niveau", 95),
                ("title", "Recommandation", 420),
                ("source", "Règle / source", 260),
            ],
            height=10,
        )
        self.tree.tag_configure(
            "urgent", background="#fdecea", foreground="#8d1c0f"
        )
        self.tree.tag_configure(
            "attention", background="#fff4e0", foreground="#8d5300"
        )
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._show_selected_explanation)

        self.detail_text = tk.Text(
            detail_frame, wrap="word", height=8, relief="flat", bg=CREAM
        )
        self.detail_text.pack(fill="both", expand=True)
        self.detail_text.configure(state="disabled")

    def _current_location_key(self) -> str:
        return self.location_lookup.get(self.location_var.get(), DEFAULT_WEATHER_LOCATION)

    def _show_selected_explanation(self, _event: object = None) -> None:
        selection = self.tree.selection()
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        if selection:
            self.detail_text.insert("1.0", self._explanations.get(selection[0], ""))
        self.detail_text.configure(state="disabled")

    def refresh(self) -> None:
        location_key = self._current_location_key()
        recommendations = self.advisory_service.generate_recommendations(
            location_key=location_key
        )
        level_labels = {"urgent": "Urgent", "attention": "Attention", "info": "Info"}
        self.tree.delete(*self.tree.get_children())
        self._explanations.clear()
        for recommendation in recommendations:
            level = recommendation["level"]
            item_id = self.tree.insert(
                "",
                "end",
                values=(
                    level_labels.get(level, level),
                    recommendation["title"],
                    recommendation["source"],
                ),
                tags=(level,) if level in ("urgent", "attention") else (),
            )
            self._explanations[item_id] = recommendation["explanation"]
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
        self._show_selected_explanation()


class MainWindow(tk.Tk):
    """Main application window."""

    def __init__(self, service: AgricultureService, project_root: Path) -> None:
        super().__init__()
        self.service = service
        self.project_root = project_root
        self.weather_service = WeatherService(self.service.database)
        self.news_service = NewsService(self.service.database)
        self.advisory_service = AdvisoryService(self.service, self.weather_service)
        self.title(f"{ORGANIZATION_NAME} — Gestion agricole {REGION_NAME}")
        self.geometry("1440x850")
        self.minsize(1120, 700)
        self.configure(bg=CREAM)

        log_path = self.project_root / "data" / "gic_agriculture.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=log_path,
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            encoding="utf-8",
        )

        self._configure_styles()
        self._configure_menu()
        self._build_header()
        self._build_body()
        self._build_status()
        self.refresh_all()

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        available = style.theme_names()
        if "vista" in available:
            style.theme_use("vista")
        elif "clam" in available:
            style.theme_use("clam")
        style.configure("TFrame", background=CREAM)
        style.configure("TLabel", background=CREAM, font=("Segoe UI", 10))
        style.configure(
            "Heading.TLabel",
            background=CREAM,
            foreground=DARK_GREEN,
            font=("Segoe UI", 18, "bold"),
        )
        style.configure("TButton", padding=(10, 6), font=("Segoe UI", 9))
        style.configure(
            "Primary.TButton",
            background=GREEN,
            foreground="white",
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#087037"), ("pressed", DARK_GREEN)],
            foreground=[("disabled", "#e0e0e0"), ("!disabled", "white")],
        )
        style.configure(
            "Treeview",
            rowheight=29,
            font=("Segoe UI", 9),
            fieldbackground="white",
            background="white",
        )
        style.configure(
            "Treeview.Heading",
            font=("Segoe UI", 9, "bold"),
            background=LIGHT_GREEN,
            foreground=DARK_GREEN,
        )
        style.configure("TNotebook", background=CREAM, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            padding=(13, 8),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", LIGHT_GREEN)],
            foreground=[("selected", GREEN)],
        )

    def _configure_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Sauvegarder la base…", command=self.backup)
        file_menu.add_command(label="Exporter en CSV…", command=self.export_csv)
        file_menu.add_separator()
        file_menu.add_command(
            label="Actualiser actualités et météo (Internet requis)",
            command=self.refresh_online_data,
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Ajouter les données de démonstration", command=self.seed_demo
        )
        file_menu.add_separator()
        file_menu.add_command(label="Quitter", command=self.destroy)
        menu.add_cascade(label="Fichier", menu=file_menu)

        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="À propos", command=self.about)
        menu.add_cascade(label="Aide", menu=help_menu)
        self.config(menu=menu)

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=DARK_GREEN, padx=22, pady=12)
        header.pack(fill="x")

        logo_path = self.project_root / "assets" / "gic_innovation_logo_rond.png"
        self.logo_image: tk.PhotoImage | None = None
        if logo_path.is_file():
            try:
                original = tk.PhotoImage(file=logo_path)
                factor = max(1, max(original.width(), original.height()) // 78)
                self.logo_image = original.subsample(factor, factor)
                self.iconphoto(True, self.logo_image)
                tk.Label(
                    header,
                    image=self.logo_image,
                    bg=DARK_GREEN,
                    borderwidth=0,
                ).pack(side="left", padx=(0, 16))
            except tk.TclError as exc:
                logging.exception("Impossible de charger le logo : %s", exc)

        title_holder = tk.Frame(header, bg=DARK_GREEN)
        title_holder.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_holder,
            text=f"{ORGANIZATION_NAME} — Gestion agricole",
            bg=DARK_GREEN,
            fg="white",
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_holder,
            text=(
                f"Adaptée à la {REGION_NAME} • Créée par la famille Blang "
                "• Fonctionnement hors connexion"
            ),
            bg=DARK_GREEN,
            fg="#cbe8d1",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(3, 0))

        tk.Label(
            header,
            text=datetime.now().strftime("%d/%m/%Y"),
            bg=DARK_GREEN,
            fg="white",
            font=("Segoe UI", 11, "bold"),
        ).pack(side="right", padx=10)

    def _build_body(self) -> None:
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        self.dashboard_tab = DashboardTab(self.notebook, self.service)
        self.parcels_tab = ParcelsTab(self.notebook, self)
        self.campaigns_tab = CampaignsTab(self.notebook, self)
        self.tasks_tab = TasksTab(self.notebook, self)
        self.stock_tab = StockTab(self.notebook, self)
        self.finance_tab = FinanceTab(self.notebook, self)
        self.plants_tab = PlantsTab(self.notebook, self)
        self.observations_tab = ObservationsTab(self.notebook, self)
        self.news_tab = NewsTab(self.notebook, self)
        self.weather_tab = WeatherTab(self.notebook, self)
        self.advisory_tab = AdvisoryTab(self.notebook, self)

        self.tabs = (
            self.dashboard_tab,
            self.parcels_tab,
            self.campaigns_tab,
            self.tasks_tab,
            self.stock_tab,
            self.finance_tab,
            self.plants_tab,
            self.observations_tab,
            self.news_tab,
            self.weather_tab,
            self.advisory_tab,
        )
        for tab, label in (
            (self.dashboard_tab, "Tableau de bord"),
            (self.parcels_tab, "Parcelles"),
            (self.campaigns_tab, "Campagnes"),
            (self.tasks_tab, "Travaux"),
            (self.stock_tab, "Stocks"),
            (self.finance_tab, "Finances"),
            (self.plants_tab, "Plants fruitiers"),
            (self.observations_tab, "Observations"),
            (self.news_tab, "Actualités"),
            (self.weather_tab, "Météo"),
            (self.advisory_tab, "Assistant agricole"),
        ):
            self.notebook.add(tab, text=label)

    def _build_status(self) -> None:
        self.status_var = tk.StringVar(
            value=f"Base locale : {self.service.database.path}"
        )
        status = tk.Label(
            self,
            textvariable=self.status_var,
            bg="#e5ece7",
            fg=DARK_GREEN,
            anchor="w",
            padx=12,
            pady=5,
            font=("Segoe UI", 9),
        )
        status.pack(fill="x", side="bottom")

    def refresh_all(self) -> None:
        for tab in self.tabs:
            tab.refresh()

    def perform(self, operation: Callable[[], Any], success_message: str) -> Any:
        try:
            result = operation()
            self.refresh_all()
        except ValidationError as exc:
            messagebox.showwarning("Donnée à vérifier", str(exc), parent=self)
            return None
        except NetworkError as exc:
            logging.warning("Connexion en ligne indisponible : %s", exc)
            messagebox.showwarning(
                "Connexion Internet requise",
                (
                    f"{exc}\n\n"
                    "Cette fonction nécessite une connexion Internet. Les "
                    "données déjà enregistrées restent disponibles hors "
                    "connexion."
                ),
                parent=self,
            )
            return None
        except Exception as exc:
            logging.error(
                "Erreur inattendue : %s\n%s", exc, traceback.format_exc()
            )
            messagebox.showerror(
                "Erreur",
                (
                    "L'opération n'a pas été enregistrée.\n\n"
                    f"Détail : {exc}\n\n"
                    "Consultez data\\gic_agriculture.log si le problème persiste."
                ),
                parent=self,
            )
            return None
        self.status_var.set(success_message)
        return result

    def refresh_online_data(self) -> None:
        def _do_refresh() -> tuple[dict[str, int], dict[str, int]]:
            news_result = self.news_service.refresh_all()
            weather_result = self.weather_service.refresh_all_locations()
            return news_result, weather_result

        result = self.perform(_do_refresh, "Actualités et météo mises à jour.")
        if result is None:
            return
        news_result, weather_result = result
        news_ok = sum(1 for value in news_result.values() if value >= 0)
        news_failed = sum(1 for value in news_result.values() if value < 0)
        weather_ok = sum(1 for value in weather_result.values() if value >= 0)
        weather_failed = sum(1 for value in weather_result.values() if value < 0)
        messagebox.showinfo(
            "Actualisation en ligne",
            (
                f"Actualités : {news_ok} source(s) mise(s) à jour, "
                f"{news_failed} indisponible(s).\n"
                f"Météo : {weather_ok} localité(s) mise(s) à jour, "
                f"{weather_failed} indisponible(s)."
            ),
            parent=self,
        )

    def backup(self) -> None:
        default_name = f"gic_agriculture_{datetime.now():%Y%m%d_%H%M}.db"
        destination = filedialog.asksaveasfilename(
            parent=self,
            title="Sauvegarder la base",
            initialfile=default_name,
            defaultextension=".db",
            filetypes=(("Base SQLite", "*.db"), ("Tous les fichiers", "*.*")),
        )
        if not destination:
            return
        self.perform(
            lambda: self.service.database.backup_to(destination),
            f"Sauvegarde créée : {destination}",
        )

    def export_csv(self) -> None:
        selected = filedialog.askdirectory(
            parent=self, title="Choisir le dossier d'export"
        )
        if not selected:
            return
        destination = (
            Path(selected) / f"export_gic_{datetime.now():%Y%m%d_%H%M%S}"
        )
        self.perform(
            lambda: self.service.export_csv(destination),
            f"Export CSV créé : {destination}",
        )

    def seed_demo(self) -> None:
        if not messagebox.askyesno(
            "Données de démonstration",
            (
                "Ajouter un exemple de parcelle, campagne, tâche, stock et plants ?\n"
                "L'ajout est refusé si une parcelle existe déjà."
            ),
            parent=self,
        ):
            return
        result = self.perform(
            self.service.seed_demo_data,
            "Données de démonstration ajoutées.",
        )
        if result is False:
            messagebox.showinfo(
                "Aucun ajout",
                "La base contient déjà une parcelle.",
                parent=self,
            )

    def about(self) -> None:
        messagebox.showinfo(
            f"À propos de {ORGANIZATION_NAME}",
            (
                f"{ORGANIZATION_NAME}\n"
                f"Gestion agricole adaptée à la {REGION_NAME}\n\n"
                "Créée par la famille Blang.\n"
                "Version 0.2.0 — stockage local SQLite ; les onglets Parcelles, "
                "Campagnes, Travaux, Stocks, Finances, Plants fruitiers et "
                "Observations fonctionnent entièrement hors connexion.\n\n"
                "Les onglets Actualités, Météo et Assistant agricole ajoutent des "
                "informations complémentaires : actualités filtrées depuis des "
                "sources camerounaises authentiques (MINADER, IRAD, presse "
                "économique), prévisions météo Open-Meteo pour la Haute-Sanaga, "
                "et un assistant de recommandations. Ces trois onglets ont "
                "besoin d'Internet pour se mettre à jour ; les dernières "
                "données récupérées restent consultables hors connexion.\n\n"
                "L'assistant agricole est un système de règles agronomiques et "
                "météorologiques explicable : chaque recommandation indique la "
                "règle qui l'a produite. Ce n'est pas un modèle d'intelligence "
                "artificielle entraîné sur des données secrètes, et il ne "
                "remplace pas l'avis d'un agronome, d'un technicien ou d'un "
                "vétérinaire."
            ),
            parent=self,
        )
