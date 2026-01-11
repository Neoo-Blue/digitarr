"""
Configuration Manager - Handles loading and validating settings.json
Supports environment variable overrides
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages configuration loading and validation"""
    
    DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "settings.json"
    
    DEFAULT_SETTINGS = {
        "overseerr": {
            "api_url": "",
            "api_key": ""
        },
        "riven": {
            "api_url": "",
            "api_key": ""
        },
        "tmdb": {
            "api_key": ""
        },
        "filters": {
            "min_tmdb_rating": 0,
            "exclude_adult": True,
            "allowed_languages": [],  # empty means all languages (e.g., ["en", "es"])
            "excluded_genres": [],  # genres to exclude (e.g., ["Horror", "Documentary"])
            "excluded_certifications": []  # age ratings to exclude (e.g., ["R", "NC-17"])
        },
        "release_source": "tmdb",  # "tmdb" or "dvdsreleasedates"
        "run_time": "",  # Time to run daily (e.g., "19:00"), empty = run once
        "request_delay_minutes": 0,  # Minutes to wait after detection before sending requests
        "logging": {
            "level": "INFO"
        },
        "discord": {
            "webhook_url": ""  # Discord webhook URL for notifications
        }
    }
    
    def __init__(self, config_path: str = None):
        """Initialize config manager with optional custom path"""
        self.config_path = Path(config_path) if config_path else self.DEFAULT_CONFIG_PATH
        self.config = None
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from settings.json with environment variable overrides"""
        try:
            if self.config_path.exists():
                logger.info(f"Loading configuration from {self.config_path}")
                with open(self.config_path, 'r') as f:
                    self.config = json.load(f)
                
                # Merge with defaults for missing keys
                self.config = self._merge_with_defaults(self.config)
            else:
                logger.warning(f"Config file not found at {self.config_path}")
                logger.info("Creating default configuration")
                self.config = self.DEFAULT_SETTINGS.copy()
                self._save_config(self.config)
            
            # Apply environment variable overrides
            self.config = self._apply_env_overrides(self.config)
            
            self._validate_config(self.config)
            return self.config
        
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in settings.json: {str(e)}")
        except Exception as e:
            raise Exception(f"Error loading configuration: {str(e)}")
    
    def _merge_with_defaults(self, config: Dict) -> Dict:
        """Recursively merge config with defaults"""
        merged = self.DEFAULT_SETTINGS.copy()
        for key, value in config.items():
            if isinstance(value, dict) and key in merged:
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
        return merged
    
    def _validate_config(self, config: Dict) -> None:
        """Validate configuration settings"""
        # Check if at least one requester is configured
        overseerr_configured = bool(config.get("overseerr", {}).get("api_key"))
        riven_configured = bool(config.get("riven", {}).get("api_key"))

        if not overseerr_configured and not riven_configured:
            logger.warning("Neither Overseerr nor Riven API key is configured - at least one is required")

        # Validate Overseerr URL if API key is provided
        if overseerr_configured:
            url = config.get("overseerr", {}).get("api_url", "")
            if url and not (url.startswith("http://") or url.startswith("https://")):
                raise ValueError("Overseerr API URL must start with http:// or https://")

        # Validate Riven URL if API key is provided
        if riven_configured:
            url = config.get("riven", {}).get("api_url", "")
            if url and not (url.startswith("http://") or url.startswith("https://")):
                raise ValueError("Riven API URL must start with http:// or https://")

        # Validate filters
        filters = config.get("filters", {})
        if filters.get("min_tmdb_rating", 0) < 0 or filters.get("min_tmdb_rating", 0) > 10:
            raise ValueError("min_tmdb_rating must be between 0 and 10")
    
    def _save_config(self, config: Dict) -> None:
        """Save default configuration to settings.json"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
            logger.info(f"Default configuration saved to {self.config_path}")
        except Exception as e:
            logger.error(f"Error saving configuration: {str(e)}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        if self.config is None:
            self.load_config()
        return self.config.get(key, default)
    
    def _apply_env_overrides(self, config: Dict) -> Dict:
        """Apply environment variable overrides to configuration

        Supports environment variables:
        - TMDB_API_KEY (required)
        - OVERSEERR_API_URL, OVERSEERR_API_KEY (optional - enabled if API key provided)
        - RIVEN_API_URL, RIVEN_API_KEY (optional - enabled if API key provided)
        - DISCORD_WEBHOOK_URL (optional - enabled if provided)
        - RUN_TIME (time to run daily, e.g., "19:00")
        - REQUEST_DELAY_MINUTES (minutes to wait before sending requests)
        - FILTERS_* for filtering options
        - LOGGING_LEVEL
        """
        # Nested config mappings (section, key, type)
        env_map = {
            "OVERSEERR_API_KEY": ("overseerr", "api_key"),
            "OVERSEERR_API_URL": ("overseerr", "api_url"),
            "RIVEN_API_KEY": ("riven", "api_key"),
            "RIVEN_API_URL": ("riven", "api_url"),
            "TMDB_API_KEY": ("tmdb", "api_key"),
            "DISCORD_WEBHOOK_URL": ("discord", "webhook_url"),
            "FILTERS_MIN_TMDB_RATING": ("filters", "min_tmdb_rating", "float"),
            "FILTERS_EXCLUDE_ADULT": ("filters", "exclude_adult", "bool"),
            "FILTERS_ALLOWED_LANGUAGES": ("filters", "allowed_languages", "list"),
            "FILTERS_EXCLUDED_GENRES": ("filters", "excluded_genres", "list"),
            "FILTERS_EXCLUDED_CERTIFICATIONS": ("filters", "excluded_certifications", "list"),
            "LOGGING_LEVEL": ("logging", "level"),
        }

        # Top-level config mappings (key, type)
        top_level_map = {
            "RELEASE_SOURCE": ("release_source", "str"),
            "RUN_TIME": ("run_time", "str"),
            "REQUEST_DELAY_MINUTES": ("request_delay_minutes", "int"),
        }

        # Apply nested config overrides
        for env_var, path_info in env_map.items():
            value = os.getenv(env_var)
            if value is not None and value.strip():
                section = path_info[0]
                key = path_info[1]
                data_type = path_info[2] if len(path_info) > 2 else "str"

                # Ensure section exists
                if section not in config:
                    config[section] = {}

                # Convert value to appropriate type
                if data_type == "bool":
                    config[section][key] = value.lower() in ("true", "1", "yes", "on")
                elif data_type == "int":
                    config[section][key] = int(value)
                elif data_type == "float":
                    config[section][key] = float(value)
                elif data_type == "list":
                    config[section][key] = [item.strip() for item in value.split(",") if item.strip()]
                else:
                    config[section][key] = value

                logger.info(f"Applied environment override: {env_var}")

        # Apply top-level config overrides
        for env_var, key_info in top_level_map.items():
            value = os.getenv(env_var)
            if value is not None and value.strip():
                key = key_info[0]
                data_type = key_info[1] if len(key_info) > 1 else "str"

                if data_type == "int":
                    config[key] = int(value)
                elif data_type == "float":
                    config[key] = float(value)
                else:
                    config[key] = value

                logger.info(f"Applied environment override: {env_var}")

        return config
