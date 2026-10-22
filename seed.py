"""Seed / maintain the admin login in MongoDB.

  python seed.py                       create indexes + admin login (if missing)
  python seed.py --hash                print a password hash for SEED_ADMIN_PASSWORD_HASH
  python seed.py --set-password        set a new admin password (stored hashed)
"""

import getpass
import sys

from werkzeug.security import generate_password_hash

from config import Config
from db import get_db, init_db


def ask_password() -> str:
    first = getpass.getpass("New admin password: ")
    if len(first) < 6 or first != getpass.getpass("Repeat password: "):
        sys.exit("Passwords must match and be at least 6 characters.")
    return first


if __name__ == "__main__":
    if "--hash" in sys.argv:
        print(generate_password_hash(ask_password()))
        sys.exit()

    init_db()
    email = Config.SEED_ADMIN_EMAIL.lower()
    if "--set-password" in sys.argv:
        result = get_db().users.update_one({"email": email},
                                           {"$set": {"password_hash": generate_password_hash(ask_password())}})
        print("Password updated." if result.matched_count else f"No user {email} found.")
        sys.exit()

    user = get_db().users.find_one({"email": email})
    print(f"Database : {Config.DB_NAME}")
    print(f"Login    : {user['email'] if user else 'not created (set SEED_ADMIN_PASSWORD_HASH in .env)'}")
    print("Password : stored only as a hash")
