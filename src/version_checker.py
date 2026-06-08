"""
Version Checker - Compares the running version against the latest GitHub release.
"""

import logging
from typing import Optional, Tuple

import requests

logger = logging.getLogger(__name__)

DEFAULT_REPO = "Neoo-Blue/digitarr"


class VersionChecker:
    """Checks GitHub for a newer release than the one currently running."""

    def __init__(self, current_version: str, repo: str = DEFAULT_REPO):
        self.current_version = current_version
        self.repo = repo or DEFAULT_REPO

    def check(self) -> Optional[dict]:
        """Return {version, url, notes} if a newer release exists, else None.

        Never raises - a failed update check must not affect the main run.
        """
        release = self._get_latest_release()
        if not release:
            return None

        latest = release.get("tag_name") or release.get("name") or ""
        if not latest:
            return None

        if self._is_newer(latest, self.current_version):
            return {
                "version": latest,
                "url": release.get("html_url") or f"https://github.com/{self.repo}/releases",
                "notes": (release.get("body") or "").strip(),
            }
        return None

    def _get_latest_release(self) -> Optional[dict]:
        url = f"https://api.github.com/repos/{self.repo}/releases/latest"
        try:
            resp = requests.get(
                url, headers={"Accept": "application/vnd.github+json"}, timeout=10
            )
            if resp.status_code == 404:
                logger.debug(f"No published releases for {self.repo}")
                return None
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Update check failed: {e}")
            return None

    @staticmethod
    def _normalize(version: str) -> Tuple[int, ...]:
        version = version.strip().lstrip("vV")
        version = version.split("-")[0].split("+")[0]  # drop pre-release/build metadata
        parts = []
        for piece in version.split("."):
            try:
                parts.append(int(piece))
            except ValueError:
                parts.append(0)
        return tuple(parts)

    @classmethod
    def _is_newer(cls, latest: str, current: str) -> bool:
        lt = cls._normalize(latest)
        cur = cls._normalize(current)
        width = max(len(lt), len(cur))
        lt = lt + (0,) * (width - len(lt))
        cur = cur + (0,) * (width - len(cur))
        return lt > cur
