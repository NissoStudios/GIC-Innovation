"""Rule-based agricultural advisory engine — explainable, offline-capable.

Why rule-based rather than a trained machine-learning model?
--------------------------------------------------------------
Modern research on crop-recommendation systems (see README, section
« Sources ») increasingly favours *explainable* decision support: every
recommendation should state the concrete rule and data point that produced
it, rather than an opaque score from a model trained on data whose quality
cannot be verified. GIC INNOVATION does not have access to a verified,
representative historical dataset of soils, yields and pest incidence for
the Haute-Sanaga; training a statistical model on invented or unrelated
data would be dishonest and could lead to harmful advice.

This module therefore implements a transparent expert system: each
recommendation always carries a ``source`` field naming the rule and
reference (regional rainy-season calendar, live Open-Meteo forecast, or the
application's own stock/task tracking) that triggered it. This mirrors the
architecture used by real agricultural extension decision-support tools
(FAO digital advisory guidelines, USDA Extension rule-based advisories)
before any statistical layer is added — a foundation that can later be
extended with machine learning once real local data is collected, still
under the same explainability principle.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .constants import CROP_CALENDAR, HAUTE_SANAGA_LOCATIONS
from .services import AgricultureService
from .weather import WeatherService

# Cumulative precipitation, in millimetres, considered over the forecast
# horizon below which the assistant flags a short-term drought risk.
DROUGHT_CUMULATIVE_THRESHOLD_MM = 5.0

# A single forecast day at or above this precipitation is considered
# "heavy rain" on its own, regardless of the cumulative total.
HEAVY_RAIN_DAY_THRESHOLD_MM = 20.0

# Cumulative precipitation over the horizon considered high enough to raise
# a waterlogging / fungal-disease-risk flag.
WATERLOGGING_CUMULATIVE_THRESHOLD_MM = 60.0

# Number of upcoming cached forecast days examined for the weather rules.
FORECAST_HORIZON_DAYS = 7

_LEVEL_ORDER = {"urgent": 0, "attention": 1, "info": 2}


def _month_in_window(month: int, start_month: int, end_month: int) -> bool:
    if start_month <= end_month:
        return start_month <= month <= end_month
    return month >= start_month or month <= end_month


def _format_windows(windows: tuple[dict[str, int], ...]) -> str:
    return ", ".join(
        f"{window['label']} (mois {window['start_month']} à {window['end_month']})"
        for window in windows
    )


class AdvisoryService:
    """Combines campaigns, weather and operational data into advice."""

    def __init__(
        self,
        agriculture_service: AgricultureService,
        weather_service: WeatherService,
    ) -> None:
        self.agriculture_service = agriculture_service
        self.weather_service = weather_service

    def generate_recommendations(
        self, *, location_key: str = "nanga_eboko"
    ) -> list[dict[str, Any]]:
        """Return recommendations sorted from most to least urgent.

        Each recommendation is a dict with ``level`` (``urgent``,
        ``attention`` or ``info``), ``title``, ``explanation`` (the reason,
        in French, always naming the concrete data behind it) and
        ``source`` (short label of the rule/reference used).
        """

        recommendations: list[dict[str, Any]] = []
        recommendations.extend(self._campaign_calendar_recommendations())
        recommendations.extend(self._weather_recommendations(location_key))
        recommendations.extend(self._operational_recommendations())
        recommendations.sort(key=lambda item: _LEVEL_ORDER.get(item["level"], 3))
        return recommendations

    def _campaign_calendar_recommendations(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        today = date.today()
        for campaign in self.agriculture_service.list_campaigns():
            if campaign["status"] not in ("ACTIVE", "PLANIFIÉE"):
                continue
            calendar = CROP_CALENDAR.get(campaign["crop"])
            if calendar is None:
                continue

            planting_text = campaign.get("planting_date")
            try:
                reference_date = (
                    date.fromisoformat(planting_text) if planting_text else today
                )
            except ValueError:
                reference_date = today

            windows: tuple[dict[str, int], ...] = calendar["windows"]
            in_window = any(
                _month_in_window(
                    reference_date.month, window["start_month"], window["end_month"]
                )
                for window in windows
            )
            windows_label = _format_windows(windows)
            campaign_label = f"{campaign['crop']} — {campaign['name']}"

            if in_window:
                results.append(
                    {
                        "level": "info",
                        "title": f"{campaign_label} : période cohérente",
                        "explanation": (
                            f"La date retenue ({reference_date.isoformat()}) correspond à "
                            "une fenêtre habituelle pour cette culture dans la région du "
                            f"Centre : {windows_label}."
                        ),
                        "source": (
                            "Calendrier agricole régional (saisons des pluies, "
                            "région du Centre)"
                        ),
                    }
                )
            else:
                results.append(
                    {
                        "level": "attention",
                        "title": f"{campaign_label} : période à vérifier",
                        "explanation": (
                            f"La date retenue ({reference_date.isoformat()}) est en dehors "
                            "des fenêtres habituelles pour cette culture dans la région du "
                            f"Centre : {windows_label}. Cela ne signifie pas forcément une "
                            "erreur : vérifiez la pluviométrie réellement observée et les "
                            "bulletins ONACC/MINADER de la campagne avant de confirmer."
                        ),
                        "source": (
                            "Calendrier agricole régional (saisons des pluies, "
                            "région du Centre)"
                        ),
                    }
                )
        return results

    def _weather_recommendations(self, location_key: str) -> list[dict[str, Any]]:
        if location_key not in HAUTE_SANAGA_LOCATIONS:
            return []
        location_label = HAUTE_SANAGA_LOCATIONS[location_key]["label"]
        forecast = self.weather_service.list_cached_forecast(location_key)
        if not forecast:
            return [
                {
                    "level": "info",
                    "title": "Prévisions météo non disponibles",
                    "explanation": (
                        f"Aucune prévision n'est encore enregistrée pour {location_label}. "
                        "Ouvrez l'onglet Météo et cliquez sur « Actualiser » avec une "
                        "connexion Internet pour activer les règles météo de cet "
                        "assistant."
                    ),
                    "source": "Suivi météo local (Open-Meteo)",
                }
            ]

        horizon = forecast[:FORECAST_HORIZON_DAYS]
        total_precipitation = sum(
            float(day["precipitation_mm"] or 0) for day in horizon
        )
        heavy_rain_days = [
            day
            for day in horizon
            if float(day["precipitation_mm"] or 0) >= HEAVY_RAIN_DAY_THRESHOLD_MM
        ]

        if total_precipitation <= DROUGHT_CUMULATIVE_THRESHOLD_MM:
            return [
                {
                    "level": "attention",
                    "title": f"Risque de sécheresse à court terme — {location_label}",
                    "explanation": (
                        f"Les prévisions cumulent seulement {total_precipitation:.0f} mm "
                        f"de pluie sur {len(horizon)} jours. Pensez au paillage, à "
                        "l'arrosage des jeunes plants et des pépinières, et surveillez "
                        "les cultures récemment semées."
                    ),
                    "source": "Prévisions Open-Meteo (cumul de précipitations)",
                }
            ]

        if total_precipitation >= WATERLOGGING_CUMULATIVE_THRESHOLD_MM or heavy_rain_days:
            heavy_note = (
                f", dont {len(heavy_rain_days)} jour(s) de pluie forte"
                if heavy_rain_days
                else ""
            )
            return [
                {
                    "level": "attention",
                    "title": f"Fortes pluies attendues — {location_label}",
                    "explanation": (
                        f"Cumul prévu de {total_precipitation:.0f} mm sur "
                        f"{len(horizon)} jours{heavy_note}. Vérifiez le drainage des "
                        "parcelles, retardez si possible les traitements, et surveillez "
                        "les signes de maladies fongiques (feuilles tachées, "
                        "pourriture)."
                    ),
                    "source": "Prévisions Open-Meteo (cumul de précipitations)",
                }
            ]

        return [
            {
                "level": "info",
                "title": f"Conditions météo proches de la normale — {location_label}",
                "explanation": (
                    f"Cumul prévu de {total_precipitation:.0f} mm sur {len(horizon)} "
                    "jours, sans excès ni déficit marqué détecté par les règles de cet "
                    "assistant."
                ),
                "source": "Prévisions Open-Meteo (cumul de précipitations)",
            }
        ]

    def _operational_recommendations(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        summary = self.agriculture_service.dashboard_summary()

        low_stock = summary.get("low_stock", [])
        if low_stock:
            names = ", ".join(row["name"] for row in low_stock[:5])
            results.append(
                {
                    "level": "urgent" if len(low_stock) >= 3 else "attention",
                    "title": "Stocks sous le seuil minimum",
                    "explanation": (
                        f"{len(low_stock)} article(s) sont au niveau ou sous le seuil "
                        f"minimum défini : {names}. Planifiez un réapprovisionnement."
                    ),
                    "source": "Suivi de stock local",
                }
            )

        today_iso = date.today().isoformat()
        overdue_tasks = [
            task
            for task in self.agriculture_service.list_tasks(pending_only=True)
            if task["due_date"] < today_iso
        ]
        if overdue_tasks:
            results.append(
                {
                    "level": "urgent",
                    "title": "Travaux en retard",
                    "explanation": (
                        f"{len(overdue_tasks)} travail(aux) planifié(s) ont dépassé "
                        "leur échéance. Consultez l'onglet Travaux pour les "
                        "replanifier ou les clôturer."
                    ),
                    "source": "Suivi des travaux local",
                }
            )

        return results


__all__ = ["AdvisoryService"]
