"""
Filter Engine - Applies configured filters to releases
"""

import logging
from datetime import date, datetime
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class FilterEngine:
    """Applies filtering rules to releases"""

    def __init__(self, config: Dict[str, Any]):
        """Initialize filter engine with configuration"""
        self.config = config
        self.filters = config.get("filters", {})

    def apply_filters(self, releases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply all configured filters to releases"""
        filtered = releases

        logger.info(f"Applying filters to {len(filtered)} releases")

        if self.filters.get("exclude_adult"):
            filtered = self._filter_adult(filtered)
            logger.info(f"After adult filter: {len(filtered)} releases")

        # Drop catalog re-pickups: TMDB's digital release type also fires when a
        # decades-old title lands on a new platform, which we don't want to request.
        max_age_years = self.filters.get("max_release_age_years", 2)
        if max_age_years and max_age_years > 0:
            filtered = self._filter_by_max_release_age(filtered, max_age_years)
            logger.info(f"After catalog age filter: {len(filtered)} releases")

        if self.filters.get("min_tmdb_rating", 0) > 0:
            filtered = self._filter_by_tmdb_rating(filtered)
            logger.info(f"After TMDB rating filter: {len(filtered)} releases")

        # Filter by allowed languages (only include these languages)
        allowed_langs = self.filters.get("allowed_languages", [])
        if allowed_langs:
            filtered = self._filter_by_allowed_languages(filtered, allowed_langs)
            logger.info(f"After language filter: {len(filtered)} releases")

        # Filter by excluded genres
        excluded_genres = self.filters.get("excluded_genres", [])
        if excluded_genres:
            filtered = self._filter_by_excluded_genres(filtered, excluded_genres)
            logger.info(f"After genre filter: {len(filtered)} releases")

        # Filter by excluded certifications (age ratings)
        excluded_certs = self.filters.get("excluded_certifications", [])
        if excluded_certs:
            filtered = self._filter_by_excluded_certifications(filtered, excluded_certs)
            logger.info(f"After certification filter: {len(filtered)} releases")

        return filtered
    
    def _filter_adult(self, releases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out adult content"""
        return [r for r in releases if not r.get("adult", False)]

    def _filter_by_max_release_age(self, releases: List[Dict[str, Any]],
                                    max_years: int) -> List[Dict[str, Any]]:
        """Drop releases whose primary release date is more than max_years old.

        Catches TMDB digital re-pickups of catalog titles (e.g. a 1984 film
        landing on a new streaming platform shows up under release type 4
        even though it isn't a new release.)
        """
        today = date.today()
        filtered = []

        for release in releases:
            primary = release.get("primary_release_date") or release.get("release_date")
            if not primary:
                # No date info — keep it rather than drop a real release on missing metadata.
                filtered.append(release)
                continue

            try:
                primary_date = datetime.strptime(primary[:10], "%Y-%m-%d").date()
            except ValueError:
                filtered.append(release)
                continue

            age_days = (today - primary_date).days
            if age_days > max_years * 365:
                logger.debug(
                    f"Skipping catalog re-pickup: {release.get('title')} "
                    f"(primary release {primary_date}, age {age_days // 365}y)"
                )
                continue
            filtered.append(release)

        return filtered

    def _filter_by_tmdb_rating(self, releases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter by TMDB rating"""
        min_rating = self.filters.get("min_tmdb_rating", 0)
        filtered = []

        for release in releases:
            vote_average = release.get("vote_average", 0)
            if vote_average >= min_rating:
                filtered.append(release)
            else:
                logger.debug(f"Skipping {release.get('title')} - TMDB rating {vote_average} < {min_rating}")

        return filtered

    def _filter_by_allowed_languages(self, releases: List[Dict[str, Any]],
                                      allowed_langs: List[str]) -> List[Dict[str, Any]]:
        """Filter to only include movies in allowed languages

        Args:
            releases: List of releases
            allowed_langs: List of ISO 639-1 language codes (e.g., ["en", "es", "fr"])
        """
        filtered = []
        for release in releases:
            lang = release.get("original_language", "")
            if lang in allowed_langs:
                filtered.append(release)
            else:
                logger.debug(f"Skipping {release.get('title')} - Language '{lang}' not in allowed list")

        return filtered

    def _filter_by_excluded_genres(self, releases: List[Dict[str, Any]],
                                    excluded_genres: List[str]) -> List[Dict[str, Any]]:
        """Filter out movies with excluded genres

        Args:
            releases: List of releases
            excluded_genres: List of genre names to exclude (e.g., ["Horror", "Documentary"])
        """
        # Normalize excluded genres to lowercase for case-insensitive matching
        excluded_lower = [g.lower() for g in excluded_genres]
        filtered = []

        for release in releases:
            genres = release.get("genres", [])
            genres_lower = [g.lower() for g in genres]

            # Check if any genre matches excluded list
            if any(g in excluded_lower for g in genres_lower):
                logger.debug(f"Skipping {release.get('title')} - Has excluded genre: {genres}")
            else:
                filtered.append(release)

        return filtered

    def _filter_by_excluded_certifications(self, releases: List[Dict[str, Any]],
                                            excluded_certs: List[str]) -> List[Dict[str, Any]]:
        """Filter out movies with excluded certifications (age ratings)

        Args:
            releases: List of releases
            excluded_certs: List of certifications to exclude (e.g., ["R", "NC-17"])
        """
        # Normalize certifications to uppercase for case-insensitive matching
        excluded_upper = [c.upper() for c in excluded_certs]
        filtered = []

        for release in releases:
            cert = release.get("certification", "")
            if cert and cert.upper() in excluded_upper:
                logger.debug(f"Skipping {release.get('title')} - Has excluded certification: {cert}")
            else:
                filtered.append(release)

        return filtered
