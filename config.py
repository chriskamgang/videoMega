import json
from pathlib import Path

CONFIG_PATH = Path.home() / "Documents" / "mega-sync" / "config.json"

DEFAULT_CONFIG = {
    "mega_email": "",
    "mega_password": "",
    "source_path": "/Volumes/TOSHIBA EXT",
    "mega_dest_folder": "TOSHIBA EXT Backup"
}

def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return DEFAULT_CONFIG.copy()

def save_config(config):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
