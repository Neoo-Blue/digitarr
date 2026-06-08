"""
Digitarr - Daily Digital Movie Release Checker and Media Requester
Supports: Overseerr, Riven
"""

import logging
import os
import time
from datetime import datetime, timedelta

from config_manager import ConfigManager
from release_checker import ReleaseChecker
from dvd_release_checker import DVDReleaseChecker
from combined_release_checker import CombinedReleaseChecker, DVDReleaseAdapter
from overseerr_requester import OverseerrRequester
from riven_requester import RivenRequester
from filters import FilterEngine
from discord_notifier import DiscordNotifier
from version_checker import VersionChecker
from version import __version__

logger = logging.getLogger(__name__)

# Persisted in the logs volume so the one-time Discord alert survives restarts.
UPDATE_STATE_FILE = os.path.join("logs", ".last_notified_version")


def setup_logging(config):
    """Setup logging configuration"""
    log_level = config.get("logging", {}).get("level", "INFO")
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(
        level=getattr(logging, log_level),
        format=log_format,
        handlers=[
            logging.FileHandler("digitarr.log"),
            logging.StreamHandler()
        ]
    )


def _read_last_notified_version():
    try:
        with open(UPDATE_STATE_FILE) as f:
            return f.read().strip()
    except OSError:
        return ""


def _write_last_notified_version(version):
    try:
        os.makedirs(os.path.dirname(UPDATE_STATE_FILE), exist_ok=True)
        with open(UPDATE_STATE_FILE, "w") as f:
            f.write(version)
    except OSError as e:
        logger.debug(f"Could not persist update-notification state: {e}")


def check_for_updates(version_checker, discord_notifier):
    """Log when a newer version exists (every call) and Discord-notify once.

    The log line is emitted at boot and on every run so it's always visible;
    the Discord notification fires a single time per new version.
    """
    update = version_checker.check()
    if not update:
        logger.info(f"Digitarr is up to date (version {__version__})")
        return

    latest = update["version"]
    logger.warning(
        f"A new Digitarr version is available: {latest} "
        f"(running {__version__}) - {update['url']}"
    )

    if discord_notifier.is_enabled() and _read_last_notified_version() != latest:
        if discord_notifier.send_update_notification(
            __version__, latest, update["url"], update["notes"]
        ):
            _write_last_notified_version(latest)


def run_check(release_checker, overseerr_requester, riven_requester,
              filter_engine, discord_notifier):
    """Run a single check for releases and process them"""
    logger.info("Checking for today's digital movie releases...")

    # Check for releases
    releases = release_checker.get_today_releases()
    logger.info(f"Found {len(releases)} digital movie releases for today")

    # Apply filters
    filtered_releases = filter_engine.apply_filters(releases)
    logger.info(f"After filtering: {len(filtered_releases)} releases qualify")

    # Track per-release results for Discord notifications
    # Maps tmdb_id -> {"overseerr": bool, "riven": bool}
    release_results = {}

    # Request through Overseerr
    overseerr_successful = 0
    overseerr_skipped = 0
    overseerr_failed = 0

    if overseerr_requester and filtered_releases:
        logger.info("Requesting through Overseerr...")
        for release in filtered_releases:
            tmdb_id = str(release.get("tmdb_id", ""))
            if tmdb_id not in release_results:
                release_results[tmdb_id] = {"overseerr": False, "riven": False}

            try:
                result = overseerr_requester.request_media(release)
                title = release.get("title", "Unknown")
                if result == "requested":
                    overseerr_successful += 1
                    release_results[tmdb_id]["overseerr"] = True
                    logger.info(f"Overseerr: Successfully requested {title}")
                elif result == "skipped":
                    overseerr_skipped += 1
                    logger.info(f"Overseerr: Skipped {title} (already on Overseerr)")
                else:
                    overseerr_failed += 1
                    logger.warning(f"Overseerr: Failed to request {title}")

            except Exception as e:
                overseerr_failed += 1
                logger.error(f"Overseerr: Error requesting {release.get('title', 'Unknown')}: {str(e)}")

    # Request through Riven (batch request, so we mark all as successful if batch succeeds)
    riven_success_count = 0
    riven_failed_count = 0

    if riven_requester and filtered_releases:
        logger.info("Adding to Riven...")
        riven_results = riven_requester.add_media(filtered_releases)
        riven_success_count = riven_results.get("success", 0)
        riven_failed_count = riven_results.get("failed", 0)

        # If Riven batch succeeded, mark all releases as successful
        if riven_success_count > 0:
            for release in filtered_releases:
                tmdb_id = str(release.get("tmdb_id", ""))
                if tmdb_id not in release_results:
                    release_results[tmdb_id] = {"overseerr": False, "riven": False}
                release_results[tmdb_id]["riven"] = True

        logger.info(f"Riven: Added {riven_success_count} items, {riven_failed_count} failed")

    # Log summary
    logger.info(
        f"Overseerr summary - Successful: {overseerr_successful}, "
        f"Skipped: {overseerr_skipped}, Failed: {overseerr_failed}"
    )
    logger.info(f"Riven summary - Successful: {riven_success_count}, Failed: {riven_failed_count}")

    # Send individual Discord notifications for each successful release
    if discord_notifier.is_enabled() and release_results:
        discord_notifier.send_release_notifications(filtered_releases, release_results)

    logger.info("Digitarr check completed successfully")


