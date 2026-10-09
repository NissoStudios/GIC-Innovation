"""Entry point for the GIC INNOVATION desktop application."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from gic_agri.database import Database
from gic_agri.services import AgricultureService


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "gic_agriculture.db"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gestion agricole hors connexion de GIC INNOVATION."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help="Chemin du fichier SQLite.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Initialise et vérifie la base sans ouvrir l'interface.",
    )
    parser.add_argument(
        "--seed-demo",
        action="store_true",
        help="Ajoute un petit jeu de démonstration si la base est vide.",
    )
    parser.add_argument(
        "--refresh-online",
        action="store_true",
        help=(
            "Récupère les actualités agricoles et la météo Haute-Sanaga sans "
            "ouvrir l'interface (nécessite une connexion Internet)."
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    database = Database(args.database)
    service = AgricultureService(database)

    if args.seed_demo:
        created = service.seed_demo_data()
        print(
            "Données de démonstration ajoutées."
            if created
            else "La base contient déjà des parcelles ; aucune donnée ajoutée."
        )

    if args.check:
        print(json.dumps(database.healthcheck(), ensure_ascii=False, indent=2))
        return 0

    if args.refresh_online:
        from gic_agri.news import NewsService
        from gic_agri.weather import WeatherService

        news_result = NewsService(database).refresh_all()
        weather_result = WeatherService(database).refresh_all_locations()
        print(
            json.dumps(
                {"actualites": news_result, "meteo": weather_result},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    from gic_agri.ui import MainWindow

    window = MainWindow(service=service, project_root=PROJECT_ROOT)
    window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
