"""Create indexes and the seeded admin login in MongoDB:  python seed.py"""

from config import Config
from db import get_db, init_db

if __name__ == "__main__":
    init_db()
    user = get_db().users.find_one({"email": Config.SEED_ADMIN_EMAIL.lower()})
    print(f"Database : {Config.DB_NAME}")
    print(f"Login    : {user['email']}")
    print(f"Password : {Config.SEED_ADMIN_PASSWORD}  (from .env SEED_ADMIN_PASSWORD; change it after first login)")
