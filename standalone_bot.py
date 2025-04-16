#!/usr/bin/env python3
"""
Standalone Telegram bot for handling purchase issue reports.
This runs completely independently from the Flask application.
"""
import os
import sys
import json
import logging
import asyncio
import sqlite3
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
logger = logging.getLogger(__name__)

# Import Telegram libraries
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler
    from telegram.ext import ContextTypes, filters, ConversationHandler
except ImportError as e:
    logger.error(f"Failed to import Telegram libraries: {e}")
    logger.error("Please install the python-telegram-bot package with: pip install python-telegram-bot")
    sys.exit(1)

# Issue categories
CATEGORIES = [
    "Delivery Issue", 
    "Product Quality", 
    "Wrong Item", 
    "Damaged Package", 
    "Payment Issue",
    "Missing Parts",
    "Other"
]

# Define conversation states
CATEGORY, DESCRIPTION = range(2)

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the command /start is issued."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.first_name}) started the bot")
    
    await update.message.reply_text(
        f"Hello {user.first_name}! 👋\n\n"
        "I'm the Purchase Issue Reporter Bot. I can help you report problems with your purchases.\n\n"
        "Use /report to start a new issue report.\n"
        "Use /help to see all available commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "Here are the available commands:\n\n"
        "/start - Start the bot\n"
        "/report - Report a new purchase issue\n"
        "/cancel - Cancel the current operation\n"
        "/help - Show this help message"
    )

async def start_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the report process by asking for the category."""
    keyboard = [[InlineKeyboardButton(category, callback_data=category)] for category in CATEGORIES]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Let's start your report. First, please select the category that best describes your issue:",
        reply_markup=reply_markup
    )
    
    return CATEGORY

async def category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the selected category and ask for description."""
    query = update.callback_query
    await query.answer()
    
    category = query.data
    context.user_data['category'] = category
    
    await query.message.reply_text(
        f"You selected: {category}\n\n"
        "Now, please provide a detailed description of the issue. Include relevant information like:\n"
        "- Order number (if applicable)\n"
        "- Date of purchase\n"
        "- What exactly went wrong\n\n"
        "Type your description below:"
    )
    
    return DESCRIPTION

async def report_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the description and complete the report."""
    user = update.effective_user
    description = update.message.text
    category = context.user_data.get('category')
    
    logger.info(f"Report from {user.id} ({user.username or user.first_name}): {category}")
    
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
    
    await update.message.reply_text(
        f"Thank you! Your report (ID: {report_id}) has been submitted successfully.\n\n"
        f"Category: {category}\n"
        "Our team will review your issue and take appropriate action. If needed, we may contact you for additional information.\n\n"
        "You can submit another report using the /report command."
    )
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel and end the conversation."""
    await update.message.reply_text(
        "Report process cancelled. If you want to submit a report later, use the /report command."
    )
    return ConversationHandler.END

async def main():
    """Start the bot."""
    # Get the token from environment
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("No TELEGRAM_BOT_TOKEN found in environment variables!")
        return
    
    logger.info(f"Starting bot with token: {token[:4]}...")
    
    # Build the application
    application = ApplicationBuilder().token(token).build()
    
    # Add conversation handler for reporting
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('report', start_report)],
        states={
            CATEGORY: [CallbackQueryHandler(category_selected)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_description)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(conv_handler)
    
    # Initialize the database
    init_db()
    
    # Start the bot with polling
    logger.info("Starting polling...")
    await application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    # Run the async function
    asyncio.run(main())