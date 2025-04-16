#!/bin/bash

# This script runs the standalone_bot.py in a separate process
# with its own event loop, eliminating the conflict with gunicorn

# Kill any existing bot processes
pkill -f "python standalone_bot.py" || true

# Start the bot in the background
nohup python standalone_bot.py > telegram_bot.log 2>&1 &

echo "Started Telegram bot with PID: $!"