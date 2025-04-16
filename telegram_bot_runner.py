#!/usr/bin/env python3
"""
Simple bot runner script that uses a synchronous approach to avoid event loop conflicts.
"""
import os
import sys
import logging
import sqlite3
import threading
import time
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("telegram_bot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("telegram_bot_runner")

# Import Telegram libraries with error handling
try:
    import telegram
except ImportError as e:
    logger.error(f"Failed to import Telegram libraries: {e}")
    logger.error("Please install the python-telegram-bot package with: pip install python-telegram-bot")
    sys.exit(1)

# Database setup
DB_PATH = "instance/telegram_bot.db"

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
    """Simple, synchronous Telegram bot implementation."""
    
    def __init__(self, token):
        self.token = token
        self.bot = telegram.Bot(token=token)
        self.categories = [
            "Delivery Issue", 
            "Product Quality", 
            "Wrong Item", 
            "Damaged Package", 
            "Payment Issue",
            "Missing Parts",
            "Other"
        ]
        # Track user conversation states
        self.user_states = {}  # user_id -> state
        self.user_data = {}    # user_id -> data dict
        
        # Define state constants
        self.STATE_INIT = 0
        self.STATE_CATEGORY = 1
        self.STATE_DESCRIPTION = 2
        
        # Initialize the database
        init_db()
        
        # Last processed update ID
        self.last_update_id = 0
    
    def run(self):
        """Main bot polling loop."""
        logger.info("Starting bot polling...")
        
        while True:
            try:
                # Get updates using long polling
                updates = self.bot.get_updates(offset=self.last_update_id + 1, timeout=30)
                
                for update in updates:
                    # Process each update
                    self.process_update(update)
                    
                    # Update the last processed update ID
                    self.last_update_id = update.update_id
                
                # Sleep a bit to reduce CPU usage
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                # Wait a bit before trying again
                time.sleep(5)
    
    def process_update(self, update):
        """Process a single update from Telegram."""
        # Command handling
        if update.message and update.message.text:
            user_id = update.effective_user.id
            text = update.message.text
            
            # Process commands
            if text == '/start':
                self.cmd_start(update)
                self.user_states[user_id] = self.STATE_INIT
            elif text == '/help':
                self.cmd_help(update)
                self.user_states[user_id] = self.STATE_INIT
            elif text == '/report':
                self.cmd_report(update)
                self.user_states[user_id] = self.STATE_CATEGORY
            elif text == '/cancel':
                self.cmd_cancel(update)
                self.user_states[user_id] = self.STATE_INIT
            # Process conversation states
            elif user_id in self.user_states:
                state = self.user_states[user_id]
                
                if state == self.STATE_DESCRIPTION:
                    self.process_description(update)
                    self.user_states[user_id] = self.STATE_INIT
        
        # Callback query handling (for inline keyboard buttons)
        elif update.callback_query:
            user_id = update.effective_user.id
            
            if user_id in self.user_states and self.user_states[user_id] == self.STATE_CATEGORY:
                self.process_category(update)
                self.user_states[user_id] = self.STATE_DESCRIPTION
    
    def cmd_start(self, update):
        """Handle the /start command."""
        user = update.effective_user
        logger.info(f"User {user.id} ({user.first_name}) started the bot")
        
        keyboard = telegram.ReplyKeyboardMarkup([['/report'], ['/help']], resize_keyboard=True)
        
        self.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Hello {user.first_name}! 👋\n\n"
                 "I'm the Purchase Issue Reporter Bot. I can help you report problems with your purchases.\n\n"
                 "Use /report to start a new issue report.\n"
                 "Use /help to see all available commands.",
            reply_markup=keyboard
        )
    
    def cmd_help(self, update):
        """Handle the /help command."""
        self.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Here are the available commands:\n\n"
                 "/start - Start the bot\n"
                 "/report - Report a new purchase issue\n"
                 "/cancel - Cancel the current operation\n"
                 "/help - Show this help message"
        )
    
    def cmd_report(self, update):
        """Handle the /report command."""
        keyboard = []
        for category in self.categories:
            keyboard.append([telegram.InlineKeyboardButton(category, callback_data=category)])
        
        reply_markup = telegram.InlineKeyboardMarkup(keyboard)
        
        self.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Let's start your report. First, please select the category that best describes your issue:",
            reply_markup=reply_markup
        )
    
    def cmd_cancel(self, update):
        """Handle the /cancel command."""
        user_id = update.effective_user.id
        
        # Clear any stored data for this user
        if user_id in self.user_data:
            del self.user_data[user_id]
        
        self.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Report process cancelled. If you want to submit a report later, use the /report command."
        )
    
    def process_category(self, update):
        """Process the selected category."""
        user_id = update.effective_user.id
        query = update.callback_query
        category = query.data
        
        # Store the category for this user
        if user_id not in self.user_data:
            self.user_data[user_id] = {}
        
        self.user_data[user_id]['category'] = category
        
        # Answer the callback query to remove the loading indicator
        self.bot.answer_callback_query(callback_query_id=query.id)
        
        # Send a message to request the description
        self.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"You selected: {category}\n\n"
                 "Now, please provide a detailed description of the issue. Include relevant information like:\n"
                 "- Order number (if applicable)\n"
                 "- Date of purchase\n"
                 "- What exactly went wrong\n\n"
                 "Type your description below:"
        )
    
    def process_description(self, update):
        """Process the issue description."""
        user_id = update.effective_user.id
        user = update.effective_user
        description = update.message.text
        
        if user_id not in self.user_data or 'category' not in self.user_data[user_id]:
            # Something went wrong, start over
            self.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Sorry, I lost track of your report. Please start over with /report"
            )
            return
        
        category = self.user_data[user_id]['category']
        
        # Get a username or a fallback
        username = user.username
        if not username:
            username = f"{user.first_name} {user.last_name or ''}".strip()
        
        # Save to database
        report_id = save_report(
            user_id=user.id,
            username=username,
            category=category,
            description=description
        )
        
        # Send confirmation
        self.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Thank you! Your report (ID: {report_id}) has been submitted successfully.\n\n"
                 f"Category: {category}\n"
                 "Our team will review your issue and take appropriate action. If needed, we may contact you for additional information.\n\n"
                 "You can submit another report using the /report command."
        )
        
        # Clear stored data
        del self.user_data[user_id]

def main():
    """Main function to start the bot."""
    # Get the token from environment
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("No TELEGRAM_BOT_TOKEN found in environment variables!")
        return
    
    logger.info(f"Starting bot with token: {token[:4]}...")
    
    # Create and run the bot
    bot = TelegramBot(token)
    
    try:
        # Start the bot in a separate thread to avoid blocking
        bot_thread = threading.Thread(target=bot.run)
        bot_thread.daemon = True  # Allow the program to exit even if the thread is running
        bot_thread.start()
        
        # Keep the main thread alive
        logger.info("Bot is running in background thread...")
        while True:
            time.sleep(60)  # Check every minute
            if not bot_thread.is_alive():
                logger.error("Bot thread died, restarting...")
                bot_thread = threading.Thread(target=bot.run)
                bot_thread.daemon = True
                bot_thread.start()
            
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error in main thread: {e}")

if __name__ == "__main__":
    main()