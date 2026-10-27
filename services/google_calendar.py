"""Google Calendar OAuth connection flow and encrypted per-user token storage."""

import hmac
import json
import logging
from functools import wraps
from typing import Optional

from bson import ObjectId
from cryptography.fernet import Fernet, InvalidToken
from flask import Blueprint, abort, jsonify, redirect, request, session, url_for
from google_auth_oauthlib.flow import Flow

from config import Config
from db import get_db, oid, utcnow

log = logging.getLogger(__name__)
google_calendar_bp = Blueprint("google_calendar", __name__)

CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


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
