# Cognitive Fatigue Data Consolidator

Reads Post Survey and simulator data and creates an Excel workbook with `Consolidated_Data` and `Long_Format` worksheets.

## Input ZIP

Create this folder structure and ZIP the `Pilot_Data` folder:

```text
Pilot_Data/
├── Survey_Data/
│   ├── ...Post...Survey...csv   # Required; includes NASA-TLX ratings
│   └── ...pre...survey...csv    # Optional; not added to the output
└── Simulation_Data/
    ├── P1_F_M2.json
    ├── P1_NF_M1.json
    └── ...
```

When there are multiple survey files of the same type, the file with the newest date in its filename is selected (for example, October 11 over October 9). Give each version a readable date. Simulation filenames should include participant ID, condition (`F` or `NF`), and mission (`M1` or `M2`). A numbered duplicate such as `P18_F_M2 (2).json` is treated as the redo.

## Output

- `Consolidated_Data`: existing output, one row per survey session, with survey and NASA-TLX ratings plus matched simulator summaries.
- `Long_Format`: two rows per participant, one Fatigue (`F`) and one Non-fatigue (`NF`), with general measure columns and condition identified in `Fatigue Condition`.
- `NASA_Total_Workload` is blank because pairwise NASA-TLX weights are not included in the input.

## Download and install (Windows PowerShell)

1. Download the repository ZIP from [GitHub](https://github.com/binnuuuu/Cognitive-Fatigue-Data-Consolidator) using **Code → Download ZIP**, then extract it.
2. In PowerShell, go to the extracted project folder containing `consolidate.py` and `requirements.txt`:

```powershell
cd "C:\path\to\Cognitive-Fatigue-Data-Consolidator-main"
```

3. Create the environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run

Pass the path to your ZIP file:

```powershell
.\.venv\Scripts\python.exe consolidate.py --input "C:\path\to\Pilot_Data.zip" --output "output\consolidated_study_data.xlsx"
```

The workbook is saved to `output\consolidated_study_data.xlsx`. The input can also be an extracted `Pilot_Data` folder instead of a ZIP.

Keep participant data private; do not commit it to GitHub.
