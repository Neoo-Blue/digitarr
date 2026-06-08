"""
Test suite for DigiQuest
"""

import unittest
from unittest.mock import patch, MagicMock
import json
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config_manager import ConfigManager
from release_checker import ReleaseChecker
from filters import FilterEngine
from overseerr_requester import OverseerrRequester
from riven_requester import RivenRequester
from combined_release_checker import CombinedReleaseChecker, DVDReleaseAdapter


class TestConfigManager(unittest.TestCase):
    """Test ConfigManager"""
    
    def test_default_config_loading(self):
        """Test loading default configuration"""
        config_manager = ConfigManager(str(Path(__file__).parent.parent / "settings.json"))
        config = config_manager.load_config()
        
        self.assertIn("overseerr", config)
        self.assertIn("tmdb", config)
        self.assertIn("filters", config)
    
    def test_invalid_rating_validation(self):
        """Test that invalid ratings are rejected"""
        config_manager = ConfigManager()
        bad_config = {
            "filters": {
                "min_tmdb_rating": 11  # Invalid: > 10
            }
        }
        
        with self.assertRaises(ValueError):
            config_manager._validate_config(bad_config)
    
    def test_api_url_validation(self):
        """Test that API URL must have http protocol"""
        config_manager = ConfigManager()
        bad_config = {
            "overseerr": {
                "api_url": "localhost:5055",  # Invalid: no protocol
                "api_key": "test_key"
            }
        }
        
        with self.assertRaises(ValueError):
            config_manager._validate_config(bad_config)


class TestReleaseChecker(unittest.TestCase):
    """Test ReleaseChecker"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.config = {
            "tmdb": {"api_key": "test_key"},
            "sources": {"enabled": ["tmdb"]},
            "filters": {}
        }
    
    @patch('release_checker.requests.get')
    def test_fetch_tmdb_movies(self, mock_get):
        """Test fetching movies from TMDB"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 123,
                    "title": "Test Movie",
                    "release_date": "2026-01-10",
                    "vote_average": 7.5,
                    "adult": False
                }
            ]
        }
        mock_get.return_value = mock_response
        
        checker = ReleaseChecker(self.config)
        with patch.object(checker, '_get_movie_with_release_dates') as mock_details:
            mock_details.return_value = {
                "id": 123,
                "title": "Test Movie",
                "type": "movie"
            }
            movies = checker._fetch_digital_releases(checker.today)
        
        self.assertEqual(len(movies), 1)
        self.assertEqual(movies[0]["title"], "Test Movie")
        self.assertEqual(movies[0]["type"], "movie")
    
    @patch('release_checker.ReleaseChecker._fetch_digital_releases')
    def test_get_today_releases(self, mock_fetch):
        """Test getting today's releases"""
        mock_fetch.return_value = [{"title": "Test Movie", "type": "movie"}]
        checker = ReleaseChecker(self.config)
        releases = checker.get_today_releases()
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0]["title"], "Test Movie")


class _StubChecker:
    """Minimal checker exposing get_today_releases for combined-source tests."""

    def __init__(self, releases=None, raises=False):
        self._releases = releases or []
        self._raises = raises

    def get_today_releases(self):
        if self._raises:
            raise RuntimeError("source down")
        return self._releases


class TestCombinedReleaseChecker(unittest.TestCase):
    """Test CombinedReleaseChecker merge/dedupe behavior"""

    def test_union_of_two_sources(self):
        """Titles unique to each source all come through."""
        tmdb = _StubChecker([{"tmdb_id": 1, "title": "A"}])
        dvd = _StubChecker([{"tmdb_id": 2, "title": "B"}])
        combined = CombinedReleaseChecker([("tmdb", tmdb), ("dvd", dvd)])

        result = combined.get_today_releases()
        titles = sorted(r["title"] for r in result)
        self.assertEqual(titles, ["A", "B"])

    def test_dedupe_by_tmdb_id_and_fill_missing_fields(self):
        """Same tmdb_id from both sources collapses to one, merging fields."""
        tmdb = _StubChecker([{"tmdb_id": 1, "title": "A", "vote_average": 7.0}])
        dvd = _StubChecker([{"tmdb_id": 1, "title": "A", "imdb_id": "tt1"}])
        combined = CombinedReleaseChecker([("tmdb", tmdb), ("dvd", dvd)])

        result = combined.get_today_releases()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["vote_average"], 7.0)
        self.assertEqual(result[0]["imdb_id"], "tt1")
        self.assertEqual(result[0]["_sources"], ["tmdb", "dvd"])

    def test_one_source_failing_does_not_break_the_other(self):
        """If a source raises, the run continues with the surviving source."""
        tmdb = _StubChecker(raises=True)
        dvd = _StubChecker([{"tmdb_id": 2, "title": "B"}])
        combined = CombinedReleaseChecker([("tmdb", tmdb), ("dvd", dvd)])

        result = combined.get_today_releases()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "B")

    def test_dvd_adapter_maps_method(self):
        """DVDReleaseAdapter exposes get_today_releases over the DVD checker."""
        class _DVD:
            def get_todays_digital_releases(self):
                return [{"tmdb_id": 9, "title": "Z"}]

        adapter = DVDReleaseAdapter(_DVD())
        self.assertEqual(adapter.get_today_releases()[0]["title"], "Z")


