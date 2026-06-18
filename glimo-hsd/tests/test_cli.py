import json
import os
import subprocess
import sys


def test_cli_process_smoke(tmp_path):
    env = {**os.environ, "PYTHONPATH": "src"}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "glimo_hsd.cli",
            "process",
            "tests/fixtures/sample_5.csv",
            "--text-col",
            "text",
            "--label-col",
            "hs",
            "--out",
            str(tmp_path / "run"),
            "--classifier-backend",
            "keyword",
            "--restatement-backend",
            "none",
            "--final-scrub",
        ],
        cwd=".",
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(proc.stdout)
    assert payload["restated_csv"].endswith("final_scrubbed.csv")
    assert payload["manifest_json"].endswith("manifest.json")
