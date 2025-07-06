# host_config.py

import json
import os
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Default configuration file path
CONFIG_DIR = "config"
os.makedirs(CONFIG_DIR, exist_ok=True)

# Then update the config file path
HOST_CONFIG_FILE = os.path.join(CONFIG_DIR, "host_config.json")

# Default configuration
DEFAULT_HOST_CONFIG = {
    "primary_hosts": ["rapidgator", "nitroflare"],  # The two main premium hosts
    "mirror_hosts": ["uploadgig", "filefactory", "keep2share"],  # Additional mirror hosts
    "host_display_names": {  # Friendly names for display
        "rapidgator": "Rapidgator",
        "nitroflare": "Nitroflare",
        "uploadgig": "Uploadgig",
        "filefactory": "FileFactory",
        "keep2share": "Keep2Share"
    },
    "host_patterns": {  # URL patterns for detection
        "rapidgator": r"rapidgator\.net",
        "nitroflare": r"nitroflare\.com",
        "uploadgig": r"uploadgig\.com",
        "filefactory": r"filefactory\.com",
        "keep2share": r"keep2share\.cc"
    }
}

def load_host_config() -> Dict:
    """
    Load host configuration from file or create default if not exists.
    Returns the host configuration dictionary.
    """
    if os.path.exists(HOST_CONFIG_FILE):
        try:
            with open(HOST_CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                
            # Validate and merge with defaults if needed
            if not isinstance(config.get("primary_hosts"), list):
                config["primary_hosts"] = DEFAULT_HOST_CONFIG["primary_hosts"]
            if not isinstance(config.get("mirror_hosts"), list):
                config["mirror_hosts"] = DEFAULT_HOST_CONFIG["mirror_hosts"]
            if not isinstance(config.get("host_display_names"), dict):
                config["host_display_names"] = DEFAULT_HOST_CONFIG["host_display_names"]
            if not isinstance(config.get("host_patterns"), dict):
                config["host_patterns"] = DEFAULT_HOST_CONFIG["host_patterns"]
                
            return config
        except Exception as e:
            logger.error(f"Failed to load host config: {e}, using defaults")
            return DEFAULT_HOST_CONFIG.copy()
    else:
        # Create default config file
        save_host_config(DEFAULT_HOST_CONFIG)
        return DEFAULT_HOST_CONFIG.copy()

def save_host_config(config: Dict) -> None:
    """
    Save host configuration to file.
    """
    try:
        with open(HOST_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save host config: {e}")

def update_primary_hosts(new_hosts: List[str]) -> None:
    """
    Update the primary hosts in configuration.
    Args:
        new_hosts: List of host identifiers (e.g., ["uploadgig", "filefactory"])
    """
    config = load_host_config()
    config["primary_hosts"] = new_hosts
    save_host_config(config)

def add_mirror_host(host: str, pattern: str, display_name: Optional[str] = None) -> None:
    """
    Add a new mirror host to configuration.
    Args:
        host: Host identifier (e.g., "mega")
        pattern: URL pattern for detection (e.g., r"mega\.nz")
        display_name: Optional friendly name for display
    """
    config = load_host_config()
    
    if host not in config["mirror_hosts"]:
        config["mirror_hosts"].append(host)
    
    config["host_patterns"][host] = pattern
    config["host_display_names"][host] = display_name or host.capitalize()
    
    save_host_config(config)

def remove_host(host: str) -> None:
    """
    Remove a host from configuration (both primary and mirror lists).
    Args:
        host: Host identifier to remove
    """
    config = load_host_config()
    
    if host in config["primary_hosts"]:
        config["primary_hosts"].remove(host)
    
    if host in config["mirror_hosts"]:
        config["mirror_hosts"].remove(host)
    
    if host in config["host_patterns"]:
        del config["host_patterns"][host]
    
    if host in config["host_display_names"]:
        del config["host_display_names"][host]
    
    save_host_config(config)

def detect_host(url: str) -> str:
    """
    Detect which host a URL belongs to based on configured patterns.
    Args:
        url: The URL to analyze
    Returns:
        Host identifier (e.g., "rapidgator") or "unknown" if no match
    """
    if not url or not isinstance(url, str):
        return "unknown"
    
    config = load_host_config()
    url_lower = url.lower()
    
    for host, pattern in config["host_patterns"].items():
        if re.search(pattern, url_lower):
            return host
    
    return "unknown"

def get_host_display_name(host: str) -> str:
    """
    Get the display name for a host.
    Args:
        host: Host identifier (e.g., "rapidgator")
    Returns:
        Friendly display name (e.g., "Rapidgator")
    """
    config = load_host_config()
    return config["host_display_names"].get(host, host.capitalize())

def get_primary_hosts() -> List[str]:
    """Get the list of primary hosts"""
    config = load_host_config()
    return config["primary_hosts"]

def get_mirror_hosts() -> List[str]:
    """Get the list of mirror hosts"""
    config = load_host_config()
    return config["mirror_hosts"]

def get_all_hosts() -> List[str]:
    """Get all configured hosts (primary + mirror)"""
    config = load_host_config()
    return list(set(config["primary_hosts"] + config["mirror_hosts"]))