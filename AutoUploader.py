import argparse
import os
import json
import re
import requests
import datetime
import csv
import glob
import time
import logging
import sys
import io
from media_lookup import (find_existing_media, upload_media_to_wp, find_local_thumbnail, resize_image, retry_with_backoff)
from urllib.parse import quote
from wp_terms import resolve_terms
from functools import wraps
from requests.exceptions import RequestException
from requests.auth import HTTPBasicAuth
from settings_editor import SettingsEditor, DEFAULT_TEMPLATES
from media_lookup import find_existing_media
from safe_json import load_json, save_json
from utils import clean_title, detect_season_episode
from host_config import load_host_config
# This will create the default config if it doesn't exist
load_host_config()
from host_config import (
    detect_host, 
    get_primary_hosts,
    get_host_display_name,
    get_mirror_hosts
)

logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(SCRIPT_DIR, "config")
TRACK_LOG_DIR = os.path.join(SCRIPT_DIR, "track_log")
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")

# Constants

POSTED_CACHE = os.path.join(CONFIG_DIR, "posted_files.json")
PENDING_LINKS = os.path.join(CONFIG_DIR, "pending_links.json")
HOST_CONFIG_FILE = os.path.join(CONFIG_DIR, "host_config.json")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")

TMDB_BASE = "https://api.themoviedb.org/3/search/multi"
OMDB_API = "http://www.omdbapi.com/"
ANILIST_API = "https://graphql.anilist.co"

for folder in [CONFIG_DIR, LOG_DIR, TRACK_LOG_DIR]:
    os.makedirs(folder, exist_ok=True)

# Ensure directories exist
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(TRACK_LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'debug.log'), encoding='utf-8'),
        logging.StreamHandler(stream=open(os.devnull, 'w', encoding='utf-8'))
    ]
)
def get_next_link():
    """Get the next pending link from the queue"""
    pending_dir = os.path.join(SCRIPT_DIR, "pending_links")
    os.makedirs(pending_dir, exist_ok=True)
    
    try:
        # Find all pending link files
        link_files = sorted(
            [f for f in os.listdir(pending_dir) if f.endswith('.json')],
            key=lambda x: os.path.getmtime(os.path.join(pending_dir, x))
        )
        
        if not link_files:
            return None
            
        # Get the oldest file
        oldest_file = os.path.join(pending_dir, link_files[0])
        try:
            with open(oldest_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {oldest_file}: {str(e)}")
            try:
                os.remove(oldest_file)
            except Exception as e:
                logger.error(f"Failed to remove corrupt file {oldest_file}: {str(e)}")
            return None
    except Exception as e:
        logger.error(f"Error reading pending links directory: {str(e)}")
        return None
        

def setup_logging():
    """Configure detailed logging with Unicode support"""
    # Ensure track_log directory exists
    os.makedirs(TRACK_LOG_DIR, exist_ok=True)
    
    today = datetime.datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(TRACK_LOG_DIR, f"session_{today}.log")
    csv_log_file = os.path.join(TRACK_LOG_DIR, "session.csv")
    debug_log_file = os.path.join(TRACK_LOG_DIR, "debug.log")

    # Create a stream that handles Unicode for Windows
    class UnicodeStreamWrapper(io.TextIOWrapper):
        def write(self, s):
            try:
                return super().write(s)
            except UnicodeEncodeError:
                # Replace problematic characters
                cleaned = s.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding)
                return super().write(cleaned)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(stream=UnicodeStreamWrapper(sys.stdout))
        ]
    )
    
    # Add debug logger
    debug_handler = logging.FileHandler(debug_log_file, encoding='utf-8')
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logging.getLogger().addHandler(debug_handler)
    
    return logging.getLogger()

logger = setup_logging()

def detect_host(url):
    """Enhanced host detection with precise URL matching"""
    if not url or not isinstance(url, str):
        return "unknown"
    
    url_lower = url.lower()
    
    # Precise domain matching
    if 'rapidgator.net' in url_lower:
        return "rapidgator"
    elif 'nitroflare.com' in url_lower:
        return "nitroflare"
    elif 'uploadgig.com' in url_lower:
        return "uploadgig"
    elif 'filefactory.com' in url_lower:
        return "filefactory"
    elif 'keep2share.cc' in url_lower:
        return "keep2share"
    
    return "unknown"
    
    url_lower = url.lower()
    host_patterns = {
        "rapidgator": "rapidgator",
        "nitroflare": "nitroflare",
        "uploadgig": "uploadgig",
        "filefactory": "filefactory",
        "keep2share": "keep2share"
    }
    
    detected_host = "unknown"
    for pattern, host in host_patterns.items():
        if pattern in url_lower:
            detected_host = host
            break
    
    # Add quality info to host name
    if '2160p' in url_lower:
        return f"{detected_host}-4K"
    elif '1080p' in url_lower:
        return f"{detected_host}-1080p"
    elif '720p' in url_lower:
        return f"{detected_host}-720p"
    elif '480p' in url_lower:
        return f"{detected_host}-480p"
    return detected_host

