# media_lookup.py
import os
import re
import logging
import requests
import time
from requests.auth import HTTPBasicAuth
from requests.exceptions import RequestException
from PIL import Image
from functools import wraps
from utils import detect_season_episode
from host_config import get_primary_hosts, get_host_display_name

logger = logging.getLogger(__name__)

def retry_with_backoff(max_retries=3, initial_delay=1, backoff_factor=2):
    """Decorator for retrying API calls with exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            delay = initial_delay
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except RequestException:
                    retries += 1
                    if retries >= max_retries:
                        raise
                    time.sleep(delay)
                    delay *= backoff_factor
        return wrapper
    return decorator

@retry_with_backoff()
def find_existing_media(title, wp, auth, media_type="image", is_thumbnail=False):
    """Media lookup that uses title directly for search without special suffix handling"""
    logger.info(f"Starting media lookup for: {title} (thumbnail: {is_thumbnail})")
    
    try:
        if is_thumbnail:
            logger.debug("=== THUMBNAIL SEARCH PROCESS ===")
            logger.debug(f"Original input: {title}")
            
            # Use the title directly as search pattern for thumbnails
            search_pattern = title
            logger.debug(f"Using title directly as search pattern: {search_pattern}")
        else:
            # Original cleaning logic for posters
            cleaned_title = re.sub(r'[^\w\-_. ]', '', title.replace(" ", "_").lower())
            search_pattern = re.sub(r'_poster$', '', cleaned_title) + "_poster"

        logger.debug(f"Final search pattern: {search_pattern}")
        
        try:
            logger.debug(f"Querying WordPress media API for: {search_pattern}")
            res = requests.get(
                f"{wp['url'].rstrip('/')}/wp-json/wp/v2/media",
                params={
                    "search": search_pattern,
                    "media_type": media_type,
                    "per_page": 1,
                    "orderby": "date",
                    "order": "desc"
                },
                auth=auth,
                timeout=10
            )
            res.raise_for_status()
            found_media = res.json()
            
            logger.debug(f"API returned {len(found_media)} results")
            if found_media:
                media = found_media[0]
                logger.debug(f"Match found - ID: {media['id']}, Title: {media['title']['rendered']}, URL: {media['source_url']}")
                return media['id'], media['source_url']

        except RequestException as e:
            logger.warning(f"Media API request failed: {str(e)}")

        logger.info(f"No matching media found for '{search_pattern}'")
        return None, None

    except Exception as e:
        logger.error(f"Media lookup error: {str(e)}", exc_info=True)
        return None, None

@retry_with_backoff()
def upload_media_to_wp(image_path, wp, auth):
    """Upload media file to WordPress"""
    logger.info(f"Starting media upload for: {image_path}")
    
    for attempt in range(3):
        try:
            logger.debug(f"Attempt {attempt + 1} of 3")
            logger.debug(f"Opening file: {image_path}")
            
            with open(image_path, "rb") as f:
                filename = os.path.basename(image_path)
                title = os.path.splitext(filename)[0]
                
                logger.debug(f"Preparing upload headers - filename: {filename}, title: {title}")
                headers = {
                    "Content-Disposition": f'attachment; filename="{filename}"'
                }
                
                logger.debug(f"Making POST request to WordPress media API")
                res = requests.post(
                    f"{wp['url'].rstrip('/')}/wp-json/wp/v2/media",
                    headers=headers,
                    files={"file": (filename, f)},
                    auth=auth,
                    timeout=30,
                    data={"title": title}
                )
                
                logger.debug(f"Response status: {res.status_code}")
                res.raise_for_status()
                
                media_data = res.json()
                logger.debug(f"Upload successful - ID: {media_data['id']}, URL: {media_data['source_url']}")
                return media_data["id"], media_data["source_url"]
                
        except (IOError, PermissionError) as e:
            logger.warning(f"File access error on attempt {attempt + 1}: {str(e)}")
            if attempt == 2:
                logger.error("Max attempts reached for file access")
                raise RequestException(f"File access failed: {str(e)}")
            time.sleep(1 * (2 ** attempt))
            logger.debug(f"Waiting {1 * (2 ** attempt)} seconds before retry")
            
        except RequestException as e:
            logger.error(f"WordPress upload failed: {str(e)}")
            raise RequestException(f"WordPress upload failed: {str(e)}")

def find_local_thumbnail(folder, filename, settings=None):
    """
    Search for matching thumbnail file in local folder with exact pattern matching.
    Checks:
    1. Same folder as file
    2. Thumbnail folder from settings (if provided)
    """
    logger.info(f"Starting local thumbnail search in {folder} for {filename}")
    
    try:
        # Get base filename without extension
        base_name = os.path.splitext(os.path.basename(filename))[0]
        logger.debug(f"Base filename: {base_name}")
        
        # Create exact thumbnail pattern (add _thumb_1 before extension)
        exact_thumb_name = f"{base_name}_thumb_1"
        logger.debug(f"1. Searching for exact thumbnail match: {exact_thumb_name}.*")
        
        # Check for exact match first with various extensions
        for ext in ['jpg', 'jpeg', 'png', 'webp']:
            # Check in same folder as file
            thumb_path = os.path.join(folder, f"{exact_thumb_name}.{ext}")
            logger.debug(f"Checking for {thumb_path}")
            if os.path.exists(thumb_path):
                logger.info(f"Found exact thumbnail match: {thumb_path}")
                return thumb_path
            
            # Check in thumbnail folder from settings if provided
            if settings and settings.get("thumbnail_path"):
                thumb_path = os.path.join(settings["thumbnail_path"], f"{exact_thumb_name}.{ext}")
                logger.debug(f"Checking in settings thumbnail path: {thumb_path}")
                if os.path.exists(thumb_path):
                    logger.info(f"Found exact thumbnail match in settings folder: {thumb_path}")
                    return thumb_path
        
        logger.debug("2. No exact match found, trying fallback pattern matching")
        
        # If no exact match, look for pattern matches (without _thumb_1)
        core_pattern = re.sub(
            r'\.\d{3,4}p\..*$',  # Remove quality and everything after
            '', 
            base_name
        )
        logger.debug(f"3. Core pattern after removing quality info: {core_pattern}")
        
        # Standardize season/episode format
        core_pattern = re.sub(
            r's(\d{1,2})[\._]e(\d{2,4})',
            lambda m: f"S{int(m.group(1)):02d}E{int(m.group(2)):02d}",
            core_pattern,
            flags=re.IGNORECASE
        )
        logger.debug(f"4. After standardizing season/episode: {core_pattern}")
        
        # Create pattern for fallback matching (just the show.name.S01E06 part)
        pattern = re.compile(
            r'^' + re.escape(core_pattern) + r'\.(.*?)\.(jpg|jpeg|png|webp)$',
            re.IGNORECASE
        )
        logger.debug(f"5. Final fallback regex pattern: {pattern.pattern}")
        
        # Search through all files in folder
        logger.debug(f"6. Scanning folder {folder} for matches")
        for file in os.listdir(folder):
            if pattern.match(file):
                full_path = os.path.join(folder, file)
                logger.debug(f"7. Potential match found: {file}")
                logger.info(f"Found fallback thumbnail match: {full_path}")
                return full_path
                
        # Search in settings thumbnail folder if provided
        if settings and settings.get("thumbnail_path"):
            thumb_folder = settings["thumbnail_path"]
            logger.debug(f"8. Scanning settings thumbnail folder {thumb_folder}")
            for file in os.listdir(thumb_folder):
                if pattern.match(file):
                    full_path = os.path.join(thumb_folder, file)
                    logger.debug(f"9. Potential match found in settings folder: {file}")
                    logger.info(f"Found fallback thumbnail match in settings folder: {full_path}")
                    return full_path
                
        logger.debug("10. No matching thumbnails found after full scan")
        return None
        
    except Exception as e:
        logger.error(f"Local thumbnail search failed: {str(e)}", exc_info=True)
        return None

def resize_image(input_path, max_size=(1200, 1200)):
    """Resize image to specified maximum dimensions"""
    logger.info(f"Starting image resize for {input_path} (max size: {max_size})")
    
    try:
        logger.debug(f"Opening image file: {input_path}")
        with Image.open(input_path) as img:
            original_size = img.size
            logger.debug(f"Original dimensions: {original_size}")
            
            logger.debug("Resizing image...")
            img.thumbnail(max_size)
            
            new_size = img.size
            logger.debug(f"New dimensions: {new_size}")
            
            if new_size != original_size:
                logger.info(f"Resized from {original_size} to {new_size}")
            else:
                logger.debug("Image already within size limits - no resizing needed")
                
            logger.debug("Saving resized image")
            img.save(input_path)
            
    except Exception as e:
        logger.error(f"Image resize failed: {str(e)}", exc_info=True)
        raise