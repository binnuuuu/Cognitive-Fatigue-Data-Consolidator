import csv
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.config import DEFAULT_CONFIG
from src.consolidator import build_consolidated_data


POST_COLUMNS = [
    "StartDate",
    "PID",
    "Day",
    "Fatigue Condition",
    "AI_Decision_Support",
    "AI_Action_Support",
    "Dependent_Variable",
]


def write_post_survey(path: Path, participant_rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(POST_COLUMNS)
        writer.writerow(["Question text"] * len(POST_COLUMNS))
        writer.writerow(["ImportId"] * len(POST_COLUMNS))
        writer.writerows(participant_rows)


def write_nasa(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "Mental Demand\t60\n"
        "Physical Demand\t10\n"
        "Temporal Demand\t40\n"
        "Performance\t30\n"
        "Effort\t50\n"
        "Frustration\t20\n"
        "Total Workload\t35\n",
        encoding="utf-8",
    )


def write_simulator(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "PID": "PT3",
        "Day": 1,
        "AISupportDisplay": "HighSupport",
        "AIActionDisplay": "Manual",
        "UserRunData": {
            "MissionNum": 2,
            "TimeToComplete": 123.5,
            "AUVRunData": [
                {"AUVNum": 1, "TargetsFound": 4, "BatterySamples": [90, 80]},
                {"AUVNum": 2, "TargetsFound": 7, "BatterySamples": [75, 65]},
            ],
            "Sagat1": [{"CorrectAnswer": "A", "IsCorrect": True}],
            "Sagat2": [{"CorrectAnswer": "B", "IsCorrect": False}],
        },
        "ActionOrder": [
            {"UserCorrect": True, "UserVerified": True, "Time": 2.5},
            {"UserCorrect": False, "UserVerified": False, "Time": 5.5},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class ConsolidatorTests(unittest.TestCase):
    def test_zip_input_merges_post_nasa_and_separate_auv_results(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "Pilot_Data"
            write_post_survey(
                root / "Post_Survey" / "Post_Survey.csv",
                [["ignored", "PT3", "1", "0", "2", "1", "42"]],
            )
            (root / "Pre_Survey.csv").write_text(
                "PID,Pre_Measure\nPT3,99\n",
                encoding="utf-8",
            )
            write_nasa(root / "NASA_TLX" / "PT3_Day1_NASA_TLX.xls")
            write_simulator(root / "sim_Data" / "PT3_Day1_ParticipantData.json")

            archive_path = Path(temp_dir) / "pilot.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                for source in root.rglob("*"):
                    if source.is_file():
                        archive.write(source, source.relative_to(root.parent))

            frame, warnings = build_consolidated_data(archive_path, DEFAULT_CONFIG)

            self.assertEqual(len(frame), 1)
            row = frame.iloc[0]
            self.assertEqual(row["PID"], "PT3")
            self.assertEqual(row["Fatigue Condition Label"], "Non-fatigue")
            self.assertEqual(row["NASA_Mental_Demand"], 60)
            self.assertEqual(row["SIM_AUV1_TargetsFound"], 4)
            self.assertEqual(row["SIM_AUV2_TargetsFound"], 7)
            self.assertEqual(row["SIM_SAGAT_Accuracy"], 0.5)
            self.assertEqual(row["SIM_Action_Accuracy"], 0.5)
            self.assertEqual(row["NASA_Available"], "Yes")
            self.assertEqual(row["Simulator_Available"], "Yes")
            self.assertNotIn("Pre_Measure", frame.columns)
            self.assertEqual(warnings, [])

    def test_dayless_nasa_is_not_guessed_when_two_sessions_exist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_post_survey(
                root / "Post_Survey.csv",
                [
                    ["ignored", "PT3", "1", "0", "2", "1", "42"],
                    ["ignored", "PT3", "2", "1", "1", "2", "43"],
                ],
            )
            write_nasa(root / "NASA_TLX" / "PT3_NASA_TLX.xls")

            frame, warnings = build_consolidated_data(root, DEFAULT_CONFIG)

            self.assertEqual(len(frame), 2)
            self.assertTrue((frame["NASA_Available"] == "No").all())
            self.assertTrue(any("multiple sessions" in warning for warning in warnings))

    def test_nasa_f_and_nf_names_match_the_correct_days(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_post_survey(
                root / "Post_Survey.csv",
                [
                    ["ignored", "PT2", "1", "1", "1", "2", "42"],
                    ["ignored", "PT2", "2", "0", "1", "2", "43"],
                ],
            )
            fatigue_file = root / "NASA_TLX" / "PT2_F.xls"
            non_fatigue_file = root / "NASA_TLX" / "PT2_NF.xls"
            write_nasa(fatigue_file)
            write_nasa(non_fatigue_file)
            fatigue_file.write_text(
                fatigue_file.read_text(encoding="utf-8").replace(
                    "Mental Demand\t60", "Mental Demand\t90"
                ),
                encoding="utf-8",
            )

            frame, warnings = build_consolidated_data(root, DEFAULT_CONFIG)

            day1 = frame.loc[frame["Day"] == 1].iloc[0]
            day2 = frame.loc[frame["Day"] == 2].iloc[0]
            self.assertEqual(day1["NASA_Source_File"], "PT2_F.xls")
            self.assertEqual(day1["NASA_Mental_Demand"], 90)
            self.assertEqual(day2["NASA_Source_File"], "PT2_NF.xls")
            self.assertEqual(day2["NASA_Mental_Demand"], 60)
            self.assertFalse(any("Could not match NASA-TLX" in warning for warning in warnings))

    def test_conflicting_day_and_fatigue_filename_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_post_survey(
                root / "Post_Survey.csv",
                [["ignored", "PT2", "1", "1", "1", "2", "42"]],
            )
            write_nasa(root / "NASA_TLX" / "PT2_Day1_NF_NASA_TLX.xls")

            frame, warnings = build_consolidated_data(root, DEFAULT_CONFIG)

            self.assertEqual(frame.iloc[0]["NASA_Available"], "No")
            self.assertTrue(any("conflicts" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()
