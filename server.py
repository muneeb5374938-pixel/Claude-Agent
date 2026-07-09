"""
server.py — Flask API server for Claude Agent Telegram Mini App.
"""

import hashlib
import hmac
import json
import os
import time
import threading
import urllib.parse
from datetime import datetime

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

from database import (
    init_db, get_user, register_user, credit_ad_reward, get_referral_stats,
    DAILY_AD_LIMIT, _reset_ads_if_new_day, get_connection,
)

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), "webapp")

app = Flask(__name__, static_folder=WEBAPP_DIR, static_url_path="")
CORS(app)

BOT_TOKEN    = os.environ.get("BOT_TOKEN", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "YourBotUsername")

INIT_DATA_MAX_AGE = 3600

def _verify_init_data(init_data: str) -> dict | None:
    if not BOT_TOKEN:
        return None
    try:
        params = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        return None

    received_hash = params.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(params.items())
    )

    secret_key = hmac.new(
        b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256
    ).digest()

    expected_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        return None

    auth_date = params.get("auth_date")
    if auth_date:
        try:
            age = int(time.time()) - int(auth_date)
            if age > INIT_DATA_MAX_AGE:
                return None
        except ValueError:
            return None

    user_json = params.get("user")
    if not user_json:
        return None
    try:
        return json.loads(user_json)
    except (json.JSONDecodeError, ValueError):
        return None


def _get_verified_telegram_id() -> int | None:
    init_data = request.headers.get("X-Telegram-Init-Data", "").strip()
    if not init_data and request.is_json:
        init_data = (request.get_json(silent=True) or {}).get("init_data", "")
    if not init_data:
        return None
    user = _verify_init_data(init_data)
    if not user:
        return None
    try:
        return int(user["id"])
    except (KeyError, ValueError, TypeError):
        return None


def require_auth():
    telegram_id = _get_verified_telegram_id()
    if not telegram_id:
        return None, (jsonify({"error": "Unauthorized."}), 401)
    return telegram_id, None


_recent_ad_requests: dict[str, float] = {}
_recent_lock = threading.Lock()
DEBOUNCE_SECONDS = 5


def _is_duplicate_ad_request(telegram_id: int) -> bool:
    key = str(telegram_id)
    now = time.time()
    with _recent_lock:
        last = _recent_ad_requests.get(key, 0)
        if now - last < DEBOUNCE_SECONDS:
            return True
        _recent_ad_requests[key] = now
    return False


@app.route("/")
def index():
    return send_from_directory(WEBAPP_DIR, "index.html")


@app.route("/api/user/<int:telegram_id>", methods=["GET"])
def api_get_user(telegram_id: int):
    verified_id, err = require_auth()
    if err:
        return err
    if verified_id != telegram_id:
        return jsonify({"error": "Forbidden."}), 403

    user = get_user(telegram_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    conn = get_connection()
    cursor = conn.cursor()
    _reset_ads_if_new_day(cursor, user)
    conn.commit()
    conn.close()

    referral_stats = get_referral_stats(telegram_id)

    return jsonify({
        "telegram_id":         user["telegram_id"],
        "username":            user["username"],
        "first_name":          user["first_name"],
        "ca_balance":          user["ca_balance"],
        "ads_watched_today":   user["ads_watched_today"],
        "ads_remaining_today": DAILY_AD_LIMIT - user["ads_watched_today"],
        "total_ads_watched":   user["total_ads_watched"],
        "join_date":           user["join_date"],
        "referral_count":      referral_stats["referral_count"],
        "referral_ca_earned":  referral_stats["referral_ca_earned"],
    })


@app.route("/api/ad-watched", methods=["POST"])
def api_ad_watched():
    verified_id, err = require_auth()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    request_id = data.get("request_id")

    if _is_duplicate_ad_request(verified_id):
        return jsonify({"error": "Duplicate request."}), 429

    result = credit_ad_reward(verified_id, request_id=request_id)

    if not result["success"]:
        status = 429 if result["reason"] == "Duplicate request." else 400
        return jsonify({"error": result["reason"]}), status

    return jsonify({
        "success":           True,
        "ca_earned":         result["ca_earned"],
        "new_balance":       result["new_balance"],
        "ads_watched_today": result["ads_watched_today"],
        "ads_remaining":     result["ads_remaining"],
    })


@app.route("/api/referral-link/<int:telegram_id>", methods=["GET"])
def api_referral_link(telegram_id: int):
    verified_id, err = require_auth()
    if err:
        return err
    if verified_id != telegram_id:
        return jsonify({"error": "Forbidden."}), 403

    link = f"https://t.me/{BOT_USERNAME}?start=ref_{telegram_id}"
    return jsonify({"referral_link": link, "bot_username": BOT_USERNAME})


@app.route("/api/referrals/<int:telegram_id>", methods=["GET"])
def api_referrals(telegram_id: int):
    verified_id, err = require_auth()
    if err:
        return err
    if verified_id != telegram_id:
        return jsonify({"error": "Forbidden."}), 403

    user = get_user(telegram_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    return jsonify(get_referral_stats(telegram_id))


if __name__ == "__main__":
    init_db()
    print("✅ Database initialised.")
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Flask server starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
