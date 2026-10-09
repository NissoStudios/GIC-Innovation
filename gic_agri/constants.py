"""Shared domain constants."""

ORGANIZATION_NAME = "GIC INNOVATION"
FOUNDER_NAME = "Famille Blang"
REGION_NAME = "Haute-Sanaga"

CROPS = (
    "Manioc",
    "Maïs",
    "Arachide",
    "Plantain",
    "Gombo",
    "Citronnier",
    "Mandarinier",
    "Avocatier",
    "Corossolier",
    "Safoutier",
    "Prunier",
    "Autre",
)

CAMPAIGN_STATUSES = ("PLANIFIÉE", "ACTIVE", "RÉCOLTÉE", "ANNULÉE")
TASK_STATUSES = ("À FAIRE", "TERMINÉE", "ANNULÉE")
TASK_PRIORITIES = ("BASSE", "NORMALE", "HAUTE", "URGENTE")
TASK_TYPES = (
    "Préparation du terrain",
    "Plantation / semis",
    "Entretien",
    "Désherbage",
    "Fertilisation",
    "Observation",
    "Récolte",
    "Transport",
    "Vente",
    "Autre",
)

STOCK_CATEGORIES = (
    "Semences et boutures",
    "Intrants",
    "Matériel",
    "Aliments pour animaux",
    "Récoltes",
    "Emballages",
    "Autre",
)
STOCK_UNITS = ("kg", "sac", "litre", "unité", "botte", "régime", "caisse", "tonne")
MOVEMENT_TYPES = ("ENTRÉE", "SORTIE")

FINANCE_KINDS = ("DÉPENSE", "RECETTE")
FINANCE_CATEGORIES = (
    "Main-d'œuvre",
    "Semences / boutures",
    "Intrants",
    "Aliments",
    "Transport",
    "Matériel",
    "Vente de récolte",
    "Vente de plants",
    "Autre",
)

FRUIT_SPECIES = (
    "Citronnier",
    "Mandarinier",
    "Avocatier",
    "Corossolier",
    "Safoutier",
    "Prunier",
    "Autre",
)

OBSERVATION_CATEGORIES = (
    "Croissance",
    "Ravageur",
    "Maladie suspectée",
    "Eau / humidité",
    "Sol",
    "Récolte",
    "Élevage",
    "Autre",
)

# --- Actualités agricoles -------------------------------------------------
#
# Chaque source a été vérifiée manuellement avant intégration (voir README,
# section « Sources »). Les sources sans `feed_url` fonctionnel restent
# listées comme annuaire ouvrable dans le navigateur : l'application ne
# fabrique jamais de contenu et ne s'appuie que sur ce qui est réellement
# publié par l'organisme cité.
NEWS_SOURCES: tuple[dict[str, object], ...] = (
    {
        "key": "minader",
        "name": "MINADER — Ministère de l'Agriculture et du Développement Rural",
        "category": "Institution officielle",
        "site_url": "https://www.minader.cm/index.php/category/actualites/",
        "feed_url": "https://www.minader.cm/index.php/category/actualites/feed/",
        "description": (
            "Actualités officielles du ministère camerounais chargé de "
            "l'agriculture : programmes, campagnes, filières, nominations."
        ),
        "keyword_filter": False,
    },
    {
        "key": "irad",
        "name": "IRAD — Institut de Recherche Agricole pour le Développement",
        "category": "Recherche agricole publique",
        "site_url": "https://irad.cm/a-la-une/",
        "feed_url": "https://irad.cm/feed/",
        "description": (
            "Résultats de recherche, publications et actualités de "
            "l'institut public camerounais de recherche agricole."
        ),
        "keyword_filter": False,
    },
    {
        "key": "investir_cameroun",
        "name": "Investir au Cameroun — actualités économiques",
        "category": "Presse économique",
        "site_url": "https://www.investiraucameroun.com/agriculture",
        "feed_url": "https://www.investiraucameroun.com/feed",
        "description": (
            "Presse économique camerounaise. Le flux général est filtré "
            "automatiquement pour ne garder que les articles liés à "
            "l'agriculture et à l'élevage."
        ),
        "keyword_filter": True,
    },
    {
        "key": "onacc",
        "name": "ONACC — Observatoire National sur les Changements Climatiques",
        "category": "Bulletins climatiques officiels",
        "site_url": "https://onacc.cm/fr/bulletins",
        "feed_url": None,
        "description": (
            "Bulletins agrométéorologiques et alertes climatiques "
            "décadaires et saisonnières, référence officielle pour valider "
            "les périodes de semis au Cameroun."
        ),
        "keyword_filter": False,
    },
    {
        "key": "camagro",
        "name": "CamAgro — portail agropastoral du Cameroun",
        "category": "Portail agropastoral",
        "site_url": "https://www.camagro.cm/",
        "feed_url": None,
        "description": (
            "Annonces, prix de marché et fiches pratiques pour les "
            "filières agropastorales camerounaises."
        ),
        "keyword_filter": False,
    },
)

