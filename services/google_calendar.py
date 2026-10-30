"""Google Calendar OAuth connection flow and encrypted per-user token storage."""

import hmac
import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from datetime import date, datetime, time, timedelta
from typing import Optional

from bson import ObjectId
from cryptography.fernet import Fernet, InvalidToken
from flask import Blueprint, abort, jsonify, redirect, request, session, url_for
from google_auth_oauthlib.flow import Flow
import requests

from config import Config
from db import get_db, oid, utcnow
from services import tabular
from services.insights import parse_date

log = logging.getLogger(__name__)
google_calendar_bp = Blueprint("google_calendar", __name__)

CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
_EVENT_TYPES = (
    ("meeting", re.compile(
        r"\b(meeting|appointment|conference|interview|seminar|workshop|conference call)\b", re.I
    )),
    ("travel", re.compile(
        r"\b(travel|trip|journey|flight|departure|arrival|boarding|vacation|holiday|tour)\b", re.I
    )),
    ("family get-together", re.compile(
        r"\b(family\s+(?:get[- ]?together|gathering|reunion|event|celebration)|get[- ]?together)\b",
        re.I,
    )),
    ("validity / expiry", re.compile(
        r"\b(expir\w*|valid(?:ity)?\s+(?:until|till|through|thru|upto|up to)|renew\w*)\b", re.I
    )),
    ("deadline", re.compile(r"\b(deadline|due date|submit by|last date)\b", re.I)),
    ("review", re.compile(r"\b(review|hearing|exam)\b", re.I)),
)
_HIGH_PRIORITY_FIELD_RE = re.compile(
    r"(?:^|[|,;\t])\s*(?:priority\s*[:=]\s*)?high\s*(?:[|,;\t]|$)", re.I
)
_HIGH_PRIORITY_PHRASE_RE = re.compile(r"\bhigh[- ]priority\b", re.I)
_WEEKDAY_RE = re.compile(
    r"^(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)$", re.I
)
_TIME_CELL_RE = re.compile(r"^(?:[01]?\d|2[0-3]):[0-5]\d$")
_TIME_RE = re.compile(
    r"(?<!\d)(?P<hour>0?[1-9]|1[0-2])(?::(?P<minute>[0-5]\d))?\s*"
    r"(?P<ampm>a\.?m\.?|p\.?m\.?)\b|"
    r"(?<!\d)(?P<hour24>[01]?\d|2[0-3]):(?P<minute24>[0-5]\d)(?!\d)",
    re.I,
)


