"""
Overseerr Requester - Handles requests to Overseerr API
Adds movies to the request list without requiring Radarr/Sonarr configuration
"""

import logging
import requests
from typing import Dict, Any

logger = logging.getLogger(__name__)


class OverseerrRequester:
    """Handles requests to Overseerr API"""

    def __init__(self, config: Dict[str, Any]):
        """Initialize Overseerr requester with configuration"""
        self.config = config
        self.api_url = config.get("overseerr", {}).get("api_url", "http://localhost:5055")
        self.api_key = config.get("overseerr", {}).get("api_key", "")

        if not self.api_key:
            raise ValueError("Overseerr API key is required")

    def request_media(self, release: Dict[str, Any]) -> str:
        """Request media through Overseerr - adds to request list only.

        Returns one of: "requested", "skipped", "failed".
        "skipped" means the title was already on Overseerr (not an error).
        """
        try:
            tmdb_id = release.get("tmdb_id")
            title = release.get("title", "Unknown")

            if not tmdb_id:
                logger.warning(f"Cannot request {title} - no TMDB ID")
                return "failed"

            # Check if already requested or available
            if self._is_already_requested(tmdb_id):
                logger.info(f"{title} already requested or available, skipping")
                return "skipped"

            # Make the request - minimal payload, just adds to request list
            endpoint = f"{self.api_url}/api/v1/request"
            headers = {
                "X-Api-Key": self.api_key,
                "Content-Type": "application/json"
            }

            payload = {
                "mediaId": int(tmdb_id),
                "mediaType": "movie"
            }

            response = requests.post(endpoint, json=payload, headers=headers, timeout=10)

            if response.status_code in [200, 201]:
                logger.info(f"Successfully added {title} to Overseerr request list")
                return "requested"
            elif response.status_code == 409:
                logger.info(f"{title} already exists in Overseerr")
                return "skipped"
            else:
                logger.error(f"Error requesting {title}: {response.status_code} - {response.text}")
                return "failed"

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error requesting media: {str(e)}")
            return "failed"
        except Exception as e:
            logger.error(f"Error requesting media: {str(e)}")
            return "failed"
    
    def _is_already_requested(self, tmdb_id: int) -> bool:
        """Check if movie has already been requested or is available"""
        try:
            # Check media status in Overseerr
            endpoint = f"{self.api_url}/api/v1/movie/{tmdb_id}"
            headers = {"X-Api-Key": self.api_key}

            response = requests.get(endpoint, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                media_info = data.get("mediaInfo", {})
                # Check if already requested or available
                status = media_info.get("status")
                # Status: 1=unknown, 2=pending, 3=processing, 4=partially available, 5=available
                if status and status >= 2:
                    return True

            return False

        except Exception as e:
            logger.warning(f"Error checking if media already requested: {str(e)}")
            return False
