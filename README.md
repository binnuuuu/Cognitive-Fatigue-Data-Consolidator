# Cognitive Fatigue Data Consolidator

This tool combines the study's **Post Survey**, **NASA-TLX**, and **simulator** results into one Excel worksheet. Each row represents one participant on one experiment day.

For the current pilot data, the output contains four rows (PT1–PT4, Day 1). When Day 2 is collected, it can contain eight rows—two rows per participant.

## What is included

- Post Survey columns beginning with `PID` (the earlier Qualtrics metadata columns A–Q are excluded)
- Independent variables and readable labels:
  - Fatigue Condition: `0 = Non-fatigue`, `1 = Fatigue`
  - AI Decision Support: `1 = LowSupport`, `2 = HighSupport`
  - AI Action Support: `1 = Manual`, `2 = AIAssisted`
- NASA-TLX: Mental, Physical, Temporal, Performance, Effort, Frustration, and Total Workload
- Simulator session results, SAGAT and action summaries, with each AUV kept in separate `SIM_AUV1_...`, `SIM_AUV2_...`, etc. columns
- Source-file and availability columns so missing data is visible rather than silently guessed

Pre Survey, PsychoPy, heart-rate, eye-tracking, and NASA-TLX weights are intentionally excluded from this version.

## Input

The input may be either the supplied ZIP file or an extracted folder. The tool searches subfolders, so their exact order is not important. It expects:

```text
Pilot_Data/
├── Post_Survey/
│   └── ...Post...Survey....csv
├── NASA_TLX/
│   └── PT3_Day1_NASA_TLX.xls
└── sim_Data/
    └── PT3_Day1_ParticipantData.json
```

The pilot NASA-TLX files use an `.xls` filename but are tab-delimited text; the reader handles that format directly.

The Post Survey is the master session list. Every participant/day that should appear in the output must have one row there with `PID`, `Day`, `Fatigue Condition`, `AI_Decision_Support`, and `AI_Action_Support`.

For Day 2 and later, include the day in auxiliary filenames—for example, `PT3_Day2_NASA_TLX.xls` and `PT3_Day2_ParticipantData.json`. A file without a day is accepted only when that participant has one Post Survey session. If two sessions exist and a NASA-TLX file has no day, the tool leaves it unmatched and reports a warning instead of attaching it to the wrong row.

## Install

```bash
git clone https://github.com/binnuuuu/Cognitive-Fatigue-Data-Consolidator.git
cd Cognitive-Fatigue-Data-Consolidator

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

```

## Run with the pilot ZIP

```bash
python consolidate.py \
  --input "/Users/dspl_013/Downloads/Pilot_Data.zip" \
  --output "output/consolidated_study_data.xlsx"
```

Or place an extracted dataset in `incoming_data/` and run:

```bash
python consolidate.py
```

The generated workbook contains one sheet named `Consolidated_Data`. Running the command again replaces that output file atomically, so it does not create an ever-growing collection of timestamped Excel files.

## Missing pilot data

PT1 and PT2 remain in the consolidated output because they exist in the Post Survey. Their simulator fields are blank because the simulation was updated and those files are no longer available. NASA-TLX fields are also blank when no matching file is supplied. `NASA_Available`, `Simulator_Available`, and `Data_Status_Notes` explain these gaps.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Privacy

Human-participant source data should not be committed to GitHub. `incoming_data/`, `private_reference/`, generated workbooks, and logs are ignored by Git.
