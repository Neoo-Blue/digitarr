"""
Riven Requester - Handles requests to Riven API for movies
"""

import logging
import requests
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class RivenRequester:
    """Handles requests to Riven API"""

    def __init__(self, config: Dict[str, Any]):
        """Initialize Riven requester with configuration"""
        self.config = config
        self.api_url = config.get("riven", {}).get("api_url", "http://localhost:8083")
        self.api_key = config.get("riven", {}).get("api_key", "")

        if not self.api_key:
            logger.warning("Riven API key is not configured")

    def is_enabled(self) -> bool:
        """Check if Riven is enabled (enabled automatically when API key is provided)"""
        return bool(self.api_key) and bool(self.api_url)

    def add_media(self, releases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Add movies to Riven

        Args:
            releases: List of release dictionaries with tmdb_id

        Returns:
            Dictionary with success count and results
        """
        if not self.is_enabled():
            logger.warning("Riven is not enabled or API key not configured")
            return {"success": 0, "failed": 0, "results": []}

        # All releases are movies
        movies = [r for r in releases if r.get("type") == "movie"]

        if movies:
            return self._add_items("movie", movies)

        return {"success": 0, "failed": 0, "results": []}
    
    def _get_unknown_items(self, media_type: str) -> Dict[str, str]:
        """Get all items in 'Unknown' state from Riven

        Returns:
            Dictionary mapping tmdb_id -> riven internal id
        """
        try:
            endpoint = f"{self.api_url}/api/v1/items"
            headers = {"x-api-key": self.api_key}
            params = {
                "limit": 500,
                "page": 1,
                "type": media_type,
                "states": "Unknown",
                "extended": "false",
                "count_only": "false"
            }

            response = requests.get(endpoint, headers=headers, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                items = data.get("items", [])
                # Map tmdb_id -> internal id
                return {str(item.get("tmdb_id")): str(item.get("id")) for item in items if item.get("tmdb_id")}
            else:
                logger.warning(f"Failed to get Unknown items: {response.status_code}")
                return {}

        except Exception as e:
            logger.error(f"Error getting Unknown items: {str(e)}")
            return {}

    def _remove_items(self, item_ids: List[str]) -> bool:
        """Remove items from Riven by their internal IDs

        Args:
            item_ids: List of Riven internal item IDs to remove

        Returns:
            True if successful, False otherwise
        """
        if not item_ids:
            return True

        try:
            endpoint = f"{self.api_url}/api/v1/items/remove"
            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json"
            }
            payload = {"ids": item_ids}

            response = requests.delete(endpoint, json=payload, headers=headers, timeout=10)

            if response.status_code == 200:
                logger.info(f"Removed {len(item_ids)} item(s) from Riven for re-request")
                return True
            else:
                logger.warning(f"Failed to remove items: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error removing items: {str(e)}")
            return False

    def _add_items(self, media_type: str, releases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Add items of a specific media type to Riven

        If items already exist in 'Unknown' state, they are removed first
        and then re-added to trigger a fresh request.

        Args:
            media_type: 'movie' or 'tv'
            releases: List of releases to add

        Returns:
            Dictionary with results
        """
        try:
            # Extract TMDB IDs
            tmdb_ids = [str(r.get("tmdb_id")) for r in releases if r.get("tmdb_id")]

            if not tmdb_ids:
                logger.warning(f"No TMDB IDs found for {media_type}s")
                return {"success": 0, "failed": len(releases), "results": []}

            # Check for existing items in Unknown state and remove them
            unknown_items = self._get_unknown_items(media_type)
            items_to_remove = []
            for tmdb_id in tmdb_ids:
                if tmdb_id in unknown_items:
                    items_to_remove.append(unknown_items[tmdb_id])
                    logger.info(f"Found existing Unknown item with TMDB ID {tmdb_id}, will re-request")

            if items_to_remove:
                self._remove_items(items_to_remove)
            
            endpoint = f"{self.api_url}/api/v1/items/add"
            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            payload = {
                "media_type": media_type,
                "tmdb_ids": tmdb_ids
            }
            
            logger.debug(f"Sending request to Riven: {endpoint}")
            logger.debug(f"Payload: {payload}")
            
            response = requests.post(endpoint, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"Successfully added {len(tmdb_ids)} {media_type}(s) to Riven")
                return {
                    "success": len(tmdb_ids),
                    "failed": 0,
                    "results": [{"status": "success", "ids": tmdb_ids}]
                }
            elif response.status_code == 404:
                logger.warning(f"Riven API endpoint not found (404)")
                return {
                    "success": 0,
                    "failed": len(tmdb_ids),
                    "results": [{"status": "error", "code": 404, "message": "Not found"}]
                }
            elif response.status_code == 422:
                logger.error(f"Validation error (422): {response.text}")
                return {
                    "success": 0,
                    "failed": len(tmdb_ids),
                    "results": [{"status": "error", "code": 422, "message": "Validation error"}]
                }
            else:
                logger.error(f"Error adding to Riven: {response.status_code} - {response.text}")
                return {
                    "success": 0,
                    "failed": len(tmdb_ids),
                    "results": [{"status": "error", "code": response.status_code}]
                }
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error adding to Riven: {str(e)}")
            return {
                "success": 0,
                "failed": len(releases),
                "results": [{"status": "error", "message": str(e)}]
            }
        except Exception as e:
            logger.error(f"Error adding to Riven: {str(e)}")
            return {
                "success": 0,
                "failed": len(releases),
                "results": [{"status": "error", "message": str(e)}]
            }
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """Get Riven API status"""
        try:
            endpoint = f"{self.api_url}/health"
            response = requests.get(endpoint, timeout=5)
            
            if response.status_code == 200:
                logger.debug("Riven API is healthy")
                return {"status": "healthy"}
            else:
                logger.warning(f"Riven API returned status {response.status_code}")
                return {"status": "unhealthy", "code": response.status_code}
        
        except Exception as e:
            logger.error(f"Error checking Riven status: {str(e)}")
            return {"status": "unreachable", "error": str(e)}
