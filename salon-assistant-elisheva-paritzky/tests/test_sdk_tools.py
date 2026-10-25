"""Offline tests for the SDK tool wrappers: call the handlers directly, no Claude Code process."""
import asyncio
from datetime import date

from shared.tools import SalonTools

from SDK.tools import Recorder, build_server

TODAY = date(2026, 10, 25)


def build(tmp_path):
    rec = Recorder()
    _, allowed, tools = build_server(SalonTools(tmp_path, "c1", today=TODAY), rec)
    return {t.name: t.handler for t in tools}, allowed, rec


def call(handler, args):
    return asyncio.run(handler(args))


def test_allowed_tools_are_namespaced(tmp_path):
    _, allowed, _ = build(tmp_path)
    assert "mcp__salon__search_services" in allowed and len(allowed) == 7


def test_handler_success_and_is_error(tmp_path):
    tools, _, rec = build(tmp_path)
    ok = call(tools["search_services"], {"query": "פאות"})
    assert "wig-course" in ok["content"][0]["text"] and "is_error" not in ok
    bad = call(tools["book_appointment"], {"service_id": "x", "date": "2027-01-07", "time": "11:00"})
    assert bad["is_error"] is True
    assert rec.calls == ["search_services", "book_appointment"]


def test_gallery_handler_records_images(tmp_path):
    tools, _, rec = build(tmp_path)
    call(tools["find_gallery_images"], {"tags": ["אסוף", "כלה"]})
    assert rec.images[0] == "img_0577.jpg"


def test_recall_client_tool_reads_shared_memory(tmp_path):
    SalonTools(tmp_path, "c1", today=TODAY).remember_client_fact("name", "שירה")
    tools, _, _ = build(tmp_path)
    assert "name: שירה" in call(tools["recall_client"], {})["content"][0]["text"]
