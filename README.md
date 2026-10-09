# GIC INNOVATION — Gestion agricole

Application de bureau hors connexion adaptée aux activités agricoles de la Haute-Sanaga.

**GIC INNOVATION est une initiative créée par la famille Blang.**

## Objectif de cette version

L'application centralise les informations utiles d'une exploitation sans nécessiter Internet :

- parcelles, villages, superficies et accès à l'eau ;
- campagnes de manioc, maïs, arachide, plantain, gombo et arbres fruitiers ;
- calendrier des travaux et priorités ;
- stocks d'intrants, aliments, récoltes, emballages et matériels ;
- recettes, dépenses et solde enregistré ;
- lots de citronniers, mandariniers, avocatiers, corossoliers, safoutiers et pruniers ;
- observations terrain et photos destinées à préparer de futures fonctions d'IA ;
- sauvegarde de la base et export CSV.

Trois onglets complémentaires ont besoin d'une connexion Internet pour se
mettre à jour, mais restent consultables hors connexion avec les dernières
données récupérées :

- **Actualités** : actualités agricoles filtrées depuis des sources
  camerounaises authentiques (voir « Sources » ci-dessous) ;
- **Météo** : prévisions sur 7 jours pour les principales communes de la
  Haute-Sanaga (Open-Meteo) ;
- **Assistant agricole** : recommandations explicables combinant le
  calendrier agricole régional, la météo et le suivi local des stocks et
  des travaux (voir « Assistant agricole : un système de règles, pas une
  boîte noire » ci-dessous).

Les données sont enregistrées localement dans SQLite. Aucun compte en ligne ni abonnement n'est nécessaire.

## Lancer l'application sous Windows

### Méthode la plus simple

Double-cliquer sur `lancer_gic.bat`.

### Depuis PowerShell

```powershell
Set-Location "chemin\vers\gic-innovation-gestion-agricole"
py app.py
```

Python 3.11 ou plus récent est requis. L'application utilise uniquement la bibliothèque standard de Python : Tkinter pour l'interface et SQLite pour les données.

## Première utilisation

1. Ouvrir l'onglet **Parcelles** et enregistrer au moins une parcelle.
2. Créer une **Campagne** et l'associer à la parcelle.
3. Ajouter les travaux dans **Travaux**.
4. Enregistrer les articles et mouvements dans **Stocks**.
5. Enregistrer recettes et dépenses dans **Finances**.
6. Gérer les plants disponibles dans **Plants fruitiers**.
7. Ajouter les constats et photos dans **Observations**.
8. Avec une connexion Internet, ouvrir **Actualités** puis cliquer sur
   « Actualiser les actualités », et ouvrir **Météo** puis choisir une
   localité et cliquer sur « Actualiser la météo ».
9. Ouvrir **Assistant agricole** pour voir les recommandations ; chaque
   ligne sélectionnée affiche son explication complète.

Le menu `Fichier > Actualiser actualités et météo (Internet requis)` met à
jour les deux en une seule fois.

Pour essayer rapidement l'interface, utiliser le menu :

`Fichier > Ajouter les données de démonstration`

La base principale est créée dans `data\gic_agriculture.db`.

## Sauvegardes et export

- **Sauvegarder la base** crée une copie complète du fichier SQLite.
- **Exporter en CSV** produit un fichier compatible avec Excel pour chaque rubrique.

Il est conseillé de sauvegarder régulièrement la base sur un support distinct.

## Sources des actualités et de la météo

Chaque source a été ouverte et vérifiée manuellement avant d'être intégrée.
L'application ne fabrique jamais de contenu : elle filtre et met en cache ce
qui est réellement publié par les organismes cités.

