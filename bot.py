"""
bot.py — Telegram bot for Claude Agent using Aiogram 3.x.
Handles /start command, user registration, and referral tracking.
Run with: python bot.py
"""

import asyncio
import logging
import os
import re

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
)
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Import database helpers
from database import init_db, register_user, get_user

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set.")

WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://your-repl-url.replit.app/")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def handle_start(message: Message, command: CommandObject):
    user = message.from_user
    telegram_id = user.id
    username = user.username or ""
    first_name = user.first_name or ""

    referred_by = None
    args = command.args

    if args:
        match = re.match(r"^ref_(\d+)$", args.strip())
        if match:
            referrer_id = int(match.group(1))
            if referrer_id != telegram_id:
                referrer = get_user(referrer_id)
                if referrer:
                    referred_by = referrer_id

    is_new = register_user(telegram_id, username, first_name, referred_by)

    open_app_button = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🚀 Open App",
            web_app=WebAppInfo(url=WEBAPP_URL),
        )
    ]])

    welcome_text = (
        "👋 Welcome to <b>Claude Agent</b>!\n\n"
        "Earn <b>CA tokens</b> by watching ads and referring friends.\n\n"
        "• 📺 Watch up to <b>20 ads per day</b> — earn <b>10 CA</b> each\n"
        "• 👫 Refer a friend — earn <b>10% bonus</b> on every ad they watch\n\n"
        "Tap <b>Open App</b> below to get started!"
    )

    await message.answer(
        welcome_text,
        parse_mode="HTML",
        reply_markup=open_app_button,
    )


async def main():
    init_db()
    logger.info("✅ Database initialised.")
    logger.info("🤖 Bot starting — polling for updates...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
