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


# A trimmed payload with the fields quirkBadges reads, so the badge logic is
# exercised without depending on whatever this machine happens to have done.
LIVE_PAYLOAD = {
    "rateLimits": LIVE_RATE_LIMITS,
    "today": {"totalTokens": 1_781_115_342},
    "toolUse": {"byTool": {"Bash": 30268, "Read": 2862, "Edit": 1152,
                           "Write": 270, "Agent": 223, "Grep": 167}},
    "compaction": {"count": 11},
    "streak": {"days": 1},
    "lifetime": {"peakHours": {"0": 7, "1": 3, "2": 2, "14": 76, "16": 60}},
    "burnRate": {"total_per_hour": 372436672},
}


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_weekly_rows_against_live_payload(tmp_path):
    payload = tmp_path / "rate_limits.json"
    payload.write_text(json.dumps(LIVE_RATE_LIMITS))
    full = tmp_path / "widget-data.json"
    full.write_text(json.dumps(LIVE_PAYLOAD))
    r = subprocess.run(["node", str(RUNNER), str(payload), str(QML), str(full)],
                       capture_output=True, text=True)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert "TODAS PASSARAM" in r.stdout, r.stdout
