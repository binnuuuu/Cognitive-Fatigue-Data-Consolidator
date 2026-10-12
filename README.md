# Cognitive Fatigue Data Consolidator

This Python tool reads the study's Post Survey CSV and simulator JSON files, joins them by participant and session, and writes an Excel workbook with two worksheets:

- `Consolidated_Data` — the existing output sheet.
- `Long_Format` — two condition rows per participant (Fatigue and Non-fatigue), using the same measurement columns.

## Input data and how it is read

The input can be a ZIP file or an extracted folder. Put the survey exports and simulator JSONs in this layout, then ZIP the top-level study folder:

```text
Pilot_Data/
├── Survey_Data/
│   ├── Diss+study+2+Post+Survey_October+11,+2026_20.36.csv
│   └── Diss+study+2+pre+survey_October+11,+2026_20.34.csv
└── Simulation_Data/
    ├── P1_F_M2.json
    ├── P1_NF_M1.json
    └── ...
```

The folder names can vary; the program searches the input's subfolders. Keep the Post Survey and simulator files in the ZIP. The Pre Survey is optional for this consolidation: the program identifies the newest dated Pre Survey if there are multiple, but does not currently add Pre Survey data to the workbook.

### Which survey file is selected?

The Post Survey is required and is the master list of participant sessions. If multiple Post Survey CSVs are present, the program selects the file with the newest date in its filename. It applies the same selection rule to multiple Pre Survey CSVs. For example, an October 11 export is selected over an October 9 export. When there are multiple versions, put a readable date in each filename; if any candidate filename has no readable date, the program stops and reports that it cannot choose safely.

From the selected Post Survey, the program:

- keeps columns from `PID` onward, excluding the configured `Spacer` fields;
- uses `PID`, `Day`, `Fatigue Condition`, and the survey's other fields as the session/master data;
- adds readable labels for the configured fatigue and AI support codes;
- renames `NASA_TLX_1` through `NASA_TLX_6` to Mental Demand, Physical Demand, Temporal Demand, Performance, Effort, and Frustration output columns.

Participant IDs such as `1`, `01`, and `P1` are normalized to `P1`. Survey rows without a participant ID are skipped. The selected Post Survey filename is recorded in `Post_Source_File` and, when it contains NASA-TLX ratings, `NASA_Source_File`.

### Which simulator files are selected?

Simulator JSON files should be named with participant, condition, and mission tokens, for example `P1_F_M2.json` and `P1_NF_M1.json`:

- `F` means Fatigue; `NF` means Non-fatigue.
- `M1` and `M2` identify the mission.
- The participant ID and condition are used to match the simulation to the Post Survey session. The mission is retained as simulator data.

If duplicate simulator files identify the same participant, condition, and mission and one has a numbered copy suffix, such as `P18_F_M2 (2).json`, the highest numbered copy is selected. A warning is written to the run log. Simulator summaries include AUV metrics, SAGAT totals/correct counts/accuracy, and action counts/accuracy/timing. The source filename is recorded in `SIM_Source_File`.

Separate NASA-TLX files are not required; ratings come from the selected Post Survey. `NASA_Total_Workload` is included but left blank because the input does not include the pairwise-comparison weights needed to calculate the weighted NASA-TLX workload score. The Pre Survey, heart-rate, eye-tracking, and other unrelated files are not included in the output.

## Workbook worksheets and row/column structure

### `Consolidated_Data` (existing sheet)

This sheet preserves the current output layout. In the current code, each row represents a Post Survey participant session (typically a participant/day), and condition is identified by the `Fatigue Condition` column (`1 = Fatigue`, `0 = Non-fatigue`). Measurements are stored in their own columns. The sheet includes:

- Post Survey data from `PID` onward, plus readable condition/support labels;
- NASA-TLX ratings from the Post Survey;
- simulator fields and summaries matched to the participant session;
- `NASA_Available`, `Simulator_Available`, and `Data_Status_Notes` so missing source data is visible;
- source filename columns (`Post_Source_File`, `NASA_Source_File`, and `SIM_Source_File`).

The program does not change `Consolidated_Data` when creating the `Long_Format` sheet.

### `Long_Format` (additional sheet)

This sheet has two rows per participant, in this order: Fatigue (`1`) and Non-fatigue (`0`). The row's `Fatigue Condition` and `Fatigue Condition Label` identify which condition its measurements represent. It carries the same general measurement columns as `Consolidated_Data`; it does not add separate `F_` and `NF_` versions of each measure. If a participant has no session for one condition, that condition still has a row with blank session measurements and a status note.

The key distinction is the arrangement: one row is one participant-condition, while the existing sheet has one row for each session. In this code, dependent measures (such as NASA-TLX ratings and simulator accuracy) are in columns, and condition is represented by rows in `Long_Format`. The participant ID cell is visually shown once across its adjacent F/NF pair, while the ID remains stored in both rows.

**Note about the term “wide”:** The current `Consolidated_Data` code stores one row per session and uses `Fatigue Condition` to identify the condition. It does not currently create paired columns such as `F_SAGAT_Accuracy` and `NF_SAGAT_Accuracy` on one row per participant. The additional sheet follows the current code's session data and produces the two condition rows described above; it does not pivot paired F/NF columns into a single measure column.

## Download and install on Windows

1. Open the [GitHub repository](https://github.com/binnuuuu/Cognitive-Fatigue-Data-Consolidator).
2. Select **Code**, then **Download ZIP**. Extract the downloaded repository ZIP.
3. Open PowerShell and change to the extracted project folder—the folder containing both `consolidate.py` and `requirements.txt`:

```powershell
cd "C:\path\to\Cognitive-Fatigue-Data-Consolidator-main"
```

4. Create the virtual environment and install the dependencies from that project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If `python` is not recognized, install Python and enable **Add Python to PATH**, then reopen PowerShell.

## Prepare and ZIP your study input

1. Create a folder, for example `Pilot_Data`.
2. Inside it, create `Survey_Data` and `Simulation_Data`.
3. Put the Post Survey CSV (with NASA-TLX columns) and, if available, the Pre Survey CSV in `Survey_Data`.
4. Put the simulator JSON files in `Simulation_Data`.
5. In File Explorer, right-click the `Pilot_Data` folder and choose **Compress to ZIP file** (or **Send to > Compressed (zipped) folder**). The ZIP should contain the `Pilot_Data` folder and its two subfolders.

Example ZIP contents:

```text
Pilot_Data.zip
└── Pilot_Data/
    ├── Survey_Data/
    └── Simulation_Data/
```

## Run the consolidation

Run this from the project folder. Replace the input path with the location of your ZIP:

```powershell
.\.venv\Scripts\python.exe consolidate.py --input "C:\Users\YourName\Downloads\Pilot_Data.zip" --output "output\consolidated_study_data.xlsx"
```

The workbook will be created at `output\consolidated_study_data.xlsx` and will contain `Consolidated_Data` and `Long_Format`. Running the command again replaces that output workbook. Run details and warnings are saved in `logs\run.log`.

If replacement fails with a permission error, close the output workbook in Excel or any other application and run the command again. The existing workbook is preserved when replacement fails.

You can pass an extracted input folder instead of a ZIP:

```powershell
.\.venv\Scripts\python.exe consolidate.py --input "C:\path\to\Pilot_Data" --output "output\consolidated_study_data.xlsx"
```

## Privacy

Human-participant source data should not be committed to GitHub. Keep the survey and simulator data ZIP private; do not upload it to the repository.
