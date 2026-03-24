import json
import os

from app.models import ensure_user_schema

DB_FILE = "myfitness_users_db.json"


def load_db() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("users", {})
                for user in data["users"].values():
                    ensure_user_schema(user)
                return data
        except Exception:
            return {"users": {}}
    return {"users": {}}


def sync_db(db: dict) -> None:
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4, ensure_ascii=False)
