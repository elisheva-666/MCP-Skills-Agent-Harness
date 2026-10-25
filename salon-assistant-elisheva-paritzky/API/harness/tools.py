"""Tool layer: JSON schemas the model sees, and dispatch from a tool_use block to shared/tools.py.

The model never runs code. It returns a tool_use block (name + JSON input); this file
looks up the matching Python function, runs it, and wraps the outcome as a tool_result.
Any failure becomes is_error=True with a readable message, never a crash of the loop.
"""
from shared.tools import MEMORY_KEYS, SalonTools, ToolError

from API.harness.trace import log

SRC = "tools.py"

DATE = {"type": "string", "description": "YYYY-MM-DD"}


def _schema(name: str, description: str, properties: dict) -> dict:
    # strict=True makes the API guarantee the input matches the schema exactly.
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }


TOOL_SCHEMAS = [
    _schema("search_services",
            "Search the salon's services, courses and prices. Returns one line per service: "
            "id | name | price | duration | description.",
            {"query": {"type": "string", "description": "Hebrew keywords, e.g. 'איפור כלה'"}}),
    _schema("find_gallery_images",
            "Pick photos of past work from the gallery by tags. Returns 'file | description' lines. "
            "Use when the client wants to see examples.",
            {"tags": {"type": "array", "items": {"type": "string"},
                      "description": "Hebrew tags, e.g. ['אסוף', 'כלה']"}}),
    _schema("check_availability",
            "Free appointment slots on a date.",
            {"date": DATE}),
    _schema("book_appointment",
            "Book a slot for the current client. If she already has a booking it is moved, not duplicated.",
            {"service_id": {"type": "string", "description": "id from search_services"},
             "date": DATE,
             "time": {"type": "string", "description": "HH:MM, one of the free slots"}}),
    _schema("check_jewish_calendar",
            "Hebrew date and whether a date is Shabbat, erev Shabbat or a holiday (live, from Hebcal). "
            "Check before booking an event date.",
            {"date": DATE}),
    _schema("remember_client_fact",
            "Save a lasting fact about the current client for future visits. A new value replaces the old one.",
            {"key": {"type": "string", "enum": MEMORY_KEYS},
             "value": {"type": "string"}}),
]


class ToolBox:
    """Runs tool_use blocks against one client's SalonTools."""

    def __init__(self, salon: SalonTools):
        self.salon = salon
        self.handlers = {
            "search_services": lambda a: salon.search_services(a["query"]),
            "find_gallery_images": lambda a: salon.find_gallery_images(a["tags"]),
            "check_availability": lambda a: salon.check_availability(a["date"]),
            "book_appointment": lambda a: salon.book_appointment(a["service_id"], a["date"], a["time"]),
            "check_jewish_calendar": lambda a: salon.check_jewish_calendar(a["date"]),
            "remember_client_fact": lambda a: salon.remember_client_fact(a["key"], a["value"]),
        }
        self.calls: list[str] = []          # tool names used this turn, for measurement
        self.shown_images: list[str] = []   # gallery files the UI should display

    def start_turn(self) -> None:
        self.calls, self.shown_images = [], []

    def run(self, block: dict) -> dict:
        """One tool_use block in, one tool_result block out."""
        name, args = block["name"], block["input"]
        self.calls.append(name)
        handler = self.handlers.get(name)
        try:
            if handler is None:
                raise ToolError(f"unknown tool '{name}'")
            content, is_error = handler(args), False
        except ToolError as e:
            content, is_error = str(e), True
        except Exception as e:  # a bug in a tool must not kill the conversation
            content, is_error = f"internal error: {type(e).__name__}", True

        if name == "find_gallery_images" and not is_error:
            self.shown_images += [line.split(" | ")[0] for line in content.splitlines() if " | " in line]

        log(SRC, f"{name}({_short(args)}) -> {'ERROR ' if is_error else ''}{_short(content)}")
        result = {"type": "tool_result", "tool_use_id": block["id"], "content": content}
        if is_error:
            result["is_error"] = True
        return result


def _short(value, limit: int = 70) -> str:
    text = str(value).replace("\n", " / ")
    return text if len(text) <= limit else text[:limit] + "…"
