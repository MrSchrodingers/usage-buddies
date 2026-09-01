"""Lines from Claude instead of from the table, and the money that costs.

Measured on this machine: one short answer costs about $0.024 and takes forty
seconds; a batch of twelve costs $0.031 and takes fifty-four. $0.0026 a line.
That ratio is why this exists as a queue and not as a call per sentence.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import buddy_voice as voice


def _state(n=1, idle=125):
    return voice.situation(
        {"sessions": [{"name": f"repo{i}", "state": "waiting", "idleSeconds": idle}
                      for i in range(n)]},
        {"rateLimits": {"session": {"percentUsed": 31},
                        "weeklyAll": {"percentUsed": 47}}})


def test_the_situation_is_coarse_enough_not_to_churn():
    """A number ticking up by one must not read as a new situation and buy a
    new batch. Idle is bucketed and percentages round to tens."""
    a = _state(idle=125)
    b = _state(idle=170)          # same minute bucket
    assert voice.signature(a) == voice.signature(b), "two minutes apart bought a batch"
    c = _state(idle=600)
    assert voice.signature(a) != voice.signature(c), "ten minutes later looks identical"


def test_a_desktop_that_has_not_changed_costs_nothing():
    v = voice.Voice("pt", now=0.0)
    state = _state()
    assert v.should_refill(state, 1000.0)
    v.started(state, 1000.0)
    v.delivered(["uma", "duas", "tres", "quatro", "cinco"])
    assert not v.should_refill(state, 1001.0), "called again immediately"
    assert not v.should_refill(state, 9000.0), "spent on an unchanged desktop"


def test_a_changed_desktop_buys_more():
    v = voice.Voice("pt", now=0.0)
    v.started(_state(1), 1000.0)
    v.delivered(["a", "b", "c", "d", "e"])
    assert v.should_refill(_state(3), 1000.0 + voice.MIN_SECONDS + 1)


def test_running_low_buys_more_even_unchanged():
    v = voice.Voice("pt", now=0.0)
    state = _state()
    v.started(state, 1000.0)
    v.delivered(["a", "b"])
    assert v.should_refill(state, 1000.0 + voice.MIN_SECONDS + 1)


def test_repeated_failure_backs_off_instead_of_retrying():
    """A broken CLI must not become a call every four minutes forever."""
    v = voice.Voice("pt", now=0.0)
    state = _state()
    v.started(state, 1000.0)
    v.delivered([])
    v.delivered([])
    v.delivered([])
    assert not v.should_refill(state, 1000.0 + voice.MIN_SECONDS + 1), \
        "retried at the same rate after three failures"


def test_an_empty_queue_falls_back_to_the_table():
    """None means the caller keeps the written line. The companion must never
    go quiet because a call failed."""
    v = voice.Voice("pt", now=0.0)
    assert v.take() is None
    v.delivered(["so uma"])
    assert v.take() == "so uma"
    assert v.take() is None


def test_harvest_strips_what_a_model_adds_to_a_list():
    raw = json.dumps([{"type": "result", "subtype": "success",
                       "total_cost_usd": 0.03, "usage": {"output_tokens": 400},
                       "result": json.dumps({"lines": [
                           "1. numerada",
                           "- com traco",
                           '"entre aspas"',
                           "curta",                      # too short, dropped
                           "x" * 200,                    # too long, dropped
                           42,                           # not a string
                           "Uma frase de tamanho perfeitamente razoavel.",
                       ]})}])
    lines, meta = voice.harvest(raw)
    assert "numerada" in lines
    assert "com traco" in lines
    assert "entre aspas" in lines
    assert "Uma frase de tamanho perfeitamente razoavel." in lines
    assert not any(len(x) > voice.MAX_CHARS for x in lines)
    assert not any(x.startswith(("-", '"', "1.")) for x in lines)
    assert meta["costUSD"] == 0.03


def test_harvest_never_raises_on_junk():
    for junk in ("", "not json", "[]", '{"result":"{}"}', None):
        assert voice.harvest(junk)[0] == []


def test_the_batch_carries_a_hard_spending_ceiling():
    """The CLI enforces it, so a runaway call cannot cost more than this."""
    command = voice.build(_state(), "pt")
    assert "--max-budget-usd" in command
    assert float(command[command.index("--max-budget-usd") + 1]) <= 0.25
    assert "--json-schema" in command
    assert command[command.index("--effort") + 1] == "low"
