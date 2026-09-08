import argparse
import logging
import re
from pathlib import Path

import pandas as pd

from .config import load_config
from .discovery import discover_study_files, normalize, open_input_tree
from .excel_writer import write_consolidated_workbook
from .readers import NASA_COLUMNS, read_nasa_tlx, read_post_survey, read_simulator_json
from .validator import (
    ConsolidationError,
    validate_master_sessions,
    validate_unique_auxiliary,
)


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "run.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )


def _participant_sort_key(value: str):
    match = re.search(r"(\d+)", str(value))
    return (int(match.group(1)) if match else float("inf"), str(value))


def _normalized_equal(left, right) -> bool:
    if left is None or right is None or pd.isna(left) or pd.isna(right):
        return False
    return normalize(str(left)) == normalize(str(right))


def _resolve_record_day(
    record: dict,
    master: pd.DataFrame,
    source_name: str,
    warnings: list[str],
):
    participant = str(record.get("PID") or "").strip().upper()
    candidates = master[master["PID"] == participant]
    if candidates.empty:
        warnings.append(f"Ignored {source_name} record for unknown participant {participant}.")
        return None

    requested_day = record.get("Day")
    if requested_day is not None and not pd.isna(requested_day):
        exact = candidates[candidates["Day"].astype(str) == str(requested_day)]
        if len(exact) == 1:
            return exact.iloc[0]["Day"]
        warnings.append(
            f"Could not match {source_name} for {participant}: Day {requested_day} is not unique."
        )
        return None

    if len(candidates) == 1:
        return candidates.iloc[0]["Day"]

    # Simulator support modes can disambiguate sessions when filenames omit Day.
    if source_name == "simulator":
        matching = candidates[
            candidates.apply(
                lambda row: _normalized_equal(
                    row.get("AI_Decision_Support Label"),
                    record.get("SIM_AI_Decision_Mode"),
                )
                and _normalized_equal(
                    row.get("AI_Action_Support Label"),
                    record.get("SIM_AI_Action_Mode"),
                ),
                axis=1,
            )
        ]
        if len(matching) == 1:
            return matching.iloc[0]["Day"]

    warnings.append(
        f"Could not match {source_name} for {participant}: multiple sessions exist and the file has no Day."
    )
    return None


def _resolve_records(
    records: list[dict],
    master: pd.DataFrame,
    source_name: str,
    warnings: list[str],
) -> list[dict]:
    resolved = []
    for record in records:
        day = _resolve_record_day(record, master, source_name, warnings)
        if day is None:
            continue
        matched = record.copy()
        matched["PID"] = str(matched["PID"]).strip().upper()
        matched["Day"] = day
        resolved.append(matched)
    validate_unique_auxiliary(resolved, source_name)
    return resolved


def _ensure_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        if column not in frame:
            frame[column] = pd.NA


def _merge_records(master: pd.DataFrame, records: list[dict]) -> pd.DataFrame:
    if not records:
        return master
    auxiliary = pd.DataFrame(records)
    return master.merge(auxiliary, how="left", on=["PID", "Day"], validate="one_to_one")


def _reorder_columns(frame: pd.DataFrame) -> pd.DataFrame:
    first = [
        "PID",
        "Day",
        "Fatigue Condition",
        "Fatigue Condition Label",
        "AI_Decision_Support",
        "AI_Decision_Support Label",
        "AI_Action_Support",
        "AI_Action_Support Label",
    ]
    first = [column for column in first if column in frame]
    final = [
        "NASA_Available",
        "Simulator_Available",
        "Data_Status_Notes",
        "Post_Source_File",
        "NASA_Source_File",
        "SIM_Source_File",
    ]
    final = [column for column in final if column in frame]
    middle = [column for column in frame.columns if column not in first and column not in final]
    return frame[first + middle + final]


def build_consolidated_data(input_path: Path, config: dict) -> tuple[pd.DataFrame, list[str]]:
    warnings = []
    with open_input_tree(input_path) as root:
        files = discover_study_files(root)
        master = read_post_survey(files["post_survey"], config)
        validate_master_sessions(master)

        nasa_records = []
        for path in files["nasa_tlx"]:
            try:
                nasa_records.append(read_nasa_tlx(path))
            except Exception as exc:
                warnings.append(f"Failed to read NASA-TLX file {path.name}: {exc}")

        simulator_records = []
        for path in files["simulator"]:
            try:
                simulator_records.extend(read_simulator_json(path))
            except Exception as exc:
                warnings.append(f"Failed to read simulator file {path.name}: {exc}")

        nasa_records = _resolve_records(nasa_records, master, "NASA-TLX", warnings)
        simulator_records = _resolve_records(simulator_records, master, "simulator", warnings)

        output = _merge_records(master, nasa_records)
        output = _merge_records(output, simulator_records)

    _ensure_columns(output, ["NASA_Source_File", *NASA_COLUMNS.values(), "SIM_Source_File"])
    output["NASA_Available"] = output["NASA_Source_File"].notna().map({True: "Yes", False: "No"})
    output["Simulator_Available"] = output["SIM_Source_File"].notna().map({True: "Yes", False: "No"})

    notes = []
    for row in output.itertuples(index=False):
        missing = []
        if getattr(row, "NASA_Available") == "No":
            missing.append("NASA-TLX unavailable")
        if getattr(row, "Simulator_Available") == "No":
            missing.append("Simulator unavailable")
        notes.append("; ".join(missing))
    output["Data_Status_Notes"] = notes

    for row in output.itertuples(index=False):
        if row.NASA_Available == "No":
            warnings.append(f"NASA-TLX unavailable for {row.PID}/Day{row.Day}.")
        if row.Simulator_Available == "No":
            warnings.append(f"Simulator unavailable for {row.PID}/Day{row.Day}.")

    output["_participant_sort"] = output["PID"].map(_participant_sort_key)
    output = output.sort_values(["_participant_sort", "Day"]).drop(columns="_participant_sort")
    return _reorder_columns(output.reset_index(drop=True)), warnings


def consolidate(input_path: Path, output_path: Path, config: dict):
    data, warnings = build_consolidated_data(input_path, config)
    written = write_consolidated_workbook(
        output_path,
        data,
        config.get("worksheet_name", "Consolidated_Data"),
    )
    return written, data, warnings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Consolidate Post Survey, NASA-TLX, and simulator data into one workbook."
    )
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--input", dest="input_path", default=None)
    parser.add_argument("--output", dest="output_path", default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    input_path = Path(args.input_path or config["input_path"])
    output_path = Path(args.output_path or config["output_file"])
    setup_logging(Path(config.get("log_directory", "logs")))

    try:
        written, data, warnings = consolidate(input_path, output_path, config)
    except (ConsolidationError, FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    for warning in warnings:
        logging.warning(warning)
    logging.info("Created %s with %d participant-session row(s).", written, len(data))


if __name__ == "__main__":
    main()
