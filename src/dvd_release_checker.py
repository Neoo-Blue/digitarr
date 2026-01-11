"""
DVD Release Dates scraper for digital movie releases.
Scrapes https://www.dvdsreleasedates.com/digital-releases/ and cross-references with TMDB.
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime
import logging
import re

logger = logging.getLogger(__name__)

DVDSRELEASEDATES_URL = "https://www.dvdsreleasedates.com/digital-releases/"


class DVDReleaseChecker:
    def __init__(self, tmdb_api_key: str):
        self.tmdb_api_key = tmdb_api_key
        self.tmdb_base_url = "https://api.themoviedb.org/3"
    
    def get_todays_digital_releases(self) -> list:
        """
        Scrape dvdsreleasedates.com for today's digital releases,
        then look up each movie on TMDB for full details.
        """
        today = datetime.now().date()
        logger.info(f"Fetching digital releases from dvdsreleasedates.com for {today}")
        
        try:
            # Fetch the page
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(DVDSRELEASEDATES_URL, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all release entries
            movies_today = self._parse_releases(soup, today)
            
            if not movies_today:
                logger.info("No digital releases found for today on dvdsreleasedates.com")
                return []
            
            logger.info(f"Found {len(movies_today)} releases on dvdsreleasedates.com for today")
            
            # Look up each movie on TMDB
            releases = []
            for movie_info in movies_today:
                tmdb_movie = self._lookup_on_tmdb(movie_info['title'], movie_info.get('year'))
                if tmdb_movie:
                    releases.append(tmdb_movie)
                else:
                    logger.warning(f"Could not find '{movie_info['title']}' on TMDB")
            
            logger.info(f"Successfully matched {len(releases)} movies with TMDB")
            return releases
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch dvdsreleasedates.com: {e}")
            return []
        except Exception as e:
            logger.error(f"Error parsing dvdsreleasedates.com: {e}")
            return []
    
    def _parse_releases(self, soup: BeautifulSoup, target_date: datetime.date) -> list:
        """Parse the HTML to find movies released on the target date."""
        movies = []
        current_date = None
        
        # The page structure has dates followed by movie entries
        # Look for date headers and movie rows
        for element in soup.find_all(['td', 'div', 'tr']):
            text = element.get_text(strip=True)
            
            # Check if this is a date header (e.g., "Tuesday January 14, 2025")
            date_match = re.search(r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+'
                                   r'(January|February|March|April|May|June|July|August|'
                                   r'September|October|November|December)\s+(\d{1,2}),\s+(\d{4})', text)
            if date_match:
                try:
                    month_name = date_match.group(2)
                    day = int(date_match.group(3))
                    year = int(date_match.group(4))
                    current_date = datetime.strptime(f"{month_name} {day} {year}", "%B %d %Y").date()
                except ValueError:
                    continue
            
            # If we're on the target date, look for movie titles
            if current_date == target_date:
                # Look for links that might be movie titles
                links = element.find_all('a')
                for link in links:
                    href = link.get('href', '')
                    title = link.get_text(strip=True)
                    # Movie links typically go to /movies/ path
                    if '/movies/' in href and title and len(title) > 1:
                        # Avoid navigation links
                        if title.lower() not in ['digital releases', 'new dvd releases', 'release date news']:
                            movies.append({'title': title, 'year': target_date.year})
        
        # Deduplicate
        seen = set()
        unique_movies = []
        for m in movies:
            if m['title'] not in seen:
                seen.add(m['title'])
                unique_movies.append(m)
        
        return unique_movies
    
    def _lookup_on_tmdb(self, title: str, year: int = None) -> dict:
        """Search TMDB for a movie by title and return full details."""
        try:
            # Search for the movie
            search_url = f"{self.tmdb_base_url}/search/movie"
            params = {
                'api_key': self.tmdb_api_key,
                'query': title,
                'include_adult': False
            }
            if year:
                params['year'] = year
            
            response = requests.get(search_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if not data.get('results'):
                # Try without year
                if year:
                    del params['year']
                    response = requests.get(search_url, params=params, timeout=10)
                    data = response.json()
                
                if not data.get('results'):
                    return None
            
            # Get the first (best) match
            movie = data['results'][0]
            
            # Fetch full movie details including certifications
            details_url = f"{self.tmdb_base_url}/movie/{movie['id']}"
            params = {
                'api_key': self.tmdb_api_key,
                'append_to_response': 'release_dates'
            }
            details_response = requests.get(details_url, params=params, timeout=10)
            details = details_response.json()
            
            # Extract US certification
            certification = self._get_us_certification(details.get('release_dates', {}))
            
            # Get genre names
            genre_names = [g['name'] for g in details.get('genres', [])]
            
            return {
                'id': movie['id'],
                'title': movie.get('title', title),
                'overview': movie.get('overview', ''),
                'vote_average': movie.get('vote_average', 0),
                'poster_path': movie.get('poster_path'),
                'release_date': movie.get('release_date', ''),
                'original_language': movie.get('original_language', ''),
                'adult': movie.get('adult', False),
                'genre_names': genre_names,
                'certification': certification,
                'media_type': 'movie'
            }
            
        except requests.RequestException as e:
            logger.error(f"TMDB lookup failed for '{title}': {e}")
            return None
    
    def _get_us_certification(self, release_dates: dict) -> str:
        """Extract US certification from TMDB release_dates data."""
        results = release_dates.get('results', [])
        for country in results:
            if country.get('iso_3166_1') == 'US':
                for release in country.get('release_dates', []):
                    cert = release.get('certification', '')
                    if cert:
                        return cert
        return ''