# Mots-clés utilisés pour ne garder, parmi les flux généralistes, que les
# articles pertinents pour l'agriculture et l'élevage. Volontairement, la
# forme "maïs" n'est gardée qu'avec son tréma : sans lui, elle serait
# identique à la conjonction française très courante « mais » et
# déclencherait un nombre important de faux positifs.
AGRICULTURE_KEYWORDS: tuple[str, ...] = (
    "agri",
    "agro",
    "manioc",
    "maïs",
    "arachide",
    "plantain",
    "banane",
    "cacao",
    "café",
    "coton",
    "hévéa",
    "palmier",
    "riz",
    "élevage",
    "porcin",
    "avicole",
    "volaille",
    "poulet",
    "récolte",
    "semence",
    "engrais",
    "irad",
    "minader",
    "onacc",
    "ferme",
    "producteur",
    "planteur",
    "climat",
    "pluviométrie",
    "sécheresse",
)

# --- Météo — localités de la Haute-Sanaga ---------------------------------
#
# Coordonnées des principales communes du département, utilisées pour
# interroger l'API Open-Meteo (gratuite, sans clé). Source des coordonnées :
# références géographiques publiques (voir README).
HAUTE_SANAGA_LOCATIONS: dict[str, dict[str, object]] = {
    "nanga_eboko": {
        "label": "Nanga-Eboko (chef-lieu)",
        "latitude": 4.6833,
        "longitude": 12.3667,
    },
    "mbandjock": {
        "label": "Mbandjock",
        "latitude": 4.4464,
        "longitude": 11.9053,
    },
    "nkoteng": {
        "label": "Nkoteng",
        "latitude": 4.5167,
        "longitude": 12.0333,
    },
    "minta": {
        "label": "Minta",
        "latitude": 4.5333,
        "longitude": 12.7667,
    },
    "bibey": {
        "label": "Bibey",
        "latitude": 4.4222,
        "longitude": 12.1722,
    },
}

DEFAULT_WEATHER_LOCATION = "nanga_eboko"

# --- Calendrier agricole régional (région du Centre, pluviométrie bimodale) -
#
# Fenêtres indicatives de plantation/semis, établies à partir des saisons
# des pluies habituelles de la région du Centre du Cameroun (grande saison :
# mars à juin ; petite saison : août à novembre). Ces fenêtres sont des
# repères généraux : elles doivent toujours être confrontées aux bulletins
# ONACC/MINADER de la campagne en cours, car les dates réelles de début des
# pluies varient chaque année.
CROP_CALENDAR: dict[str, dict[str, object]] = {
    "Manioc": {
        "windows": (
            {"label": "Grande saison des pluies", "start_month": 3, "end_month": 4},
            {"label": "Petite saison des pluies", "start_month": 8, "end_month": 9},
        ),
        "note": (
            "Plantation possible presque toute l'année si le sol reste "
            "humide, mais la levée est meilleure juste après le début des "
            "pluies."
        ),
    },
    "Maïs": {
        "windows": (
            {"label": "Première saison", "start_month": 3, "end_month": 4},
            {
                "label": "Deuxième saison (variétés précoces)",
                "start_month": 7,
                "end_month": 8,
            },
        ),
        "note": "Attendre l'installation effective des pluies avant de semer.",
    },
    "Arachide": {
        "windows": (
            {"label": "Saison principale", "start_month": 3, "end_month": 4},
        ),
        "note": "Une deuxième saison est rare dans la région du Centre.",
    },
    "Plantain": {
        "windows": (
            {"label": "Période idéale", "start_month": 3, "end_month": 6},
            {"label": "Fenêtre secondaire", "start_month": 8, "end_month": 9},
        ),
        "note": "Une bonne humidité du sol favorise l'enracinement des rejets.",
    },
}

