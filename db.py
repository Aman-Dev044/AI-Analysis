"""MongoDB access (pymongo is thread-safe, so background workers share one client).

Collections used (kept minimal because the shared Atlas cluster has a collection cap):
  users          – accounts, preferences and a capped recent-activity list
  documents      – uploads, extraction status/progress, text and insights
  summaries      – every generated summary (with live progress while running)
  chat_messages  – document Q&A history
  files          – original file bytes, split into <=4 MB chunks
"""

from datetime import datetime, timezone
from typing import Optional

from bson import Binary, ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, DESCENDING, MongoClient
from werkzeug.security import generate_password_hash

from config import Config

FILE_CHUNK_BYTES = 4 * 1024 * 1024
ACTIVITY_KEEP = 100

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

    # Work interrupted by a restart can never finish; surface it so the user can retry.
    db.documents.update_many(
        {"status": {"$nin": ["ready", "failed"]}},
        {"$set": {"status": "failed", "stage": "failed",
                  "error": "Processing was interrupted by a server restart. Use Reprocess."}},
    )
    db.summaries.update_many(
        {"status": {"$in": ["queued", "running"]}},
        {"$set": {"status": "failed", "error": "Generation was interrupted by a server restart."}},
    )
    db.chat_messages.update_many(
        {"status": {"$in": ["queued", "running"]}},
        {"$set": {"status": "failed", "error": "Interrupted by a server restart."}},
    )
    seed_admin()


def seed_admin() -> bool:
    """Create the seeded login from .env if it does not exist. Returns True when created."""
    db = get_db()
    email = Config.SEED_ADMIN_EMAIL.strip().lower()
    if not email or db.users.find_one({"email": email}):
        return False
    db.users.insert_one({
        "name": Config.SEED_ADMIN_NAME,
        "email": email,
        "password_hash": generate_password_hash(Config.SEED_ADMIN_PASSWORD),
        "role": "admin",
        "prefs": {"mode": "short", "language": "English", "length": "standard", "model": None},
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
