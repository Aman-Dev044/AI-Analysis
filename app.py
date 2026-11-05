"""DocuMind AI — Flask app: auth, uploads, live processing status, summaries and document chat."""

import logging
import mimetypes
import re
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, session, url_for
from pymongo.errors import DuplicateKeyError
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from config import Config
from db import delete_file, get_db, init_db, iso, log_activity, oid, put_file, read_file, recent_activity, utcnow
from services.google_calendar import google_calendar_bp
from services import fields as fields_mod, insights as insights_mod, jobs, ollama_client, summarizer, tabular

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("documind")

app = Flask(__name__)
app.config.from_object(Config)
app.permanent_session_lifetime = timedelta(seconds=Config.PERMANENT_SESSION_LIFETIME)
app.register_blueprint(google_calendar_bp)

INLINE_TYPES = {"application/pdf", "text/plain", "text/csv", "text/markdown",
                "image/png", "image/jpeg", "image/bmp", "image/tiff", "image/webp"}


# ------------------------------------------------------------------ helpers
def api_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def current_user():
    user_id = oid(session.get("uid"))
    if not user_id:
        return None
    return get_db().users.find_one({"_id": user_id})


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            if request.path.startswith("/api/"):
                return api_error("Please sign in again.", 401)
            return redirect(url_for("login_page"))
        return view(user, *args, **kwargs)
    return wrapper


@app.before_request
def csrf_guard():
    # State-changing API calls must come from our own JS (custom header can't be sent cross-site without CORS).
    if request.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("X-Requested-With") != "DocuMind":
            return api_error("Missing request header.", 403)


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


@app.errorhandler(HTTPException)
def http_error(exc):
    if request.path.startswith("/api/"):
        message = exc.description
        if exc.code == 413:
            message = f"File too large. Maximum upload size is {Config.MAX_UPLOAD_MB} MB."
        return api_error(message, exc.code)
    return exc


def public_user(user: dict) -> dict:
    prefs = user.get("prefs") or {}
    return {
        "id": str(user["_id"]), "name": user.get("name", ""), "email": user.get("email", ""),
        "role": user.get("role", "user"), "created_at": iso(user.get("created_at")),
        "prefs": {"mode": prefs.get("mode", Config.DEFAULT_MODE), "language": prefs.get("language", "English"),
                  "length": prefs.get("length", "standard"), "model": prefs.get("model")},
    }


def owned_doc(user, doc_id, projection=None):
    _id = oid(doc_id)
    doc = get_db().documents.find_one({"_id": _id, "user_id": user["_id"]}, projection) if _id else None
    if not doc:
        abort(404, "Document not found")
    return doc


def doc_brief(doc: dict, info: dict = None) -> dict:
    jobs.reap_document(doc)
    state = jobs.document_state(doc)
    filename = doc.get("filename") or "document"
    ext = Path(filename).suffix.lower()
    text = doc.get("text") or ""
    if info is None:
        info = insights_mod.analyze(text, soon_days=Config.EXPIRING_SOON_DAYS) \
            if text and state.get("status") in {"ready", "failed"} else {}
    expiry_date = doc.get("expiry_date")
    expiry_text = doc.get("expiry_text")
    if not expiry_date:
        computed_expiry = info.get("expiry") or {}
        expiry_date = computed_expiry.get("date")
        expiry_text = expiry_text or computed_expiry.get("text")
    expiry = {"date": expiry_date, "text": expiry_text} if expiry_date and expiry_text else None
    if expiry and expiry.get("date"):
        expiry_date = expiry["date"]
        if isinstance(expiry_date, datetime):
            expiry_date = expiry_date.date()
        elif not isinstance(expiry_date, date):
            expiry_date = date.fromisoformat(str(expiry_date)[:10])
        days = (expiry_date - date.today()).days
        ambiguous = bool((info.get("expiry") or {}).get("ambiguous"))
        expiry = {
            "date": expiry_date.isoformat(), "text": expiry["text"], "days_remaining": days,
            "status": "verify" if ambiguous else "expired" if days < 0 else
                      "expiring_soon" if days <= Config.EXPIRING_SOON_DAYS else "valid",
            "ambiguous": ambiguous,
        }
    title = Path(filename).stem
    status = state.get("status")
    return {
        "id": str(doc["_id"]),
        "title": title,
        "filename": filename,
        "ext": ext,
        "size": doc.get("size", 0),
        "status": status,
        "stage": state.get("stage", status),
        "progress": state.get("progress", 100 if status == "ready" else 0),
        "stage_message": state.get("stage_message"),
        "error": state.get("error"),
        "doc_type": info.get("doc_type"),
        "pages": None,
        "word_count": (info.get("stats") or {}).get("words"),
        "reading_minutes": (info.get("stats") or {}).get("reading_minutes"),
        "ocr_used": bool(doc.get("ocr_engine")),
        "ocr_engine": doc.get("ocr_engine"),
        "is_plan": bool(text and jobs.plan_for(text)),
        "expiry": expiry,
        "summary_failed": state.get("summary_failed", False),
        "auto_summary_id": str(state["auto_summary_id"]) if state.get("auto_summary_id") else None,
        "uploaded_at": iso(doc.get("uploaded_at")),
        "updated_at": iso(doc.get("updated_at")),
    }


