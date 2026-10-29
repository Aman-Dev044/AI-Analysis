"""Background pipeline: extract -> analyse -> summarise, with live progress in MongoDB.

The browser polls the document / summary records, so every stage, percentage and
the partially-generated summary text are visible while work is running.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Optional

from bson import ObjectId

from config import Config
from db import get_db, read_file, utcnow
from services import extractor, fields as fields_mod, google_calendar, insights as insights_mod, plan as plan_mod, summarizer
from services.ollama_client import OllamaError

log = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=Config.WORKERS, thread_name_prefix="docjob")


class _Throttle:
    """Limit how often partial progress is written to the database."""

    def __init__(self, interval: float = 0.35):
        self.interval = interval
        self.last = 0.0

    def ready(self) -> bool:
        now = time.monotonic()
        if now - self.last >= self.interval:
            self.last = now
            return True
        return False


def _set_doc(doc_id: ObjectId, **fields):
    fields["updated_at"] = utcnow()
    get_db().documents.update_one({"_id": doc_id}, {"$set": fields})


def _set_summary(summary_id: ObjectId, **fields):
    fields["updated_at"] = utcnow()
    get_db().summaries.update_one({"_id": summary_id}, {"$set": fields})


def _friendly(exc: Exception) -> str:
    return str(exc) if isinstance(exc, (OllamaError, extractor.ExtractionError, ValueError)) else \
        f"{type(exc).__name__}: {exc}"


# ------------------------------------------------------------------ summaries
def create_summary(doc: dict, user: dict, *, mode: str, length: str, language: str,
                   instructions: str = "", model: Optional[str] = None) -> ObjectId:
    now = utcnow()
    return get_db().summaries.insert_one({
        "document_id": doc["_id"],
        "user_id": user["_id"],
        "mode": mode if mode in summarizer.MODES else Config.DEFAULT_MODE,
        "length": length if length in summarizer.LENGTHS else "standard",
        "language": language if language in summarizer.LANGUAGES else "English",
        "instructions": instructions[:2000],
        "model": model or (user.get("prefs") or {}).get("model") or Config.OLLAMA_MODEL,
        "status": "queued",
        "progress": 0,
        "stage_message": "Waiting in queue",
        "content": "",
        "error": None,
        "created_at": now,
        "updated_at": now,
    }).inserted_id


def run_summary(summary_id: ObjectId, on_progress=None) -> bool:
    db = get_db()
    summary = db.summaries.find_one({"_id": summary_id})
    if not summary:
        return False
    doc = db.documents.find_one({"_id": summary["document_id"]})
    if not doc or not (doc.get("text") or "").strip():
        _set_summary(summary_id, status="failed", error="Document has no extracted text.")
        return False

    started = time.monotonic()
    throttle = _Throttle()
    _set_summary(summary_id, status="running", progress=2,
                 stage_message="Reading the document" if Config.AI_BACKEND == "rules" else "Connecting to Ollama")

    def progress(pct: int, message: str, partial: Optional[str]):
        if on_progress:
            on_progress(pct, message)
        if partial is None or throttle.ready():
            fields = {"progress": pct, "stage_message": message}
            if partial is not None:
                fields["content"] = summarizer.clean_markdown(partial)
            _set_summary(summary_id, **fields)

    try:
        content = summarizer.summarize(
            doc["text"],
            mode=summary["mode"], length=summary.get("length", "standard"), language=summary["language"],
            instructions=summary.get("instructions") or "", insights=doc.get("insights") or {},
            title=doc.get("title", ""), model=summary.get("model"), progress=progress,
        )
        _set_summary(summary_id, status="done", progress=100, stage_message="Completed", content=content,
                     duration_ms=int((time.monotonic() - started) * 1000), error=None)
        return True
    except Exception as exc:
        log.exception("Summary %s failed", summary_id)
        _set_summary(summary_id, status="failed", stage_message="Failed", error=_friendly(exc))
        return False


def enqueue_summary(summary_id: ObjectId):
    _executor.submit(run_summary, summary_id)


# ------------------------------------------------------------------ documents
def _labelled_expiry(info: dict):
    """Prefer an explicitly labelled "Valid till / Expiry" field over a date that merely sits near such words."""
    exp = next((f for f in info["fields"] if f["key"] == "expiry_date"), None)
    if not exp:
        return None
    days = exp["days_from_today"]
    status = "expired" if days < 0 else "expiring_soon" if days <= Config.EXPIRING_SOON_DAYS else "valid"
    return {"date": exp["iso"], "text": exp["value"], "days_remaining": days,
            "status": "verify" if exp.get("ambiguous") else status, "context": f"{exp['label']}: {exp['value']}"}


def process_document(doc_id: ObjectId):
    db = get_db()
    doc = db.documents.find_one({"_id": doc_id})
    if not doc:
        return
    user = db.users.find_one({"_id": doc["user_id"]}) or {}
    prefs = user.get("prefs") or {}
    try:
        _set_doc(doc_id, status="extracting", stage="extracting", progress=5,
                 stage_message="Opening file", error=None)
        data = read_file(doc["file_id"])

        throttle = _Throttle(0.3)

        def extract_progress(pct: int, message: str):
            if throttle.ready() or pct >= 100:
                _set_doc(doc_id, progress=5 + int(pct * 0.5), stage_message=message)

        result = extractor.extract(data, doc["ext"], extract_progress)
        text = (result.text or "").strip()
        if not text:
            raise extractor.ExtractionError(
                "No readable text was found in this file. If it is a scan/photo, configure an OCR engine.")

        _set_doc(doc_id, status="analyzing", stage="analyzing", progress=58,
                 stage_message="Finding dates, amounts and key facts", text=text, pages=result.pages,
                 ocr_used=result.ocr_used, ocr_engine=result.ocr_engine)

        info = insights_mod.analyze(text, soon_days=Config.EXPIRING_SOON_DAYS)
        info["fields"] = fields_mod.extract_fields(text)
        info["expiry"] = _labelled_expiry(info) or info.get("expiry")
        is_plan = plan_mod.detect_plan(text) is not None
        _set_doc(doc_id, progress=64, stage_message="Document analysed", insights=info,
                 doc_type=info["doc_type"], word_count=info["stats"]["words"], is_plan=is_plan,
                 expiry=info.get("expiry"))
        try:
            calendar_result = google_calendar.sync_document_events(
                user, str(doc_id), doc.get("title") or doc.get("filename") or "Document",
                info.get("dates") or [],
            )
            _set_doc(
                doc_id,
                calendar_event_status=calendar_result["status"],
                calendar_events=calendar_result["events"],
            )
        except Exception:
            log.exception("Google Calendar event sync failed for document %s", doc_id)
            _set_doc(
                doc_id,
                calendar_event_status="failed",
                calendar_events=[],
            )

        if not doc.get("auto_summary", True):
            _set_doc(doc_id, status="ready", stage="ready", progress=100, stage_message="Ready")
            return

        _set_doc(doc_id, status="summarizing", stage="summarizing", progress=66,
                 stage_message="Generating AI summary")
        summary_id = create_summary(
            doc, user,
            mode=doc.get("auto_mode") or prefs.get("mode") or Config.DEFAULT_MODE,
            length=doc.get("auto_length") or "standard",
            language=doc.get("auto_language") or prefs.get("language", "English"),
        )
        _set_doc(doc_id, auto_summary_id=summary_id)
        doc_throttle = _Throttle(0.5)

        def summary_progress(pct: int, message: str):
            if doc_throttle.ready():
                _set_doc(doc_id, progress=66 + int(pct * 0.33), stage_message=message)

        ok = run_summary(summary_id, on_progress=summary_progress)
        _set_doc(doc_id, status="ready", stage="ready", progress=100,
                 stage_message="Ready" if ok else "Ready — summary failed, you can retry",
                 summary_failed=not ok)
    except Exception as exc:
        log.exception("Processing document %s failed", doc_id)
        _set_doc(doc_id, status="failed", stage="failed", stage_message="Failed", error=_friendly(exc))


def enqueue_document(doc_id: ObjectId):
    _executor.submit(process_document, doc_id)


# ------------------------------------------------------------------ chat
def run_chat(message_id: ObjectId):
    db = get_db()
    msg = db.chat_messages.find_one({"_id": message_id})
    if not msg:
        return
    doc = db.documents.find_one({"_id": msg["document_id"]})
    question = msg.get("question", "")
    history = list(db.chat_messages.find(
        {"document_id": msg["document_id"], "status": "done", "_id": {"$lt": msg["question_id"]}},
        {"role": 1, "content": 1},
    ).sort("_id", 1))
    throttle = _Throttle(0.3)
    db.chat_messages.update_one({"_id": message_id}, {"$set": {"status": "running"}})

    def on_token(partial: str):
        if throttle.ready():
            db.chat_messages.update_one({"_id": message_id}, {"$set": {"content": partial}})

    try:
        answer = summarizer.answer_question(
            doc.get("text") or "", question, history,
            language=msg.get("language", "English"), model=msg.get("model"), on_token=on_token,
            insights=doc.get("insights") or {},
        )
        db.chat_messages.update_one({"_id": message_id}, {"$set": {"status": "done", "content": answer}})
    except Exception as exc:
        log.exception("Chat %s failed", message_id)
        db.chat_messages.update_one({"_id": message_id},
                                    {"$set": {"status": "failed", "error": _friendly(exc)}})


def enqueue_chat(message_id: ObjectId):
    _executor.submit(run_chat, message_id)


def plan_for(text: str) -> Optional[dict]:
    return plan_mod.detect_plan(text, date.today())
