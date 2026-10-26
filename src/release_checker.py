"""
Release Checker - Checks for digital movie releases using TMDB
"""

import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

MAX_PAGES = 3  # 20 results per page

# TMDB Release Types
RELEASE_TYPE_PREMIERE = 1
RELEASE_TYPE_THEATRICAL_LIMITED = 2
RELEASE_TYPE_THEATRICAL = 3
RELEASE_TYPE_DIGITAL = 4
RELEASE_TYPE_PHYSICAL = 5
RELEASE_TYPE_TV = 6


class ReleaseChecker:
    """Checks for today's digital movie releases"""

    def __init__(self, config: Dict[str, Any]):
        """Initialize release checker with configuration"""
        self.config = config
        self.tmdb_api_key = config.get("tmdb", {}).get("api_key")
        self.tmdb_base_url = "https://api.themoviedb.org/3"
        self.today = datetime.now().date()

    def get_today_releases(self) -> List[Dict[str, Any]]:
        """Get digital movie releases for today, plus the last lookback_days.

        A streaming premiere has almost no TMDB votes on release day, so the
        vote-count filter would never let it through. Re-checking a trailing
        window requests it once enough votes are in; requesters skip titles
        already requested.
        """
        self.today = datetime.now().date()
        start = self.today - timedelta(days=self.config.get("lookback_days", 0))
        releases = []

        if not self.tmdb_api_key:
            logger.warning("TMDB API key not configured")
            return releases

        try:
            releases = self._fetch_digital_releases(self.today, start)
        except Exception as e:
            logger.error(f"Error fetching releases: {str(e)}")

        logger.info(f"Found {len(releases)} digital movie releases for {start} to {self.today}")
        return releases

    def _fetch_digital_releases(self, target_date: datetime.date,
                                start_date: datetime.date = None) -> List[Dict[str, Any]]:
        """Fetch movies with digital releases between start_date and target_date"""
        movies = []

        try:
            # Use discover endpoint with release date filter for digital releases
            # with_release_type=4 filters for digital releases only
            url = f"{self.tmdb_base_url}/discover/movie"
            params = {
                "api_key": self.tmdb_api_key,
                "with_release_type": RELEASE_TYPE_DIGITAL,
                "release_date.gte": (start_date or target_date).isoformat(),
                "release_date.lte": target_date.isoformat(),
                "sort_by": "popularity.desc",
            }

            # Sorted by popularity, so the first few pages hold every plausible hit.
            results = []
            page, total_pages = 1, 1
            while page <= min(total_pages, MAX_PAGES):
                response = requests.get(url, params={**params, "page": page}, timeout=10)
                response.raise_for_status()
                data = response.json()
                results.extend(data.get("results", []))
                total_pages = data.get("total_pages", 1)
                page += 1

            # Get detailed info for each movie including release dates
            for movie in results:
                movie_id = movie.get("id")
                movie_details = self._get_movie_with_release_dates(movie_id)

                if movie_details:
                    movies.append(movie_details)

            logger.info(f"Fetched {len(movies)} digital releases from TMDB")

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching movies from TMDB: {str(e)}")

        return movies

    def _get_movie_with_release_dates(self, movie_id: int) -> Dict[str, Any]:
        """Get movie details with release dates, certifications, and genres"""
        try:
            url = f"{self.tmdb_base_url}/movie/{movie_id}"
            params = {
                "api_key": self.tmdb_api_key,
                "append_to_response": "release_dates"
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            movie = response.json()

            # Find digital release date and certification
            digital_release_date, certification = self._find_digital_release_info(movie)

            # Extract genre names
            genres = [g.get("name") for g in movie.get("genres", [])]

            return {
                "type": "movie",
                "tmdb_id": movie.get("id"),
                "title": movie.get("title"),
                "release_date": digital_release_date or movie.get("release_date"),
                "primary_release_date": movie.get("release_date"),
                "overview": movie.get("overview"),
                "imdb_id": movie.get("imdb_id"),
                "vote_average": movie.get("vote_average"),
                "vote_count": movie.get("vote_count"),
                "popularity": movie.get("popularity"),
                "adult": movie.get("adult", False),
                "poster_path": movie.get("poster_path"),
                "original_language": movie.get("original_language", ""),
                "genres": genres,
                "certification": certification
            }

        except Exception as e:
            logger.warning(f"Error fetching movie {movie_id} details: {str(e)}")
            return None

    def _find_digital_release_info(self, movie: Dict[str, Any]) -> tuple:
        """Extract digital release date and certification from movie release_dates

        Returns:
            tuple: (release_date, certification)
        """
        release_dates = movie.get("release_dates", {}).get("results", [])
        digital_date = None
        certification = None

        # Prefer US certification, fallback to any available
        for country_releases in release_dates:
            country = country_releases.get("iso_3166_1", "")
            for release in country_releases.get("release_dates", []):
                if release.get("type") == RELEASE_TYPE_DIGITAL:
                    release_date = release.get("release_date", "")
                    if release_date and not digital_date:
                        digital_date = release_date[:10]  # YYYY-MM-DD

                    cert = release.get("certification", "")
                    if cert:
                        # Prefer US certification
                        if country == "US":
                            certification = cert
                        elif not certification:
                            certification = cert

        return digital_date, certification
