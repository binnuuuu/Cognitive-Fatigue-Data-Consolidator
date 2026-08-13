from pathlib import Path
import pandas as pd

def read_data_file(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()

    if suffix == ".csv":
        # utf-8-sig handles normal UTF-8 as well as Excel-exported CSVs.
        return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)

    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)

    raise ValueError(f"Unsupported file type: {path.suffix}")
