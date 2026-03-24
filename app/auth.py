import hashlib
import re


EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(user_data: dict, raw_password: str) -> bool:
    stored_hash = user_data.get("password_hash")
    legacy_raw = user_data.get("password")

    if stored_hash:
        return stored_hash == hash_password(raw_password)
    if legacy_raw is not None:
        return legacy_raw == raw_password
    return False


def migrate_legacy_password(user_data: dict) -> bool:
    legacy_raw = user_data.get("password")
    if legacy_raw is None:
        return False
    user_data["password_hash"] = hash_password(legacy_raw)
    user_data.pop("password", None)
    return True


def validate_email(email: str) -> bool:
    return bool(EMAIL_REGEX.match(email))
