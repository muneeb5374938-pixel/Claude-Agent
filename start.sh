#!/bin/bash
set -e

echo "🤖 Starting Telegram bot in background..."
python bot.py &

echo "🚀 Starting Flask server..."
python server.py