class TestFilterEngine(unittest.TestCase):
    """Test FilterEngine"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.config = {
            "tmdb": {"api_key": "test_key"},
            "filters": {
                "exclude_adult": True,
                "min_imdb_rating": 0,
                "min_tmdb_rating": 0,
                "languages": []
            }
        }
        self.releases = [
            {
                "type": "movie",
                "tmdb_id": 1,
                "title": "Clean Movie",
                "adult": False,
                "vote_average": 7.0
            },
            {
                "type": "movie",
                "tmdb_id": 2,
                "title": "Adult Movie",
                "adult": True,
                "vote_average": 6.0
            }
        ]
    
    def test_filter_adult_content(self):
        """Test filtering out adult content"""
        filter_engine = FilterEngine(self.config)
        filtered = filter_engine._filter_adult(self.releases)
        
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["title"], "Clean Movie")
    
    def test_apply_all_filters(self):
        """Test applying multiple filters"""
        filter_engine = FilterEngine(self.config)
        filtered = filter_engine.apply_filters(self.releases)
        
        self.assertEqual(len(filtered), 1)
        self.assertFalse(any(r.get("adult") for r in filtered))
    
    def test_max_release_age_filter_drops_catalog_repickup(self):
        """Catalog titles with old primary release dates are dropped."""
        from datetime import date, timedelta
        recent = (date.today() - timedelta(days=10)).isoformat()
        old = (date.today() - timedelta(days=365 * 5)).isoformat()
        config = {"filters": {"max_release_age_years": 2}}
        releases = [
            {"title": "Fresh", "primary_release_date": recent},
            {"title": "Catalog Re-pickup", "primary_release_date": old},
        ]

        filter_engine = FilterEngine(config)
        filtered = filter_engine._filter_by_max_release_age(releases, 2)

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["title"], "Fresh")

    def test_max_release_age_filter_keeps_releases_without_date(self):
        """Releases without a primary_release_date are kept (don't drop on missing metadata)."""
        config = {"filters": {"max_release_age_years": 2}}
        releases = [{"title": "Unknown Date"}]
        filter_engine = FilterEngine(config)
        filtered = filter_engine._filter_by_max_release_age(releases, 2)
        self.assertEqual(len(filtered), 1)

    def test_tmdb_rating_filter(self):
        """Test TMDB rating filter"""
        self.config["filters"]["min_tmdb_rating"] = 7.0
        releases = [
            {"title": "Good Movie", "vote_average": 7.5},
            {"title": "Bad Movie", "vote_average": 5.0}
        ]
        
        filter_engine = FilterEngine(self.config)
        filtered = filter_engine._filter_by_tmdb_rating(releases)
        
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["title"], "Good Movie")


