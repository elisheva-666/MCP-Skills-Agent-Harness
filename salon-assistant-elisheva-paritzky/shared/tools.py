"""Domain tools for the salon assistant, shared by the API and SDK versions.

Plain Python with no knowledge of Claude: each method takes simple arguments and
returns a short text string. Bad input raises ToolError; each harness turns that
into an is_error tool result so the model can correct itself.

Outputs are deliberately compact (one line per item, no JSON) because every
character returned here is billed as input tokens on the next model call.
"""
import json
import ssl
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

import truststore

from shared import config
from shared.store import read_json, write_json

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
MEMORY_KEYS = ["name", "event_type", "event_date", "style", "liked_image", "notes"]


class ToolError(Exception):
    """Invalid input or a failed lookup. The message is shown to the model."""


# Verify TLS with the OS certificate store, not Python's bundle. Needed on machines where
# antivirus/network filters inject a certificate that Windows trusts but Python 3.13+ rejects.
_TLS = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def _http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "salon-assistant/1.0"})
    with urllib.request.urlopen(req, timeout=8, context=_TLS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ToolError(f"bad date '{value}', use YYYY-MM-DD")


def _matches(token: str, text: str) -> bool:
    # Hebrew glues one-letter prefixes to words (ה, ל, ו, ב...), so also try without the first letter.
    return token in text or (len(token) > 3 and token[1:] in text)


class SalonTools:
    """All tools for one client, bound to one state folder.

    client_id comes from the harness (e.g. the visitor's phone), never from the
    model, so the model cannot read or change another client's data.
    """

    def __init__(self, state_dir: Path, client_id: str,
                 business_dir: Path = config.BUSINESS_DIR,
                 today: date | None = None, http_get=_http_get_json):
        self.state_dir = Path(state_dir)
        self.client_id = client_id
        self.business_dir = Path(business_dir)
        self.today = today or date.today()
        self.http_get = http_get
        self.business = read_json(self.business_dir / "business.json", {})
        self.services = read_json(self.business_dir / "services.json", {}).get("services", [])
        self.gallery = read_json(self.business_dir / "gallery.json", {}).get("images", [])

    @property
    def _bookings_path(self) -> Path:
        return self.state_dir / "bookings.json"

    @property
    def _memory_path(self) -> Path:
        return self.state_dir / "memory.json"

    # ---- catalog -------------------------------------------------------------

    def search_services(self, query: str) -> str:
        tokens = [t for t in query.lower().split() if t]
        scored = []
        for s in self.services:
            text = " ".join([s["name"], s["category"], s["description"], *s["tags"]]).lower()
            scored.append((sum(_matches(t, text) for t in tokens), s))
        # Keep only the best-matching services: "איפור כלה" should not return every makeup service.
        best = max(score for score, _ in scored)
        hits = [s for score, s in scored if score == best] if tokens and best else []
        if not tokens:
            hits = self.services
        if not hits:
            cats = sorted({s["category"] for s in self.services})
            return f"no match for '{query}'. categories: {', '.join(cats)}"
        lines = []
        for s in hits:
            price = {None: "price on request", 0: "free"}.get(s["price"], f"{s['price']}₪")
            lines.append(f"{s['id']} | {s['name']} | {price} | {s.get('length') or '-'} | {s['description']}")
        return "\n".join(lines)

    def business_info(self) -> str:
        """One compact block about the business, for the system prompt."""
        b = self.business
        return (f"{b.get('name')} | {b.get('area')} | {b.get('address')}\n"
                f"phone {b.get('phone')} | info line {b.get('info_line')} | {b.get('email')}\n"
                f"{b.get('about')}\npricing: {b.get('pricing_policy')}")

    # ---- gallery -------------------------------------------------------------

    def find_gallery_images(self, tags: list[str], limit: int = 3) -> str:
        if not tags:
            raise ToolError("give at least one tag")
        wanted = {t.strip() for t in tags if t.strip()}
        scored = []
        for img in self.gallery:
            score = len(wanted & set(img["tags"]))
            if score:
                scored.append((score, img))
        if not scored:
            known = sorted({t for img in self.gallery for t in img["tags"]})
            return f"no images for {sorted(wanted)}. known tags: {', '.join(known)}"
        scored.sort(key=lambda pair: -pair[0])
        return "\n".join(f"{img['file']} | {img['description']}" for _, img in scored[:limit])

    def image_path(self, file: str) -> Path:
        """Full path of a gallery image, for harnesses that display or attach it."""
        return self.business_dir / "images" / file

    # ---- calendar ------------------------------------------------------------

    def _slots(self, day: date) -> list[str]:
        return self.business.get("slots_by_weekday", {}).get(WEEKDAYS[day.weekday()], [])

    def check_availability(self, date_str: str) -> str:
        day = _parse_date(date_str)
        if day < self.today:
            raise ToolError(f"{date_str} is in the past (today is {self.today})")
        slots = self._slots(day)
        weekday = WEEKDAYS[day.weekday()]
        if not slots:
            return f"{date_str} ({weekday}): closed"
        taken = {b["time"] for b in read_json(self._bookings_path, []) if b["date"] == date_str}
        free = [s for s in slots if s not in taken]
        return f"{date_str} ({weekday}): free {', '.join(free) or 'none'}"

    def book_appointment(self, service_id: str, date_str: str, time: str) -> str:
        """Book a slot. A client has at most one booking: booking again moves it."""
        service = next((s for s in self.services if s["id"] == service_id), None)
        if not service:
            raise ToolError(f"unknown service_id '{service_id}'. use search_services")
        day = _parse_date(date_str)
        if day < self.today:
            raise ToolError(f"{date_str} is in the past")
        if time not in self._slots(day):
            raise ToolError(f"{time} is not a slot on {date_str}. use check_availability")

        bookings = read_json(self._bookings_path, [])
        mine = next((b for b in bookings if b["client_id"] == self.client_id), None)
        if any(b["date"] == date_str and b["time"] == time and b is not mine for b in bookings):
            raise ToolError(f"{date_str} {time} is taken")

        new = {"client_id": self.client_id, "service_id": service_id, "date": date_str, "time": time}
        if mine:
            bookings.remove(mine)
        bookings.append(new)
        write_json(self._bookings_path, bookings)
        if mine:
            return f"moved: {service['name']} from {mine['date']} {mine['time']} to {date_str} {time}"
        return f"booked: {service['name']} on {date_str} {time}"

    def current_booking(self) -> str:
        b = next((b for b in read_json(self._bookings_path, []) if b["client_id"] == self.client_id), None)
        return f"{b['service_id']} on {b['date']} {b['time']}" if b else "none"

    # ---- external: Hebcal ----------------------------------------------------

    def check_jewish_calendar(self, date_str: str) -> str:
        day = _parse_date(date_str)
        q = urllib.parse.urlencode
        try:
            conv = self.http_get("https://www.hebcal.com/converter?" + q(
                {"cfg": "json", "date": date_str, "g2h": 1, "strict": 1}))
            hol = self.http_get("https://www.hebcal.com/hebcal?" + q(
                {"cfg": "json", "v": 1, "maj": "on", "min": "on", "mod": "on", "i": "on",
                 "lg": "he", "start": date_str, "end": date_str}))
        except Exception as e:
            raise ToolError(f"calendar service unavailable: {type(e).__name__}")

        parts = [f"{date_str}", conv.get("hebrew", "?")]
        weekday = WEEKDAYS[day.weekday()]
        if weekday == "sat":
            parts.append("SHABBAT")
        elif weekday == "fri":
            parts.append("erev shabbat")
        for item in hol.get("items", []):
            if item.get("category") == "holiday":
                parts.append(item["title"] + (" (yom tov)" if item.get("yomtov") else ""))
        return " | ".join(parts)

    # ---- memory --------------------------------------------------------------

    def remember_client_fact(self, key: str, value: str) -> str:
        """Upsert one fact. A new value replaces the old one; the old one is kept as history."""
        if key not in MEMORY_KEYS:
            raise ToolError(f"unknown key '{key}'. allowed: {', '.join(MEMORY_KEYS)}")
        memory = read_json(self._memory_path, {})
        facts = memory.setdefault(self.client_id, {})
        old = facts.get(key)
        if old and old["value"] == value:
            return f"unchanged: {key}={value}"
        facts[key] = {
            "value": value,
            "updated": self.today.isoformat(),
            "previous": ([old["value"]] + old.get("previous", [])) if old else [],
        }
        write_json(self._memory_path, memory)
        return f"replaced: {key} {old['value']} -> {value}" if old else f"saved: {key}={value}"

    def recall_client(self) -> str:
        """Compact profile: current facts only (not history) plus the booking."""
        facts = read_json(self._memory_path, {}).get(self.client_id, {})
        lines = [f"{k}: {v['value']}" for k, v in facts.items()]
        lines.append(f"booking: {self.current_booking()}")
        return "\n".join(lines) if facts else f"new client\nbooking: {self.current_booking()}"
