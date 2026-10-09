from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from unittest.mock import patch

from gic_agri.database import Database
from gic_agri.network import NetworkError
from gic_agri.news import (
    NewsService,
    _matches_agriculture_keywords,
    _parse_feed,
    _strip_html,
)

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Exemple</title>
<item>
<title>Le manioc protège les revenus des producteurs</title>
<link>https://exemple.test/manioc-revenus</link>
<pubDate>Mon, 28 Sep 2026 08:00:00 +0000</pubDate>
<description><![CDATA[<p>Un article sur le <b>manioc</b> et l'agriculture.</p>]]></description>
</item>
<item>
<title>Resultats sportifs du week-end</title>
<link>https://exemple.test/sport-weekend</link>
<pubDate>Mon, 28 Sep 2026 09:00:00 +0000</pubDate>
<description>Rien a signaler pour le secteur sportif local.</description>
</item>
</channel>
</rss>
"""

TEST_SOURCES = (
    {
        "key": "test_official",
        "name": "Source officielle de test",
        "category": "Test",
        "site_url": "https://exemple.test/officiel",
        "feed_url": "https://exemple.test/officiel/feed",
        "description": "Source de test sans filtrage.",
        "keyword_filter": False,
    },
    {
        "key": "test_filtered",
        "name": "Source generaliste de test",
        "category": "Test",
        "site_url": "https://exemple.test/general",
        "feed_url": "https://exemple.test/general/feed",
        "description": "Source de test avec filtrage par mots-clés.",
        "keyword_filter": True,
    },
    {
        "key": "test_directory_only",
        "name": "Source sans flux",
        "category": "Test",
        "site_url": "https://exemple.test/annuaire",
        "feed_url": None,
        "description": "Source répertoriée sans récupération automatique.",
        "keyword_filter": False,
    },
)


class HelperFunctionTests(unittest.TestCase):
    def test_strip_html_removes_tags_and_collapses_whitespace(self) -> None:
        self.assertEqual(
            _strip_html("<p>Un   article <b>important</b>.</p>"),
            "Un article important .",
        )

    def test_matches_agriculture_keywords_is_case_insensitive(self) -> None:
        self.assertTrue(
            _matches_agriculture_keywords("Le MANIOC en Haute-Sanaga", "")
        )
        self.assertFalse(
            _matches_agriculture_keywords("Résultats sportifs", "Rien à signaler")
        )

    def test_parse_feed_extracts_title_link_date_and_summary(self) -> None:
        items = _parse_feed(SAMPLE_RSS)

        self.assertEqual(len(items), 2)
        first = items[0]
        self.assertEqual(first["title"], "Le manioc protège les revenus des producteurs")
        self.assertEqual(first["link"], "https://exemple.test/manioc-revenus")
        self.assertEqual(first["published_at"], "2026-09-28")
        self.assertIn("manioc", first["summary"].lower())


class NewsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temporary_directory.name) / "news.db")
        self.service = NewsService(self.database)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_refresh_source_without_filter_keeps_every_headline(self) -> None:
        with patch("gic_agri.news.NEWS_SOURCES", TEST_SOURCES), patch(
            "gic_agri.news.fetch_text", return_value=SAMPLE_RSS
        ):
            kept = self.service.refresh_source("test_official")

        self.assertEqual(kept, 2)
        cached = self.service.list_cached_items()
        self.assertEqual(len(cached), 2)

    def test_refresh_source_with_keyword_filter_keeps_only_agriculture_items(
        self,
    ) -> None:
        with patch("gic_agri.news.NEWS_SOURCES", TEST_SOURCES), patch(
            "gic_agri.news.fetch_text", return_value=SAMPLE_RSS
        ):
            kept = self.service.refresh_source("test_filtered")

        self.assertEqual(kept, 1)
        cached = self.service.list_cached_items()
        self.assertEqual(len(cached), 1)
        self.assertIn("manioc", cached[0]["title"].lower())

    def test_refresh_source_without_feed_url_is_a_no_op(self) -> None:
        with patch("gic_agri.news.NEWS_SOURCES", TEST_SOURCES):
            kept = self.service.refresh_source("test_directory_only")

        self.assertEqual(kept, 0)
        self.assertEqual(self.service.list_cached_items(), [])

    def test_refresh_all_degrades_gracefully_on_network_failure(self) -> None:
        with patch("gic_agri.news.NEWS_SOURCES", TEST_SOURCES), patch(
            "gic_agri.news.fetch_text", side_effect=NetworkError("hors ligne")
        ):
            results = self.service.refresh_all()

        self.assertEqual(results["test_official"], -1)
        self.assertEqual(results["test_filtered"], -1)
        self.assertNotIn("test_directory_only", results)

    def test_refresh_all_reports_invalid_xml_as_failure_without_raising(self) -> None:
        with patch("gic_agri.news.NEWS_SOURCES", TEST_SOURCES), patch(
            "gic_agri.news.fetch_text", return_value="not xml at all"
        ):
            results = self.service.refresh_all()

        self.assertEqual(results["test_official"], -1)

    def test_refresh_source_raises_for_invalid_xml(self) -> None:
        with patch("gic_agri.news.NEWS_SOURCES", TEST_SOURCES), patch(
            "gic_agri.news.fetch_text", return_value="not xml at all"
        ):
            with self.assertRaises(ElementTree.ParseError):
                self.service.refresh_source("test_official")

    def test_list_sources_returns_the_real_curated_directory_by_default(self) -> None:
        sources = NewsService.list_sources()

        keys = {source["key"] for source in sources}
        self.assertIn("minader", keys)
        self.assertIn("irad", keys)


if __name__ == "__main__":
    unittest.main()
