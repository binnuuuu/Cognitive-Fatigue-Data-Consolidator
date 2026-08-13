from pathlib import Path
import yaml

DEFAULT_CONFIG = {
    "input_directory": "sample_data",
    "output_directory": "output",
    "log_directory": "logs",
    "stream_aliases": {},
    "supported_extensions": [".csv", ".xlsx", ".xls"],
}

def load_config(path: str = "config.yaml") -> dict:
    config_path = Path(path)
    config = DEFAULT_CONFIG.copy()

    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        config.update(loaded)

    return config