def _fernet():
    if not Config.GOOGLE_TOKEN_ENCRYPTION_KEY:
        return None
    try:
        return Fernet(Config.GOOGLE_TOKEN_ENCRYPTION_KEY.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return None


def is_configured() -> bool:
    return bool(
        Config.GOOGLE_CLIENT_ID
        and Config.GOOGLE_CLIENT_SECRET
        and Config.SECRET_KEY != "change-me-in-.env"
        and _fernet()
    )


def _encrypt_token(token_json: str, key: bytes) -> str:
    return Fernet(key).encrypt(token_json.encode("utf-8")).decode("ascii")


def _decrypt_token(token_ciphertext: str, key: bytes) -> str:
    try:
        return Fernet(key).decrypt(token_ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeEncodeError) as exc:
        raise RuntimeError("Stored Google Calendar credentials could not be decrypted.") from exc


def _parse_time_match(match) -> time:
    if match.group("hour24") is not None:
        return time(int(match.group("hour24")), int(match.group("minute24")))
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    suffix = match.group("ampm").lower().replace(".", "")
    if suffix == "pm" and hour != 12:
        hour += 12
    elif suffix == "am" and hour == 12:
        hour = 0
    return time(hour, minute)


def _high_priority_title(context: str) -> Optional[str]:
    cells = [cell.strip() for cell in re.split(r"[|;\t]", context) if cell.strip()]
    high_index = next(
        (index for index, cell in enumerate(cells)
         if re.fullmatch(r"(?:priority\s*[:=]\s*)?high", cell, re.I)),
        None,
    )
    if high_index is not None:
        candidates = []
        for cell in cells[:high_index]:
            if (
                re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", cell)
                or _WEEKDAY_RE.fullmatch(cell)
                or _TIME_CELL_RE.fullmatch(cell)
            ):
                continue
            if len(cell.split()) >= 3:
                candidates.append(cell)
        if candidates:
            return max(candidates, key=len).strip(" .,-")
        return "High priority task"

    match = re.search(
        r"\bhigh[- ]priority\b\s*[:\-]\s*(?P<title>[^|;\n.]+)",
        context,
        re.I,
    )
    if match:
        title = match.group("title").strip(" ,:-")
        return title or "High priority task"
    if _HIGH_PRIORITY_PHRASE_RE.search(context):
        return "High priority task"
    return None


def _event_type(context: str, label: str, high_priority_title: Optional[str]) -> str:
    if high_priority_title:
        return "high priority task"
    matched_type = next(
        (name for name, pattern in _EVENT_TYPES if pattern.search(context)),
        None,
    )
    if matched_type:
        return matched_type
    return {
        "expiry": "validity / expiry",
        "deadline": "deadline",
        "review": "review",
        "issue": "document date",
        "birth": "birthday",
    }.get(label, "date reminder")


def build_calendar_events(
    document_id: str,
    document_title: str,
    dates: list[dict],
    today: Optional[date] = None,
    schedule_table: Optional[dict] = None,
) -> list[dict]:
    """Build calendar events for every unambiguous date on or after today."""
    today = today or date.today()
    events = []
    seen = set()
    schedule_info = tabular.analyze(schedule_table, today) if schedule_table else None
    is_schedule = bool(schedule_info and tabular.doc_type(schedule_info) == "Schedule")
    if is_schedule:
        date_index = schedule_info["date_col"]["index"]
        task_column = schedule_info["roles"]["task"]
        schedule_items = []
        for row in schedule_info["rows"]:
            event_date, ambiguous = parse_date(row[date_index])
            if not event_date:
                continue
            context = " | ".join(row)
            schedule_items.append({
                "iso": event_date.isoformat(),
                "ambiguous": ambiguous,
                "event_context": context,
                "event_title": row[task_column["index"]],
            })
    else:
        schedule_items = dates

    for item in schedule_items:
        if item.get("ambiguous"):
            continue
        try:
            event_date = date.fromisoformat(item["iso"])
        except (KeyError, TypeError, ValueError):
            continue
        if event_date < today:
            continue

        context = " ".join(str(item.get("event_context") or item.get("context") or "").split())
        high_priority_title = _high_priority_title(context)
        event_type = _event_type(context, str(item.get("label") or ""), high_priority_title)
        identity = f"{document_id}|{event_date.isoformat()}|{event_type}|{context.lower()}"
        if identity in seen:
            continue
        seen.add(identity)

        summary = (
            f"High priority - {high_priority_title}"
            if high_priority_title
            else f"{event_type.title()} - {item.get('event_title') or item.get('context') or context or document_title}".strip(" -")
        )
        event = {
            "id": "a" + hashlib.sha256(identity.encode("utf-8")).hexdigest(),
            "summary": summary[:1000],
            "description": (
                f"Extracted from: {document_title}\n\n{context}"
            )[:8192],
            "source_date": event_date.isoformat(),
            "source_type": event_type,
        }
        time_matches = list(_TIME_RE.finditer(context))
        if time_matches:
            event_time = _parse_time_match(time_matches[0])
            event_end_time = (
                _parse_time_match(time_matches[1])
                if len(time_matches) > 1
                else (datetime.combine(event_date, event_time) + timedelta(hours=1)).time()
            )
            start = datetime.combine(event_date, event_time)
            end = datetime.combine(event_date, event_end_time)
            if end <= start:
                end += timedelta(days=1)
            event["start_local"] = start.isoformat(timespec="minutes")
            event["end_local"] = end.isoformat(timespec="minutes")
        else:
            event["start"] = {"date": event_date.isoformat()}
            event["end"] = {"date": (event_date + timedelta(days=1)).isoformat()}
        events.append(event)
    return events


def _calendar_access_token(user: dict) -> str:
    connection = user.get("google_calendar") or {}
    ciphertext = connection.get("token_encrypted")
    if not ciphertext:
        raise RuntimeError("Google Calendar is not connected.")
    token_data = json.loads(_decrypt_token(
        ciphertext, Config.GOOGLE_TOKEN_ENCRYPTION_KEY.encode("ascii")
    ))
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("Google Calendar refresh token is missing; reconnect Calendar.")
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": Config.GOOGLE_CLIENT_ID,
            "client_secret": Config.GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"Google token refresh failed (HTTP {response.status_code}).")
    refreshed = response.json()
    token_data["token"] = refreshed["access_token"]
    token_data["expiry"] = (
        datetime.utcnow() + timedelta(seconds=int(refreshed.get("expires_in", 3600)))
    ).isoformat() + "Z"
    token_data["refresh_token"] = refreshed.get("refresh_token", refresh_token)
    get_db().users.update_one(
        {"_id": user["_id"]},
        {"$set": {"google_calendar.token_encrypted": _encrypt_token(
            json.dumps(token_data), Config.GOOGLE_TOKEN_ENCRYPTION_KEY.encode("ascii")
        )}},
    )
    return token_data["token"]