| Source | Type | Récupération automatique |
| --- | --- | --- |
| [MINADER](https://www.minader.cm/index.php/category/actualites/) — Ministère de l'Agriculture et du Développement Rural | Institution officielle | Oui (flux RSS officiel de la catégorie Actualités) |
| [IRAD](https://irad.cm/a-la-une/) — Institut de Recherche Agricole pour le Développement | Recherche agricole publique | Oui (flux RSS officiel) |
| [Investir au Cameroun](https://www.investiraucameroun.com/agriculture) | Presse économique | Oui (flux général, filtré localement par mots-clés agricoles) |
| [ONACC](https://onacc.cm/fr/bulletins) — Observatoire National sur les Changements Climatiques | Bulletins climatiques officiels | Non — annuaire uniquement ; référence pour valider les périodes de semis |
| [CamAgro](https://www.camagro.cm/) — portail agropastoral | Annonces et prix de marché | Non — annuaire uniquement |

Le filtrage par mots-clés (`gic_agri/constants.py`, `AGRICULTURE_KEYWORDS`) est
une recherche de sous-chaînes simple, pas une analyse sémantique : il peut
laisser passer un article non agricole si son texte contient un mot ambigu
(par exemple « ferme », qui peut aussi signifier « il/elle ferme » ou
« ferme » au sens de fermeté). C'est une limite assumée d'un filtre
transparent et vérifiable plutôt qu'un classement automatique opaque.

La météo provient d'[Open-Meteo](https://open-meteo.com/) (prévisions
publiques, gratuites, sans clé ni compte). Les coordonnées des communes de
la Haute-Sanaga (`gic_agri/constants.py`, `HAUTE_SANAGA_LOCATIONS`) viennent
de références géographiques publiques ; en cas de doute, comparez-les aux
bulletins officiels de l'ONACC.

## Assistant agricole : un système de règles, pas une boîte noire

L'onglet **Assistant agricole** (`gic_agri/advisory.py`) combine trois
sources déjà présentes dans l'application :

1. le **calendrier agricole régional** (saisons des pluies de la région du
   Centre : grande saison mars-juin, petite saison août-novembre) comparé à
   la date de plantation de chaque campagne ;
2. les **prévisions météo** mises en cache (cumul de précipitations sur les
   7 prochains jours) ;
3. le **suivi local** des stocks sous le seuil minimum et des travaux en
   retard.

Chaque recommandation affichée indique explicitement la règle qui l'a
produite (champ « Règle / source ») et une explication complète en texte
clair. Ce choix est volontaire : GIC INNOVATION ne dispose d'aucun jeu de
données vérifié (sols, rendements, incidence des maladies) propre à la
Haute-Sanaga qui permettrait d'entraîner un modèle statistique de façon
honnête. Entraîner un modèle sur des données inventées ou non représentatives
aurait pu produire des conseils trompeurs. La recherche récente sur les
systèmes d'aide à la décision agricole converge d'ailleurs vers l'IA
explicable (« explainable AI », XAI) plutôt que les modèles opaques, pour les
mêmes raisons de confiance et de vérifiabilité.

L'assistant ne remplace donc pas l'avis d'un agronome, d'un technicien ou
d'un vétérinaire, et ses recommandations doivent toujours être confrontées
aux bulletins officiels (ONACC, MINADER) et à l'expérience de terrain.

## Commandes de contrôle

Vérifier la base sans ouvrir l'interface :

```powershell
py app.py --check
```

Créer les données de démonstration depuis la ligne de commande :

```powershell
py app.py --seed-demo
```

Mettre à jour les actualités et la météo sans ouvrir l'interface (nécessite
Internet) :

```powershell
py app.py --refresh-online
```

Exécuter les tests :

```powershell
py -m unittest discover -s tests -v
```

## Architecture

```text
gic-innovation-gestion-agricole/
├── app.py
├── lancer_gic.bat
├── assets/
│   └── gic_innovation_logo_rond.png
├── data/
├── gic_agri/
│   ├── advisory.py
│   ├── constants.py
│   ├── database.py
│   ├── network.py
│   ├── news.py
│   ├── services.py
│   ├── ui.py
│   ├── validators.py
│   └── weather.py
└── tests/
    ├── test_advisory.py
    ├── test_database.py
    ├── test_news.py
    ├── test_services.py
    └── test_weather.py
```

- `database.py` crée le schéma SQLite, les contraintes et les sauvegardes.
- `services.py` contient les règles métier et les transactions.
- `validators.py` contrôle les données saisies.
- `network.py` est le seul point d'accès Internet de l'application (stdlib
  `urllib`, aucune dépendance externe) ; toute erreur réseau devient un
  message clair plutôt qu'un plantage.
- `news.py` récupère et filtre les actualités agricoles (voir « Sources »).
- `weather.py` interroge Open-Meteo et met les prévisions en cache local.
- `advisory.py` est le moteur de règles explicable de l'Assistant agricole.
- `ui.py` contient l'interface Tkinter (onglets, formulaires, tableaux).
- `tests/` protège les règles importantes : sorties de stock, filtrage des
  actualités, mise en cache météo hors ligne, et chaque règle de
  l'assistant agricole.

## Feuille de route pour l'intelligence artificielle

La version 0.2.0 ajoute un **système de règles explicable** (voir
« Assistant agricole » ci-dessus), pas un modèle d'apprentissage automatique
entraîné sur des données propres à la Haute-Sanaga — ces données n'existent
pas encore sous une forme vérifiée.

L'intégration d'une véritable couche statistique devra progresser par
étapes, en gardant la même exigence d'explicabilité :

1. **Qualité des données** *(en cours)* : stabiliser les parcelles,
   campagnes, stocks, finances et observations ; les observations photo
   constituent déjà une base pour un futur assistant visuel.
2. **Assistant local explicable** *(fait dans cette version)* : calendrier
   régional, météo Open-Meteo, alertes de stock et de travaux, chaque
   recommandation justifiée.
3. **Prévisions** : une fois un historique local suffisant accumulé,
   estimations de consommation, risques de rupture et tendances de
   rendement, toujours avec un niveau de confiance visible et la règle
   d'origine affichée.
4. **Assistant photo encadré** : classer une observation et préparer des
   questions à partir des photos déjà enregistrées, sans jamais se
   présenter comme un diagnostic certain, et toujours renvoyer vers un
   agronome, un technicien ou un vétérinaire en cas de doute.
5. **Fonctionnement hors connexion** : privilégier des modèles locaux
   légers ou une synchronisation facultative plutôt qu'un service en ligne
   obligatoire.
6. **Protection des données** : consentement, journal des recommandations,
   sauvegarde et contrôle de l'utilisateur sur ce qui est partagé.

Avant d'aller plus loin, il faudra interroger les producteurs de la
Haute-Sanaga sur leurs téléphones, leur connexion, leurs langues, leurs
méthodes de travail et les décisions qu'ils veulent réellement améliorer.

## Limites connues de cette version

- un seul poste utilise directement la base locale ;
- aucune synchronisation entre plusieurs ordinateurs ;
- aucun rôle utilisateur ni mot de passe ;
- aucun diagnostic automatique — l'Assistant agricole est un système de
  règles explicable, pas un modèle entraîné (voir ci-dessus) ;
- les actualités et la météo nécessitent une connexion Internet pour se
  mettre à jour ; seules les dernières données déjà récupérées restent
  visibles hors connexion ;
- le filtrage des actualités par mots-clés peut laisser passer de rares
  articles non agricoles (voir « Sources ») ;
- les formats monétaires utilisent le FCFA, sans module comptable
  réglementaire.

Ces limites seront traitées après validation du besoin sur le terrain.

