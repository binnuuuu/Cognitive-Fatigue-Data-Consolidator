import pandas as pd

def quality_metrics(df: pd.DataFrame) -> dict:
    rows, cols = df.shape

    duplicate_rows = int(df.duplicated().sum())
    missing_cells = int(df.isna().sum().sum())
    empty_rows = int(df.isna().all(axis=1).sum()) if rows else 0
    empty_columns = int(df.isna().all(axis=0).sum()) if cols else 0

    time_column = find_time_column(df)
    duration = None

    if time_column is not None:
        values = pd.to_numeric(df[time_column], errors="coerce").dropna()
        if len(values) >= 2:
            duration = float(values.max() - values.min())

    return {
        "Rows": rows,
        "Columns": cols,
        "Missing Cells": missing_cells,
        "Duplicate Rows": duplicate_rows,
        "Empty Rows": empty_rows,
        "Empty Columns": empty_columns,
        "Time Column": time_column or "",
        "Time Range": duration if duration is not None else "",
    }

def find_time_column(df: pd.DataFrame):
    preferred = [
        "timestamp", "time", "datetime", "date_time",
        "elapsed_time", "elapsed", "time_s", "seconds"
    ]

    normalized = {
        str(c).strip().lower().replace(" ", "_"): c
        for c in df.columns
    }

    for name in preferred:
        if name in normalized:
            return normalized[name]

    for c in df.columns:
        name = str(c).lower()
        if "timestamp" in name or name.endswith("_time") or name == "time":
            return c

    return None