def sync_document_events(
    user: dict,
    document_id: str,
    document_title: str,
    dates: list[dict],
    schedule_table: Optional[dict] = None,
    on_event_update=None,
    today: Optional[date] = None,
) -> dict:
    """Create upcoming document-date events in the user's primary calendar."""
    events = build_calendar_events(
        document_id, document_title, dates, today=today, schedule_table=schedule_table,
    )
    if not events:
        return {"status": "no_events", "events": []}
    if not (user.get("google_calendar") or {}).get("token_encrypted"):
        outcomes = [{
            "id": event["id"],
            "title": event["summary"],
            "date": event["source_date"],
            "start_local": event.get("start_local"),
            "end_local": event.get("end_local"),
            "status": "not_connected",
            "message": "Connect Google Calendar to add this event.",
        } for event in events]
        if on_event_update:
            for outcome in outcomes:
                on_event_update(outcome)
        return {"status": "not_connected", "events": outcomes}

    try:
        token = _calendar_access_token(user)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        timed = any("start_local" in event for event in events)
        timezone = None
        if timed:
            calendar_response = requests.get(
                "https://www.googleapis.com/calendar/v3/calendars/primary",
                headers=headers,
                timeout=20,
            )
            calendar_response.raise_for_status()
            timezone = calendar_response.json().get("timeZone")
            if not timezone:
                raise RuntimeError("Could not determine the primary Calendar time zone.")
    except Exception as exc:
        log.error("Google Calendar setup failed (%s)", type(exc).__name__)
        outcomes = [{
            "id": event["id"],
            "title": event["summary"],
            "date": event["source_date"],
            "start_local": event.get("start_local"),
            "end_local": event.get("end_local"),
            "status": "failed",
            "message": str(exc)[:240],
        } for event in events]
        if on_event_update:
            for outcome in outcomes:
                on_event_update(outcome)
        return {"status": "failed", "events": outcomes}

    def insert_event(event):
        payload = {
            "id": event["id"],
            "summary": event["summary"],
            "description": event["description"],
        }
        if "start_local" in event:
            payload["start"] = {"dateTime": event["start_local"], "timeZone": timezone}
            payload["end"] = {"dateTime": event["end_local"], "timeZone": timezone}
        else:
            payload["start"] = event["start"]
            payload["end"] = event["end"]
        try:
            response = requests.post(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                headers=headers,
                json=payload,
                timeout=20,
            )
            if response.status_code == 409:
                status, message = "created", "Already added to Google Calendar."
            elif response.ok:
                status, message = "created", "Added to Google Calendar."
            else:
                status, message = "failed", f"Google Calendar returned HTTP {response.status_code}."
                log.warning("Google Calendar event insert failed (HTTP %s)", response.status_code)
        except requests.RequestException as exc:
            status, message = "failed", f"Google Calendar request failed ({type(exc).__name__})."
            log.error("Google Calendar event insert request failed (%s)", type(exc).__name__)
        outcome = {
            "id": event["id"],
            "title": event["summary"],
            "date": event["source_date"],
            "start_local": event.get("start_local"),
            "end_local": event.get("end_local"),
            "status": status,
            "message": message,
        }
        if on_event_update:
            on_event_update(outcome)
        return outcome

    with ThreadPoolExecutor(max_workers=min(8, len(events))) as executor:
        outcomes = list(executor.map(insert_event, events))

    statuses = {event["status"] for event in outcomes}
    result_status = "created" if statuses == {"created"} else "partial" if "created" in statuses else "failed"
    return {"status": result_status, "events": outcomes}