def main():
    """Main entry point"""
    try:
        # Load configuration
        config_manager = ConfigManager()
        config = config_manager.load_config()

        # Setup logging
        setup_logging(config)
        logger.info("Starting Digitarr - Daily Digital Movie Release Checker")

        # Determine enabled services based on API key presence
        overseerr_enabled = bool(config.get("overseerr", {}).get("api_key"))
        riven_enabled = bool(config.get("riven", {}).get("api_key"))
        discord_enabled = bool(config.get("discord", {}).get("webhook_url"))

        if not overseerr_enabled and not riven_enabled:
            raise ValueError("At least one requester (Overseerr or Riven) must be configured with an API key")

        if overseerr_enabled:
            logger.info("Overseerr is enabled (API key provided)")
        if riven_enabled:
            logger.info("Riven is enabled (API key provided)")
        if discord_enabled:
            logger.info("Discord notifications enabled")

        if not config.get("tmdb", {}).get("api_key"):
            raise ValueError("TMDB API key is required")

        # Initialize release checker based on source.
        # "both"/"all" runs TMDB and dvdsreleasedates.com together and merges them.
        release_source = config.get("release_source", "tmdb").lower()
        tmdb_api_key = config.get("tmdb", {}).get("api_key")

        if release_source in ("both", "all", "tmdb+dvdsreleasedates"):
            logger.info("Using BOTH TMDB and dvdsreleasedates.com as release sources")
            release_checker = CombinedReleaseChecker([
                ("tmdb", ReleaseChecker(config)),
                ("dvdsreleasedates", DVDReleaseAdapter(DVDReleaseChecker(tmdb_api_key))),
            ])
        elif release_source == "dvdsreleasedates":
            logger.info("Using dvdsreleasedates.com as release source")
            release_checker = DVDReleaseAdapter(DVDReleaseChecker(tmdb_api_key))
        else:
            logger.info("Using TMDB as release source")
            release_checker = ReleaseChecker(config)

        # Initialize components
        overseerr_requester = OverseerrRequester(config) if overseerr_enabled else None
        riven_requester = RivenRequester(config) if riven_enabled else None
        filter_engine = FilterEngine(config)
        discord_notifier = DiscordNotifier(config)
        update_repo = config.get("update_check", {}).get("repo")
        version_checker = VersionChecker(__version__, update_repo)

        logger.info(f"Digitarr version {__version__}")
        # Update check at boot (logs every start; Discord-notifies once).
        check_for_updates(version_checker, discord_notifier)

        # Get run settings
        run_time = config.get("run_time", "")  # e.g., "19:00" or empty to run once
        request_delay_minutes = config.get("request_delay_minutes", 0)

        if not run_time:
            # Run once and exit
            logger.info("No run_time configured - running once and exiting")
            if request_delay_minutes > 0:
                logger.info(f"Waiting {request_delay_minutes} minutes before sending requests...")
                time.sleep(request_delay_minutes * 60)
            run_check(release_checker, overseerr_requester, riven_requester,
                     filter_engine, discord_notifier)
        else:
            # Run daily at specified time
            logger.info(f"Scheduled to run daily at {run_time}")
            while True:
                # Calculate seconds until next run time
                now = datetime.now()
                target_hour, target_minute = map(int, run_time.split(":"))
                next_run = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)

                # If we've passed today's run time, schedule for tomorrow
                if next_run <= now:
                    next_run += timedelta(days=1)

                sleep_seconds = (next_run - now).total_seconds()
                logger.info(f"Next run at {next_run.strftime('%Y-%m-%d %H:%M:%S')} (in {sleep_seconds/3600:.1f} hours)")
                time.sleep(sleep_seconds)

                try:
                    # Logs the update status on every run; Discord alert stays one-time.
                    check_for_updates(version_checker, discord_notifier)
                    if request_delay_minutes > 0:
                        logger.info(f"Waiting {request_delay_minutes} minutes before sending requests...")
                        time.sleep(request_delay_minutes * 60)
                    run_check(release_checker, overseerr_requester, riven_requester,
                             filter_engine, discord_notifier)
                except Exception as e:
                    logger.error(f"Error during check: {str(e)}", exc_info=True)

    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
