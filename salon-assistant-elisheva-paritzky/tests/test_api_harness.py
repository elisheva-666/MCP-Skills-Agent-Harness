"""Offline tests for the API harness, using FakeClient instead of the real API."""
from datetime import date

from shared import scenario as sc
from shared.store import read_json
from shared.tools import SalonTools

from API.agent import SalonAgent
from API.harness import caching, compaction, tokens
from API.harness.history import History
from API.harness.loop import run_turn
from API.harness.tools import ToolBox
from tests.fakes import FakeClient, response, text, tool_use

TODAY = date(2026, 10, 25)


def fake_hebcal(url):
    return {"hebrew": "ז׳ בִּשְׁבָט"} if "converter" in url else {"items": []}


def toolbox(tmp_path):
    return ToolBox(SalonTools(tmp_path, "c1", today=TODAY, http_get=fake_hebcal))


def sys_prompt():
    return [{"type": "text", "text": "rules"}]


def test_loop_runs_tools_until_end_turn(tmp_path):
    client = FakeClient(
        response(tool_use("t1", "search_services", {"query": "כלה"}), stop="tool_use"),
        response(text("יש לנו איפור כלה")),
    )
    messages = [{"role": "user", "content": "מה יש לכלות?"}]
    result = run_turn(client, toolbox(tmp_path), sys_prompt(), messages)

    assert result.text == "יש לנו איפור כלה"
    assert len(client.requests) == 2
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[2]["content"][0]["tool_use_id"] == "t1"
    assert "bridal-makeup" in messages[2]["content"][0]["content"]


def test_parallel_tool_results_go_back_in_one_message(tmp_path):
    client = FakeClient(
        response(tool_use("a", "check_availability", {"date": "2027-01-07"}),
                 tool_use("b", "check_jewish_calendar", {"date": "2027-01-07"}), stop="tool_use"),
        response(text("פנוי")),
    )
    messages = [{"role": "user", "content": "פנוי ב-7.1?"}]
    result = run_turn(client, toolbox(tmp_path), sys_prompt(), messages)
    results = messages[2]["content"]
    assert [r["tool_use_id"] for r in results] == ["a", "b"]
    assert result.tools_called == ["check_availability", "check_jewish_calendar"]


def test_tool_error_returns_is_error_and_loop_continues(tmp_path):
    client = FakeClient(
        response(tool_use("t1", "book_appointment",
                          {"service_id": "nails", "date": "2027-01-07", "time": "11:00"}), stop="tool_use"),
        response(text("אין שירות כזה")),
    )
    messages = [{"role": "user", "content": "ציפורניים"}]
    run_turn(client, toolbox(tmp_path), sys_prompt(), messages)
    result = messages[2]["content"][0]
    assert result["is_error"] is True and "search_services" in result["content"]


def test_unknown_tool_is_error_not_crash(tmp_path):
    client = FakeClient(response(tool_use("t1", "rm_rf", {}), stop="tool_use"), response(text("ok")))
    messages = [{"role": "user", "content": "x"}]
    run_turn(client, toolbox(tmp_path), sys_prompt(), messages)
    assert messages[2]["content"][0]["is_error"] is True


def test_request_uses_model_effort_and_fallbacks(tmp_path):
    client = FakeClient(response(text("שלום")))
    run_turn(client, toolbox(tmp_path), sys_prompt(), [{"role": "user", "content": "היי"}])
    req = client.requests[0]
    assert req["model"] == "claude-opus-5-5"
    assert req["output_config"] == {"effort": "medium"}
    assert req["fallbacks"] == "default"


def test_gallery_images_are_collected(tmp_path):
    client = FakeClient(
        response(tool_use("t1", "find_gallery_images", {"tags": ["אסוף", "כלה"]}), stop="tool_use"),
        response(text("הנה")),
    )
    result = run_turn(client, toolbox(tmp_path), sys_prompt(), [{"role": "user", "content": "דוגמאות"}])
    assert result.images[0] == "img_0577.jpg"


