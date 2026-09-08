import csv
import json
from pathlib import Path
from statistics import mean

import pandas as pd

from .discovery import day_from_name, participant_from_name


def _number(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return int(number) if number.is_integer() else number


def _convert_numeric_columns(frame: pd.DataFrame, text_columns: set[str]) -> pd.DataFrame:
    for column in frame.columns:
        if column in text_columns:
            continue
        values = frame[column].astype("string").str.strip()
        present = values.notna() & values.ne("")
        converted = pd.to_numeric(values, errors="coerce")
        if present.any() and converted[present].notna().all():
            frame[column] = converted
    return frame


def read_post_survey(path: Path, config: dict) -> pd.DataFrame:
    """Read a Qualtrics Post Survey export and retain columns from PID onward."""
    frame = pd.read_csv(
        path,
        encoding="utf-8-sig",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    if "PID" not in frame.columns:
        raise ValueError(f"Post Survey has no PID column: {path.name}")

    # Qualtrics exports contain question text and ImportId rows below the header.
    if len(frame) >= 2 and frame.iloc[1].astype(str).str.contains("ImportId").any():
        frame = frame.iloc[2:].copy()

    pid_position = frame.columns.get_loc("PID")
    frame = frame.iloc[:, pid_position:].copy()
    frame.columns = [str(column).strip() for column in frame.columns]
    frame["PID"] = frame["PID"].astype(str).str.strip().str.upper()
    frame = frame[frame["PID"].ne("")].reset_index(drop=True)

    drop_columns = config.get("post_survey_drop_columns", ["Spacer", "Spacer_2"])
    frame = frame.drop(columns=[column for column in drop_columns if column in frame], errors="ignore")

    condition_labels = config.get("condition_labels", {})
    for column, mapping in condition_labels.items():
        if column not in frame:
            continue
        normalized_mapping = {str(key): value for key, value in mapping.items()}
        labels = frame[column].map(
            lambda value: normalized_mapping.get(str(value), f"Unknown ({value})")
            if str(value).strip() else pd.NA
        )
        frame.insert(frame.columns.get_loc(column) + 1, f"{column} Label", labels)

    frame["Post_Source_File"] = path.name
    text_columns = {
        "PID",
        "Post_Source_File",
        *(column for column in frame.columns if column.endswith(" Label")),
    }
    return _convert_numeric_columns(frame, text_columns)


NASA_COLUMNS = {
    "Mental Demand": "NASA_Mental_Demand",
    "Physical Demand": "NASA_Physical_Demand",
    "Temporal Demand": "NASA_Temporal_Demand",
    "Performance": "NASA_Performance",
    "Effort": "NASA_Effort",
    "Frustration": "NASA_Frustration",
    "Total Workload": "NASA_Total_Workload",
}


def read_nasa_tlx(path: Path) -> dict:
    """Read the tab-delimited NASA-TLX text files supplied with an .xls suffix."""
    participant = participant_from_name(path)
    if participant is None:
        raise ValueError(f"Cannot identify participant from NASA-TLX filename: {path.name}")

    record = {
        "PID": participant,
        "Day": day_from_name(path),
        "NASA_Source_File": path.name,
    }
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle, delimiter="\t"):
            cells = [cell.strip() for cell in row]
            if len(cells) >= 2 and cells[0] in NASA_COLUMNS:
                record[NASA_COLUMNS[cells[0]]] = _number(cells[1])

    if not any(column in record for column in NASA_COLUMNS.values()):
        raise ValueError(f"No NASA-TLX values found in: {path.name}")
    return record


def _summarize_numeric_list(record: dict, prefix: str, values) -> None:
    values = values if isinstance(values, list) else []
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    record[f"{prefix}_Count"] = len(values)
    record[f"{prefix}_Mean"] = mean(numeric) if numeric else None
    record[f"{prefix}_Minimum"] = min(numeric) if numeric else None
    record[f"{prefix}_Maximum"] = max(numeric) if numeric else None


def _add_sagat_summary(record: dict, run_data: dict) -> None:
    all_questions = []
    for set_number, key in enumerate(("Sagat1", "Sagat2"), start=1):
        questions = run_data.get(key) or []
        scorable = [question for question in questions if question.get("CorrectAnswer") is not None]
        correct = sum(bool(question.get("IsCorrect")) for question in scorable)
        record[f"SIM_SAGAT{set_number}_Total"] = len(questions)
        record[f"SIM_SAGAT{set_number}_Scorable"] = len(scorable)
        record[f"SIM_SAGAT{set_number}_Correct"] = correct
        record[f"SIM_SAGAT{set_number}_Accuracy"] = correct / len(scorable) if scorable else None
        all_questions.extend(scorable)

    total_correct = sum(bool(question.get("IsCorrect")) for question in all_questions)
    record["SIM_SAGAT_Scorable"] = len(all_questions)
    record["SIM_SAGAT_Correct"] = total_correct
    record["SIM_SAGAT_Accuracy"] = total_correct / len(all_questions) if all_questions else None


def _add_action_summary(record: dict, actions: list[dict]) -> None:
    record["SIM_Action_Count"] = len(actions)
    record["SIM_Correct_Action_Count"] = sum(bool(action.get("UserCorrect")) for action in actions)
    record["SIM_Action_Accuracy"] = (
        record["SIM_Correct_Action_Count"] / len(actions) if actions else None
    )
    record["SIM_Verified_Action_Count"] = sum(bool(action.get("UserVerified")) for action in actions)
    times = [float(action["Time"]) for action in actions if isinstance(action.get("Time"), (int, float))]
    record["SIM_Action_Time_Mean"] = mean(times) if times else None
    record["SIM_Action_Time_Minimum"] = min(times) if times else None
    record["SIM_Action_Time_Maximum"] = max(times) if times else None


def read_simulator_json(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    sessions = payload if isinstance(payload, list) else [payload]

    records = []
    for session in sessions:
        if not isinstance(session, dict):
            raise ValueError(f"Unexpected simulator record in: {path.name}")
        participant = str(session.get("PID") or participant_from_name(path) or "").strip().upper()
        if not participant:
            raise ValueError(f"Cannot identify participant in simulator file: {path.name}")

        run_data = session.get("UserRunData") or {}
        record = {
            "PID": participant,
            "Day": _number(session.get("Day")) or day_from_name(path),
            "SIM_Source_File": path.name,
            "SIM_Date": session.get("Date"),
            "SIM_StartTime": session.get("StartTime"),
            "SIM_EndTime": session.get("EndTime"),
            "SIM_MissionNum": _number(run_data.get("MissionNum")),
            "SIM_Run_StartTime": run_data.get("StartTime"),
            "SIM_Run_EndTime": run_data.get("EndTime"),
            "SIM_TimeToComplete": _number(run_data.get("TimeToComplete")),
            "SIM_AI_Decision_Mode": session.get("AISupportDisplay"),
            "SIM_AI_Action_Mode": session.get("AIActionDisplay"),
            "SIM_Map": session.get("MapDisplay"),
        }

        auv_records = sorted(
            run_data.get("AUVRunData") or [],
            key=lambda item: _number(item.get("AUVNum")) or 0,
        )
        for position, auv in enumerate(auv_records, start=1):
            auv_number = _number(auv.get("AUVNum")) or position
            prefix = f"SIM_AUV{auv_number}"
            for key, value in auv.items():
                if key == "AUVNum":
                    continue
                if isinstance(value, list):
                    _summarize_numeric_list(record, f"{prefix}_{key}", value)
                else:
                    record[f"{prefix}_{key}"] = _number(value)

        _add_sagat_summary(record, run_data)
        _add_action_summary(record, session.get("ActionOrder") or [])
        records.append(record)
    return records
