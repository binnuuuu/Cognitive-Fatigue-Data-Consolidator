# Cognitive Fatigue Data Consolidator

This tool combines the study's **Post Survey**, **NASA-TLX**, and **simulator** results into one Excel worksheet. Each row represents one participant on one experiment day.

For the updated pilot data, the output contains seven rows: Day 1 for PT1–PT4 and Day 2 for PT2–PT4. PT1 did not complete Day 2.

## What is included

- Post Survey columns beginning with `PID` (the earlier Qualtrics metadata columns A–Q are excluded)
- Independent variables and readable labels:
  - Fatigue Condition: `0 = Non-fatigue`, `1 = Fatigue`
  - AI Decision Support: `1 = LowSupport`, `2 = HighSupport`
  - AI Action Support: `1 = Manual`, `2 = AIAssisted`
- NASA-TLX: Mental, Physical, Temporal, Performance, Effort, Frustration, and Total Workload
- Simulator session results, SAGAT and action summaries, with each AUV kept in separate `SIM_AUV1_...`, `SIM_AUV2_...`, etc. columns
- Source-file and availability columns so missing data is visible rather than silently guessed

Pre Survey, PsychoPy, heart-rate, eye-tracking, and NASA-TLX weights are intentionally excluded from this version. The Pre Survey CSV may remain inside the ZIP; the tool identifies and uses only the Post Survey CSV.

## SPSS structure

The output is a flat, analysis-ready table for import into SPSS Statistics:

- one row represents one participant on one completed experiment day
- `PID` repeats when a participant completed both days
- `Day` and `Fatigue Condition` identify the session
- each dependent measure has its own column
- unavailable measurements remain blank and are explained by availability/status columns

SPSS performs the statistical analysis. This consolidator prepares and checks the input structure; it does not perform or validate the statistical analysis itself.

## Input

The input may be either the supplied ZIP file or an extracted folder. The tool searches subfolders, so their exact order is not important. It expects:

```text
Pilot_Data/
├── ...Post...Survey....csv
├── ...pre...survey....csv
├── NASA_TLX/
│   ├── PT3_NF.xls
│   └── PT3_F.xls
└── Sim_Data/
    ├── ParticipantData_PID_PT3_Day1.json
    └── ParticipantData_PID_PT3_Day2.json
```

The pilot NASA-TLX files use an `.xls` filename but are tab-delimited text; the reader handles that format directly.

The Post Survey is the master session list. Every participant/day that should appear in the output must have one row there with `PID`, `Day`, `Fatigue Condition`, `AI_Decision_Support`, and `AI_Action_Support`.

NASA-TLX files can identify the session with either a day (`PT3_Day2_NASA_TLX.xls`) or a fatigue-condition suffix (`PT3_F.xls` or `PT3_NF.xls`). Here, `F` means fatigue and `NF` means non-fatigue. For future collections, including both is clearest, for example `PT3_Day2_F_NASA_TLX.xls`.

Simulator JSON filenames must include `Day1`, `Day2`, and so on because the supplied JSON records do not contain a day value internally.

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
  --input "/path/to/Pilot_Data.zip" \
  --output "output/consolidated_study_data.xlsx"
```

Or place an extracted dataset in `incoming_data/` and run:

```bash
python consolidate.py
```

The generated workbook contains one sheet named `Consolidated_Data`. Running the command again replaces that output file atomically, so it does not create an ever-growing collection of timestamped Excel files.

## Missing pilot data

PT1 Day 1 and PT2 Day 1 remain in the consolidated output, but their simulator fields are blank because those files are no longer available. PT1 has no Day 2 row because that session was not completed. `NASA_Available`, `Simulator_Available`, and `Data_Status_Notes` explain source-data gaps.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Privacy

Human-participant source data should not be committed to GitHub. `incoming_data/`, `private_reference/`, generated workbooks, and logs are ignored by Git.
