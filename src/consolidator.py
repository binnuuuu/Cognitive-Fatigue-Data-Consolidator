import argparse
import logging
from pathlib import Path
from datetime import datetime

import pandas as pd

from .config import load_config
from .discovery import (
    discover_participants, discover_days, discover_files, identify_stream
)
from .readers import read_data_file
from .validator import quality_metrics
from .excel_writer import write_workbook

EXPECTED_STREAMS = ["EyeTracking", "HeartRate", "EEG", "Behavior", "Subjective"]

def setup_logging(log_dir: Path):
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "run.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler()
        ],
        force=True,
    )

def consolidate_participant(participant_dir: Path, output_dir: Path, config: dict):
    participant = participant_dir.name
    aliases = config.get("stream_aliases", {})
    extensions = config.get("supported_extensions", [".csv", ".xlsx", ".xls"])

    stream_frames = {stream: [] for stream in EXPECTED_STREAMS}
    overview = []
    summary = []
    warnings = []

    days = discover_days(participant_dir)

    if not days:
        warnings.append("No day folders found.")

    for day_dir in days:
        day = day_dir.name
        files = discover_files(day_dir, extensions)

        found_streams = set()

        for file_path in files:
            stream = identify_stream(file_path.name, aliases)

            if stream is None:
                warnings.append(f"Unrecognized file: {day}/{file_path.name}")
                continue

            try:
                df = read_data_file(file_path)
                df = df.copy()
                df.insert(0, "Day", day)
                df.insert(0, "Participant", participant)
                df.insert(2, "Source File", file_path.name)

                stream_frames.setdefault(stream, []).append(df)
                found_streams.add(stream)

                metrics = quality_metrics(df)
                metrics.update({
                    "Participant": participant,
                    "Day": day,
                    "Stream": stream,
                    "Source File": file_path.name,
                })
                summary.append(metrics)

                logging.info("%s | %s | %s | %d rows",
                             participant, day, stream, len(df))

            except Exception as exc:
                message = f"Failed to read {day}/{file_path.name}: {exc}"
                warnings.append(message)
                logging.exception(message)

        missing = set(EXPECTED_STREAMS) - found_streams
        for stream in sorted(missing):
            warnings.append(f"Missing {stream} file in {day}")

    combined = {}
    for stream, frames in stream_frames.items():
        if frames:
            combined[stream] = pd.concat(frames, ignore_index=True, sort=False)
        else:
            combined[stream] = pd.DataFrame({
                "Participant": [],
                "Day": [],
                "Source File": [],
            })

    total_files = sum(len(frames) for frames in stream_frames.values())
    overview.extend([
        {"Property": "Participant", "Value": participant},
        {"Property": "Generated", "Value": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        {"Property": "Days Detected", "Value": len(days)},
        {"Property": "Files Imported", "Value": total_files},
        {"Property": "Warnings", "Value": len(warnings)},
        {"Property": "Status", "Value": "Completed with warnings" if warnings else "Completed"},
    ])

    if warnings:
        overview.append({"Property": "Warnings / Notes", "Value": " | ".join(warnings)})

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{participant}.xlsx"
    write_workbook(output_path, participant, combined, overview, summary)

    if warnings:
        logging.warning("%s completed with %d warning(s)", participant, len(warnings))
    else:
        logging.info("%s completed successfully", participant)

    return output_path, warnings

def main():
    parser = argparse.ArgumentParser(
        description="Consolidate multi-stream participant data into Excel workbooks."
    )
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--input", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    config = load_config(args.config)

    input_dir = Path(args.input or config["input_directory"])
    output_dir = Path(args.output or config["output_directory"])
    log_dir = Path(config.get("log_directory", "logs"))

    setup_logging(log_dir)

    if not input_dir.exists():
        raise SystemExit(f"Input directory does not exist: {input_dir}")

    participants = discover_participants(input_dir)
    if not participants:
        raise SystemExit(f"No participant folders found in: {input_dir}")

    logging.info("Found %d participant(s).", len(participants))

    failures = 0
    for participant_dir in participants:
        try:
            consolidate_participant(participant_dir, output_dir, config)
        except Exception:
            failures += 1
            logging.exception("Participant failed: %s", participant_dir.name)

    logging.info("Batch complete. Participants: %d | Failures: %d",
                 len(participants), failures)

if __name__ == "__main__":
    main()