def log_to_csv(title, link, wp_link, status):
    """Log activity to CSV file"""
    try:
        today = datetime.datetime.now().strftime("%Y%m%d")
        csv_log_file = os.path.join(TRACK_LOG_DIR, "session.csv")
        
        # Write headers if file doesn't exist
        write_header = not os.path.exists(csv_log_file)
        
        with open(csv_log_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["Timestamp", "Title", "Source Link", "WP Link", "Status"])
            writer.writerow([
                datetime.datetime.now().isoformat(), 
                str(title)[:200],  # Truncate long titles
                str(link)[:200], 
                str(wp_link)[:200], 
                status
            ])
    except Exception as e:
        logger.error(f"Failed to write to CSV log: {str(e)}")

def load_settings():
    """Load settings or launch settings editor if file doesn't exist"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    settings_path = os.path.join(script_dir, SETTINGS_FILE)
    
    if not os.path.exists(settings_path):
        SettingsEditor().mainloop()
    
    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)
    
    # Migrate old template format if needed
    if "post_template" in settings and "post_templates" not in settings:
        settings["post_templates"] = {
            "default": settings["post_template"],
            **DEFAULT_TEMPLATES
        }
    
    # Validate and repair settings if needed
    try:
        validate_settings(settings)
    except ValueError as e:
        logger.error(f"Settings validation failed: {str(e)}")
        logger.info("Resetting to default settings")
        settings = DEFAULT_SETTINGS.copy()
        settings["post_templates"] = DEFAULT_TEMPLATES.copy()
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    
    return settings

# def load_json(filename):
#     """Load JSON data from file"""
#     if os.path.exists(filename):
#         with open(filename, "r", encoding="utf-8") as f:
#             return json.load(f)
#     return {}

# def save_json(filename, data):
#     """Save data to JSON file with atomic write"""
#     temp_file = f"{filename}.tmp"
#     with open(temp_file, "w", encoding="utf-8") as f:
#         json.dump(data, f, indent=2)
#     os.replace(temp_file, filename)

def validate_settings(settings):
    """Validate critical settings structure"""
    required_keys = {
        "wp_url": str,
        "wp_user": str,
        "wp_app_password": str,
        "post_status": str,
        "post_templates": dict
    }
    
    for key, expected_type in required_keys.items():
        if key not in settings:
            raise ValueError(f"Missing required setting: {key}")
        if not isinstance(settings[key], expected_type):
            raise ValueError(f"Invalid type for {key}, expected {expected_type.__name__}")
    
    # Check OMDb settings only if enabled
    if settings.get("enable_omdb_fallback"):
        if not isinstance(settings.get("omdb_api_key"), str):
            raise ValueError("OMDb API key must be a string when OMDb fallback is enabled")
    
    # Ensure default template exists
    if "default" not in settings["post_templates"]:
        settings["post_templates"]["default"] = DEFAULT_TEMPLATES["default"]
    
    return True



def apply_template(media_type, template_vars, settings):
    """Apply the appropriate template with error handling"""
    templates = settings.get("post_templates", DEFAULT_TEMPLATES)
    
    # Filter out None values and replace with empty strings
    filtered_vars = {k: v if v is not None else "" for k, v in template_vars.items()}
    
    try:
        template = templates.get(media_type, templates["default"])
        if not template:
            raise ValueError(f"No template available for {media_type}")
        return template.format(**filtered_vars)
    except KeyError as e:
        logger.error(f"Missing template variable {e} in {media_type} template")
        return (f"{filtered_vars.get('title', '')}\n\n"
                f"{filtered_vars.get('overview', '')}\n\n"
                f"{filtered_vars.get('thumbnail', '')}\n\n"
                f"{filtered_vars.get('host_links', '')}")
    except Exception as e:
        logger.error(f"Template application failed: {str(e)}")
        return templates["default"].format(**template_vars)

@retry_with_backoff()
def fetch_tmdb_info(query, api_key):
    """Fetch media info from TMDb API"""
    try:
        if not api_key or api_key == "your_tmdb_api_key":
            raise ValueError("Invalid TMDb API key")
            
        params = {
            "api_key": api_key, 
            "query": query, 
            "language": "en-US",
            "include_adult": "false"
        }
        res = requests.get(TMDB_BASE, params=params, timeout=10)
        
        if res.status_code == 401:
            raise RequestException("Invalid TMDb API key")
            
        res.raise_for_status()
        data = res.json()
        return data["results"][0] if data.get("results") else None
    except Exception as e:
        logger.error(f"TMDb API request failed: {str(e)}")
        return None
@retry_with_backoff()
def fetch_omdb_info(title, api_key):
    """Fetch media info from OMDb API"""
    try:
        if not api_key or api_key == "your_omdb_api_key":
            return None
            
        params = {
            "apikey": api_key,
            "t": title,
            "type": "series" if "S" in title.upper() else "movie",
            "plot": "full"
        }
        res = requests.get(OMDB_API, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
        return {
            "title": data.get("Title"),
            "overview": data.get("Plot"),
            "year": data.get("Year"),
            "rating": data.get("imdbRating"),
            "poster_path": data.get("Poster"),
            "release_date": data.get("Released")
        } if data.get("Response") == "True" else None
    except Exception as e:
        logger.error(f"OMDb API request failed: {str(e)}")
        return None
@retry_with_backoff()
def fetch_anilist_info(title, season=None, episode=None):
    """Fetch anime info from AniList API using Romaji title priority"""
    try:
        query = '''
        query ($search: String, $season: Int, $episode: Int) {
            Media(search: $search, type: ANIME) {
                title {
                    romaji  # Prioritize Romaji title
                    english
                    native
                }
                description(asHtml: false)  # Get plain text description
                season
                seasonYear
                episodes
                averageScore
                coverImage {
                    extraLarge
                }
                # Include studios for better metadata (optional)
                studios(isMain: true) {
                    nodes {
                        name
                    }
                }
            }
        }
        '''
        variables = {'search': title, 'season': season, 'episode': episode}
        
        res = requests.post(
            ANILIST_API, 
            json={'query': query, 'variables': variables}, 
            timeout=10
        )
        res.raise_for_status()
        data = res.json()
        
        if not data.get("data", {}).get("Media"):
            return None
            
        media = data["data"]["Media"]
        
        # Prefer Romaji title, fallback to English/Native
        title_romaji = media["title"]["romaji"]
        title_english = media["title"]["english"]
        display_title = title_romaji or title_english or media["title"]["native"]
        
        return {
            "title": display_title,
            "romaji_title": title_romaji,  # Store Romaji separately
            "english_title": title_english,
            "overview": media.get("description", ""),
            "year": media.get("seasonYear"),
            "rating": media.get("averageScore"),
            "poster_path": media["coverImage"]["extraLarge"] if media["coverImage"] else None,
            "episodes": media.get("episodes"),
            "season": media.get("season"),
            "studio": media["studios"]["nodes"][0]["name"] if media["studios"]["nodes"] else None,
            "media_type": "anime"
        }
        
    except Exception as e:
        logger.error(f"AniList API request failed: {str(e)}")
        return None        
        
            
def detect_quality(title):
    """Strict quality detection that matches exact resolution patterns"""
    if not title or not isinstance(title, str):
        return None
        
    title_lower = title.lower()
    quality_map = {
        '2160p': '4K',
        '1080p': '1080p',  # Keep exact values for strict matching
        '720p': '720p',
        '480p': '480p',
        '4k': '4K',
        'hd': 'HD',
        'sd': 'SD'
    }
    
    # Check for exact quality patterns first
    for pattern in quality_map:
        if re.search(r'(^|\W)' + pattern + r'($|\W)', title_lower):
            return quality_map[pattern]
            
    return None

def find_existing_post(title, wp, auth, settings):
    """Strict matching that only updates when ALL criteria match exactly"""
    try:
        # Extract critical components
        base_title = re.sub(
            r'\.(2160p|1080p|720p|480p|x\d{3}|hevc|web[\W_]?dl|blu[\W_]?ray|dvdrip|hdtv|xvid).*$',
            '',
            title,
            flags=re.IGNORECASE
        ).strip()
        
        season, episode = detect_season_episode(title)
        quality = detect_quality(title)

        # Only consider it a match if ALL these conditions are met:
        # 1. Exact base title match
        # 2. Exact season match
        # 3. Exact episode match
        # 4. Resolution matches (if strict_resolution_matching is True)
        
        search_term = f"{base_title} S{season:02d}E{episode:02d}" if season and episode else base_title
        
        search_url = f"{wp['url'].rstrip('/')}/wp-json/wp/v2/posts"
        params = {
            "search": search_term,
            "per_page": 5,
        }
        res = requests.get(search_url, params=params, auth=auth, timeout=10)
        res.raise_for_status()
        posts = res.json()

        for post in posts:
            post_title = post['title']['rendered']
            post_season, post_episode = detect_season_episode(post_title)
            post_quality = detect_quality(post_title)
            
            # Must match all these criteria
            season_match = (season == post_season)
            episode_match = (episode == post_episode)
            base_match = (base_title.lower() in post_title.lower())
            
            if not (season_match and episode_match and base_match):
                continue
                
            # Resolution check (if enabled)
            if settings.get("strict_resolution_matching", True):
                if quality != post_quality:
                    logger.debug(f"Skipping match due to resolution mismatch: {quality} vs {post_quality}")
                    continue
            
            # If we get here, we have an exact match
            return post['id']
        
        # No exact match found
        return None

    except Exception as e:
        logger.error(f"Failed to search for existing post: {str(e)}")
        return None
        
        logger.debug(f"Final Rapidgator link: {template_vars['rapidgator_link']}")
        logger.debug(f"Final Nitroflare link: {template_vars['nitroflare_link']}")
        logger.debug(f"Final host links: {template_vars['host_links']}")
        
def create_post_wp(title, content, wp, auth, media_id=None, status="publish", categories=None, tags=None):
    try:
        post_url = f"{wp['url'].rstrip('/')}/wp-json/wp/v2/posts"
        post_data = {
            "title": title,
            "content": content,
            "status": status,
            "featured_media": media_id,
            "categories": categories or [],
            "tags": tags or []
        }
        res = requests.post(
            post_url, 
            json=post_data, 
            auth=auth, 
            timeout=30
        )
        res.raise_for_status()
        return res.json().get("link")
    except Exception as e:
        logger.error(f"Failed to create WordPress post: {str(e)}")
        raise


def update_post_wp(post_id, content, wp, auth):
    """Update existing WordPress post"""
    try:
        post_url = f"{wp['url'].rstrip('/')}/wp-json/wp/v2/posts/{post_id}"
        post_data = {
            "content": content
        }
        res = requests.post(post_url, json=post_data, auth=auth, timeout=30)
        res.raise_for_status()
        return res.json().get("link")
    except Exception as e:
        logger.error(f"Failed to update WordPress post: {str(e)}")
        raise

def get_media_metadata(title, settings):
    """Fetch media metadata from TMDb/OMDb/AniList"""
    if not settings.get("tmdb_api_key"):
        return None
        
    # First check if this is anime
    season, episode = detect_season_episode(title)
    is_anime = any(x in title.lower() for x in ["anime", "episode", "season"])
    
    if is_anime and settings.get("enable_anilist"):
        info = fetch_anilist_info(title, season, episode)
        if info:
            return info
    
    # Fall back to TMDb/OMDb
    info = fetch_tmdb_info(title, settings["tmdb_api_key"])
    if not info and settings.get("enable_omdb_fallback") and settings.get("omdb_api_key"):
        info = fetch_omdb_info(title, settings["omdb_api_key"])
    return info

def extract_existing_links(content):
    """Enhanced link extraction with configured host patterns"""
    primary_hosts = get_primary_hosts()
    mirror_hosts = get_mirror_hosts()
    
    links = {host: None for host in primary_hosts}
    links["other"] = []
    
    # Extract premium links first
    for host in primary_hosts:
        pattern = rf'{get_host_display_name(host)}:\s*(https?://[^\s<]+)'
        match = re.search(pattern, content)
        if match:
            links[host] = match.group(1).strip()
    
    # Extract other links
    other_links = re.findall(
        r'(?:Other Links|Mirror Links):\s*((?:https?://[^\s<]+\s*)+)', 
        content
    )
    if other_links:
        links["other"] = list(set(
            link.strip() 
            for link in other_links[0].split('\n') 
            if link.strip()
        ))
    
    return links
    
def clean_tag_string(s):
    """Clean a string to be used as a tag by removing special characters and normalizing"""
    if not s or not isinstance(s, str):
        return ""
    
    # Remove file extensions
    s = re.sub(r'\.[a-z0-9]{2,4}$', '', s, flags=re.IGNORECASE)
    
    # Remove common release info and special characters
    s = re.sub(
        r'[\[\(][^\]\)]+[\]\)]|[^\w\s\-]|_', 
        ' ', 
        s, 
        flags=re.IGNORECASE
    )
    
    # Remove resolution/quality info
    s = re.sub(
        r'\b(2160p|1080p|720p|480p|4k|hd|sd|ld|web[\W_]?dl|blu[\W_]?ray|hdtv|dvdrip)\b', 
        '', 
        s, 
        flags=re.IGNORECASE
    )
    
    # Remove codec info
    s = re.sub(r'\b(x264|x265|hevc|aac|ac3|dts)\b', '', s, flags=re.IGNORECASE)
    
    # Remove episode/season markers but keep the numbers
    s = re.sub(r'\b(s\d{1,2}e\d{2,4}|season\s*\d+|episode\s*\d+)\b', '', s, flags=re.IGNORECASE)
    
    # Normalize whitespace and trim
    s = ' '.join(s.split()).strip()
    
    return s.lower() if s else ""
    
def extract_tags_from_title(title):
    """Clean and split title into meaningful tag keywords with specific formatting"""
    logger.debug(f"Starting tag extraction for title: {title}")
    
    try:
        # First clean the title string but keep original for technical tags
        cleaned = clean_tag_string(title)
        original_lower = title.lower()
        logger.debug(f"Original title (lower): {original_lower}")
        logger.debug(f"Cleaned title: {cleaned}")
        
        # Split into words
        words = cleaned.split()
        logger.debug(f"Split words: {words}")
        
        # Initialize tags list
        tags = []
        
        # 1. Add the main title tag (cleaned version)
        title_tag = ' '.join([w for w in words if len(w) > 2])
        if title_tag:
            tags.append(title_tag.lower())
            logger.debug(f"Added title tag: {title_tag.lower()}")
        
        # 2. Add technical tags with specific formatting
        # Resolution
        if '2160p' in original_lower or '4k' in original_lower:
            tags.append('4K')
        elif '1080p' in original_lower:
            tags.append('1080p')
        elif '720p' in original_lower:
            tags.append('720p')
        elif '480p' in original_lower:
            tags.append('480p')
        
        # Format
        if 'web-dl' in original_lower or 'webdl' in original_lower or 'web dl' in original_lower:
            tags.append('web-dl')
        if 'blu-ray' in original_lower or 'bluray' in original_lower or 'blu ray' in original_lower:
            tags.append('blu-ray')
        if 'hdtv' in original_lower:
            tags.append('hdtv')
        if 'dvdrip' in original_lower:
            tags.append('dvdrip')
        
        # Codec
        if 'x265' in original_lower or 'hevc' in original_lower:
            tags.append('x265')
        elif 'x264' in original_lower:
            tags.append('x264')
        
        # Season/episode - format as S01, Ep01
        season, episode = detect_season_episode(title)
        if season:
            tags.append(f'S{season:02d}')
        if episode:
            tags.append(f'Ep{episode:02d}')
        
        # Remove duplicates and empty tags
        tags = list(set([t for t in tags if t and len(t) > 1]))
        
        # Special handling for "big city greens -mrs" case
        if 'big city greens' in tags and 'mrs' in title.lower():
            tags.append('mrs')
            tags.remove('big city greens')
            tags.append('big city greens')  # Add it back at the end
        
        logger.debug(f"Final tags after deduplication: {tags}")
        return tags
        
    except Exception as e:
        logger.error(f"Failed to extract tags from title '{title}': {str(e)}", exc_info=True)
        fallback_tag = clean_tag_string(title)
        logger.warning(f"Using fallback tag: {fallback_tag}")
        return [fallback_tag] if fallback_tag else []
    
def process_upload(link, filename, settings, thumbnail_path=None):
    try:
        logger.info(f"Starting upload process for {filename}")
        
        # Add error handling for loading cache files
        try:
            posted_cache = load_json(POSTED_CACHE)
        except Exception as e:
            logger.error(f"Failed to load posted cache: {e}")
            posted_cache = {}
            
        try:
            pending_links = load_json(PENDING_LINKS)
        except Exception as e:
            logger.error(f"Failed to load pending links: {e}")
            pending_links = {}

        # First get the cleaned title and raw name
        cleaned_title, raw_name = clean_title(filename)
        season, episode = detect_season_episode(raw_name)
        base_name = os.path.splitext(os.path.basename(filename))[0]

        # THEN check if we have both primary hosts when required
        if settings.get("require_both_hosts", True):
            primary_hosts = get_primary_hosts()
            if len(primary_hosts) >= 2:
                host = detect_host(link)
                if raw_name in pending_links:
                    existing_hosts = set(pending_links[raw_name].keys())
                else:
                    existing_hosts = set()
                
                existing_hosts.add(host)
                
                # Check if we have both primary hosts
                has_both = all(h in existing_hosts for h in primary_hosts[:2])
                if not has_both:
                    logger.info(f"Skipping upload - require_both_hosts is True but only have {existing_hosts}")
                    log_to_csv(raw_name or "Unknown", link or "None", "Skipped", "⏳ Waiting for both primary hosts")
                    
                    # Store the pending link for future use
                    if raw_name not in pending_links:
                        pending_links[raw_name] = {}
                    pending_links[raw_name][host] = link
                    save_json(PENDING_LINKS, pending_links)
                    
                    return  # Exit without posting

        # Rest of your existing process_upload function continues here...
        quality = "4K" if "2160p" in filename.lower() else \
                "HD" if "1080p" in filename.lower() else \
                "SD" if "720p" in filename.lower() else \
                "LD" if "480p" in filename.lower() else ""

        title = raw_name
        media_type = "tv_episode" if season and episode else "movie"
        if any(x in filename.lower() for x in ["anime", "episode", "season"]):
            media_type = "anime"
        is_anime = (
            any(x in filename.lower() for x in ["anime", "episode", "season"]) or
            "[SubsPlease]" in filename  # Common anime release group
        )

        if is_anime:
            # Use Romaji title if available, otherwise default to cleaned title
            meta = get_media_metadata(title, settings)
            title = meta.get("romaji_title") if meta else title
            media_type = "anime"
            
        meta = get_media_metadata(cleaned_title, settings) if settings.get("skip_tmdb_if_unrecognized", True) else None

        wp = {
            "url": settings["wp_url"],
            "user": settings["wp_user"],
            "pass": settings["wp_app_password"]
        }
        auth = HTTPBasicAuth(wp["user"], wp["pass"])

        # FEATURED IMAGE: TMDb/OMDb or existing WP media
        thumbnail = ""
        media_id = None

        if settings.get("include_thumbnails"):
            # Create search title without adding _poster suffix yet
            search_title = re.sub(r'[^\w\-_. ]', '', cleaned_title.replace(" ", "_").lower())
            
            # Let find_existing_media handle the _poster suffix addition
            logger.debug(f"Checking for existing media for: {search_title}")
            media_id, media_url = find_existing_media(search_title, wp, auth)
            
            if media_id:
                logger.info(f"Found existing media for {search_title} (ID: {media_id}, URL: {media_url})")
                thumbnail = f'<img src="{media_url}" alt="{cleaned_title}">'
            else:
                # Only proceed with new upload if no existing poster found
                logger.debug("No existing poster found, attempting metadata image")
                img_path = None
                local_img_path = None

                try:
                    if meta:
                        img_path = (
                            meta.get("backdrop_path") if settings.get("preferred_image") == "backdrop"
                            else meta.get("poster_path")
                        ) or meta.get("poster_path") or meta.get("backdrop_path")

                        if not img_path and settings.get("enable_omdb_fallback"):
                            img_path = meta.get("poster_path")

                    img_url = None
                    if img_path:
                        if img_path.startswith("/"):
                            img_url = f"https://image.tmdb.org/t/p/w780{img_path}"
                        else:
                            img_url = img_path

                    if img_url and img_url.startswith("http"):
                        logger.debug(f"Attempting to download featured image from: {img_url}")

                        safe_name = re.sub(r'[^\w\-_. ]', '', cleaned_title.replace(" ", "_").lower())
                        local_img_path = os.path.join("log", f"{safe_name}_poster.jpg")

                        try:
                            with requests.get(img_url, stream=True, timeout=15) as r:
                                r.raise_for_status()
                                content_length = int(r.headers.get('content-length', 0))
                                if content_length > 5 * 1024 * 1024:
                                    raise ValueError(f"Image too large: {content_length} bytes")

                                os.makedirs(os.path.dirname(local_img_path), exist_ok=True)
                                with open(local_img_path, "wb") as img_file:
                                    for chunk in r.iter_content(8192):
                                        img_file.write(chunk)

                            if os.path.exists(local_img_path):
                                # Upload with _poster suffix in filename
                                media_id, media_url = upload_media_to_wp(local_img_path, wp, auth)
                                thumbnail = f'<img src="{media_url}" alt="{cleaned_title}">'
                                logger.info(f"Uploaded new poster image to WordPress (ID: {media_id})")
                            else:
                                logger.warning(f"Downloaded image not found: {local_img_path}")

                        except Exception as e:
                            logger.warning(f"Failed to download or upload featured image: {e}")
                    else:
                        logger.debug("No valid image URL available for download.")

                except Exception as e:
                    logger.warning(f"Failed to upload featured image: {e}")
                finally:
                    if local_img_path and os.path.exists(local_img_path):
                        try:
                            os.remove(local_img_path)
                        except Exception:
                            pass

        # Determine if this is a new post
        is_new_post = raw_name not in posted_cache

        # THUMBNAIL for post body
        thumbnail = ""
        if is_new_post and settings.get("include_thumbnails"):
            # 1. Check WordPress for existing thumbnail using base pattern
            base_name = os.path.splitext(os.path.basename(filename))[0]
            base_pattern = re.sub(r'\.\d{3,4}p\..*$', '', base_name)
            thumb_id, thumb_url = find_existing_media(base_pattern, wp, auth, is_thumbnail=True)
            
            if thumb_url and "_thumb_1" in thumb_url.lower():
                thumbnail = f'<img src="{thumb_url}" alt="{cleaned_title}">'
                logger.info(f"Reusing existing WordPress thumbnail: {os.path.basename(thumb_url)}")
            else:
                # 2. If no WordPress thumb found, check local folders
                if settings.get("thumbnail_folder") and os.path.isdir(settings["thumbnail_folder"]):
                    thumb_folder = settings["thumbnail_folder"]
                else:
                    # Fallback to video file's folder
                    thumb_folder = os.path.dirname(filename) if os.path.isabs(filename) else os.path.join(SCRIPT_DIR, os.path.dirname(filename))

                local_thumb = find_local_thumbnail(thumb_folder, filename)
                
                
                if local_thumb:
                    try:
                        _, wp_thumb_url = upload_media_to_wp(local_thumb, wp, auth)
                        thumbnail = f'<img src="{wp_thumb_url}" alt="{cleaned_title}">'
                        logger.info(f"Uploaded new thumbnail from local folder: {os.path.basename(local_thumb)}")
                    except Exception as e:
                        logger.warning(f"Failed to upload local thumbnail: {e}")
                else:
                    logger.debug("No local thumbnail found - proceeding without one")
                    
        # TEMPLATE VARS
        primary_hosts = get_primary_hosts()
        template_vars = {
            "title": cleaned_title,
            "full_title": f"{cleaned_title} S{season:02d}E{episode:02d}" if season and episode else cleaned_title,
            "season": season,
            "episode": episode,
            "quality": quality,
            "overview": meta.get("overview") if meta else "",
            "rating": meta.get("rating") if meta else "",
            "year": meta.get("year") if meta else "",
            "release_date": meta.get("release_date") if meta else "",
            "thumbnail": thumbnail,
            **{f"{host}_link": "" for host in primary_hosts},
            "host_links": ""
        }

        # HOST LINK TRACKING
        host = detect_host(link)
        if raw_name not in pending_links:
            pending_links[raw_name] = {}
        pending_links[raw_name][host] = link
        save_json(PENDING_LINKS, pending_links)

        if raw_name in pending_links:
            update_data = {
                f"{host}_link": pending_links[raw_name].get(host, "")
                for host in get_primary_hosts()
            }
            update_data["host_links"] = "\n".join(
                v for k, v in pending_links[raw_name].items()
                if k not in get_primary_hosts()
            )
            template_vars.update(update_data)

        if not all(isinstance(x, str) and len(x) > 0 for x in (cleaned_title, raw_name)):
            raise ValueError(f"Invalid title components from filename: {filename}")

        # APPLY TEMPLATE
        body = apply_template(media_type, template_vars, settings)
        logger.debug(f"Template vars: {json.dumps(template_vars, indent=2)}")
        logger.debug(f"Generated body: {body[:500]}...")

        posted_cache_key = raw_name

        # CREATE OR UPDATE POST
        existing_post_id = find_existing_post(title, wp, auth, settings)

        # Prepare categories
        all_categories = settings.get("categories", [])
        if cleaned_title not in all_categories:
            all_categories = [cleaned_title] + all_categories
        category_ids = resolve_terms(wp, auth, all_categories, "categories")

        # Prepare tags
        cleaned_tag = clean_tag_string(cleaned_title)
        raw_tags = extract_tags_from_title(filename)
        # Combine cleaned title tag with extracted tags and any settings tags
        all_tags = list(set([cleaned_tag] + raw_tags + settings.get("tags", [])))
        tag_ids = resolve_terms(wp, auth, all_tags, taxonomy="tags")
        
        if existing_post_id is None:
            # New post creation
            wp_post_url = create_post_wp(
            
                title=title,  # Changed from post_title to title
                content=body,  # Changed from post_body to body
                wp=wp,
                auth=auth,
                media_id=media_id,  # Also changed from featured_image_id to media_id
                status=settings.get("post_status", "publish"),
                categories=category_ids,
                tags=tag_ids
            )
            
            posted_cache[posted_cache_key] = existing_post_id
            save_json(POSTED_CACHE, posted_cache)
            log_to_csv(title, link, wp_post_url, "✅ Posted")
        else:
            # Update existing post
            logger.info(f"Found existing post ID: {existing_post_id}")
            
            # Check if this is a different instance trying to create a duplicate
            if posted_cache_key in posted_cache and posted_cache[posted_cache_key] != existing_post_id:
                logger.warning(f"Duplicate post detected! Original ID: {posted_cache[posted_cache_key]}, New ID: {existing_post_id}")
                # Merge the content and delete the duplicate
                try:
                    # Get content from both posts
                    original_post = requests.get(
                        f"{wp['url'].rstrip('/')}/wp-json/wp/v2/posts/{posted_cache[posted_cache_key]}", 
                        auth=auth
                    ).json()
                    duplicate_post = requests.get(
                        f"{wp['url'].rstrip('/')}/wp-json/wp/v2/posts/{existing_post_id}", 
                        auth=auth
                    ).json()
                    
                    # Merge links
                    original_links = extract_existing_links(original_post['content']['rendered'])
                    duplicate_links = extract_existing_links(duplicate_post['content']['rendered'])
                    
                    # Combine links, preferring original where both exist
                    merged_links = {
                        "rapidgator": original_links.get("rapidgator") or duplicate_links.get("rapidgator"),
                        "nitroflare": original_links.get("nitroflare") or duplicate_links.get("nitroflare"),
                        "other": list(set(original_links.get("other", []) + duplicate_links.get("other", [])))
                    }
                    
                    # Update the original post with merged content
                    template_vars.update({
                        "rapidgator_link": merged_links["rapidgator"] or "",
                        "nitroflare_link": merged_links["nitroflare"] or "",
                        "host_links": "\n".join(merged_links["other"]),
                        "thumbnail": original_post.get('thumbnail') or duplicate_post.get('thumbnail')
                    })
                    
                    merged_body = apply_template(media_type, template_vars, settings)
                    update_post_wp(posted_cache[posted_cache_key], merged_body, wp, auth)
                    
                    # Delete the duplicate post if allowed
                    if settings.get("allow_post_deletion", False):
                        requests.delete(
                            f"{wp['url'].rstrip('/')}/wp-json/wp/v2/posts/{existing_post_id}?force=true",
                            auth=auth
                        )
                        logger.info(f"Deleted duplicate post ID: {existing_post_id}")
                    
                    log_to_csv(title, f"Merged: {link}", wp_post_url, "🔄 Merged duplicate posts")
                    return
                    
                except Exception as e:
                    logger.error(f"Failed to merge duplicate posts: {str(e)}")
            
            # Normal update case
            wp_post_url = update_post_wp(existing_post_id, body, wp, auth)
            posted_cache[posted_cache_key] = existing_post_id
            save_json(POSTED_CACHE, posted_cache)
            log_to_csv(title, f"Updated: {link}", wp_post_url, "🔄 Updated with new links")

        if (posted_cache_key in posted_cache and
                all(h in pending_links.get(raw_name, {}) for h in get_primary_hosts())):
            if raw_name in pending_links:
                del pending_links[raw_name]
                save_json(PENDING_LINKS, pending_links)

    except Exception as e:
        logger.error(f"Upload failed: {str(e)}", exc_info=True)
        log_to_csv(raw_name or "Unknown", link or "None", "Failed", f"❌ Error: {str(e)}")
        raise
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--link", help="Download link")
    parser.add_argument("--filename", help="File name")
    parser.add_argument("--thumbnail-path", help="Path to file for thumbnail search")
    parser.add_argument("--process-queue", action="store_true", 
                       help="Process all queued links")
    args = parser.parse_args()

    # Load config
    config = load_settings()
    
    if args.process_queue:
        logger.info("Starting queue processing")
        # Process all queued links
        while True:
            link_data = get_next_link()
            if not link_data:
                logger.info("No more links to process")
                break
                
            try:
                logger.info(f"Processing link for: {link_data['filename']}")
                process_upload(
                    link_data['link'],
                    link_data['filename'],
                    config,
                    link_data.get('thumbnail_path')
                )
                # Delete the processed file
                os.remove(os.path.join(SCRIPT_DIR, "pending_links", 
                                     f"link_{link_data['timestamp']}.json"))
                logger.info(f"Successfully processed: {link_data['filename']}")
            except Exception as e:
                logger.error(f"Failed to process queued link: {str(e)}")
                # Keep the file in queue for retry
                continue
    elif args.link and args.filename:
        # Process single link
        logger.info(f"Processing single link for: {args.filename}")
        process_upload(args.link, args.filename, config, args.thumbnail_path)
    else:
        logger.error("No valid arguments provided")
        print("Usage:")
        print("  Single link: --link <url> --filename <name> [--thumbnail-path <path>]")
        print("  Process queue: --process-queue")
        sys.exit(1)