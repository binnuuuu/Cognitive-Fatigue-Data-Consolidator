# Cognitive Fatigue Data Consolidator

A small Python tool for consolidating research data into one Excel workbook per participant.

## What it does

This project reads participant data from a folder structure like this:

```text
my_data/
  P001/
    Day1/
      eye_tracking.csv
      heart_rate.csv
      eeg.csv
      behavior.csv
      subjective.csv
    Day2/
      eye_tracking.csv
      heart_rate.csv
      eeg.csv
      behavior.csv
      subjective.csv
```

It groups files by participant and day, identifies each file by its name, and writes a workbook such as `P001.xlsx`.

## Why the file names matter

The script uses file names to decide what kind of data each file is.

Examples:

- `eye_tracking.csv` → EyeTracking
- `heart_rate.csv` → HeartRate
- `eeg.csv` → EEG
- `behavior.csv` → Behavior
- `subjective.csv` → Subjective

If your files use different names, add custom aliases in `config.yaml`.

## Column consistency

The tool does not require all participants to have the exact same columns or the same number of columns.

That said, keeping a consistent schema is better for research quality.

## Install



```bash
git clone https://github.com/binnuuuu/Cognitive-Fatigue-Data-Consolidator.git
cd Cognitive-Fatigue-Data-Consolidator

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

```

## Run

```bash
python consolidate.py
```

Or with your own folder:

```bash
python consolidate.py --input "/path/to/my_data" --output "/path/to/output_folder"
```

## Output

The tool creates one Excel file per participant in the output directory, with sheets for the different data streams and a summary.

## Project type

This is best described as a research data consolidation tool or Python data-processing utility.

It is not a web app or a manual data-entry tool.
