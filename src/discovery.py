from pathlib import Path
import re
from typing import Optional

def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())

def identify_stream(filename: str, aliases: dict) -> Optional[str]:
    stem = Path(filename).stem
    normalized = normalize(stem)

    # Prefer longer aliases to avoid short aliases matching first.
    candidates = []
    for stream, names in aliases.items():
        for alias in names:
            candidates.append((normalize(alias), stream))

    candidates.sort(key=lambda x: len(x[0]), reverse=True)

    for alias, stream in candidates:
        if alias and alias in normalized:
            return stream
    return None

def discover_participants(input_dir: Path):
    return sorted([p for p in input_dir.iterdir() if p.is_dir()])

def discover_days(participant_dir: Path):
    return sorted([p for p in participant_dir.iterdir() if p.is_dir()],
                  key=lambda p: natural_key(p.name))

def natural_key(text: str):
    return [int(x) if x.isdigit() else x.lower()
            for x in re.split(r"(\d+)", text)]

def discover_files(day_dir: Path, extensions):
    allowed = {e.lower() for e in extensions}
    return sorted([
        p for p in day_dir.iterdir()
        if p.is_file() and p.suffix.lower() in allowed
    ])
