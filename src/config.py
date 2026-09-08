from pathlib import Path
import yaml

DEFAULT_CONFIG = {
    "input_path": "incoming_data",
    "output_file": "output/consolidated_study_data.xlsx",
    "log_directory": "logs",
    "worksheet_name": "Consolidated_Data",
    "post_survey_drop_columns": ["Spacer", "Spacer_2"],
    "condition_labels": {
        "Fatigue Condition": {
            "0": "Non-fatigue",
            "1": "Fatigue",
        },
        "AI_Decision_Support": {
            "1": "LowSupport",
            "2": "HighSupport",
        },
        "AI_Action_Support": {
            "1": "Manual",
            "2": "AIAssisted",
        },
    },
}

def load_config(path: str = "config.yaml") -> dict:
    config_path = Path(path)
    config = DEFAULT_CONFIG.copy()

    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        config.update(loaded)

    return config
