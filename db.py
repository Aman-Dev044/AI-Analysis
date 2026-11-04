"""MongoDB access (pymongo is thread-safe, so background workers share one client).

Collections used (kept minimal because the shared Atlas cluster has a collection cap):
  users          – accounts, preferences and a capped recent-activity list
  documents      – file metadata, extracted text, expiry date and calendar events
  summaries      – every generated summary (with live progress while running)
  chat_messages  – document Q&A history
  files          – original file bytes, split into <=4 MB chunks
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from bson import Binary, ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.results import UpdateResult
from werkzeug.security import generate_password_hash

from config import Config

FILE_CHUNK_BYTES = 4 * 1024 * 1024
ACTIVITY_KEEP = 100
DOCUMENT_FIELDS = {
    "user_id", "file_id", "filename", "size", "uploaded_at", "updated_at",
    "ocr_engine", "text", "expiry_date", "expiry_text", "calendar_events",
}

_client: Optional[MongoClient] = None
_db = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_db():
    global _client, _db
    if _db is None:
        _client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=20000, tz_aware=True)
        _db = _client[Config.DB_NAME]
    return _db


def oid(value) -> Optional[ObjectId]:
    try:
        return value if isinstance(value, ObjectId) else ObjectId(str(value))
    except (InvalidId, TypeError):
        return None


def init_db() -> None:
    db = get_db()
    db.users.create_index("email", unique=True)
    db.documents.create_index([("user_id", ASCENDING), ("uploaded_at", DESCENDING)])
    db.summaries.create_index([("document_id", ASCENDING), ("created_at", DESCENDING)])
    db.chat_messages.create_index([("document_id", ASCENDING), ("_id", ASCENDING)])
    db.files.create_index([("file_id", ASCENDING), ("n", ASCENDING)], unique=True)

    minimize_document_records(db)

    # Summary and chat jobs survive in MongoDB; document-job state is memory-only.
    cutoff = utcnow() - timedelta(minutes=2)
    stale = {"$nor": [{f: {"$gte": cutoff}} for f in ("updated_at", "created_at", "uploaded_at")]}
    db.summaries.update_many(
        {"status": {"$in": ["queued", "running"]}, **stale},
        {"$set": {"status": "failed", "error": "Generation was interrupted (the server restarted). Generate it again."}},
    )
    db.chat_messages.update_many(
        {"status": {"$in": ["queued", "running"]}, **stale},
        {"$set": {"status": "failed", "error": "Interrupted by a server restart."}},
    )
    seed_admin()


def minimize_document_records(db=None) -> UpdateResult:
    """Keep document records limited to the approved persistence fields."""
    db = db if db is not None else get_db()
    allowed = sorted(DOCUMENT_FIELDS | {"_id"})
    has_extra_top_level_fields = {"$anyElementTrue": [{
        "$map": {
            "input": {"$objectToArray": "$$ROOT"},
            "as": "field",
            "in": {"$not": [{"$in": ["$$field.k", allowed]}]},
        }
    }]}
    expiry_date = {"$convert": {
        "input": {"$ifNull": ["$expiry_date", "$expiry.date"]},
        "to": "date", "onError": None, "onNull": None,
    }}
    expiry_text = {"$ifNull": ["$expiry_text", "$expiry.text"]}
    replace = {"$replaceWith": {
        "_id": "$_id",
        **{
            field: {"$ifNull": [f"${field}", "$$REMOVE"]}
            for field in DOCUMENT_FIELDS - {"expiry_date", "expiry_text"}
        },
        "expiry_date": {"$cond": [{"$ne": [expiry_date, None]}, expiry_date, "$$REMOVE"]},
        "expiry_text": {"$cond": [{"$ne": [expiry_text, None]}, expiry_text, "$$REMOVE"]},
    }}
    return db.documents.update_many(
        {"$expr": {"$or": [
            has_extra_top_level_fields,
            {"$ne": [{"$type": "$expiry"}, "missing"]},
            {"$and": [
                {"$ne": [{"$type": "$expiry_date"}, "missing"]},
                {"$ne": [{"$type": "$expiry_date"}, "date"]},
            ]},
            {"$and": [
                {"$ne": [{"$type": "$expiry_text"}, "missing"]},
                {"$ne": [{"$type": "$expiry_text"}, "string"]},
            ]},
        ]}},
        [replace],
    )


def seed_admin() -> bool:
    """Create the seeded login from .env if it does not exist. Returns True when created."""
    db = get_db()
    email = Config.SEED_ADMIN_EMAIL.strip().lower()
    password_hash = Config.SEED_ADMIN_PASSWORD_HASH or (
        generate_password_hash(Config.SEED_ADMIN_PASSWORD) if Config.SEED_ADMIN_PASSWORD else ""
    )
    if not email or not password_hash or db.users.find_one({"email": email}):
        return False
    db.users.insert_one({
        "name": Config.SEED_ADMIN_NAME,
        "email": email,
        "password_hash": password_hash,
        "role": "admin",
        "prefs": {"mode": Config.DEFAULT_MODE, "language": "English", "length": "standard", "model": None},
        "activity": [],
        "created_at": utcnow(),
    })
    return True


# ------------------------------------------------------------------ file storage
def put_file(data: bytes) -> ObjectId:
    file_id = ObjectId()
    chunks = [
        {"file_id": file_id, "n": i, "data": Binary(data[start:start + FILE_CHUNK_BYTES])}
        for i, start in enumerate(range(0, len(data), FILE_CHUNK_BYTES))
    ]
    get_db().files.insert_many(chunks)
    return file_id


def read_file(file_id: ObjectId) -> bytes:
    parts = get_db().files.find({"file_id": file_id}).sort("n", ASCENDING)
    return b"".join(bytes(p["data"]) for p in parts)


def delete_file(file_id: ObjectId) -> None:
    get_db().files.delete_many({"file_id": file_id})


def mongo_date(value) -> Optional[datetime]:
    """Convert a date/datetime or ISO date string to UTC midnight for BSON Date storage."""
    if isinstance(value, datetime):
        return datetime.combine(value.date(), time.min, tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.combine(date.fromisoformat(value[:10]), time.min, tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


# ------------------------------------------------------------------ activity
def log_activity(user_id: ObjectId, action: str, description: str, document_id=None) -> None:
    entry = {"action": action, "description": description,
             "document_id": str(document_id) if document_id else None, "created_at": utcnow()}
    get_db().users.update_one(
        {"_id": user_id},
        {"$push": {"activity": {"$each": [entry], "$position": 0, "$slice": ACTIVITY_KEEP}}},
    )


def recent_activity(user: dict, limit: int = 50) -> list[dict]:
    return [{**a, "created_at": iso(a.get("created_at"))} for a in (user.get("activity") or [])[:limit]]


def iso(value) -> Optional[str]:
    return value.isoformat() if isinstance(value, datetime) else value