def summary_out(s: dict) -> dict:
    jobs.reap_summary(s)
    return {
        "id": str(s["_id"]), "document_id": str(s["document_id"]), "mode": s.get("mode"),
        "mode_label": summarizer.MODES.get(s.get("mode"), {}).get("label", s.get("mode")),
        "length": s.get("length"), "language": s.get("language"), "instructions": s.get("instructions"),
        "model": s.get("model"), "status": s.get("status"), "progress": s.get("progress", 0),
        "stage_message": s.get("stage_message"), "content": s.get("content", ""), "error": s.get("error"),
        "duration_ms": s.get("duration_ms"), "created_at": iso(s.get("created_at")),
    }


def chat_out(m: dict) -> dict:
    return {"id": str(m["_id"]), "role": m["role"], "content": m.get("content", ""),
            "status": m.get("status"), "error": m.get("error"), "created_at": iso(m.get("created_at"))}


def calendar_status(events: list[dict]) -> str:
    statuses = {event.get("status") for event in events}
    if not statuses:
        return "no_events"
    if "pending" in statuses:
        return "pending"
    if "failed" in statuses and "created" in statuses:
        return "partial"
    if "failed" in statuses:
        return "failed"
    if "not_connected" in statuses:
        return "not_connected"
    return "created"


# ------------------------------------------------------------------ pages
@app.get("/")
def index():
    return redirect(url_for("app_page") if current_user() else url_for("login_page"))


@app.get("/login")
def login_page():
    if current_user():
        return redirect(url_for("app_page"))
    return render_template("login.html", seed_email=Config.SEED_ADMIN_EMAIL)


@app.get("/app")
@login_required
def app_page(user):
    return render_template("app.html", user=public_user(user))


