import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


def _header_fill(column_name: str) -> str:
    if column_name.startswith("NASA_"):
        return "548235"
    if column_name.startswith("SIM_"):
        return "8064A2"
    if column_name.endswith("Available") or column_name == "Data_Status_Notes":
        return "7F6000"
    return "1F4E78"


def _style_worksheet(worksheet, columns: list[str]) -> None:
    worksheet.freeze_panes = "C2"
    worksheet.auto_filter.ref = worksheet.dimensions
    worksheet.sheet_view.showGridLines = False
    worksheet.row_dimensions[1].height = 42

    for index, cell in enumerate(worksheet[1], start=1):
        cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=_header_fill(columns[index - 1]))
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    data_border = Border(bottom=Side(style="hair", color="D9E2F3"))
    wrap_columns = {
        "Data_Status_Notes",
        "Post_Source_File",
        "NASA_Source_File",
        "SIM_Source_File",
    }

    for column_index, column_cells in enumerate(worksheet.columns, start=1):
        column_name = columns[column_index - 1]
        max_length = len(column_name)
        for cell in list(column_cells)[1:101]:
            if cell.value is not None:
                max_length = max(max_length, len(str(cell.value)))
            cell.font = Font(name="Arial", size=10)
            cell.alignment = Alignment(
                vertical="center",
                wrap_text=column_name in wrap_columns,
            )
            cell.border = data_border
            if "Accuracy" in column_name and isinstance(cell.value, (int, float)):
                cell.number_format = "0.0%"
            elif isinstance(cell.value, float):
                cell.number_format = "0.000"

        maximum_width = 42 if column_name in wrap_columns else 28
        width = min(max(max_length + 2, 12), maximum_width)
        worksheet.column_dimensions[get_column_letter(column_index)].width = width


def write_consolidated_workbook(
    output_path: Path,
    data: pd.DataFrame,
    worksheet_name: str = "Consolidated_Data",
) -> Path:
    """Write one workbook atomically so a failed run preserves the prior output."""
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with NamedTemporaryFile(
        prefix=f".{output_path.stem}-",
        suffix=".xlsx",
        dir=output_path.parent,
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)

    try:
        with pd.ExcelWriter(temporary_path, engine="openpyxl") as writer:
            data.to_excel(writer, sheet_name=worksheet_name[:31], index=False)
            workbook = writer.book
            worksheet = writer.sheets[worksheet_name[:31]]
            _style_worksheet(worksheet, list(data.columns))
            workbook.properties.title = "Cognitive Fatigue Study Consolidated Data"
            workbook.properties.subject = "One row per participant study session"
            workbook.properties.creator = "Cognitive Fatigue Data Consolidator"
        os.replace(temporary_path, output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    return output_path
