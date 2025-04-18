#!/usr/bin/env python3
"""
Simple Telegram bot that uses HTTP requests instead of python-telegram-bot 
to avoid asyncio issues and event loop conflicts.
"""
import os
import sys
import json
import time
import logging
import sqlite3
import requests
from datetime import datetime
from threading import Thread
import pytz

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("telegram_api_bot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("telegram_api_bot")

# Channel to forward reports to
FORWARD_CHANNEL = "https://t.me/+gZPKIWO217BhMzc1"
# Channel to forward admin responses to
RESPONSE_CHANNEL = "https://t.me/+VaDMrI1e4yEyNDU1"
# Telegram channel IDs
CHANNEL_ID = "-1002544234044"  # Use the channel ID that worked in your test
RESPONSE_CHANNEL_ID = "-1002326727802"  # Response channel ID for https://t.me/+VaDMrI1e4yEyNDU1

# Issue categories
CATEGORIES = [
    "Discord Items", 
    "Premiums", 
]

# Database setup
DB_PATH = "instance/telegram_bot.db"

# User states dictionary
user_states = {}  # user_id -> {'state': int, 'category': str}

# States constants
STATE_IDLE = 0
STATE_AWAITING_CATEGORY = 1
STATE_AWAITING_DESCRIPTION = 2

def init_db():
    """Initialize the database if it doesn't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if the reports table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='report'")
    if not cursor.fetchone():
        cursor.execute('''
        CREATE TABLE report (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        logger.info("Created reports table in database")

    conn.commit()
    conn.close()
    logger.info("Database initialized")

def save_report(user_id, username, category, description):
    """Save a report to the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO report (user_id, username, category, description) VALUES (?, ?, ?, ?)",
            (user_id, username, category, description)
        )

        report_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Report #{report_id} saved to database")
        return report_id
    except Exception as e:
        logger.error(f"Error saving report to database: {e}")
        return None

