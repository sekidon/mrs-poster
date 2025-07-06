import requests
from requests.auth import HTTPBasicAuth
from requests.exceptions import RequestException
import time
from functools import wraps

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
def get_or_create_term(wp, auth, term_name, taxonomy="categories"):
    """Fetches the term ID for a category or tag, creates it if not found"""
    term_name = term_name.strip()
    url = f"{wp['url'].rstrip('/')}/wp-json/wp/v2/{taxonomy}"
    params = {"search": term_name}
    
    res = requests.get(url, params=params, auth=auth, timeout=10)
    res.raise_for_status()
    results = res.json()
    
    if results:
        return results[0]["id"]
    
    # Create new term
    res = requests.post(url, json={"name": term_name}, auth=auth, timeout=10)
    res.raise_for_status()
    return res.json()["id"]

def resolve_terms(wp, auth, term_names, taxonomy="categories"):
    """Resolves a list of term names to their WordPress term IDs"""
    return [
        get_or_create_term(wp, auth, name, taxonomy)
        for name in term_names if name.strip()
    ]
