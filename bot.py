import os
import logging
import subprocess

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

def start_bot():
    """Start the Telegram bot as a separate process."""
    logger.info("Starting the Telegram bot...")
    
    # Check if we have a token
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not found in environment variables! Bot functionality will be disabled.")
        return
    
    try:
        # Kill any existing bot processes
        try:
            subprocess.run(["pkill", "-f", "telegram_api_bot.py"], stderr=subprocess.PIPE)
            logger.info("Killed any existing bot processes")
        except Exception as e:
            logger.warning(f"Could not kill existing processes: {e}")
        
        # Start the bot as a separate process
        bot_process = subprocess.Popen(["python", "telegram_api_bot.py"])
        logger.info(f"Started Telegram bot process (PID: {bot_process.pid})")
        
        # Wait a moment to make sure it didn't crash immediately
        try:
            return_code = bot_process.wait(timeout=1)
            logger.error(f"Bot process exited immediately with code {return_code}")
        except subprocess.TimeoutExpired:
            # This is good - it means the process is still running
            logger.info("Bot process is running")
            
    except Exception as e:
        logger.error(f"Error starting Telegram bot: {e}")
        logger.info("Continuing without bot functionality")