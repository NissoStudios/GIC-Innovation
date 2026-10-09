"""Curated agricultural news from authentic Cameroonian sources.

Every source listed in :data:`gic_agri.constants.NEWS_SOURCES` was opened
and checked manually before being wired in here (see README, section
« Sources »). Automatic headline retrieval is only attempted for sources
whose RSS feed was confirmed to return real content:

* MINADER (Ministère de l'Agriculture et du Développement Rural) — official
  government feed, filtered to the « Actualités » category.
* IRAD (Institut de Recherche Agricole pour le Développement) — official
  research institute feed.
* Investir au Cameroun — general economic news feed, filtered locally by
  keyword so only agriculture/livestock-related articles are kept.

Sources without a working feed (ONACC, CamAgro) remain listed as a
directory the user can open directly; the application never invents
headlines for them. All fetched headlines are cached locally so the page
still shows the last known content when there is no Internet access.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ElementTree
from email.utils import parsedate_to_datetime
from typing import Any

from .constants import AGRICULTURE_KEYWORDS, NEWS_SOURCES
from .database import Database
from .network import NetworkError, fetch_text

logger = logging.getLogger(__name__)

_TAG_PATTERN = re.compile(r"<[^>]+>")
_ATOM_NAMESPACE = "{http://www.w3.org/2005/Atom}"


def _strip_html(value: str) -> str:
    """Remove HTML markup and collapse whitespace from *value*."""

    text = _TAG_PATTERN.sub(" ", value or "")
    return re.sub(r"\s+", " ", text).strip()


def _matches_agriculture_keywords(title: str, summary: str) -> bool:
    haystack = f"{title} {summary}".lower()
    return any(keyword in haystack for keyword in AGRICULTURE_KEYWORDS)


def _parse_feed(xml_text: str) -> list[dict[str, str]]:
    """Parse an RSS 2.0 or Atom feed into a flat list of headline dicts."""

    root = ElementTree.fromstring(xml_text)
    items: list[dict[str, str]] = []
    for element in root.iter():
        tag = element.tag
        if tag not in ("item", f"{_ATOM_NAMESPACE}entry"):
            continue

        title = element.findtext("title") or element.findtext(
            f"{_ATOM_NAMESPACE}title"
        ) or ""

        link = ""
        link_element = element.find("link")
        if link_element is not None:
            link = (link_element.text or link_element.get("href") or "").strip()
        if not link:
            atom_link = element.find(f"{_ATOM_NAMESPACE}link")
            if atom_link is not None:
                link = (atom_link.get("href") or "").strip()

        description = (
            element.findtext("description")
            or element.findtext(f"{_ATOM_NAMESPACE}summary")
            or ""
        )

        published_raw = (
            element.findtext("pubDate")
            or element.findtext(f"{_ATOM_NAMESPACE}published")
            or element.findtext(f"{_ATOM_NAMESPACE}updated")
            or ""
        )
        published_at = ""
        if published_raw:
            try:
                published_at = parsedate_to_datetime(published_raw).date().isoformat()
            except (TypeError, ValueError):
                published_at = published_raw[:10]

        items.append(
            {
                "title": _strip_html(title),
                "link": link,
                "summary": _strip_html(description)[:400],
                "published_at": published_at,
            }
        )
    return items


class NewsService:
    """Fetches, filters and caches agricultural news for offline reading."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()

    @staticmethod
    def list_sources() -> tuple[dict[str, Any], ...]:
        return NEWS_SOURCES

    @staticmethod
    def _find_source(source_key: str) -> dict[str, Any]:
        for source in NEWS_SOURCES:
            if source["key"] == source_key:
                return source
        raise ValueError(f"Source d'actualités inconnue : {source_key}")

    def refresh_source(self, source_key: str) -> int:
        """Fetch and cache the latest headlines for *source_key*.

        Returns the number of headlines kept after filtering. Raises
        :class:`gic_agri.network.NetworkError` on network failure and
        :class:`xml.etree.ElementTree.ParseError` if the feed content is not
        valid XML — callers running unattended refreshes should catch both.
        """

        source = self._find_source(source_key)
        feed_url = source.get("feed_url")
        if not feed_url:
            return 0

        xml_text = fetch_text(str(feed_url))
        items = _parse_feed(xml_text)
        if source.get("keyword_filter"):
            items = [
                item
                for item in items
                if _matches_agriculture_keywords(item["title"], item["summary"])
            ]
        items = [item for item in items if item["title"] and item["link"]]

        with self.database.connection() as connection:
            connection.executemany(
                """
                INSERT INTO news_items(
                    source_key, title, link, published_at, summary, fetched_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(source_key, link) DO UPDATE SET
                    title = excluded.title,
                    published_at = excluded.published_at,
                    summary = excluded.summary,
                    fetched_at = CURRENT_TIMESTAMP
                """,
                [
                    (
                        source_key,
                        item["title"],
                        item["link"],
                        item["published_at"] or None,
                        item["summary"],
                    )
                    for item in items
                ],
            )
        return len(items)

    def refresh_all(self) -> dict[str, int]:
        """Refresh every source that has a feed URL; never raises.

        Returns a mapping of ``source_key`` to the number of headlines kept,
        or ``-1`` for a source that failed (network unavailable, feed
        temporarily broken, etc.). Sources without a feed URL are omitted.
        """

        results: dict[str, int] = {}
        for source in NEWS_SOURCES:
            if not source.get("feed_url"):
                continue
            try:
                results[source["key"]] = self.refresh_source(source["key"])
            except (NetworkError, ElementTree.ParseError) as exc:
                logger.warning(
                    "Échec de récupération des actualités pour %s : %s",
                    source["key"],
                    exc,
                )
                results[source["key"]] = -1
        return results

    def list_cached_items(self, *, limit: int = 80) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT source_key, title, link, published_at, summary, fetched_at
                FROM news_items
                ORDER BY COALESCE(published_at, fetched_at) DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]


__all__ = ["NewsService"]
