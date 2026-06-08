"""
Combined Release Checker - Runs multiple release sources and merges the results.
"""

import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


class DVDReleaseAdapter:
    """Adapts DVDReleaseChecker to the ReleaseChecker.get_today_releases() interface."""

    def __init__(self, checker):
        self.checker = checker

    def get_today_releases(self) -> List[Dict[str, Any]]:
        return self.checker.get_todays_digital_releases()


class CombinedReleaseChecker:
    """Runs several release sources and merges them, deduplicating by TMDB id.

    When the same movie comes from more than one source the first source's entry
    is kept as the base and any fields it is missing are filled in from the
    later sources, so we keep the richest possible metadata.
    """

    def __init__(self, sources: List[Tuple[str, Any]]):
        """sources: list of (name, checker), each checker exposing get_today_releases()."""
        self.sources = sources

    def get_today_releases(self) -> List[Dict[str, Any]]:
        merged: Dict[Any, Dict[str, Any]] = {}
        order: List[Any] = []

        for name, checker in self.sources:
            try:
                releases = checker.get_today_releases()
            except Exception as e:
                logger.error(f"Release source '{name}' failed: {e}")
                continue

            logger.info(f"Source '{name}': {len(releases)} releases")

            for release in releases:
                key = release.get("tmdb_id") or (release.get("title"), release.get("release_date"))

                if key in merged:
                    existing = merged[key]
                    for field, value in release.items():
                        if value and not existing.get(field):
                            existing[field] = value
                    if name not in existing["_sources"]:
                        existing["_sources"].append(name)
                else:
                    entry = dict(release)
                    entry["_sources"] = [name]
                    merged[key] = entry
                    order.append(key)

        result = [merged[k] for k in order]
        logger.info(f"Combined {len(self.sources)} sources into {len(result)} unique releases")
        return result