def test_caching_marks_system_and_last_message_without_touching_originals():
    system = sys_prompt()
    messages = [{"role": "user", "content": "a"}, {"role": "assistant", "content": [{"type": "text", "text": "b"}]}]
    cs, cm = caching.with_breakpoints(system, messages)
    assert cs[-1]["cache_control"] == {"type": "ephemeral"}
    assert cm[-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in system[-1] and "cache_control" not in messages[-1]["content"][-1]


def test_cache_breakpoints_sent_on_every_call(tmp_path):
    client = FakeClient(
        response(tool_use("t1", "search_services", {"query": "קורס"}), stop="tool_use"),
        response(text("יש")),
    )
    run_turn(client, toolbox(tmp_path), sys_prompt(), [{"role": "user", "content": "קורסים?"}])
    for req in client.requests:
        assert req["system"][-1]["cache_control"]
        assert req["messages"][-1]["content"][-1]["cache_control"]


def test_tokens_cost_and_cache_pct():
    r = response(text("x"), input=1000, cache_read=9000, cache_write=0, output=500)
    u = tokens.turn_usage([r])
    assert u["cost_usd"] == round((1000 * 4 + 9000 * 0.2 + 500 * 20) / 1e6, 6)
    assert u["cache_hit_pct"] == 90.0 and u["model_calls"] == 1


def test_history_is_append_only_and_survives_restart(tmp_path):
    h = History(tmp_path, "s1")
    h.append({"role": "user", "content": "1"})
    h.append({"role": "assistant", "content": "2"})
    assert len(History(tmp_path, "s1").load()) == 2


def test_compaction_over_threshold_summarizes_and_keeps_old_lines(tmp_path):
    h = History(tmp_path, "s1")
    old = [{"role": "user", "content": "שאלה"}, {"role": "assistant", "content": "תשובה"}]
    for m in old:
        h.append(m)
    client = FakeClient(response(text("שירה, חתונה ב-14.1")))
    messages, resp = compaction.maybe_compact(client, list(old), 50_000, h, threshold=1000)
    assert resp is not None and len(messages) == 1 and "14.1" in messages[0]["content"]
    assert len(h.path.read_text(encoding="utf-8").splitlines()) == 3  # nothing deleted
    assert History(tmp_path, "s1").load() == messages


def test_compaction_under_threshold_does_nothing(tmp_path):
    messages, resp = compaction.maybe_compact(FakeClient(), [{"role": "user", "content": "x"}], 10, History(tmp_path, "s"))
    assert resp is None


def test_session2_new_instance_gets_memory_in_context(tmp_path):
    s1 = SalonAgent(FakeClient(
        response(tool_use("t1", "remember_client_fact", {"key": "style", "value": "טבעי"}), stop="tool_use"),
        response(text("רשמתי")),
    ), tmp_path, "c1", "s1", today=TODAY, http_get=fake_hebcal)
    s1.ask("אני אוהבת טבעי")

    client2 = FakeClient(response(text("את אוהבת טבעי")))
    s2 = SalonAgent(client2, tmp_path, "c1", "s2", today=TODAY, http_get=fake_hebcal)
    rec = s2.ask("מה אני אוהבת?")
    sent = client2.requests[0]["messages"]
    assert len(sent) == 1  # new conversation...
    assert "style: טבעי" in sent[0]["content"][0]["text"]  # ...but memory came from disk
    assert rec["model_calls"] == 1 and rec["tools"] == []


def test_scenario_checks_read_saved_state(tmp_path):
    salon = SalonTools(tmp_path, "c1", today=TODAY)
    salon.remember_client_fact("style", "טבעי")
    salon.remember_client_fact("style", "גלאם")
    salon.book_appointment("consultation", "2027-01-14", "11:00")
    scen = {"client_id": "c1", "checks": [
        {"id": "a", "type": "memory_contains", "key": "style", "any": ["גלאם"], "description": ""},
        {"id": "b", "type": "memory_previous_contains", "key": "style", "any": ["טבעי"], "description": ""},
        {"id": "c", "type": "booking", "count": 1, "date": "2027-01-14", "time": "11:00", "description": ""},
        {"id": "d", "type": "tool_called", "tool": "check_jewish_calendar", "description": ""},
    ]}
    turns = [{"session": "s1", "turn": 1, "tools": ["search_services"], "images": [], "reply": ""}]
    passed = {c["id"]: c["passed"] for c in sc.run_checks(scen, tmp_path, turns)}
    assert passed == {"a": True, "b": True, "c": True, "d": False}
    assert read_json(tmp_path / "bookings.json", [])[0]["service_id"] == "consultation"
