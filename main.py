import os
import io
import re
import sqlite3
import logging
import numpy as np
from PIL import Image
import easyocr

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# -----------------------------------------------------------------------------
# LOGGING CONFIGURATION
# -----------------------------------------------------------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("OKXETH_P2P_BOT")

# AI OCR Reader Initialization
logger.info("Initializing AI OCR Engine...")
ocr_reader = easyocr.Reader(['en'], gpu=False)

# -----------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_ID = 7798227927  # Owner/Admin Telegram ID

# 🎯 አዲሱ የምንዛሬ ተመን ወደ 189 Birr ተቀይሯል
DEFAULT_RATE = 189.0

TELEBIRR_NUMBER = "0900253321"
ADMIN_NAME = "Bereket"
ADMIN_WALLET_ADDRESS = "TMAbfELuLH7gGyjp6YgUV1WWpPYwhaE27V"

# የቀን ገደብ (Min: $20, Max: $600)
MIN_USD = 20.0
MAX_USD = 600.0

ORDER_TIMEOUT_SECONDS = 30 * 60  # 30 ደቂቃ (1800 ሰከንድ)

# -----------------------------------------------------------------------------
# CONVERSATION STATES
# -----------------------------------------------------------------------------
(
    LANG,
    TRADE_TYPE,
    AMOUNT,
    BUY_PAYMENT_CHOICE,
    PAYMENT_CHOICE,
    SCREENSHOT,
    WALLET_ADDRESS,
    SELL_SCREENSHOT,
    SELL_TELEBIRR,
    SUPPORT_MSG,
) = range(10)

# -----------------------------------------------------------------------------
# DATABASE MANAGEMENT
# -----------------------------------------------------------------------------
DB_FILE = "bot_data.db"

