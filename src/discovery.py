from __future__ import annotations

import re
import zipfile
from datetime import date
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def normalize_participant_id(value: object) -> str:
    """Normalize numeric IDs while preserving P and legacy PT prefixes."""
    if value is None:
        return ""
    participant = str(value).strip().upper()
    match = re.fullmatch(r"(PT|P)?[_-]?0*(\d+)(?:\.0+)?", participant)
    if match:
        prefix = match.group(1) or "P"
        return f"{prefix}{int(match.group(2))}"
    return participant


def participant_from_name(path: Path) -> str | None:
    match = re.search(
        r"(?<![A-Za-z0-9])(PT|P)[_-]?(\d+)(?![A-Za-z0-9])",
        path.stem,
        flags=re.IGNORECASE,
    )
    return f"{match.group(1).upper()}{int(match.group(2))}" if match else None


def day_from_name(path: Path) -> int | None:
    match = re.search(
        r"(?:day|session)[_\-\s]*(\d+)",
        path.stem,
        flags=re.IGNORECASE,
    )
    return int(match.group(1)) if match else None


def mission_from_name(path: Path) -> int | None:
    match = re.search(r"(?:^|[^A-Za-z0-9])M[_-]?(\d+)(?:$|[^A-Za-z0-9])", path.stem, re.I)
    return int(match.group(1)) if match else None


def fatigue_condition_from_name(path: Path) -> int | None:
    """Return 0 for non-fatigue/NF and 1 for fatigue/F filename tokens."""
    stem = path.stem.lower()
    non_fatigue = re.search(
        r"(?:^|[^a-z0-9])(?:nf|non[_\-\s]?fatigue)(?:$|[^a-z0-9])",
        stem,
    )
    if non_fatigue:
        return 0

    fatigue = re.search(
        r"(?:^|[^a-z0-9])(?:f|fatigue)(?:$|[^a-z0-9])",
        stem,
    )
    return 1 if fatigue else None


def _survey_date_from_name(path: Path) -> date | None:
    """Extract a date from survey filenames, including Qualtrics month-name exports."""
    stem = path.stem
    month_names = (
        "January|February|March|April|May|June|July|August|September|October|November|December"
        "|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
    )
    month_date = re.search(
        rf"(?<![A-Za-z])({month_names})[+_\s-]*(\d{{1,2}}),?[+_\s-]*(\d{{4}})(?!\d)",
        stem,
        flags=re.IGNORECASE,
    )
    if month_date:
        from datetime import datetime

        return date(
            int(month_date.group(3)),
            datetime.strptime(month_date.group(1)[:3], "%b").month,
            int(month_date.group(2)),
        )

    for pattern, date_format in (
        (r"(?<!\d)(\d{4})[-_](\d{1,2})[-_](\d{1,2})(?!\d)", "%Y-%m-%d"),
        (r"(?<!\d)(\d{1,2})[-_](\d{1,2})[-_](\d{4})(?!\d)", "%m-%d-%Y"),
    ):
        numeric_date = re.search(pattern, stem)
        if numeric_date:
            try:
                return date.fromisoformat(
                    "-".join(numeric_date.groups())
                    if date_format == "%Y-%m-%d"
                    else f"{numeric_date.group(3)}-{numeric_date.group(1)}-{numeric_date.group(2)}"
                )
            except ValueError:
                return None
    return None


def _select_latest_survey(paths: list[Path], survey_name: str, root: Path) -> Path:
    if not paths:
        raise FileNotFoundError(f"No {survey_name} Survey CSV was found in the input package.")
    if len(paths) == 1:
        return paths[0]

    dated = [(path, _survey_date_from_name(path)) for path in paths]
    undated = [path for path, file_date in dated if file_date is None]
    if undated:
        names = ", ".join(str(path.relative_to(root)) for path in undated)
        raise ValueError(
            f"Multiple {survey_name} Survey CSV files were found, but these have no readable "
            f"date in their filenames: {names}. Add a date to each filename so the newest "
            "survey can be selected."
        )
    return max(dated, key=lambda item: (item[1], item[0].name.casefold()))[0]


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in archive.infolist():
        target = (destination / member.filename).resolve()
        if target != destination and destination not in target.parents:
            raise ValueError(f"Unsafe path in ZIP file: {member.filename}")
    archive.extractall(destination)


@contextmanager
def open_input_tree(input_path: Path):
    """Yield an input directory for either a directory or ZIP package."""
    input_path = input_path.expanduser().resolve()

    if input_path.is_dir():
        yield input_path
        return

    if not input_path.is_file():
        raise FileNotFoundError(f"Input does not exist: {input_path}")
    if input_path.suffix.lower() != ".zip":
        raise ValueError("Input must be a directory or a .zip file.")

    with TemporaryDirectory(prefix="fatigue-consolidator-") as temp_dir:
        extraction_root = Path(temp_dir)
        with zipfile.ZipFile(input_path) as archive:
            _safe_extract(archive, extraction_root)

        children = [
            child for child in extraction_root.iterdir()
            if child.name != "__MACOSX"
        ]
        root = children[0] if len(children) == 1 and children[0].is_dir() else extraction_root
        yield root


def discover_study_files(root: Path) -> dict[str, list[Path] | Path | None]:
    files = [path for path in root.rglob("*") if path.is_file()]

    post_surveys = [
        path for path in files
        if path.suffix.lower() == ".csv"
        and "post" in normalize(path.name)
        and "survey" in normalize(path.name)
    ]
    pre_surveys = [
        path for path in files
        if path.suffix.lower() == ".csv"
        and "pre" in normalize(path.name)
        and "survey" in normalize(path.name)
    ]

    nasa_files = [
        path for path in files
        if path.suffix.lower() in {".xls", ".tsv", ".csv"}
        and any("nasatlx" in normalize(part) for part in path.parts)
    ]
    simulator_files = [
        path for path in files
        if path.suffix.lower() == ".json"
        and (
            "participantdata" in normalize(path.name)
            or any(
                normalize(part) in {"simdata", "simulationdata", "simulation"}
                for part in path.parts
            )
            or (
                participant_from_name(path) is not None
                and fatigue_condition_from_name(path) is not None
                and mission_from_name(path) is not None
            )
        )
    ]

    return {
        "post_survey": _select_latest_survey(post_surveys, "Post", root),
        "pre_survey": _select_latest_survey(pre_surveys, "Pre", root) if pre_surveys else None,
        "nasa_tlx": sorted(nasa_files),
        "simulator": sorted(simulator_files),
    }
