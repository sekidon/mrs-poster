# save_links.py (Windows-compatible version)
import os
import json
import time
import logging
from datetime import datetime
from file_utils import force_file_unlock  # Your existing Windows file utility

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('save_links.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LINKS_DIR = os.path.join(SCRIPT_DIR, "pending_links")
LOCK_FILE = os.path.join(LINKS_DIR, ".lock")
os.makedirs(LINKS_DIR, exist_ok=True)

def acquire_lock():
    """Windows-compatible file locking"""
    max_retries = 5
    retry_delay = 0.5
    
    for attempt in range(max_retries):
        try:
            # Try to create the lock file exclusively
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_WRONLY | os.O_EXCL)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except OSError:
            if attempt == max_retries - 1:
                logger.warning("Could not acquire lock after maximum retries")
                return False
            time.sleep(retry_delay)
    return False

def release_lock():
    """Release the directory lock"""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception as e:
        logger.error(f"Error releasing lock: {str(e)}")
        force_file_unlock(LOCK_FILE)  # Force unlock if normal removal fails

def save_link(link, filename, thumbnail_path=None):
    """Thread-safe link saving with file locking"""
    if not acquire_lock():
        logger.error("Could not acquire lock, skipping save")
        return None
    
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filepath = os.path.join(LINKS_DIR, f"link_{timestamp}.json")
        
        data = {
            "link": link,
            "filename": filename,
            "timestamp": timestamp,
            "processed": False
        }
        
        if thumbnail_path:
            data["thumbnail_path"] = thumbnail_path
        
        # Atomic write operation
        temp_path = f"{filepath}.tmp"
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        
        # Rename temp file to final name
        os.replace(temp_path, filepath)
        logger.info(f"Saved link to {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Failed to save link: {str(e)}")
        return None
    finally:
        release_lock()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python save_links.py <link> <filename> [thumbnail_path]")
        sys.exit(1)
    
    link = sys.argv[1]
    filename = sys.argv[2]
    thumbnail_path = sys.argv[3] if len(sys.argv) > 3 else None
    
    saved_path = save_link(link, filename, thumbnail_path)
    if saved_path:
        print(f"Link saved to: {saved_path}")
        sys.exit(0)
    else:
        print("Failed to save link")
        sys.exit(1)