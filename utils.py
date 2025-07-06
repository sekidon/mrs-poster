# utils.py
import os
import re
import logging

logger = logging.getLogger(__name__)

def clean_title(raw_title):
    """
    Clean raw filename and extract searchable title with season handling.
    Combines extension removal, episode/quality cleanup, and normalization.
    Returns cleaned title and original base name.
    """
    logger.debug(f"Starting to clean raw title: {raw_title}")
    try:
        # Strip path and extension
        base_name = os.path.splitext(os.path.basename(str(raw_title)))[0]
        logger.debug(f"Base filename without extension: {base_name}")

        # Standardize season/episode formats (convert S2.E09 to S02E09)
        base_name = re.sub(
            r's(\d{1,2})[\._]e(\d{2,4})',
            lambda m: f"S{int(m.group(1)):02d}E{int(m.group(2)):02d}",
            base_name,
            flags=re.IGNORECASE
        )
        
        # Remove known episode/season patterns (but keep the standardized version)
        name_no_episode = re.sub(
            r's\d{1,2}e\d{2,4}|e\d{2,4}|s\d{1,2}[\._]e\d{2,4}', 
            '', 
            base_name, 
            flags=re.IGNORECASE
        )
        logger.debug(f"After episode pattern removal: {name_no_episode}")

        # Remove encoding, resolution, and other known junk
        cleaned = re.sub(
            r'\d{3,4}p|x\d{3}|hevc|web[\W_]?dl|blu[\W_]?ray|dvdrip|hdtv|xvid|ac3|mp3|'
            r'\bcd\d\b|\bsubs?\b|\b[a-z]{2}sub\b|mRs|\bEN\b|\bENG\b|\bKOR\b',
            '',
            name_no_episode,
            flags=re.IGNORECASE
        )
        logger.debug(f"After quality/encoding info removal: {cleaned}")

        # Remove language codes and country indicators
        cleaned = re.sub(
            r'\b(?:EN(?:\s*(?:\d+|v\d+))?|S\d{1,2}E\d{1,2}(?:\s*v\d+)?|ENG|SPA|KOR|FR|DE|JPN|JP|CN|RUM|RUS|RO|RU|ES|IT|SUB|DUB|2nd\.STAGE)\b',
            '',
            cleaned,
            flags=re.IGNORECASE
        )
        logger.debug(f"After language code removal: {cleaned}")

        # Normalize spacing and remove leftover non-alphanumeric noise
        cleaned = re.sub(r'[\W_]+', ' ', cleaned).strip()
        logger.debug(f"After spacing normalization: {cleaned}")

        # Remove trailing 4-digit year (e.g., "ShowName 2021" → "ShowName")
        cleaned = re.sub(r'(\D)\d{4}$', r'\1', cleaned).strip()
        logger.debug(f"After trailing year cleanup: {cleaned}")

        # Handle numeric dot prefix like "1.2.3.SomeTitle"
        if re.match(r'^\d+\.\d+\.', base_name):
            parts = base_name.split('.')
            if len(parts) > 2 and parts[-1].isalpha():
                cleaned = parts[-1]
                logger.debug(f"Detected numeric dot prefix, cleaned to: {cleaned}")

        return cleaned if cleaned else base_name, base_name

    except Exception as e:
        logger.error(f"Title cleaning failed for '{raw_title}': {str(e)}")
        return "unknown", str(raw_title)[:100]  # fallback

def detect_season_episode(filename):
    """Detect season and episode from filename"""
    patterns = [
        r'(?:s|season)[\s_]*(?P<season>\d+)[\s_]*(?:e|episode)[\s_]*(?P<episode>\d+)',
        r'(?P<season>\d+)x(?P<episode>\d+)',
        r'(?:s|season)[\s_]*(?P<season>\d+)(?:\s*-\s*episode\s*(?P<episode>\d+))?',
        r's(?P<season>\d{1,2})\.e(?P<episode>\d{2,4})'  # Added pattern for S2.E09 format
    ]
    for pattern in patterns:
        match = re.search(pattern, filename, re.IGNORECASE)
        if match:
            season = int(match.group("season")) if match.group("season") else None
            episode = int(match.group("episode")) if match.group("episode") else None
            return season, episode
    return None, None