import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


def _header_fill(column_name: str, highlight_fatigue: bool = False) -> str:
    if highlight_fatigue and column_name.endswith("_F"):
        return "E2F0D9"
    if column_name.startswith("NASA_"):
        return "548235"
    if column_name.startswith("SIM_"):
        return "8064A2"
    if column_name.endswith("Available") or column_name == "Data_Status_Notes":
        return "7F6000"
    return "1F4E78"


def _style_worksheet(
    worksheet,
    columns: list[str],
    highlight_fatigue_headers: bool = False,
) -> None:
    worksheet.freeze_panes = "C2"
    worksheet.auto_filter.ref = worksheet.dimensions
    worksheet.sheet_view.showGridLines = False
    worksheet.row_dimensions[1].height = 42

    for index, cell in enumerate(worksheet[1], start=1):
        column_name = columns[index - 1]
        is_fatigue_header = highlight_fatigue_headers and column_name.endswith("_F")
        cell.font = Font(
            name="Arial",
            size=10,
            bold=True,
            color="385D3A" if is_fatigue_header else "FFFFFF",
        )
        cell.fill = PatternFill(
            "solid",
            fgColor=_header_fill(column_name, highlight_fatigue_headers),
        )
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
        wrap_column = column_name in wrap_columns or "Source_File" in column_name
        max_length = len(column_name)
        for cell in list(column_cells)[1:101]:
            if cell.value is not None:
                max_length = max(max_length, len(str(cell.value)))
            cell.font = Font(name="Arial", size=10)
            cell.alignment = Alignment(
                vertical="center",
                wrap_text=wrap_column,
            )
            cell.border = data_border
            if "Accuracy" in column_name and isinstance(cell.value, (int, float)):
                cell.number_format = "0.0%"
            elif isinstance(cell.value, float):
                cell.number_format = "0.000"

        maximum_width = 42 if wrap_column else 28
        width = min(max(max_length + 2, 12), maximum_width)
        worksheet.column_dimensions[get_column_letter(column_index)].width = width


def _visually_group_repeated_pids(worksheet, data: pd.DataFrame) -> None:
    """Hide repeated PID text in adjacent long-format rows while retaining cell values."""
    if "PID" not in data.columns:
        return

    pid_column = data.columns.get_loc("PID") + 1
    for row_index in range(1, len(data)):
        if data.iloc[row_index]["PID"] == data.iloc[row_index - 1]["PID"]:
            cell = worksheet.cell(row=row_index + 2, column=pid_column)
            cell.font = Font(name="Arial", size=10, color="FFFFFF")


def write_consolidated_workbook(
    output_path: Path,
    data: pd.DataFrame,
    worksheet_name: str = "Consolidated_Data",
    long_data: pd.DataFrame | None = None,
    long_worksheet_name: str = "Long_Format",
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
            wide_sheet_name = worksheet_name[:31]
            data.to_excel(writer, sheet_name=wide_sheet_name, index=False)
            workbook = writer.book
            worksheet = writer.sheets[wide_sheet_name]
            _style_worksheet(
                worksheet,
                list(data.columns),
                highlight_fatigue_headers=True,
            )
            if long_data is not None:
                long_sheet_name = long_worksheet_name[:31]
                if long_sheet_name.casefold() == wide_sheet_name.casefold():
                    raise ValueError("Wide and long worksheet names must be different.")
                long_data.to_excel(writer, sheet_name=long_sheet_name, index=False)
                long_worksheet = writer.sheets[long_sheet_name]
                _style_worksheet(long_worksheet, list(long_data.columns))
                _visually_group_repeated_pids(long_worksheet, long_data)
            workbook.properties.title = "Cognitive Fatigue Study Consolidated Data"
            workbook.properties.subject = "Wide and long participant study data"
            workbook.properties.creator = "Cognitive Fatigue Data Consolidator"
        try:
            os.replace(temporary_path, output_path)
        except PermissionError as exc:
            raise PermissionError(
                f"Cannot replace output workbook '{output_path}'. "
                "Close it in Excel or any other application, then try again."
            ) from exc
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    return output_path
