import pandas as pd


class ConsolidationError(ValueError):
    pass


def validate_master_sessions(frame: pd.DataFrame) -> None:
    required = {
        "PID",
        "Day",
        "Fatigue Condition",
        "AI_Decision_Support",
        "AI_Action_Support",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ConsolidationError(
            f"Post Survey is missing required column(s): {', '.join(missing)}"
        )

    if frame["PID"].isna().any() or frame["Day"].isna().any():
        raise ConsolidationError("Every Post Survey row must have both PID and Day.")

    duplicate_mask = frame.duplicated(subset=["PID", "Day"], keep=False)
    if duplicate_mask.any():
        duplicates = frame.loc[duplicate_mask, ["PID", "Day"]].astype(str)
        keys = sorted({f"{row.PID}/Day{row.Day}" for row in duplicates.itertuples(index=False)})
        raise ConsolidationError(
            f"Duplicate participant/day rows in Post Survey: {', '.join(keys)}"
        )


def validate_unique_auxiliary(records: list[dict], source_name: str) -> None:
    keys = [(str(record.get("PID")), str(record.get("Day"))) for record in records]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        formatted = ", ".join(f"{pid}/Day{day}" for pid, day in duplicates)
        raise ConsolidationError(f"Multiple {source_name} records matched: {formatted}")
