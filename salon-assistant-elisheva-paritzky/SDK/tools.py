"""The same shared tools, exposed to Claude Code as an in-process MCP server."""
from claude_agent_sdk import create_sdk_mcp_server, tool

from shared.tools import MEMORY_KEYS, SalonTools, ToolError

SERVER = "salon"


def _obj(**props) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


DATE = {"type": "string", "description": "YYYY-MM-DD"}


class Recorder:
    """Collects tool names and shown images per turn, for measurement."""

    def __init__(self):
        self.calls, self.images = [], []


def build_server(salon: SalonTools, rec: Recorder):
    def wrap(name, fn):
        async def handler(args):
            rec.calls.append(name)
            try:
                text = fn(args)  # replaces: tools (dispatch)
            except ToolError as e:
                return {"content": [{"type": "text", "text": str(e)}], "is_error": True}  # replaces: tools (is_error)
            if name == "find_gallery_images":
                rec.images += [ln.split(" | ")[0] for ln in text.splitlines() if " | " in ln]
            return {"content": [{"type": "text", "text": text}]}
        return handler

    specs = [  # replaces: tools (schemas)
        ("search_services", "Search the salon's services, courses and prices. One line per service.",
         _obj(query={"type": "string"}), lambda a: salon.search_services(a["query"])),
        ("find_gallery_images", "Pick photos of past work by Hebrew tags. Returns 'file | description' lines.",
         _obj(tags={"type": "array", "items": {"type": "string"}}), lambda a: salon.find_gallery_images(a["tags"])),
        ("check_availability", "Free appointment slots on a date.",
         _obj(date=DATE), lambda a: salon.check_availability(a["date"])),
        ("book_appointment", "Book a slot for the current client; an existing booking is moved, not duplicated.",
         _obj(service_id={"type": "string"}, date=DATE, time={"type": "string"}),
         lambda a: salon.book_appointment(a["service_id"], a["date"], a["time"])),
        ("check_jewish_calendar", "Hebrew date and Shabbat/holiday status of a date (live, Hebcal).",
         _obj(date=DATE), lambda a: salon.check_jewish_calendar(a["date"])),
        ("remember_client_fact", "Save a lasting fact about the current client. A new value replaces the old one.",
         _obj(key={"type": "string", "enum": MEMORY_KEYS}, value={"type": "string"}),
         lambda a: salon.remember_client_fact(a["key"], a["value"])),
        ("recall_client", "What we remember about the current client and her booking. Call at the start of a chat.",
         _obj(), lambda a: salon.recall_client()),  # replaces: memory (retrieval)
    ]
    tools = [tool(name, desc, schema)(wrap(name, fn)) for name, desc, schema, fn in specs]
    server = create_sdk_mcp_server(SERVER, tools=tools)  # replaces: tools
    allowed = [f"mcp__{SERVER}__{name}" for name, *_ in specs]
    return server, allowed, tools
