import argparse
import logging
import re
from pathlib import Path

import pandas as pd

from .config import load_config
from .discovery import (
    day_from_name,
    discover_study_files,
    fatigue_condition_from_name,
    mission_from_name,
    normalize,
    open_input_tree,
    participant_from_name,
)
from .excel_writer import write_consolidated_workbook
from .readers import NASA_COLUMNS, read_post_survey, read_simulator_json
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
            requested_condition = record.get("_Match_Fatigue_Condition")
            if (
                requested_condition is not None
                and str(exact.iloc[0].get("Fatigue Condition")) != str(requested_condition)
            ):
                warnings.append(
                    f"Could not match {source_name} for {participant}: "
                    f"Day {requested_day} conflicts with the filename fatigue condition."
                )
                return None
            return exact.iloc[0]["Day"]
        warnings.append(
            f"Could not match {source_name} for {participant}: Day {requested_day} is not unique."
        )
        return None

    if len(candidates) == 1:
        return candidates.iloc[0]["Day"]

    requested_condition = record.get("_Match_Fatigue_Condition")
    if requested_condition is not None and "Fatigue Condition" in candidates:
        matching = candidates[
            candidates["Fatigue Condition"].astype(str) == str(requested_condition)
        ]
        if len(matching) == 1:
            return matching.iloc[0]["Day"]

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
        matched.pop("_Match_Fatigue_Condition", None)
        resolved.append(matched)
    validate_unique_auxiliary(resolved, source_name)
    return resolved


def _ensure_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        if column not in frame:
            frame[column] = pd.NA


def _copy_number(path: Path) -> int:
    match = re.search(r"\((\d+)\)$", path.stem)
    return int(match.group(1)) if match else 1


def _prefer_redo_simulator_files(paths: list[Path], warnings: list[str]) -> list[Path]:
    """Prefer the highest numbered copy when same-session simulator files were redone."""
    groups: dict[tuple, list[Path]] = {}
    ungrouped = []
    for path in paths:
        participant = participant_from_name(path)
        condition = fatigue_condition_from_name(path)
        mission = mission_from_name(path)
        day = day_from_name(path)
        if participant is None or all(value is None for value in (condition, mission, day)):
            ungrouped.append(path)
            continue
        key = (participant, condition, day, mission)
        groups.setdefault(key, []).append(path)

    selected = list(ungrouped)
    for candidates in groups.values():
        if len(candidates) == 1:
            selected.extend(candidates)
            continue
        numbered = [path for path in candidates if _copy_number(path) > 1]
        if numbered:
            chosen = max(numbered, key=lambda path: (_copy_number(path), path.name.casefold()))
            ignored = [path.name for path in candidates if path != chosen]
            warnings.append(
                f"Selected simulator redo {chosen.name}; ignored earlier copy/copies: "
                f"{', '.join(ignored)}."
            )
            selected.append(chosen)
        else:
            selected.extend(candidates)
    return sorted(selected)


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


def _build_long_format(frame: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Return one row per participant and fatigue condition, with blank rows for missing conditions."""
    condition_values = pd.to_numeric(frame["Fatigue Condition"], errors="coerce")
    configured_labels = config.get("condition_labels", {}).get(
        "Fatigue Condition", {"0": "Non-fatigue", "1": "Fatigue"}
    )
    label_map = {
        str(key): value
        for key, value in configured_labels.items()
    }
    rows = []

    for participant in frame["PID"].drop_duplicates():
        for condition in (1, 0):  # F row, then NF row
            matches = frame.loc[
                frame["PID"].eq(participant) & condition_values.eq(condition)
            ]
            if len(matches) > 1:
                raise ConsolidationError(
                    f"Cannot create one F/NF row per participant: {participant} has "
                    f"multiple sessions for condition {condition}."
                )
            if len(matches) == 1:
                rows.append(matches.iloc[0].to_dict())
                continue

            missing = {column: pd.NA for column in frame.columns}
            missing["PID"] = participant
            missing["Fatigue Condition"] = condition
            if "Fatigue Condition Label" in missing:
                missing["Fatigue Condition Label"] = label_map.get(str(condition))
            if "NASA_Available" in missing:
                missing["NASA_Available"] = "No"
            if "Simulator_Available" in missing:
                missing["Simulator_Available"] = "No"
            if "Data_Status_Notes" in missing:
                missing["Data_Status_Notes"] = "No completed session for this condition."
            rows.append(missing)

    return pd.DataFrame(rows, columns=frame.columns)


def build_consolidated_data(input_path: Path, config: dict) -> tuple[pd.DataFrame, list[str]]:
    warnings = []
    with open_input_tree(input_path) as root:
        files = discover_study_files(root)
        master = read_post_survey(files["post_survey"], config)
        validate_master_sessions(master)

        simulator_records = []
        simulator_files = _prefer_redo_simulator_files(files["simulator"], warnings)
        for path in simulator_files:
            try:
                simulator_records.extend(read_simulator_json(path))
            except Exception as exc:
                warnings.append(f"Failed to read simulator file {path.name}: {exc}")

        simulator_records = _resolve_records(simulator_records, master, "simulator", warnings)

        output = _merge_records(master, simulator_records)

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
    long_data = _build_long_format(data, config)
    written = write_consolidated_workbook(
        output_path,
        data,
        config.get("worksheet_name", "Consolidated_Data"),
        long_data,
        config.get("long_worksheet_name", "Long_Format"),
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
    except (ConsolidationError, FileNotFoundError, PermissionError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    for warning in warnings:
        logging.warning(warning)
    logging.info("Created %s with %d participant-session row(s).", written, len(data))


if __name__ == "__main__":
    main()
