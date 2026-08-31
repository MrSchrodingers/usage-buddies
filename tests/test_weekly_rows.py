"""The weekly rows the plasmoid draws are computed in QML's JavaScript.

That logic used to be seven hand-written blocks, which is how the Sonnet row
kept rendering at a permanent 0% after the API deprecated seven_day_sonnet to
null. It is now one data-driven Repeater, so it is worth testing — but pytest
cannot run QML. This extracts the real `weeklyRows` body out of main.qml (not a
copy of it) and evaluates it in node against captured payloads.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
QML = REPO / "plasmoid" / "contents" / "ui" / "main.qml"
RUNNER = Path(__file__).resolve().parent / "weekly_rows.mjs"

# rateLimits as build_rate_limits() emits it against the live endpoint
# (2026-08-31): seven_day_sonnet/_opus null, one weekly_scoped entry for Fable.
LIVE_RATE_LIMITS = {
    "session": {"percentUsed": 1.0, "resetsInMinutes": 296, "windowHours": 5,
                "resetsAt": "2026-08-31T23:30:00+00:00"},
    "weeklyAll": {"percentUsed": 32.0, "resetsLabel": "Fri 04:59 AM",
                  "resetsAt": "2026-09-04T04:59:59+00:00"},
    "weeklyFable": {"percentUsed": 0, "modelName": "Fable",
                    "resetsLabel": "", "resetsAt": ""},
    "weeklyScoped": {"percentUsed": 0, "modelName": "Fable",
                     "resetsLabel": "", "resetsAt": ""},
    "plan": "Max (20x)", "source": "api",
}


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_weekly_rows_against_live_payload(tmp_path):
    payload = tmp_path / "rate_limits.json"
    payload.write_text(json.dumps(LIVE_RATE_LIMITS))
    r = subprocess.run(["node", str(RUNNER), str(payload), str(QML)],
                       capture_output=True, text=True)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert "TODAS PASSARAM" in r.stdout, r.stdout
