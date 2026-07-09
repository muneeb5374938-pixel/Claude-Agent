"""
database.py — SQLite database setup and helpers for Claude Agent.
"""

import sqlite3
import os
from datetime import date, datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "claude_agent.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id       INTEGER PRIMARY KEY,
            username          TEXT,
            first_name        TEXT,
            ca_balance        REAL    DEFAULT 0,
            referred_by       INTEGER,
            ads_watched_today INTEGER DEFAULT 0,
            last_ad_reset_date TEXT,
            total_ads_watched INTEGER DEFAULT 0,
            join_date         TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL,
            date        TEXT NOT NULL,
            PRIMARY KEY (referrer_id, referred_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ad_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            timestamp   TEXT    NOT NULL,
            ca_earned   REAL    NOT NULL,
            request_id  TEXT    UNIQUE
        )
    """)

    try:
        cursor.execute("ALTER TABLE ad_logs ADD COLUMN request_id TEXT UNIQUE")
    except Exception:
        pass

    conn.commit()
    conn.close()


def register_user(telegram_id: int, username: str, first_name: str, referred_by: int = None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id FROM users WHERE telegram_id = ?", (telegram_id,))
    if cursor.fetchone():
        conn.close()
        return False

    now = datetime.utcnow().isoformat()
    today = date.today().isoformat()

    cursor.execute("""
        INSERT INTO users
            (telegram_id, username, first_name, ca_balance, referred_by,
             ads_watched_today, last_ad_reset_date, total_ads_watched, join_date)
        VALUES (?, ?, ?, 0, ?, 0, ?, 0, ?)
    """, (telegram_id, username, first_name, referred_by, today, now))

    if referred_by:
        cursor.execute("""
            INSERT OR IGNORE INTO referrals (referrer_id, referred_id, date)
            VALUES (?, ?, ?)
        """, (referred_by, telegram_id, today))

    conn.commit()
    conn.close()
    return True


def get_user(telegram_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def _reset_ads_if_new_day(cursor, user: dict):
    today = date.today().isoformat()
    if user.get("last_ad_reset_date") != today:
        cursor.execute("""
            UPDATE users SET ads_watched_today = 0, last_ad_reset_date = ?
            WHERE telegram_id = ?
        """, (today, user["telegram_id"]))
        user["ads_watched_today"] = 0
        user["last_ad_reset_date"] = today


DAILY_AD_LIMIT = 20
CA_PER_AD = 10
REFERRAL_BONUS_PCT = 0.10


def credit_ad_reward(telegram_id: int, request_id: str = None):
    conn = get_connection()
    cursor = conn.cursor()

    if request_id:
        cursor.execute("SELECT id FROM ad_logs WHERE request_id = ?", (request_id,))
        if cursor.fetchone():
            conn.close()
            return {"success": False, "reason": "Duplicate request."}

    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"success": False, "reason": "User not found."}

    user = dict(row)
    _reset_ads_if_new_day(cursor, user)

    if user["ads_watched_today"] >= DAILY_AD_LIMIT:
        conn.close()
        return {
            "success": False,
            "reason": "Daily ad limit reached.",
            "new_balance": user["ca_balance"],
            "ads_watched_today": user["ads_watched_today"],
            "ads_remaining": 0,
        }

    ca_earned = CA_PER_AD
    new_balance = user["ca_balance"] + ca_earned
    new_ads_today = user["ads_watched_today"] + 1
    new_total = user["total_ads_watched"] + 1

    cursor.execute("""
        UPDATE users SET ca_balance = ?, ads_watched_today = ?, total_ads_watched = ?
        WHERE telegram_id = ?
    """, (new_balance, new_ads_today, new_total, telegram_id))

    now = datetime.utcnow().isoformat()
    try:
        cursor.execute("""
            INSERT INTO ad_logs (telegram_id, timestamp, ca_earned, request_id)
            VALUES (?, ?, ?, ?)
        """, (telegram_id, now, ca_earned, request_id))
    except Exception:
        conn.rollback()
        conn.close()
        return {"success": False, "reason": "Duplicate request."}

    if user.get("referred_by"):
        cursor.execute("""
            UPDATE users SET ca_balance = ca_balance + ? WHERE telegram_id = ?
        """, (ca_earned * REFERRAL_BONUS_PCT, user["referred_by"]))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "reason": "Reward credited.",
        "ca_earned": ca_earned,
        "new_balance": new_balance,
        "ads_watched_today": new_ads_today,
        "ads_remaining": DAILY_AD_LIMIT - new_ads_today,
    }


def get_referral_stats(telegram_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS cnt FROM referrals WHERE referrer_id = ?", (telegram_id,))
    referral_count = cursor.fetchone()["cnt"]

    cursor.execute("""
        SELECT COALESCE(SUM(al.ca_earned * ?), 0) AS total
        FROM ad_logs al
        INNER JOIN referrals r ON r.referred_id = al.telegram_id
        WHERE r.referrer_id = ?
    """, (REFERRAL_BONUS_PCT, telegram_id))
    referral_ca_earned = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT u.telegram_id, u.username, u.first_name, r.date
        FROM referrals r
        INNER JOIN users u ON u.telegram_id = r.referred_id
        WHERE r.referrer_id = ?
        ORDER BY r.date DESC
    """, (telegram_id,))
    referred_users = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return {
        "referral_count": referral_count,
        "referral_ca_earned": referral_ca_earned,
        "referred_users": referred_users,
    }
