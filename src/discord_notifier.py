"""
Discord Notifier - Sends notifications via Discord webhook
"""

import logging
import requests
import time
from typing import Dict, List, Any
from datetime import datetime

logger = logging.getLogger(__name__)

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
# Discord rate limit: ~1 second between messages
DISCORD_RATE_LIMIT_DELAY = 1.0


class DiscordNotifier:
    """Handles Discord webhook notifications"""

    def __init__(self, config: Dict[str, Any]):
        """Initialize Discord notifier with configuration"""
        self.config = config
        self.webhook_url = config.get("discord", {}).get("webhook_url", "")

    def is_enabled(self) -> bool:
        """Check if Discord notifications are enabled"""
        return bool(self.webhook_url)

    def send_release_notifications(self, releases: List[Dict[str, Any]],
                                    results: Dict[str, Dict[str, bool]]) -> int:
        """Send individual Discord notifications for each release

        Args:
            releases: List of release dictionaries with title, overview, poster_path, etc.
            results: Dict mapping tmdb_id to {"overseerr": bool, "riven": bool} success status

        Returns:
            Number of notifications sent successfully
        """
        if not self.is_enabled():
            logger.debug("Discord notifications not enabled")
            return 0

        sent_count = 0

        for release in releases:
            tmdb_id = str(release.get("tmdb_id", ""))
            release_result = results.get(tmdb_id, {})

            # Only notify for successful requests
            if not release_result.get("overseerr") and not release_result.get("riven"):
                continue

            try:
                success = self._send_release_notification(release, release_result)
                if success:
                    sent_count += 1

                # Delay between messages to avoid Discord rate limiting
                time.sleep(DISCORD_RATE_LIMIT_DELAY)

            except Exception as e:
                logger.error(f"Error sending notification for {release.get('title')}: {str(e)}")

        logger.info(f"Sent {sent_count} Discord notifications")
        return sent_count

    def _send_release_notification(self, release: Dict[str, Any],
                                    result: Dict[str, bool]) -> bool:
        """Send a single release notification"""
        title = release.get("title", "Unknown Title")
        overview = release.get("overview", "No description available.")
        poster_path = release.get("poster_path", "")
        vote_average = release.get("vote_average", 0)

        # Build where it was added
        added_to = []
        if result.get("overseerr"):
            added_to.append("Overseerr")
        if result.get("riven"):
            added_to.append("Riven")
        added_str = " & ".join(added_to)

        # Truncate overview if too long
        if len(overview) > 200:
            overview = overview[:197] + "..."

        # Build embed
        embed = {
            "title": f"🎬 {title} has been released!",
            "description": overview,
            "color": 0x00FF00,  # Green
            "fields": [
                {"name": "Rating", "value": f"⭐ {vote_average:.1f}/10", "inline": True},
                {"name": "Added to", "value": f"✅ {added_str}", "inline": True}
            ],
            "footer": {"text": "Digitarr - Digital Movie Release Checker"},
            "timestamp": datetime.utcnow().isoformat()
        }

        # Add poster image if available
        if poster_path:
            embed["thumbnail"] = {"url": f"{TMDB_IMAGE_BASE}{poster_path}"}

        payload = {"embeds": [embed]}

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )

            if response.status_code in (200, 204):
                logger.debug(f"Discord notification sent for: {title}")
                return True
            else:
                logger.error(f"Discord webhook failed for {title}: {response.status_code}")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error sending Discord notification: {str(e)}")
            return False

    def send_update_notification(self, current_version: str, latest_version: str,
                                  release_url: str, notes: str = "") -> bool:
        """Send a one-off notification that a new Digitarr version is available."""
        if not self.is_enabled():
            return False

        description = (
            f"A new version of Digitarr is available.\n\n"
            f"**Running:** {current_version}\n**Latest:** {latest_version}"
        )
        if notes:
            trimmed = notes.strip()
            if len(trimmed) > 500:
                trimmed = trimmed[:497] + "..."
            description += f"\n\n**Release notes:**\n{trimmed}"

        embed = {
            "title": "⬆️ Digitarr update available",
            "description": description,
            "url": release_url,
            "color": 0x3498DB,  # Blue
            "footer": {"text": "Digitarr - Digital Movie Release Checker"},
            "timestamp": datetime.utcnow().isoformat()
        }
        payload = {"embeds": [embed]}

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            if response.status_code in (200, 204):
                logger.info(f"Sent Discord update notification for version {latest_version}")
                return True
            logger.error(f"Discord update notification failed: {response.status_code}")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error sending update notification: {str(e)}")
            return False

    def test_webhook(self) -> bool:
        """Test the Discord webhook connection"""
        if not self.is_enabled():
            logger.warning("Discord webhook URL not configured")
            return False

        try:
            payload = {
                "embeds": [{
                    "title": "🔔 Digitarr Test",
                    "description": "Discord webhook is configured correctly!",
                    "color": 0x00FF00,
                    "timestamp": datetime.utcnow().isoformat()
                }]
            }

            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )

            if response.status_code in (200, 204):
                logger.info("Discord webhook test successful")
                return True
            else:
                logger.error(f"Discord webhook test failed: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Discord webhook test error: {str(e)}")
            return False

