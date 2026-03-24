from datetime import date


def default_user(email: str, password_hash: str) -> dict:
    return {
        "password_hash": password_hash,
        "username": email.split("@")[0],
        "profile_pic": "",
        "phone": "",
        "sms_alerts": False,
        "onboarding_done": False,
        "profile": {},
        "daily_log": [],
        "exercise_log": [],
        "weight_log": [],
        "custom_foods": {},
        "water_liters": 0.0,
        "daily_logs_by_date": {},
        "exercise_logs_by_date": {},
    }


def ensure_user_schema(user_data: dict) -> dict:
    user_data.setdefault("username", "user")
    user_data.setdefault("profile_pic", "")
    user_data.setdefault("phone", "")
    user_data.setdefault("sms_alerts", False)
    user_data.setdefault("onboarding_done", False)
    user_data.setdefault("profile", {})
    user_data.setdefault("daily_log", [])
    user_data.setdefault("exercise_log", [])
    user_data.setdefault("weight_log", [])
    user_data.setdefault("custom_foods", {})
    user_data.setdefault("water_liters", 0.0)
    user_data.setdefault("daily_logs_by_date", {})
    user_data.setdefault("exercise_logs_by_date", {})
    user_data.setdefault("water_by_date", {})

    today_key = str(date.today())
    if today_key not in user_data["daily_logs_by_date"] and user_data["daily_log"]:
        user_data["daily_logs_by_date"][today_key] = user_data["daily_log"]
    if today_key not in user_data["exercise_logs_by_date"] and user_data["exercise_log"]:
        user_data["exercise_logs_by_date"][today_key] = user_data["exercise_log"]
    if "water_liters" in user_data:
        user_data["water_by_date"].setdefault(today_key, user_data["water_liters"])
    return user_data