class TestOverseerrRequester(unittest.TestCase):
    """Test OverseerrRequester"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.config = {
            "overseerr": {
                "api_url": "http://localhost:5055",
                "api_key": "test_api_key",
                "request_type": "both"
            }
        }
        self.release = {
            "type": "movie",
            "tmdb_id": 123,
            "title": "Test Movie"
        }
    
    def test_initialization_without_api_key(self):
        """Test that initialization fails without API key"""
        bad_config = {"overseerr": {"api_url": "http://localhost:5055", "api_key": ""}}
        
        with self.assertRaises(ValueError):
            OverseerrRequester(bad_config)
    
    @patch('overseerr_requester.requests.post')
    @patch('overseerr_requester.OverseerrRequester._is_already_requested')
    def test_request_media_success(self, mock_check, mock_post):
        """Test successful media request"""
        mock_check.return_value = False
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        requester = OverseerrRequester(self.config)
        result = requester.request_media(self.release)

        self.assertEqual(result, "requested")

    @patch('overseerr_requester.requests.post')
    @patch('overseerr_requester.OverseerrRequester._is_already_requested')
    def test_request_media_conflict_is_skipped(self, mock_check, mock_post):
        """Test 409 response is treated as skipped, not failed"""
        mock_check.return_value = False
        mock_response = MagicMock()
        mock_response.status_code = 409  # Conflict
        mock_post.return_value = mock_response

        requester = OverseerrRequester(self.config)
        result = requester.request_media(self.release)

        self.assertEqual(result, "skipped")

    @patch('overseerr_requester.OverseerrRequester._is_already_requested')
    def test_request_media_already_requested_is_skipped(self, mock_check):
        """Test pre-check hit is treated as skipped, not failed"""
        mock_check.return_value = True

        requester = OverseerrRequester(self.config)
        result = requester.request_media(self.release)

        self.assertEqual(result, "skipped")


class TestRivenRequester(unittest.TestCase):
    """Test RivenRequester"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.config = {
            "riven": {
                "api_url": "http://localhost:8083",
                "api_key": "test_api_key",
                "enabled": True
            }
        }
        self.releases = [
            {
                "type": "movie",
                "tmdb_id": 123,
                "title": "Test Movie"
            },
            {
                "type": "movie",
                "tmdb_id": 456,
                "title": "Test Show"
            }
        ]
    
    def test_is_enabled(self):
        """Test that Riven is enabled when configured"""
        requester = RivenRequester(self.config)
        self.assertTrue(requester.is_enabled())
    
    def test_is_disabled_without_key(self):
        """Test that Riven is disabled without API key"""
        self.config["riven"]["api_key"] = ""
        requester = RivenRequester(self.config)
        self.assertFalse(requester.is_enabled())
    
    @patch('riven_requester.requests.post')
    def test_add_media_success(self, mock_post):
        """Test successful media addition to Riven"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        requester = RivenRequester(self.config)
        result = requester.add_media(self.releases)
        
        self.assertEqual(result["success"], 2)
        self.assertEqual(result["failed"], 0)
    
    @patch('riven_requester.requests.post')
    def test_add_media_not_found(self, mock_post):
        """Test media addition with 404 error"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_post.return_value = mock_response
        
        requester = RivenRequester(self.config)
        result = requester.add_media(self.releases)
        
        self.assertEqual(result["success"], 0)
        self.assertEqual(result["failed"], 2)
    
    @patch('riven_requester.requests.get')
    def test_get_status(self, mock_get):
        """Test getting Riven API status"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        requester = RivenRequester(self.config)
        status = requester.get_status()
        
        self.assertEqual(status["status"], "healthy")


class TestSchedulerAndRollover(unittest.TestCase):
    """Test date rollover and scheduler logic"""

    def test_month_boundary_rollover(self):
        """Test that adding days correctly rolls over month/year boundaries (avoiding day out of range ValueError)"""
        from datetime import datetime, timedelta
        # Setup next_run at end of April
        next_run = datetime(2026, 4, 30, 19, 0)
        # Advance by 1 day using timedelta (safe approach)
        next_run += timedelta(days=1)
        self.assertEqual(next_run.month, 5)
        self.assertEqual(next_run.day, 1)

        # Setup next_run at end of December (leap year transition / year boundary)
        next_run = datetime(2026, 12, 31, 19, 0)
        next_run += timedelta(days=1)
        self.assertEqual(next_run.year, 2027)
        self.assertEqual(next_run.month, 1)
        self.assertEqual(next_run.day, 1)

    @patch('release_checker.requests.get')
    def test_release_checker_today_dynamic_update(self, mock_get):
        """Test that ReleaseChecker updates self.today dynamically on every run"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_get.return_value = mock_response

        config = {"tmdb": {"api_key": "test_key"}}
        checker = ReleaseChecker(config)
        
        # Manually backdate checker.today to verify it updates
        from datetime import date, timedelta
        past_date = date.today() - timedelta(days=5)
        checker.today = past_date
        
        self.assertEqual(checker.today, past_date)
        
        # Calling get_today_releases should update self.today to today's actual date
        checker.get_today_releases()
        self.assertEqual(checker.today, date.today())


if __name__ == '__main__':
    unittest.main()