class TelegramBot:
    def __init__(self, token):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.offset = 0

        # Test connection
        try:
            response = requests.get(f"{self.api_url}/getMe")
            response.raise_for_status()
            bot_info = response.json()
            if bot_info["ok"]:
                bot_name = bot_info["result"]["username"]
                logger.info(f"Successfully connected to Telegram API. Bot name: {bot_name}")
            else:
                logger.error(f"Failed to connect to Telegram API: {bot_info}")
                raise Exception("Failed to connect to Telegram API")
        except Exception as e:
            logger.error(f"Error connecting to Telegram API: {e}")
            raise

    def send_message(self, chat_id, text, reply_markup=None):
        """Send a message to a chat."""
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }

        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)

        try:
            response = requests.post(f"{self.api_url}/sendMessage", data=data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return None

    def send_photo_to_channel(self, channel_id, file_id, caption=""):
        """Send a photo to the channel."""
        try:
            data = {
                "chat_id": channel_id,
                "photo": file_id,
                "caption": caption,
                "parse_mode": "HTML"
            }
            response = requests.post(f"{self.api_url}/sendPhoto", data=data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error sending photo to channel: {e}")
            return None

    def send_to_channel(self, text):
        """Send a message to the configured report channel."""
        try:
            logger.info(f"Attempting to forward message to channel: {CHANNEL_ID}")
            response = self.send_message(CHANNEL_ID, text)

            if response and response.get("ok", False):
                logger.info("Successfully forwarded message to channel")
                return response
            else:
                logger.error(f"Failed to send message to channel: {response}")
                return None
        except Exception as e:
            logger.error(f"Error in channel forwarding function: {e}")
            return None

    def get_updates(self):
        """Get updates from Telegram."""
        params = {
            "offset": self.offset,
            "timeout": 30
        }

        try:
            response = requests.get(f"{self.api_url}/getUpdates", params=params)
            response.raise_for_status()
            result = response.json()

            if result["ok"]:
                updates = result["result"]
                if updates:
                    self.offset = updates[-1]["update_id"] + 1
                return updates
            else:
                logger.error(f"Error getting updates: {result}")
                return []
        except Exception as e:
            logger.error(f"Error in get_updates: {e}")
            return []

    def answer_callback_query(self, callback_query_id, text=None):
        """Answer a callback query."""
        data = {
            "callback_query_id": callback_query_id
        }

        if text:
            data["text"] = text

        try:
            response = requests.post(f"{self.api_url}/answerCallbackQuery", data=data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error answering callback query: {e}")
            return None

    def send_admin_response(self, user_id, report_id, response_text):
        """Send admin response to user and response channel."""
        try:
            # Send to user
            self.send_message(user_id, f"📬 <b>Response to your report #{report_id}:</b>\n\n{response_text}")

            # Send to response channel
            channel_msg = (
                f"📬 <b>Admin Response</b>\n\n"
                f"<b>Report ID:</b> xnn_{report_id}\n"
                f"<b>To User:</b> <a href='tg://user?id={user_id}'>{user_id}</a>\n"
                f"<b>Response:</b>\n{response_text}"
            )
            self.send_message(RESPONSE_CHANNEL_ID, channel_msg)
            return True
        except Exception as e:
            logger.error(f"Error sending admin response: {e}")
            return False

    def process_command(self, update):
        """Process a command from a user."""
        message = update.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        user_id = message.get("from", {}).get("id")
        text = message.get("text", "")
        photo = message.get("photo", [])
        caption = message.get("caption", "")

        if not chat_id:
            return

        # Handle photo messages
        if photo and user_id in user_states and user_states[user_id]["state"] == STATE_AWAITING_DESCRIPTION:
            # Get the file_id of the largest photo size
            file_id = photo[-1]["file_id"]
            # Use caption as text if available, otherwise empty string
            self.process_description(chat_id, user_id, caption if caption else "")
            # Forward the photo to the channel
            self.send_photo_to_channel(CHANNEL_ID, file_id, caption)
            return

        if not text:
            return

        # Process commands
        if text.startswith("/start"):
            self.cmd_start(chat_id, user_id, message)
        elif text.startswith("/report") or text.lower() == "report":
            self.cmd_report(chat_id, user_id)
        elif text.startswith("/refund") or text.lower() == "refund":
            self.cmd_refund(chat_id, user_id)
        elif text.startswith("/respond"):
            self.cmd_respond(chat_id, user_id, text, update)
        elif text.startswith("/debug_channel"):
            self.cmd_debug_channel(chat_id, user_id, text)
        elif user_id in user_states and user_states[user_id]["state"] == STATE_AWAITING_DESCRIPTION:
            self.process_description(chat_id, user_id, text)

    def process_callback_query(self, update):
        """Process a callback query (button click)."""
        callback_query = update.get("callback_query", {})
        chat_id = callback_query.get("message", {}).get("chat", {}).get("id")
        user_id = callback_query.get("from", {}).get("id")
        data = callback_query.get("data")
        callback_id = callback_query.get("id")

        if not chat_id or not data or not user_id:
            return

        # Answer the callback query to close the loading indicator
        self.answer_callback_query(callback_id)

        # Check if this is a category selection
        if user_id in user_states and user_states[user_id]["state"] == STATE_AWAITING_CATEGORY:
            if data in CATEGORIES:
                message_data = user_states.get(user_id, {}).get("message_data", None)
                user_states[user_id] = {
                    "category": data,
                    "state": STATE_AWAITING_DESCRIPTION
                }
                if message_data:
                    user_states[user_id]["message_data"] = message_data

                self.process_category(chat_id, user_id, data)

    def cmd_start(self, chat_id, user_id, message):
        """Handle the /start command."""
        first_name = message.get("from", {}).get("first_name", "there")

        user_states[user_id] = {
            "state": STATE_IDLE,
            "message_data": message
        }

        reply_markup = {
            "keyboard": [
                [{"text": "report"}],
                [{"text": "refund"}],
            ],
            "resize_keyboard": True
        }

        self.send_message(
            chat_id,
            f"🩰⠀hello <b>@{message.get('from', {}).get('username', 'user')}</b>!\n\n"
            "⠀⠀This is the report bot for @xnnprems.\n"
            "⠀⠀⠀for updates, join our main channel\n\n"
            "<b>report</b> - to report a problem with your purchase\n"
            "<b>refund</b> - to request a refund of your purchase\n\n"
            "❗️⠀<b>reminders:</b>\n"
            "⠀.⠀make sure that the informations you provided\n"
            "⠀⠀are correct and true\n"
            "⠀.⠀refunds will only be given if we can no longer\n"
            "⠀⠀ fix the premium acc you purchased\n"
            "⠀.⠀do not request a refund if hindi ka namin\n"
            "⠀⠀ sinabihan",
            reply_markup=reply_markup
        )

    def cmd_report(self, chat_id, user_id):
        """Handle the report command."""
        message_data = user_states.get(user_id, {}).get("message_data", None)
        user_states[user_id] = {"state": STATE_AWAITING_CATEGORY}

        if message_data:
            user_states[user_id]["message_data"] = message_data

        keyboard = []
        for category in CATEGORIES:
            keyboard.append([{"text": category, "callback_data": category}])

        reply_markup = {"inline_keyboard": keyboard}

        self.send_message(
            chat_id,
            "Let's start your report. First, please select the category that best describes your issue:",
            reply_markup=reply_markup
        )

    def process_category(self, chat_id, user_id, category):
        """Process the selected category and show appropriate form."""
        if category == "Discord Items":
            self.send_message(
                chat_id,
                "🩰⠀<b>Discord Report Form</b>\n\n"
                "<code>discord username:</code>\n"
                "<code>item purchased:</code>\n"
                "<code>date of purchase:</code>\n"
                "<code>issue description:</code>\n\n"
                "❗️ Please fill out all fields in your response"
            )
        elif category == "Premiums":
            self.send_message(
                chat_id,
                "🩰⠀<b>Premium Report Form</b>\n\n"
                "<code>⠀﹒ premium availed : </code>\n"
                "<code>⠀﹒ solo or shared : </code>\n"
                "<code>⠀﹒ price paid : </code>\n"
                "<code>⠀﹒ email : </code>\n"
                "<code>⠀﹒ password : </code>\n"
                "<code>⠀﹒ date reported : </code>\n"
                "<code>⠀﹒ days used : </code>\n"
                "<code>⠀﹒ remaining days : </code>\n"
                "<code>⠀﹒ issue : </code>\n\n"
                "<b>ꕀ⠀include this in your form</b>\n"
                "⠀✅⠀proof of vouch\n"
                "⠀✅⠀proof of issue"
            )

    def cmd_refund(self, chat_id, user_id):
        """Handle the refund command."""
        message_data = user_states.get(user_id, {}).get("message_data", None)

        user_states[user_id] = {
            "category": "Refund",
            "state": STATE_AWAITING_DESCRIPTION
        }

        if message_data:
            user_states[user_id]["message_data"] = message_data

        self.send_message(
            chat_id,
            "🩰⠀<b>Refund Form</b>\n\n"
            "<code>username:</code>\n"
            "<code>date of purchase:</code>\n"
            "<code>price paid:</code>\n"
            "<code>days of subscription:</code>\n"
            "<code>remaining days:</code>\n"
            "<code>gcash number:</code>\n\n"
            "❗️<b>note:</b> there will be an 8% or 0.80 service fee\n\n"
            "<b>formula:</b> price / days of sub x 0.8 x (remaining days)"
        )

    def send_photo(self, chat_id, photo, caption=None, is_file=False):
        """Send a photo to a chat."""
        try:
            if is_file:
                files = {'photo': ('photo.jpg', photo, 'image/jpeg')}
                data = {'chat_id': chat_id, 'parse_mode': 'HTML'}
                if caption:
                    data['caption'] = caption
                response = requests.post(f"{self.api_url}/sendPhoto", data=data, files=files)
            else:
                data = {
                    "chat_id": chat_id,
                    "photo": photo,
                    "parse_mode": "HTML"
                }
                if caption:
                    data["caption"] = caption
                response = requests.post(f"{self.api_url}/sendPhoto", data=data)

            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error sending photo: {e}")
            return None

    def cmd_respond(self, chat_id, user_id, text, update=None):
        """Handle the respond command from admins."""
        try:
            # Check if this is a photo response
            if update and "message" in update and "photo" in update["message"]:
                caption = update["message"].get("caption", "")
                if not caption or not caption.startswith("/respond"):
                    self.send_message(chat_id, "❌ Usage: Send photo with caption: /respond [user_id] [message]")
                    return

                # Parse the caption
                parts = caption.split(maxsplit=2)
                if len(parts) < 3:
                    self.send_message(chat_id, "❌ Usage: Send photo with caption: /respond [user_id] [message]")
                    return

                target_user_id = parts[1]
                response_text = parts[2]

                try:
                    # Get the photo file_id (largest size)
                    photo = update["message"]["photo"][-1]["file_id"]
                    
                    # Send photo to user
                    response = self.send_photo_to_channel(target_user_id, photo, f"📬 <b>Admin Response:</b>\n\n{response_text}")
                    if not response:
                        raise Exception("Failed to send photo to user")
                    
                    # Send photo to response channel
                    channel_caption = (
                        f"📬 <b>Admin Response</b>\n\n"
                        f"<b>To User:</b> <a href='tg://user?id={target_user_id}'>{target_user_id}</a>\n"
                        f"<b>Response:</b>\n{response_text}"
                    )
                    response = self.send_photo_to_channel(RESPONSE_CHANNEL_ID, photo, channel_caption)
                    if not response:
                        raise Exception("Failed to send photo to response channel")
                    
                    # Confirm to admin
                    self.send_message(chat_id, "✅ Photo response sent successfully!")
                    return
                except Exception as e:
                    logger.error(f"Error sending photo response: {e}")
                    self.send_message(chat_id, "❌ Failed to send photo response. Please try again.")
                    return
            else:
                # Regular text response
                parts = text.split(maxsplit=2)
                if len(parts) < 3:
                    self.send_message(chat_id, "❌ Usage: /respond [user_id] [message]")
                    return

                target_user_id = parts[1]
                response_text = parts[2]

                # Send to user
                user_msg = f"❗⠀<b>Admin Response:</b>\n\n{response_text}"
                self.send_message(target_user_id, user_msg)

                # Send to response channel
                channel_msg = (
                    f"📬 <b>Admin Response</b>\n\n"
                    f"<b>To User:</b> <a href='tg://user?id={target_user_id}'>{target_user_id}</a>\n"
                    f"<b>Response:</b>\n{response_text}"
                )
                self.send_message("-1002326727802", channel_msg)

            # Confirm to admin
            self.send_message(chat_id, "✅ Response sent successfully!")

        except Exception as e:
            logger.error(f"Error in respond command: {e}")
            self.send_message(chat_id, "❌ Failed to send response. Please try again.")

    def cmd_debug_channel(self, chat_id, user_id, text):
        """Special admin command to debug channel issues."""
        parts = text.strip().split()
        new_channel_id = parts[1] if len(parts) > 1 else None

        self.send_message(
            chat_id,
            f"Debug Info:\n"
            f"• Your Chat ID: <b>{chat_id}</b>\n"
            f"• Your User ID: <b>{user_id}</b>\n"
            f"• Current Channel ID setting: <b>{CHANNEL_ID}</b>\n\n"
            "To make channel forwarding work:\n"
            "1. Add this bot as an admin to your channel\n"
            "2. Make sure it has permission to post messages\n"
            "3. Get the channel ID (you may need to use a channel ID bot)\n\n"
            "You can test sending directly to a channel with:\n"
            "/debug_channel YOUR_CHANNEL_ID"
        )

        if new_channel_id:
            test_msg = (
                "🧪 <b>TEST MESSAGE</b>\n\n"
                "This is a test message sent to verify channel connectivity.\n"
                f"Sent by user ID: {user_id}\n"
                f"Timestamp: {datetime.now(pytz.timezone('Asia/Manila')).strftime('%Y-%m-%d %H:%M:%S')}"
            )

            try:
                logger.info(f"Attempting to send test message to channel ID: {new_channel_id}")
                response = self.send_message(new_channel_id, test_msg)

                if response and response.get("ok", False):
                    self.send_message(
                        chat_id,
                        f"✅ Test message successfully sent to channel ID: <b>{new_channel_id}</b>"
                    )
                    logger.info(f"Successfully sent test message to channel: {new_channel_id}")
                else:
                    self.send_message(
                        chat_id,
                        f"❌ Failed to send test message to channel ID: <b>{new_channel_id}</b>\n"
                        f"Error: {response}\n\n"
                        "Possible causes:\n"
                        "• Bot is not a channel admin\n"
                        "• Channel ID is incorrect\n"
                        "• Bot doesn't have post permission"
                    )
                    logger.error(f"Failed to send test message to channel: {response}")
            except Exception as e:
                self.send_message(
                    chat_id,
                    f"❌ Error when trying to send to channel: <b>{str(e)}</b>"
                )
                logger.error(f"Error in debug channel command: {e}")

    def process_description(self, chat_id, user_id, description):
        """Process the description from a user."""
        if user_id not in user_states or "category" not in user_states[user_id]:
            self.send_message(chat_id, "Sorry, I've lost track of your report. Please start over with /report")
            user_states[user_id] = {"state": STATE_IDLE}
            return

        category = user_states[user_id]["category"]
        user_data = user_states[user_id].get("message_data", {}).get("from", {})
        username = user_data.get("username", f"user_{user_id}")
        first_name = user_data.get("first_name", "Customer")

        report_id = save_report(user_id, username, category, description)

        if report_id:
            if category == "Refund":
                channel_msg = (
                    f"🩰⠀ <b>Refund Request</b>\n\n"
                    f"<b>Report ID:</b> xnn_{report_id}\n"
                    f"<b>Submitted:</b> {datetime.now(pytz.timezone('Asia/Manila')).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"<b>Requested by:</b> <a href='tg://user?id={user_id}'>@{username}</a>\n"
                    f"<b>User ID:</b> {user_id}\n\n"
                    f"<b>Details:</b>\n{description}"
                )
            else:
                channel_msg = (
                    f"🩰⠀ <b>{category} Report</b>\n\n"
                    f"<b>Report ID:</b> xnn_{report_id}\n"
                    f"<b>Submitted:</b> {datetime.now(pytz.timezone('Asia/Manila')).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"<b>Reported by:</b> <a href='tg://user?id={user_id}'>@{username}</a>\n"
                    f"<b>User ID:</b> {user_id}\n\n"
                    f"<b>Details:</b>\n{description}"
                )

            channel_response = self.send_to_channel(channel_msg)

            if channel_response and channel_response.get("ok", False):
                logger.info(f"Report #{report_id} was forwarded to the channel")
                success_msg = (
                    f"✅ Your report has been submitted successfully!\n\n"
                    f"<b>Report ID:</b> <tg-spoiler>xnn_{report_id}</tg-spoiler>\n\n"
                    "❗ <b>reminders:</b>\n"
                    "⠀﹒ do not spam the admins for updates\n"
                    "⠀﹒ no update means, hindi pa na ayos report mo\n"
                    "⠀﹒ 5-7 days or up waiting time for reports\n"
                )
                self.send_message(chat_id, success_msg)
            else:
                logger.error(f"Failed to forward report #{report_id} to the channel")
                error_msg = (
                    "❌ There was an issue forwarding your report to our admins.\n"
                    "Please try again later or contact support directly."
                )
                self.send_message(chat_id, error_msg)
        else:
            self.send_message(
                chat_id,
                "Sorry, there was an error saving your report. Please try again later."
            )

        user_states[user_id] = {"state": STATE_IDLE}

    def run(self):
        """Run the bot polling loop."""
        logger.info("Starting bot polling loop...")

        while True:
            try:
                updates = self.get_updates()

                for update in updates:
                    logger.debug(f"Received update: {update}")

                    if "message" in update:
                        self.process_command(update)
                    elif "callback_query" in update:
                        self.process_callback_query(update)

                time.sleep(1)

            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                time.sleep(10)

def run_bot():
    """Run the bot in a background thread."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("No TELEGRAM_BOT_TOKEN found in environment variables")
        return

    init_db()

    try:
        bot = TelegramBot(token)
        bot.run()
    except Exception as e:
        logger.error(f"Bot crashed: {e}")

def main():
    """Main function."""
    thread = Thread(target=run_bot)
    thread.daemon = True
    thread.start()

    logger.info("Bot is running in background. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")

if __name__ == "__main__":
    main()