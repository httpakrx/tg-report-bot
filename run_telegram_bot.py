
import os
import asyncio
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler
from telegram.ext import ContextTypes, filters, ConversationHandler

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('telegram_bot')

# Set up the token
token = "7381319935:AAEgBbUDpF-3mfHkwDJo18NIq0Rxv7d5OPM"

# Define conversation states
CATEGORY, DESCRIPTION = range(2)

# Categories
CATEGORIES = ['Delivery Issue', 'Product Quality', 'Wrong Item', 'Damaged Package', 'Payment Issue', 'Missing Parts', 'Other']

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the command /start is issued."""
    user = update.effective_user
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
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
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
    """Send report to webhook for storage."""
    user = update.effective_user
    description = update.message.text
    category = context.user_data.get('category')
    
    # Create report data
    report_data = {
        'user_id': user.id,
        'username': user.username or f"{user.first_name} {user.last_name or ''}".strip(),
        'category': category,
        'description': description
    }
    
    # This will be logged, so the Flask app can see it's working
    logger.info(f"REPORT_DATA: {report_data}")
    
    # Here we would typically send this to a webhook, but for now we'll just log it
    await update.message.reply_text(
        f"Thank you! Your report has been submitted successfully.\n\n"
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
    """Run the bot."""
    logger.info("Starting bot with token: %s...", token[:4] + "...")
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
    
    logger.info("Starting the bot polling...")
    await application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    asyncio.run(main())
