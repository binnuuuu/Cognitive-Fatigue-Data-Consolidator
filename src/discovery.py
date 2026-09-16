from __future__ import annotations

import re
import zipfile
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def participant_from_name(path: Path) -> str | None:
    match = re.search(
        r"(?<![A-Za-z0-9])PT[_-]?(\d+)(?![A-Za-z0-9])",
        path.stem,
        flags=re.IGNORECASE,
    )
    return f"PT{int(match.group(1))}" if match else None


def day_from_name(path: Path) -> int | None:
    match = re.search(
        r"(?:day|session)[_\-\s]*(\d+)",
        path.stem,
        flags=re.IGNORECASE,
    )
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


def discover_study_files(root: Path) -> dict[str, list[Path] | Path]:
    files = [path for path in root.rglob("*") if path.is_file()]

    post_surveys = [
        path for path in files
        if path.suffix.lower() == ".csv"
        and "post" in normalize(path.name)
        and "survey" in normalize(path.name)
    ]
    if not post_surveys:
        raise FileNotFoundError("No Post Survey CSV was found in the input package.")
    if len(post_surveys) > 1:
        names = ", ".join(str(path.relative_to(root)) for path in post_surveys)
        raise ValueError(f"Multiple Post Survey CSV files found: {names}")

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
            or any("simdata" in normalize(part) for part in path.parts)
        )
    ]

    return {
        "post_survey": post_surveys[0],
        "nasa_tlx": sorted(nasa_files),
        "simulator": sorted(simulator_files),
    }
