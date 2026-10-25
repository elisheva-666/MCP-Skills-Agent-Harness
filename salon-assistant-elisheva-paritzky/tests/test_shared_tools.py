"""Offline tests for shared/tools.py. No network, no API key: Hebcal is faked."""
from datetime import date

import pytest

from shared.store import read_json
from shared.tools import SalonTools, ToolError

TODAY = date(2026, 10, 25)


def fake_hebcal(url: str) -> dict:
    if "converter" in url:
        return {"hebrew": "ז׳ בִּשְׁבָט תשפ״ז"}
    return {"items": [{"category": "holiday", "title": "ראש השנה", "yomtov": True}]}


@pytest.fixture
def tools(tmp_path):
    return SalonTools(tmp_path, client_id="0501111111", today=TODAY, http_get=fake_hebcal)


def test_search_services_finds_bridal_and_is_compact(tools):
    out = tools.search_services("כלה")
    assert "bridal-makeup" in out and "price on request" in out
    assert "{" not in out  # one line per item, no JSON


def test_search_services_returns_only_best_matches(tools):
    ids = [line.split(" | ")[0] for line in tools.search_services("איפור כלה").splitlines()]
    assert ids == ["bridal-makeup", "bridal-package"]


def test_search_services_hebrew_prefix(tools):
    assert "bridal-hair" in tools.search_services("לכלה")


def test_search_services_no_match_lists_categories(tools):
    assert "categories:" in tools.search_services("מניקור")


def test_gallery_ranks_by_matching_tags(tools):
    first = tools.find_gallery_images(["אסוף", "כלה"]).splitlines()[0]
    assert first.startswith("img_0577.jpg")


def test_gallery_unknown_tag_returns_known_tags(tools):
    assert "known tags:" in tools.find_gallery_images(["סגול"])


def test_availability_and_saturday_closed(tools):
    assert "free 09:00" in tools.check_availability("2027-01-14")
    assert "closed" in tools.check_availability("2027-01-16")


def test_past_date_is_an_error(tools):
    with pytest.raises(ToolError):
        tools.check_availability("2020-01-01")


def test_booking_twice_moves_instead_of_duplicating(tools):
    assert tools.book_appointment("bridal-package", "2027-01-14", "09:00").startswith("booked")
    assert tools.book_appointment("bridal-package", "2027-01-21", "11:00").startswith("moved")
    bookings = read_json(tools._bookings_path, [])
    assert len(bookings) == 1 and bookings[0]["date"] == "2027-01-21"
    assert "09:00" in tools.check_availability("2027-01-14")  # old slot was freed


def test_slot_taken_by_other_client(tmp_path):
    a = SalonTools(tmp_path, "a", today=TODAY)
    b = SalonTools(tmp_path, "b", today=TODAY)
    a.book_appointment("bridal-hair", "2027-01-14", "09:00")
    with pytest.raises(ToolError, match="taken"):
        b.book_appointment("bridal-hair", "2027-01-14", "09:00")


def test_bad_service_id_is_an_error(tools):
    with pytest.raises(ToolError, match="search_services"):
        tools.book_appointment("nails", "2027-01-14", "09:00")


def test_jewish_calendar_combines_both_calls(tools):
    out = tools.check_jewish_calendar("2027-01-15")
    assert "תשפ״ז" in out and "erev shabbat" in out and "yom tov" in out


def test_jewish_calendar_network_failure_is_tool_error(tmp_path):
    def broken(url):
        raise TimeoutError()
    t = SalonTools(tmp_path, "x", today=TODAY, http_get=broken)
    with pytest.raises(ToolError, match="unavailable"):
        t.check_jewish_calendar("2027-01-15")


def test_memory_contradiction_replaces_and_keeps_history(tools):
    assert tools.remember_client_fact("style", "טבעי").startswith("saved")
    assert tools.remember_client_fact("style", "גלאם מעושן").startswith("replaced")
    fact = read_json(tools._memory_path, {})["0501111111"]["style"]
    assert fact["value"] == "גלאם מעושן" and fact["previous"] == ["טבעי"]
    assert "טבעי" not in tools.recall_client()  # history is not sent back to the model


def test_memory_rejects_unknown_key(tools):
    with pytest.raises(ToolError, match="allowed"):
        tools.remember_client_fact("favorite_color", "pink")


def test_memory_is_per_client(tmp_path):
    SalonTools(tmp_path, "a", today=TODAY).remember_client_fact("name", "שרה")
    assert SalonTools(tmp_path, "b", today=TODAY).recall_client().startswith("new client")