def _flow(state: str = "", code_verifier: Optional[str] = None) -> Flow:
    client_config = {
        "web": {
            "client_id": Config.GOOGLE_CLIENT_ID,
            "client_secret": Config.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [Config.GOOGLE_REDIRECT_URI],
        }
    }
    return Flow.from_client_config(
        client_config,
        scopes=CALENDAR_SCOPES,
        state=state or None,
        redirect_uri=Config.GOOGLE_REDIRECT_URI,
        code_verifier=code_verifier,
    )


def _current_user():
    user_id = oid(session.get("uid"))
    return get_db().users.find_one({"_id": user_id}) if user_id else None


def _login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not _current_user():
            if request.path.startswith("/api/"):
                return jsonify({"error": "Please sign in again."}), 401
            return redirect(url_for("login_page"))
        return view(*args, **kwargs)
    return wrapper


def _settings_redirect(result: str):
    return redirect(url_for("app_page", google_calendar=result) + "#/settings")


@google_calendar_bp.get("/api/google-calendar/status")
@_login_required
def status():
    user_id = oid(session.get("uid"))
    connection = get_db().users.find_one(
        {"_id": user_id}, {"google_calendar.token_encrypted": 1}
    ) or {}
    return jsonify({
        "configured": is_configured(),
        "connected": bool(
            (connection.get("google_calendar") or {}).get("token_encrypted")
        ),
    })


@google_calendar_bp.get("/google-calendar/connect")
@_login_required
def connect():
    if not is_configured():
        abort(503, "Google Calendar OAuth is not configured on the server.")
    oauth_flow = _flow()
    authorization_url, state = oauth_flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    session["google_calendar_oauth"] = {
        "state": state,
        "code_verifier": oauth_flow.code_verifier,
        "user_id": session["uid"],
    }
    return redirect(authorization_url)


@google_calendar_bp.get("/google-calendar/callback")
@_login_required
def callback():
    pending = session.pop("google_calendar_oauth", None)
    if not pending or pending.get("user_id") != session.get("uid"):
        return _settings_redirect("error")

    expected_state = pending.get("state")
    returned_state = request.args.get("state", "")
    if not isinstance(expected_state, str) or not returned_state or not hmac.compare_digest(
        expected_state, returned_state
    ):
        return _settings_redirect("error")
    if request.args.get("error"):
        log.info("Google Calendar authorization was declined or failed: %s", request.args["error"])
        return _settings_redirect("denied")
    if not is_configured():
        return _settings_redirect("error")
    code_verifier = pending.get("code_verifier")
    if not isinstance(code_verifier, str) or not code_verifier:
        log.error("Google Calendar OAuth callback is missing its PKCE code verifier.")
        return _settings_redirect("error")

    user_id = oid(session.get("uid"))
    user = get_db().users.find_one({"_id": user_id}, {"google_calendar": 1}) or {}
    try:
        oauth_flow = _flow(state=expected_state, code_verifier=code_verifier)
        oauth_flow.fetch_token(authorization_response=request.url)
        credentials = oauth_flow.credentials
        old_connection = user.get("google_calendar") or {}
        old_ciphertext = old_connection.get("token_encrypted")
        if not credentials.refresh_token and old_ciphertext:
            old_token = json.loads(_decrypt_token(
                old_ciphertext, Config.GOOGLE_TOKEN_ENCRYPTION_KEY.encode("ascii")
            ))
            credentials.refresh_token = old_token.get("refresh_token")
        if not credentials.refresh_token:
            log.warning("Google Calendar OAuth completed without a refresh token for user %s", user_id)
            return _settings_redirect("error")

        encrypted = _encrypt_token(
            credentials.to_json(), Config.GOOGLE_TOKEN_ENCRYPTION_KEY.encode("ascii")
        )
        get_db().users.update_one(
            {"_id": user_id},
            {"$set": {
                "google_calendar.token_encrypted": encrypted,
                "google_calendar.connected_at": utcnow(),
            }},
        )
    except Exception as exc:
        log.error(
            "Google Calendar OAuth callback failed for user %s (%s)",
            user_id, type(exc).__name__,
        )
        return _settings_redirect("error")

    return _settings_redirect("connected")


@google_calendar_bp.post("/api/google-calendar/disconnect")
@_login_required
def disconnect():
    user_id: ObjectId = oid(session.get("uid"))
    get_db().users.update_one({"_id": user_id}, {"$unset": {"google_calendar": ""}})
    return jsonify({"ok": True})