def init_db() -> None:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value REAL
                )
            ''')
            # ተመኑን በዳታቤዝ ውስጥ ወደ 189 ማዘመን
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('rate', ?)", (DEFAULT_RATE,))
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    trade_type TEXT,
                    amount_usd REAL,
                    total_birr REAL,
                    status TEXT DEFAULT 'PENDING',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            conn.commit()
            cursor.execute("VACUUM;")
    except Exception as e:
        logger.error(f"Error initializing DB: {e}")

init_db()

def db_get_rate() -> float:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'rate'")
            row = cursor.fetchone()
            return float(row[0]) if row else DEFAULT_RATE
    except Exception as e:
        logger.error(f"Error fetching rate: {e}")
        return DEFAULT_RATE

def db_set_rate(new_rate: float) -> bool:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE settings SET value = ? WHERE key = 'rate'", (new_rate,))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error setting rate: {e}")
        return False

def record_user(user_id: int, username: str) -> None:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
            conn.commit()
    except Exception as e:
        logger.error(f"Error recording user: {e}")

def record_order(user_id: int, trade_type: str, amount_usd: float, total_birr: float) -> None:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO orders (user_id, trade_type, amount_usd, total_birr) VALUES (?, ?, ?, ?)",
                (user_id, trade_type, amount_usd, total_birr)
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Error recording order: {e}")

def get_stats() -> dict:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*), SUM(total_birr) FROM orders")
            row = cursor.fetchone()
            total_orders = row[0] or 0
            total_volume = row[1] or 0.0

            return {
                "users": total_users,
                "orders": total_orders,
                "volume": total_volume
            }
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        return {"users": 0, "orders": 0, "volume": 0.0}

# -----------------------------------------------------------------------------
# AI SCREENSHOT VERIFIER (OCR LOGIC)
# -----------------------------------------------------------------------------
async def verify_screenshot_ai(photo_bytes: bytes, expected_amount: float) -> tuple[bool, str]:
    try:
        image = Image.open(io.BytesIO(photo_bytes))
        image_np = np.array(image)
        results = ocr_reader.readtext(image_np)
        
        extracted_text = " ".join([text for (_, text, _) in results])
        logger.info(f"AI Extracted Text: {extracted_text}")

        formatted_amount_1 = f"{expected_amount:.2f}"
        formatted_amount_2 = f"{int(expected_amount)}" if expected_amount.is_integer() else f"{expected_amount:.2f}"

        if formatted_amount_1 in extracted_text or formatted_amount_2 in extracted_text:
            return True, "✅ **AI Verification:** Amount Matched in Screenshot!"
        else:
            return False, "⚠️ **AI Verification Warning:** Expected amount NOT detected clearly. Please verify manually!"
    except Exception as e:
        logger.error(f"AI Verification Error: {e}")
        return False, "⚠️ **AI Verification Warning:** Could not read image properly. Please verify manually."

# -----------------------------------------------------------------------------
# TIMEOUT JOB FUNCTION
# -----------------------------------------------------------------------------
async def order_timeout_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    chat_id = job.data["chat_id"]
    message_id = job.data.get("message_id")

    if message_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Could not delete message {message_id}: {e}")

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "⏰ <b>የ 30 ደቂቃ ጊዜዎ አብቅቷል!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "ትዕዛዝዎ አውቶማቲክ ተሰርዟል። እባክዎን እንደገና ለመጀመር /start ይበሉ።"
        ),
        parse_mode="HTML"
    )

def cancel_existing_timer(context: ContextTypes.DEFAULT_TYPE) -> None:
    current_jobs = context.job_queue.get_jobs_by_name("order_timer")
    for job in current_jobs:
        job.schedule_removal()

# -----------------------------------------------------------------------------
# PERMANENT KEYBOARD & TEXTS
# -----------------------------------------------------------------------------
PERMANENT_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("🔄 Main Menu / Restart")]],
    resize_keyboard=True
)

TEXTS = {
    'am': {
        'welcome': (
            "🏦 <b>OKXETH OFFICIAL P2P TRADING BOT</b> 🏦\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "👋 <b>እንኳን ወደ አስተማማኙ የ P2P የምንዛሬ ቦት በሰላም መጡ!</b>\n\n"
            "📊 <b>የዛሬው የምንዛሬ ተመን፦</b>\n"
            "└ <code>1 USD = {rate:,.2f} ETB</code>\n\n"
            "💳 <b>የክፍያ መንገዶች:</b> <code>Telebirr | Mastercard | Binance Pay</code>\n"
            "⚡ <i>ፈጣን፣ አስተማማኝ እና ሙሉ ደህንነቱ የተጠበቀ አገልግሎት!</i>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "👇 <b>እባክዎን ማድረግ የሚፈልጉትን ይምረጡ፦</b>"
        ),
        'enter_amount_buy': (
            "🟢 <b>የግዢ መጠን ያስገቡ (BUY USD)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 <b>የቀን የግዢ ወሰን፦</b>\n"
            "├ <b>አነስተኛ:</b> <code>${min:,.2f} USD</code>\n"
            "└ <b>ከፍተኛ:</b> <code>${max:,.2f} USD</code>\n\n"
            "✍️ <i>መግዛት የሚፈልጉትን የ USD መጠን በቁጥር ብቻ ያስገቡ፦</i>"
        ),
        'enter_amount_sell': (
            "🔴 <b>የመሸጫ መጠን ያስገቡ (SELL USD)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 <b>የቀን የመሸጫ ወሰን፦</b>\n"
            "├ <b>አነስተኛ:</b> <code>${min:,.2f} USD</code>\n"
            "└ <b>ከፍተኛ:</b> <code>${max:,.2f} USD</code>\n\n"
            "✍️ <i>መሸጥ የሚፈልጉትን የ USD መጠን በቁጥር ብቻ ያስገቡ፦</i>"
        ),
        'invalid_num': "⚠️ <b>የተሳሳተ ቁጥር!</b>\nእባክዎን ከ <b>${min:,.2f}</b> እስከ <b>${max:,.2f} USD</b> ባለው የቀን ወሰን ውስጥ ብቻ ያስገቡ፦",
        'select_pay_method': (
            "💳 <b>የክፍያ መንገድ ይምረጡ (Payment Method)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "ለመግዛት የሚፈልጉበትን የክፍያ አማራጭ ከታች ይምረጡ፦"
        ),
        'summary_buy': (
            "🧾 <b>የግዢ ትዕዛዝ ማጠቃለያ (BUY RECEIPT)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n
