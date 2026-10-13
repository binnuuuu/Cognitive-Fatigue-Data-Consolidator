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
    overlapping = (set(master.columns) & set(auxiliary.columns)) - {"PID", "Day"}
    merged = master.merge(
        auxiliary,
        how="left",
        on=["PID", "Day"],
        validate="one_to_one",
        suffixes=("", "__auxiliary"),
    )
    for column in overlapping:
        auxiliary_column = f"{column}__auxiliary"
        merged[column] = merged[column].combine_first(merged.pop(auxiliary_column))
    return merged


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


def _is_participant_level_column(frame: pd.DataFrame, column: str) -> bool:
    """Identify fields that stay constant for participants with repeated sessions."""
    if column == "PID":
        return True

    condition_specific = {
        "Day",
        "AI_Decision_Support",
        "AI_Decision_Support Label",
        "AI_Action_Support",
        "AI_Action_Support Label",
        "NASA_Available",
        "Simulator_Available",
        "Data_Status_Notes",
        "SIM_Source_File",
    }
    if column in condition_specific:
        return False
    if column.startswith("SIM_") or column.startswith("NASA_"):
        return column in {"NASA_Source_File"}

    repeated_participants = frame.groupby("PID", sort=False).filter(lambda rows: len(rows) > 1)
    if repeated_participants.empty:
        return False

    for _, participant_rows in repeated_participants.groupby("PID", sort=False):
        values = participant_rows[column].astype("string").fillna("<MISSING>")
        if values.nunique() > 1:
            return False
    return True


def _build_wide_format(frame: pd.DataFrame) -> pd.DataFrame:
    """Pivot session rows into one participant row with adjacent NF/F field pairs."""
    condition_values = pd.to_numeric(frame["Fatigue Condition"], errors="coerce")
    supported_conditions = condition_values.isin([0, 1])
    if not supported_conditions.all():
        bad = sorted(frame.loc[~supported_conditions, "Fatigue Condition"].astype(str).unique())
        raise ConsolidationError(
            "Cannot build Wide_Format: unsupported or missing Fatigue Condition value(s): "
            + ", ".join(bad)
        )

    excluded = {"Fatigue Condition", "Fatigue Condition Label"}
    source_columns = [column for column in frame.columns if column not in excluded and column != "PID"]
    participant_columns = [
        column for column in source_columns
        if _is_participant_level_column(frame, column)
    ]
    condition_columns = [column for column in source_columns if column not in participant_columns]

    rows = []
    for participant in frame["PID"].drop_duplicates():
        participant_rows = frame.loc[frame["PID"].eq(participant)]
        condition_rows = {
            0: participant_rows.loc[condition_values.loc[participant_rows.index].eq(0)],
            1: participant_rows.loc[condition_values.loc[participant_rows.index].eq(1)],
        }
        for condition, matches in condition_rows.items():
            if len(matches) > 1:
                label = "NF" if condition == 0 else "F"
                raise ConsolidationError(
                    f"Cannot build one Wide_Format row for {participant}: multiple {label} "
                    "sessions were found. Each participant must have at most one session "
                    "per fatigue condition."
                )

        row = {"PID": participant}
        for column in participant_columns:
            values = participant_rows[column].dropna()
            row[column] = values.iloc[0] if not values.empty else pd.NA

        # Keep Day first, then preserve the source column order with each NF/F pair adjacent.
        ordered_condition_columns = (["Day"] if "Day" in condition_columns else []) + [
            column for column in condition_columns if column != "Day"
        ]
        for column in ordered_condition_columns:
            for condition, suffix in ((0, "NF"), (1, "F")):
                matches = condition_rows[condition]
                if not matches.empty:
                    value = matches.iloc[0][column]
                elif column.endswith("Available"):
                    value = "No"
                elif column == "Data_Status_Notes":
                    value = "No completed session for this condition."
                else:
                    value = pd.NA
                row[f"{column}_{suffix}"] = value
        rows.append(row)

    columns = ["PID", *participant_columns]
    for column in (["Day"] if "Day" in condition_columns else []) + [
        name for name in condition_columns if name != "Day"
    ]:
        columns.extend([f"{column}_NF", f"{column}_F"])
    wide = pd.DataFrame(rows, columns=columns)
    source_file_columns = [column for column in wide.columns if "Source_File" in column]
    other_columns = [column for column in wide.columns if column not in source_file_columns]
    return wide[other_columns + source_file_columns]


def build_consolidated_data(input_path: Path, config: dict) -> tuple[pd.DataFrame, list[str]]:
    warnings = []
    with open_input_tree(input_path) as root:
        files = discover_study_files(root)
        master = read_post_survey(files["post_survey"], config)
        validate_master_sessions(master)

        nasa_records = [read_nasa_tlx(path) for path in files["nasa_tlx"]]
        nasa_records = _resolve_records(nasa_records, master, "NASA-TLX", warnings)

        simulator_records = []
        simulator_files = _prefer_redo_simulator_files(files["simulator"], warnings)
        for path in simulator_files:
            try:
                simulator_records.extend(read_simulator_json(path))
            except Exception as exc:
                warnings.append(f"Failed to read simulator file {path.name}: {exc}")

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
    wide_data = _build_wide_format(data)
    long_data = _build_long_format(data, config)
    written = write_consolidated_workbook(
        output_path,
        wide_data,
        config.get("worksheet_name", "Wide_Format"),
        long_data,
        config.get("long_worksheet_name", "Long_Format"),
    )
    return written, wide_data, warnings


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
    logging.info("Created %s with %d participant row(s).", written, len(data))


if __name__ == "__main__":
    main()