# ------------------------------------------------------------------ auth api
@app.post("/api/auth/signup")
def signup():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if len(name) < 2:
        return api_error("Please enter your name.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return api_error("Please enter a valid email address.")
    if len(password) < 6:
        return api_error("Password must be at least 6 characters.")
    try:
        user_id = get_db().users.insert_one({
            "name": name, "email": email, "password_hash": generate_password_hash(password),
            "role": "user", "prefs": {"mode": Config.DEFAULT_MODE, "language": "English", "length": "standard"},
            "created_at": utcnow(),
        }).inserted_id
    except DuplicateKeyError:
        return api_error("This email is already registered. Please sign in.", 409)
    session.permanent = True
    session["uid"] = str(user_id)
    log_activity(user_id, "signup", "Created an account")
    return jsonify({"ok": True})


@app.post("/api/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    user = get_db().users.find_one({"email": email})
    if not user or not check_password_hash(user["password_hash"], data.get("password") or ""):
        return api_error("Invalid email or password.", 401)
    session.clear()
    session.permanent = bool(data.get("remember", True))
    session["uid"] = str(user["_id"])
    log_activity(user["_id"], "login", "Signed in")
    return jsonify({"ok": True})


@app.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/auth/me")
@login_required
def me(user):
    return jsonify(public_user(user))


@app.put("/api/auth/me")
@login_required
def update_me(user):
    data = request.get_json(silent=True) or {}
    updates = {}
    if (data.get("name") or "").strip():
        updates["name"] = data["name"].strip()[:80]
    prefs = dict(user.get("prefs") or {})
    if data.get("mode") in summarizer.MODES:
        prefs["mode"] = data["mode"]
    if data.get("language") in summarizer.LANGUAGES:
        prefs["language"] = data["language"]
    if data.get("length") in summarizer.LENGTHS:
        prefs["length"] = data["length"]
    if "model" in data:
        prefs["model"] = (data.get("model") or "").strip() or None
    updates["prefs"] = prefs
    if data.get("new_password"):
        if not check_password_hash(user["password_hash"], data.get("current_password") or ""):
            return api_error("Current password is incorrect.")
        if len(data["new_password"]) < 6:
            return api_error("New password must be at least 6 characters.")
        updates["password_hash"] = generate_password_hash(data["new_password"])
    get_db().users.update_one({"_id": user["_id"]}, {"$set": updates})
    log_activity(user["_id"], "settings", "Updated profile / preferences")
    return jsonify(public_user(get_db().users.find_one({"_id": user["_id"]})))


# ------------------------------------------------------------------ meta
@app.get("/api/meta")
@login_required
def meta(user):
    return jsonify({
        "modes": [{"key": k, **{f: v[f] for f in ("label", "icon", "desc")}} for k, v in summarizer.MODES.items()],
        "lengths": list(summarizer.LENGTHS),
        "languages": summarizer.LANGUAGES,
        "extensions": sorted(Config.ALLOWED_EXTENSIONS),
        "max_upload_mb": Config.MAX_UPLOAD_MB,
        "default_model": Config.OLLAMA_MODEL,
    })


@app.get("/api/ollama/health")
@login_required
def ollama_health(user):
    if Config.AI_BACKEND == "rules":
        return jsonify({"ok": True, "backend": "rules", "models": [], "default_model": "Offline engine"})
    return jsonify(ollama_client.health())


# ------------------------------------------------------------------ dashboard
@app.get("/api/dashboard")
@login_required
def dashboard(user):
    db = get_db()
    uid = user["_id"]
    docs = db.documents.find({"user_id": uid}).sort("uploaded_at", -1)
    week_ago = utcnow() - timedelta(days=7)
    document_count = db.documents.count_documents({"user_id": uid})
    summaries_total = db.summaries.count_documents({"user_id": uid, "status": "done"})

    alerts, upcoming, recent, by_type = [], [], [], {}
    ready_count = processing_count = failed_count = words_count = this_week = 0
    plan = None
    for d in docs:
        info = insights_mod.analyze(d.get("text") or "", soon_days=Config.EXPIRING_SOON_DAYS) \
            if d.get("text") else {}
        brief = doc_brief(d, info)
        if len(recent) < 6:
            recent.append(brief)
        state = jobs.document_state(d)
        if state.get("status") == "ready":
            ready_count += 1
        elif state.get("status") == "failed":
            failed_count += 1
        else:
            processing_count += 1
        words_count += (info.get("stats") or {}).get("words", 0)
        if d.get("uploaded_at") and d["uploaded_at"] >= week_ago:
            this_week += 1
        if info.get("doc_type"):
            by_type[info["doc_type"]] = by_type.get(info["doc_type"], 0) + 1
        if not plan and d.get("text"):
            details = jobs.plan_for(d["text"])
            if details:
                plan = {"document_id": str(d["_id"]), "title": brief["title"], **details}
        exp = brief.get("expiry")
        if exp and exp.get("status") in {"expired", "expiring_soon", "verify"}:
            alerts.append({"document": brief, **exp})
        for item in info.get("upcoming", []):
            upcoming.append({**item, "document_id": str(d["_id"]), "document_title": brief["title"]})
    alerts.sort(key=lambda a: a.get("days_remaining", 0))
    upcoming.sort(key=lambda u: u["iso"])

    activity = recent_activity(user, 8)

    return jsonify({
        "user": public_user(user),
        "stats": {
            "documents": document_count,
            "ready": ready_count,
            "processing": processing_count,
            "failed": failed_count,
            "summaries": summaries_total,
            "words": words_count,
            "this_week": this_week,
        },
        "by_type": sorted(({"type": k, "count": v} for k, v in by_type.items()), key=lambda x: -x["count"]),
        "recent": recent,
        "alerts": alerts[:10],
        "upcoming": upcoming[:12],
        "plan": plan,
        "activity": activity,
    })


@app.get("/api/activity")
@login_required
def activity_list(user):
    limit = max(1, min(request.args.get("limit", 50, type=int), 100))
    return jsonify(recent_activity(user, limit))


# ------------------------------------------------------------------ documents
@app.post("/api/documents")
@login_required
def upload(user):
    files = request.files.getlist("files") or request.files.getlist("file")
    if not files:
        return api_error("Choose at least one file.")
    form = request.form
    auto_summary = form.get("auto_summary", "true") != "false"
    created = []
    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in Config.ALLOWED_EXTENSIONS:
            return api_error(f"'{f.filename}' is not a supported file type.")
        original_filename = secure_filename(f.filename or "") or "document"
        requested_title = secure_filename((form.get("title") or "")[:160])
        filename = f"{requested_title}{ext}" if len(files) == 1 and requested_title else original_filename
        data = f.read()
        if not data:
            return api_error(f"'{f.filename}' is empty.")
        file_id = put_file(data)
        now = utcnow()
        title = Path(filename).stem
        doc_id = get_db().documents.insert_one({
            "user_id": user["_id"], "filename": filename, "size": len(data), "file_id": file_id,
            "uploaded_at": now, "updated_at": now,
        }).inserted_id
        log_activity(user["_id"], "upload", f"Uploaded {title}", doc_id)
        jobs.enqueue_document(doc_id, {
            "auto_summary": auto_summary,
            "mode": form.get("mode") if form.get("mode") in summarizer.MODES else None,
            "length": form.get("length") if form.get("length") in summarizer.LENGTHS else None,
            "language": form.get("language") if form.get("language") in summarizer.LANGUAGES else None,
        })
        created.append({"id": str(doc_id), "title": title, "filename": f.filename})
    return jsonify({"documents": created}), 201


@app.get("/api/documents")
@login_required
def list_docs(user):
    query = {"user_id": user["_id"]}
    q = (request.args.get("q") or "").strip()
    docs = get_db().documents.find(query).sort("uploaded_at", -1).limit(500)
    type_filter = request.args.get("type")
    status_filter = request.args.get("status")
    result = []
    for doc in docs:
        brief = doc_brief(doc)
        if q and q.lower() not in brief["filename"].lower() and q.lower() not in brief["title"].lower():
            continue
        if type_filter and brief["doc_type"] != type_filter:
            continue
        if status_filter and brief["status"] != status_filter:
            continue
        result.append(brief)
    return jsonify(result)


@app.get("/api/documents/<doc_id>")
@login_required
def get_doc(user, doc_id):
    doc = owned_doc(user, doc_id)
    db = get_db()
    summaries = [summary_out(s) for s in db.summaries.find({"document_id": doc["_id"]}).sort("created_at", -1)]
    info = insights_mod.analyze(doc.get("text") or "", soon_days=Config.EXPIRING_SOON_DAYS)
    table = tabular.parse(doc.get("text") or "")
    info["fields"] = [] if table else fields_mod.extract_fields(doc.get("text") or "")
    out = doc_brief(doc, info)
    out.update({
        "insights": info,
        "calendar_event_status": calendar_status(doc.get("calendar_events", [])),
        "calendar_events": doc.get("calendar_events", []),
        "summaries": summaries,
        "plan": jobs.plan_for(doc.get("text") or ""),
        "has_text": bool(doc.get("text")),
        "mime": mimetypes.guess_type(doc.get("filename") or "")[0] or "application/octet-stream",
    })
    return jsonify(out)


@app.get("/api/documents/<doc_id>/status")
@login_required
def doc_status(user, doc_id):
    doc = owned_doc(user, doc_id)
    out = doc_brief(doc)
    out["calendar_event_status"] = calendar_status(doc.get("calendar_events", []))
    out["calendar_events"] = doc.get("calendar_events", [])
    auto_id = jobs.document_state(doc).get("auto_summary_id")
    if auto_id:
        s = get_db().summaries.find_one({"_id": auto_id})
        out["summary"] = summary_out(s) if s else None
    return jsonify(out)


@app.get("/api/documents/<doc_id>/text")
@login_required
def doc_text(user, doc_id):
    doc = owned_doc(user, doc_id, {"text": 1})
    return jsonify({"text": doc.get("text") or ""})


@app.get("/api/documents/<doc_id>/file")
@login_required
def doc_file(user, doc_id):
    doc = owned_doc(user, doc_id)
    mime = mimetypes.guess_type(doc.get("filename") or "")[0] or "application/octet-stream"
    inline = request.args.get("download") != "1" and mime in INLINE_TYPES
    name = secure_filename(doc.get("filename") or "file") or "file"
    return Response(
        read_file(doc["file_id"]), mimetype=mime,
        headers={"Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{name}"',
                 "Content-Security-Policy": "sandbox", "Cache-Control": "private, max-age=300"},
    )


@app.patch("/api/documents/<doc_id>")
@login_required
def rename_doc(user, doc_id):
    doc = owned_doc(user, doc_id, {"_id": 1, "filename": 1})
    title = ((request.get_json(silent=True) or {}).get("title") or "").strip()
    if not title:
        return api_error("Title cannot be empty.")
    suffix = Path(doc.get("filename") or "").suffix
    filename = (secure_filename(title) or "document")[:160] + suffix
    get_db().documents.update_one({"_id": doc["_id"]}, {"$set": {"filename": filename, "updated_at": utcnow()}})
    return jsonify({"ok": True, "title": title[:160]})


@app.post("/api/documents/<doc_id>/reprocess")
@login_required
def reprocess(user, doc_id):
    doc = owned_doc(user, doc_id)
    if jobs.document_state(doc).get("status") not in {"ready", "failed"}:
        return api_error("This document is still being processed.", 409)
    get_db().documents.update_one({"_id": doc["_id"]}, {"$set": {
        "calendar_events": [], "updated_at": utcnow()}})
    log_activity(user["_id"], "reprocess", f"Reprocessed {Path(doc['filename']).stem}", doc["_id"])
    jobs.enqueue_document(doc["_id"])
    return jsonify({"ok": True})


@app.delete("/api/documents/<doc_id>")
@login_required
def delete_doc(user, doc_id):
    doc = owned_doc(user, doc_id, {"text": 0})
    db = get_db()
    delete_file(doc["file_id"])
    db.summaries.delete_many({"document_id": doc["_id"]})
    db.chat_messages.delete_many({"document_id": doc["_id"]})
    db.documents.delete_one({"_id": doc["_id"]})
    jobs.clear_document_state(doc["_id"])
    log_activity(user["_id"], "delete", f"Deleted {Path(doc['filename']).stem}")
    return jsonify({"ok": True})


# ------------------------------------------------------------------ summaries
@app.post("/api/documents/<doc_id>/summaries")
@login_required
def new_summary(user, doc_id):
    doc = owned_doc(user, doc_id)
    if jobs.document_state(doc).get("status") != "ready":
        return api_error("Wait until the document finishes processing.", 409)
    data = request.get_json(silent=True) or {}
    if data.get("mode") == "custom" and not (data.get("instructions") or "").strip():
        return api_error("Write your custom instructions first.")
    summary_id = jobs.create_summary(
        doc, user, mode=data.get("mode", Config.DEFAULT_MODE), length=data.get("length", "standard"),
        language=data.get("language", "English"), instructions=data.get("instructions") or "",
        model=(data.get("model") or "").strip() or None,
    )
    log_activity(user["_id"], "summary",
                 f"Generated {summarizer.MODES.get(data.get('mode'), {}).get('label', 'summary')} "
                 f"for {Path(doc['filename']).stem}",
                 doc["_id"])
    jobs.enqueue_summary(summary_id)
    return jsonify(summary_out(get_db().summaries.find_one({"_id": summary_id}))), 201


@app.get("/api/summaries/<summary_id>")
@login_required
def get_summary(user, summary_id):
    s = get_db().summaries.find_one({"_id": oid(summary_id), "user_id": user["_id"]})
    if not s:
        return api_error("Summary not found.", 404)
    return jsonify(summary_out(s))


@app.delete("/api/summaries/<summary_id>")
@login_required
def delete_summary(user, summary_id):
    result = get_db().summaries.delete_one({"_id": oid(summary_id), "user_id": user["_id"]})
    return jsonify({"ok": bool(result.deleted_count)})


# ------------------------------------------------------------------ chat
@app.get("/api/documents/<doc_id>/chat")
@login_required
def chat_history(user, doc_id):
    doc = owned_doc(user, doc_id, {"_id": 1})
    msgs = get_db().chat_messages.find({"document_id": doc["_id"]}).sort("_id", 1)
    return jsonify([chat_out(m) for m in msgs])


@app.post("/api/documents/<doc_id>/chat")
@login_required
def ask(user, doc_id):
    doc = owned_doc(user, doc_id)
    if jobs.document_state(doc).get("status") != "ready":
        return api_error("Wait until the document finishes processing.", 409)
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return api_error("Type a question first.")
    db = get_db()
    now = utcnow()
    q_id = db.chat_messages.insert_one({"document_id": doc["_id"], "user_id": user["_id"], "role": "user",
                                        "content": question[:4000], "status": "done", "created_at": now}).inserted_id
    a_id = db.chat_messages.insert_one({
        "document_id": doc["_id"], "user_id": user["_id"], "role": "assistant", "content": "",
        "status": "queued", "question": question[:4000], "question_id": q_id,
        "language": data.get("language") if data.get("language") in summarizer.LANGUAGES else "English",
        "model": (user.get("prefs") or {}).get("model") or Config.OLLAMA_MODEL,
        "created_at": now + timedelta(milliseconds=1),
    }).inserted_id
    jobs.enqueue_chat(a_id)
    return jsonify({"question": chat_out(db.chat_messages.find_one({"_id": q_id})),
                    "answer": chat_out(db.chat_messages.find_one({"_id": a_id}))}), 201


@app.get("/api/chat/<message_id>")
@login_required
def chat_message(user, message_id):
    m = get_db().chat_messages.find_one({"_id": oid(message_id), "user_id": user["_id"]})
    if not m:
        return api_error("Message not found.", 404)
    return jsonify(chat_out(m))


@app.delete("/api/documents/<doc_id>/chat")
@login_required
def clear_chat(user, doc_id):
    doc = owned_doc(user, doc_id, {"_id": 1})
    get_db().chat_messages.delete_many({"document_id": doc["_id"]})
    return jsonify({"ok": True})


# ------------------------------------------------------------------ startup
def create_app():
    init_db()
    return app


def _port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


if __name__ == "__main__":
    # Check before touching the database: a second copy must not mark the running copy's jobs as interrupted.
    if _port_in_use(5000):
        log.error("Port 5000 is already in use - DocuMind (or another app) is already running. "
                  "Open http://127.0.0.1:5000 or stop the other process first.")
        raise SystemExit(1)
    create_app()
    try:
        from waitress import serve
        log.info("Serving on http://127.0.0.1:5000 (waitress)")
        serve(app, host="0.0.0.0", port=5000, threads=16)
    except ImportError:
        app.run(host="0.0.0.0", port=5000, threaded=True, debug=False)
