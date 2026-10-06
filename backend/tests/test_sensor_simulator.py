"""Tests for the simulated sensor tool (Phase 4 plan, sub-task 2)."""

from app.modules.mcp.tools.sensor_simulator import simulate_reading


def test_known_metric_returns_value_in_plausible_range() -> None:
    reading = simulate_reading("What is the current temperature of kiln 2?")

    assert reading["metric"] == "temperature"
    assert reading["simulated"] is True
    assert 280.0 <= reading["value"] <= 420.0
    assert reading["unit"] == "C"


def test_unknown_metric_is_honest_not_fabricated() -> None:
    reading = simulate_reading("What's the status of work order 4521?")

    assert reading["metric"] is None
    assert reading["value"] is None
    assert reading["simulated"] is True
    assert reading["note"] is not None


def test_every_result_is_marked_simulated() -> None:
    for query in ["current vibration on pump 12", "current pressure in the reactor", "is it online"]:
        assert simulate_reading(query)["simulated"] is True
