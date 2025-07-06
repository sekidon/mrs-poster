from host_config import load_host_config
from settings_editor import DEFAULT_SETTINGS

def initialize_configs():
    # Initialize host config
    host_config = load_host_config()
    
    # Initialize settings with primary hosts
    DEFAULT_SETTINGS["primary_hosts"] = host_config["primary_hosts"]
    DEFAULT_SETTINGS["mirror_hosts"] = host_config["mirror_hosts"]

if __name__ == "__main__":
    initialize_configs()
    print("Configuration files initialized successfully")