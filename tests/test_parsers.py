import json
from datetime import datetime
from pathlib import Path
import pytest
from tutu_mcp.errors import TutuError, validate_date
from tutu_mcp.parsers import parse_price, position_from_label, explicit_availability, site_date, decode_state, normalize_seats
from tutu_mcp.tutu import TutuAdapter

FIXTURES = Path(__file__).parent / "fixtures"


def test_prices():
    assert parse_price("от 4 ⁠017 ⁠₽")["amount"] == 4017
    assert parse_price("Мест нет") is None
    assert parse_price("5 270,35 руб")["amount"] == 5270.35


def test_no_guessing_position_or_availability():
    assert position_from_label("место 1, этаж 2") == "unknown"
    assert position_from_label("нижнее боковое") == "lower"
    assert explicit_availability("Место 8") is None
    assert explicit_availability("Недоступно") is False


def test_overnight_dates():
    assert site_date("1 янв, пт", "2026-12-31") == "2027-01-01"
    assert site_date("16 дек, ср", "2026-12-15") == "2026-12-16"


def test_calendar_date_and_moscow_day():
    with pytest.raises(TutuError, match="существующая"):
        validate_date("2026-02-30")
    now = datetime.fromisoformat("2026-11-22T22:00:00+00:00")
    with pytest.raises(TutuError, match="прошла"):
        validate_date("2026-11-22", now)
    validate_date("2026-11-23", now)


def test_real_snapshot_seats_and_adult_price():
    data = json.loads((FIXTURES / "car2-2026-11-23.json").read_text())
    dom = json.loads((FIXTURES / "car2-dom.json").read_text())
    seats = normalize_seats(dom, decode_state(data), "2")
    assert len(seats) == 25
    by_number = {seat["number"]: seat for seat in seats}
    assert "5" not in by_number
    assert by_number["1"]["position"] == "lower"
    assert by_number["2"]["position"] == "upper"
    assert by_number["1"]["compartment"] == "1"
    assert by_number["1"]["floor"] is None
    assert by_number["1"]["price"]["amount"] == 5105.99


def test_unknown_structure_is_error_not_empty_results():
    with pytest.raises(TutuError, match="Структура"):
        decode_state({"dictionaries": {}})


@pytest.mark.asyncio
async def test_stale_result_does_not_launch_browser():
    adapter = TutuAdapter()
    with pytest.raises(TutuError) as caught:
        await adapter.seats("00000000-0000-4000-8000-000000000000")
    assert caught.value.code == "STALE_RESULT"
    assert adapter.browser.playwright is None
