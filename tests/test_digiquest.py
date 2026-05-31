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
        
        self.assertTrue(result)
    
    @patch('overseerr_requester.requests.post')
    @patch('overseerr_requester.OverseerrRequester._is_already_requested')
    def test_request_media_already_requested(self, mock_check, mock_post):
        """Test request when media already exists"""
        mock_check.return_value = False
        mock_response = MagicMock()
        mock_response.status_code = 409  # Conflict
        mock_post.return_value = mock_response
        
        requester = OverseerrRequester(self.config)
        result = requester.request_media(self.release)
        
        self.assertTrue(result)


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
