# safe_json.py (Windows-specific version)
import json
import os
import time
import logging
import tempfile
import errno
import msvcrt  # Windows-specific
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

def _windows_lock_file(file_obj, timeout=5):
    """Attempt to lock a file on Windows with timeout."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            msvcrt.locking(file_obj.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except IOError:
            time.sleep(0.1)
    return False

def _windows_unlock_file(file_obj):
    """Release a file lock on Windows."""
    try:
        msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 1)
    except:
        pass

def load_json(path: str, max_retries: int = 3, retry_delay: float = 0.1) -> Dict[str, Any]:
    """Windows-specific JSON loading with file locking."""
    attempts = 0
    last_error = None
    
    while attempts < max_retries:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            if not os.path.exists(path):
                return {}
                
            with open(path, 'r+', encoding='utf-8') as f:
                if _windows_lock_file(f):
                    try:
                        return json.load(f)
                    finally:
                        _windows_unlock_file(f)
                else:
                    raise IOError("Could not acquire file lock")
                    
        except (IOError, OSError) as e:
            last_error = e
            attempts += 1
            time.sleep(retry_delay * (attempts ** 2))
            continue
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {path}: {e}")
            return {}
    
    logger.error(f"Failed to load JSON after {max_retries} attempts: {last_error}")
    return {}

def save_json(path: str, data: Any, max_retries: int = 3, retry_delay: float = 0.1) -> bool:
    """Windows-specific atomic JSON save with locking."""
    attempts = 0
    last_error = None
    
    while attempts < max_retries:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            with tempfile.NamedTemporaryFile(
                mode='w+',
                dir=os.path.dirname(path),
                prefix=os.path.basename(path),
                suffix='.tmp',
                delete=False,
                encoding='utf-8'
            ) as tf:
                temp_path = tf.name
                if _windows_lock_file(tf):
                    try:
                        json.dump(data, tf, indent=2)
                        tf.flush()
                        os.fsync(tf.fileno())
                    finally:
                        _windows_unlock_file(tf)
                else:
                    raise IOError("Could not acquire file lock for temp file")
            
            try:
                os.replace(temp_path, path)
                return True
            except:
                os.unlink(temp_path)
                raise
                
        except (IOError, OSError) as e:
            last_error = e
            attempts += 1
            time.sleep(retry_delay * (attempts ** 2))
            continue
    
    logger.error(f"Failed to save JSON after {max_retries} attempts: {last_error}")
    return False