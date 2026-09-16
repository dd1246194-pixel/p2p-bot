# type: ignore
import os
import sqlite3
import logging
from enum import Enum, auto
from typing import Any
from threading import Thread
from flask import Flask
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

# -----------------------------------------------------------------------------
# CONFIGURATION & ENVIRONMENT VARIABLES
# -----------------------------------------------------------------------------
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_ID = 7798227927
DEFAULT_RATE = 184.0
TELEBIRR_NUMBER = "0900253321"
ADMIN_WALLET_ADDRESS = "TMAbfELuLH7gGyjp6YgUV1WWpPYwhaE27V"

MIN_USD = 10.0
MAX_USD = 2100.0

# -----------------------------------------------------------------------------
# CONVERSATION STATES
# -----------------------------------------------------------------------------
class State(Enum):
    LANG = auto()
    TRADE_TYPE = auto()
    AMOUNT = auto()
    PAYMENT = auto()
    SCREENSHOT = auto()
    WALLET_ADDRESS = auto()
    SELL_SCREENSHOT = auto()
    SELL_TELEBIRR = auto()
    SUPPORT_MSG = auto()

# Unpack states for Telegram ConversationHandler compatibility
(
    LANG,
    TRADE_TYPE,
    AMOUNT,
    PAYMENT,
    SCREENSHOT,
    WALLET_ADDRESS,
    SELL_SCREENSHOT,
    SELL_TELEBIRR,
    SUPPORT_MSG
) = range(9)

# -----------------------------------------------------------------------------
# FLASK WEB SERVER (HEALTH CHECK / KEEP-ALIVE)
# -----------------------------------------------------------------------------
app_web = Flask(__name__)

@app_web.route('/')
def health_check():
    return "OKXETH P2P Bot Service Status: ONLINE (24/7 Active)", 200

def run_flask():
    app_web.run(host='0.0.0.0', port=8080)

# -----------------------------------------------------------------------------
# DATABASE MANAGEMENT SYSTEM
# -----------------------------------------------------------------------------
DB_FILE = "bot_data.db"

def init_db() -> None:
    """Initializes SQLite database schemas."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value REAL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                total_orders INTEGER DEFAULT 0,
                total_usd_volume REAL DEFAULT 0.0
            )
        ''')
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('rate', ?)", (DEFAULT_RATE,))
        cursor.execute("INSERT OR IGNORE INTO stats (id, total_orders, total_usd_volume) VALUES (1, 0, 0.0)")
        conn.commit()

init_db()

def db_get_rate() -> float:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'rate'")
            row = cursor.fetchone()
            return float(row[0]) if row else DEFAULT_RATE
    except Exception as e:
        logger.error(f"Error fetching rate from DB: {e}")
        return DEFAULT_RATE

def db_set_rate(new_rate: float) -> None:
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE settings SET value = ? WHERE key = 'rate'", (new_rate,))
        conn.commit()

def db_update_stats(usd_amount: float) -> None:
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE stats SET total_orders = total_orders + 1, total_usd_volume = total_usd_volume + ? WHERE id = 1", 
            (usd_amount,)
        )
        conn.commit()

def db_get_stats() -> tuple[int, float]:
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT total_orders, total_usd_volume FROM stats WHERE id = 1")
        row = cursor.fetchone()
        return row if row else (0, 0.0)

# -----------------------------------------------------------------------------
# GLOBAL STATE & MEMORY MANAGEMENT
# -----------------------------------------------------------------------------
active_orders: set[int] = set()
maintenance_mode: bool = False

PERMANENT_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("🔄 Main Menu / Restart")]],
    resize_keyboard=True
)

# -----------------------------------------------------------------------------
# LOCALIZATION RESOURCES (I18N)
# -----------------------------------------------------------------------------
TEXTS = {
    'am': {
        'welcome': (
            "💎 ─────────────── 💎\n"
            "✨ <b>OKXETH P2P TRADING BOT</b> ✨\n"
            "💎 ─────────────── 💎\n\n"
            "📈 <b>የዛሬ የምንዛሬ ተመን፦</b> <code>1 USD = {rate} Birr</code>\n\n"
            "👇 <b>እባክዎን ማድረግ የሚፈልጉትን ይምረጡ፦</b>"
        ),
        'enter_amount_buy': (
            "📊 <b>የግዢ ወሰን (Trading Limits)፦</b>\n"
            "├ 🟢 <b>አነስተኛ (Min):</b> <code>${min:,.0f} USD</code>\n"
            "└ 🔴 <b>ከፍተኛ (Max):</b> <code>${max:,.0f} USD</code>\n"
            "───────────────────\n\n"
            "✍️ <b>መግዛት የሚፈልጉትን መጠን (USD) ያስገቡ፦</b>\n"
            "💡 <i>ምሳሌ፦ 10, 50, 100</i>"
        ),
        'enter_amount_sell': (
            "📊 <b>የመሸጫ ወሰን (Trading Limits)፦</b>\n"
            "├ 🟢 <b>አነስተኛ (Min):</b> <code>${min:,.0f} USD</code>\n"
            "└ 🔴 <b>ከፍተኛ (Max):</b> <code>${max:,.0f} USD</code>\n"
            "───────────────────\n\n"
            "✍️ <b>መሸጥ የሚፈልጉትን መጠን (USD) ያስገቡ፦</b>\n"
            "💡 <i>ምሳሌ፦ 10, 50, 100</i>"
        ),
        'invalid_num': (
            "⚠️ <b>የተሳሳተ የቁጥር መጠን!</b>\n"
            "───────────────────\n"
            "እባክዎን ከ <b>${min:,.0f}</b> እስከ <b>${max:,.0f} USD</b> ባለው ወሰን ውስጥ ብቻ ያስገቡ፦"
        ),
        'summary_buy': (
            "📋 <b>የግዢ ማጠቃለያ (Buy Invoice)</b>\n"
            "───────────────────\n"
            "💵 <b>የሚገዙት መጠን፦</b> <code>${usd:,.2f} USD</code>\n"
            "💰 <b>የሚከፍሉት ብር፦</b> <code>{birr:,.2f} ETB</code>\n"
            "───────────────────\n\n"
            "👇 <i>ለመቀጠል የክፍያ አማራጩን ይጫኑ፦</i>"
        ),
        'summary_sell': (
            "📋 <b>የመሸጫ ማጠቃለያ (Sell Invoice)</b>\n"
            "───────────────────\n"
            "💵 <b>የሚሸጡት መጠን፦</b> <code>${usd:,.2f} USD</code>\n"
            "💰 <b>የሚቀበሉት ብር፦</b> <code>{birr:,.2f} ETB</code>\n"
            "───────────────────\n\n"
            "👇 <i>ለመቀጠል የክፍያ መቀበያ አማራጩን ይጫኑ፦</i>"
        ),
        'pay_instruct_buy': (
            "📱 <b>የTelebirr ክፍያ መመሪያ</b>\n"
            "───────────────────\n"
            "💳 <b>የሚከፈለው መጠን፦</b> <code>{birr:,.2f} ETB</code>\n"
            "📞 <b>የTelebirr ቁጥር፦</b> <code>{num}</code>\n"
            "───────────────────\n"
            "⏱️ <b>የጊዜ ገደብ፦</b> <b>15 ደቂቃ</b>\n\n"
            "<b>የአከፋፈል ደረጃዎች፦</b>\n"
            "1️⃣ ክፍያውን ወደላይ በተጠቀሰው ቁጥር ይላኩ።\n"
            "2️⃣ ክፍያው ሲጠናቀቅ የደረሰኙን <b>Screenshot</b> እዚህ ይላኩ።"
        ),
        'pay_instruct_sell': (
            "🌐 <b>የ USD (TRC20) መላኪያ መመሪያ</b>\n"
            "───────────────────\n"
            "💵 <b>የሚልኩት መጠን፦</b> <code>${usd:,.2f} USD</code>\n"
            "📍 <b>TRC20 Wallet Address:</b>\n<code>{wallet}</code>\n"
            "───────────────────\n"
            "⏱️ <b>የጊዜ ገደብ፦</b> <b>15 ደቂቃ</b>\n\n"
            "<b>የመላኪያ ደረጃዎች፦</b>\n"
            "1️⃣ ዶላሩን (TRC20) ወደላይ በተጠቀሰው Wallet Address ይላኩ።\n"
            "2️⃣ መላክዎን የሚያሳይ <b>Screenshot (Proof)</b> እዚህ ይላኩ።"
        ),
        'got_ss_buy': (
            "📥 <b>የክፍያ ደረሰኝዎ ተቀብለናል!</b> ✅\n"
            "───────────────────\n"
            "🎯 ዶላሩ እንዲላክሎት የሚፈልጉበትን <b>TRC20 Wallet Address</b> ይፃፉልን፦"
        ),
        'got_ss_sell': (
            "📥 <b>የዶላር መላኪያ ደረሰኝዎ ተቀብለናል!</b> ✅\n"
            "───────────────────\n"
            "🏦 ብር ገቢ የሚደረግበትን <b>የባንክ ስም</b>፣ <b>የአካውንት ቁጥር (Account Number)</b> እና <b>ሙሉ ስምዎን (Full Name)</b> አብረው ይፃፉልን፦"
        ),
        'complete': (
            "🎉 <b>ትዕዛዝዎ በስኬት ተላኳል!</b>\n"
            "───────────────────\n"
            "⏳ <b>ሁኔታ፦</b> <i>በግምገማ ላይ (Pending)</i>\n\n"
            "🔄 አድሚኑ ዝርዝሩን አረጋግጦ ወዲያውኑ ይጨርሳል፤ እናመሰግናለን!"
        ),
        'cancel': "❌ <b>ትዕዛዝዎ ተሰርዟል።</b>\n\nእንደገና ለመጀመር ከታች ያለውን <b>Restart</b> ቁልፍ ይጫኑ።",
        'timeout': "⏰ <b>ጊዜዎ አልቋል!</b>\n\nበ15 ደቂቃ ውስጥ ስላላጠናቀቁ ትዕዛዙ ተሰርዟል። እንደገና ለመጀመር Restart ይበሉ።",
        'active_exists': "⚠️ <b>ያልተጠናቀቀ ትዕዛዝ አለዎት!</b>\n\nእባክዎን ነባሩን ትዕዛዝ ያጠናቅቁ ወይም <b>Restart</b> ይበሉ።",
        'maintenance': "🛠️ <b>ቦቱ በአሁኑ ወቅት በስራ ማሻሻያ ላይ ነው!</b>",
        'support_prompt': "💬 <b>የእርዳታና ድጋፍ መስጫ (Support Center)</b>\n\nያለዎትን ጥያቄ ወይም ቅሬታ እዚህ ይፃፉልን።",
        'support_sent': "✅ <b>መልእክትዎ ለአድሚን ተልኳል!</b>",
        'btn_cancel': "❌ ሰርዝ (Cancel)",
        'btn_contact': "💬 Help & Support"
    },
    'en': {
        'welcome': (
            "💎 ─────────────── 💎\n"
            "✨ <b>OKXETH P2P TRADING BOT</b> ✨\n"
            "💎 ─────────────── 💎\n\n"
            "📈 <b>Exchange Rate:</b> <code>1 USD = {rate} Birr</code>\n\n"
            "👇 <b>Please select your trade option:</b>"
        ),
        'enter_amount_buy': (
            "📊 <b>Trading Limits:</b>\n"
            "├ 🟢 <b>Min Amount:</b> <code>${min:,.0f} USD</code>\n"
            "└ 🔴 <b>Max Amount:</b> <code>${max:,.0f} USD</code>\n"
            "───────────────────\n\n"
            "✍️ <b>Enter the USD amount you want to BUY:</b>\n"
            "💡 <i>Example: 10, 50, 100</i>"
        ),
        'enter_amount_sell': (
            "📊 <b>Trading Limits:</b>\n"
            "├ 🟢 <b>Min Amount:</b> <code>${min:,.0f} USD</code>\n"
            "└ 🔴 <b>Max Amount:</b> <code>${max:,.0f} USD</code>\n"
            "───────────────────\n\n"
            "✍️ <b>Enter the USD amount you want to SELL:</b>\n"
            "💡 <i>Example: 10, 50, 100</i>"
        ),
        'invalid_num': (
            "⚠️ <b>Invalid Amount!</b>\n"
            "───────────────────\n"
            "Please enter a value between <b>${min:,.0f}</b> and <b>${max:,.0f} USD</b>:"
        ),
        'summary_buy': (
            "📋 <b>Buy Order Invoice</b>\n"
            "───────────────────\n"
            "💵 <b>Buying Amount:</b> <code>${usd:,.2f} USD</code>\n"
            "💰 <b>Total Payable:</b> <code>{birr:,.2f} ETB</code>\n"
            "───────────────────\n\n"
            "👇 <i>Select your payment method below:</i>"
        ),
        'summary_sell': (
            "📋 <b>Sell Order Invoice</b>\n"
            "───────────────────\n"
            "💵 <b>Selling Amount:</b> <code>${usd:,.2f} USD</code>\n"
            "💰 <b>You Receive:</b> <code>{birr:,.2f} ETB</code>\n"
            "───────────────────\n\n"
            "👇 <i>Select your payout method below:</i>"
        ),
        'pay_instruct_buy': (
            "📱 <b>Telebirr Payment Instructions</b>\n"
            "───────────────────\n"
            "💳 <b>Amount to Pay:</b> <code>{birr:,.2f} ETB</code>\n"
            "📞 <b>Telebirr Number:</b> <code>{num}</code>\n"
            "───────────────────\n"
            "⏱️ <b>Time Limit:</b> <b>15 Minutes</b>\n\n"
            "1️⃣ Send exact Birr amount to the Telebirr number.\n"
            "2️⃣ Upload payment <b>Screenshot</b> here."
        ),
        'pay_instruct_sell': (
            "🌐 <b>USD (TRC20) Transfer Instructions</b>\n"
            "───────────────────\n"
            "💵 <b>Amount to Send:</b> <code>${usd:,.2f} USD</code>\n"
            "📍 <b>TRC20 Wallet Address:</b>\n<code>{wallet}</code>\n"
            "───────────────────\n"
            "⏱️ <b>Time Limit:</b> <b>15 Minutes</b>\n\n"
            "1️⃣ Transfer USD (TRC20) to the Wallet Address above.\n"
            "2️⃣ Upload transfer <b>Screenshot (Proof)</b> here."
        ),
        'got_ss_buy': "📥 <b>Payment receipt received!</b> ✅\n\nEnter your <b>TRC20 Wallet Address</b> to receive USD:",
        'got_ss_sell': "📥 <b>Transfer proof received!</b> ✅\n\nEnter your <b>Bank Name, Account Number & Full Name</b> to receive payment:",
        'complete': "🎉 <b>Order Placed Successfully!</b>\n\nStatus: <i>Pending Verification</i>",
        'cancel': "❌ <b>Order cancelled.</b>",
        'timeout': "⏰ <b>Time Expired!</b>",
        'active_exists': "⚠️ <b>You have an active pending order!</b>",
        'maintenance': "🛠️ <b>Bot is under maintenance!</b>",
        'support_prompt': "💬 Send your query below:",
        'support_sent': "✅ Message sent to Support!",
        'btn_cancel': "❌ Cancel Order",
        'btn_contact': "💬 Help & Support"
    }
}

TEXTS['om'] = TEXTS['am']
TEXTS['so'] = TEXTS['en']

# ----------------- UTILITY FUNCTIONS -----------------
def remove_timer_job(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    if context.job_queue:
        current_jobs = context.job_queue.get_jobs_by_name(str(user_id))
        for job in current_jobs:
            job.schedule_removal()

async def payment_timeout_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    if not job:
        return
    user_id = job.user_id
    lang = job.data.get('lang', 'am') if job.data else 'am'
    t = TEXTS[lang]
    if user_id in active_orders:
        active_orders.remove(user_id)
    try:
        await context.bot.send_message(chat_id=user_id, text=t['timeout'], parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to send timeout message to {user_id}: {e}")

# -----------------------------------------------------------------------------
# USER CONVERSATION HANDLERS
# -----------------------------------------------------------------------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "❓ <b>እርዳታና ድጋፍ (Help Center)</b>\n"
        "───────────────────\n"
        "ከአድሚኑ ጋር ለመገናኘት ከታች ያለውን <b>Support</b> ቁልፍ ይጫኑ።"
    )
    keyboard = [[InlineKeyboardButton("💬 Send Message to Support", callback_data="bot_support")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode="HTML")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    global maintenance_mode
    user = update.effective_user
    if not user:
        return ConversationHandler.END

    if maintenance_mode and user.id != ADMIN_ID:
        if update.message:
            await update.message.reply_text(TEXTS['am']['maintenance'], parse_mode="HTML")
        return ConversationHandler.END

    if user.id in active_orders:
        if update.message:
            await update.message.reply_text(TEXTS['am']['active_exists'], parse_mode="HTML")
        return ConversationHandler.END

    remove_timer_job(context, user.id)

    keyboard = [
        [InlineKeyboardButton("🌳 Afaan Oromoo", callback_data="lang_om"), InlineKeyboardButton("🇪🇹 አማርኛ", callback_data="lang_am")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"), InlineKeyboardButton("🇸🇴 Soomaali", callback_data="lang_so")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    start_msg = (
        "🌐 <b>Select Language / ቋንቋ ይምረጡ፦</b>\n"
        "───────────────────\n"
        "Please select your preferred language below to continue:"
    )

    if update.message:
        await update.message.reply_text(start_msg, reply_markup=reply_markup, parse_mode="HTML")
        await update.message.reply_text(
            "💡 <i>ማሳሰቢያ፦ ከስር ያለውን ቋሚ ቁልፍ በመጫን በማንኛውም ሰዓት ወደ መጀመሪያው መመለስ ይችላሉ።</i>", 
            reply_markup=PERMANENT_KEYBOARD, 
            parse_mode="HTML"
        )
    return LANG

async def select_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return LANG
    await query.answer()

    lang_code = query.data.split("_")[1]
    if context.user_data is not None:
        context.user_data['lang'] = lang_code

    t = TEXTS[lang_code]
    rate = db_get_rate()
    
    keyboard = [
        [InlineKeyboardButton("🟢 Buy USD (መግዛት)", callback_data="trade_buy"), InlineKeyboardButton("🔴 Sell USD (መሸጥ)", callback_data="trade_sell")],
        [InlineKeyboardButton(t['btn_contact'], callback_data="bot_support")],
        [InlineKeyboardButton(t['btn_cancel'], callback_data="user_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = t['welcome'].format(rate=rate)
    if query.message:
        await query.message.edit_text(msg, reply_markup=reply_markup, parse_mode="HTML")
    return TRADE_TYPE

async def select_trade_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return TRADE_TYPE
    await query.answer()

    trade_type = query.data.split("_")[1]
    user_data = context.user_data or {}
    user_data['trade_type'] = trade_type
    lang = user_data.get('lang', 'am')
    t = TEXTS[lang]

    keyboard = [
        [InlineKeyboardButton(t['btn_contact'], callback_data="bot_support")],
        [InlineKeyboardButton(t['btn_cancel'], callback_data="user_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = t['enter_amount_buy'].format(min=MIN_USD, max=MAX_USD) if trade_type == 'buy' else t['enter_amount_sell'].format(min=MIN_USD, max=MAX_USD)

    if query.message:
        await query.message.edit_text(msg, reply_markup=reply_markup, parse_mode="HTML")
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return AMOUNT
    user_data = context.user_data or {}
    lang = user_data.get('lang', 'am')
    trade_type = user_data.get('trade_type', 'buy')
    t = TEXTS[lang]

    try:
        usd_amount = float(update.message.text)
        if usd_amount < MIN_USD or usd_amount > MAX_USD:
            await update.message.reply_text(t['invalid_num'].format(min=MIN_USD, max=MAX_USD), parse_mode="HTML")
            return AMOUNT
        
        rate = db_get_rate()
        total_birr = usd_amount * rate
        user_data['usd_amount'] = usd_amount
        user_data['total_birr'] = total_birr

        keyboard = [
            [InlineKeyboardButton("📲 Continue / ቀጥል", callback_data="proceed_pay")],
            [InlineKeyboardButton(t['btn_cancel'], callback_data="user_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        msg = t['summary_buy'].format(usd=usd_amount, birr=total_birr) if trade_type == 'buy' else t['summary_sell'].format(usd=usd_amount, birr=total_birr)

        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="HTML")
        return PAYMENT
    except ValueError:
        await update.message.reply_text(t['invalid_num'].format(min=MIN_USD, max=MAX_USD), parse_mode="HTML")
        return AMOUNT

async def payment_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return PAYMENT
    await query.answer()
    user_data = context.user_data or {}
    lang = user_data.get('lang', 'am')
    trade_type = user_data.get('trade_type', 'buy')
    t = TEXTS[lang]

    total_birr = user_data.get('total_birr', 0)
    usd_amount = user_data.get('usd_amount', 0)

    user = update.effective_user
    if user:
        active_orders.add(user.id)
        if context.job_queue:
            remove_timer_job(context, user.id)
            context.job_queue.run_once(
                payment_timeout_job,
                when=900,
                user_id=user.id,
                name=str(user.id),
                data={'lang': lang}
            )

    keyboard = [[InlineKeyboardButton(t['btn_cancel'], callback_data="user_cancel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if trade_type == 'buy':
        msg = t['pay_instruct_buy'].format(birr=total_birr, usd=usd_amount, num=TELEBIRR_NUMBER)
        if query.message:
            await query.message.reply_text(msg, reply_markup=reply_markup, parse_mode="HTML")
        return SCREENSHOT
    else:
        msg = t['pay_instruct_sell'].format(birr=total_birr, usd=usd_amount, wallet=ADMIN_WALLET_ADDRESS)
        if query.message:
            await query.message.reply_text(msg, reply_markup=reply_markup, parse_mode="HTML")
        return SELL_SCREENSHOT

async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.photo:
        return SCREENSHOT

    user_data = context.user_data or {}
    lang = user_data.get('lang', 'am')
    t = TEXTS[lang]

    user_data['photo_file'] = update.message.photo[-1].file_id
    keyboard = [[InlineKeyboardButton(t['btn_cancel'], callback_data="user_cancel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(t['got_ss_buy'], reply_markup=reply_markup, parse_mode="HTML")
    return WALLET_ADDRESS

async def receive_sell_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.photo:
        return SELL_SCREENSHOT

    user_data = context.user_data or {}
    lang = user_data.get('lang', 'am')
    t = TEXTS[lang]

    user_data['photo_file'] = update.message.photo[-1].file_id
    keyboard = [[InlineKeyboardButton(t['btn_cancel'], callback_data="user_cancel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(t['got_ss_sell'], reply_markup=reply_markup, parse_mode="HTML")
    return SELL_TELEBIRR

async def receive_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return WALLET_ADDRESS
    wallet_address = update.message.text
    user = update.effective_user
    user_data = context.user_data or {}
    lang = user_data.get('lang', 'am')
    t = TEXTS[lang]

    usd_amount = user_data.get('usd_amount', 0)
    total_birr = user_data.get('total_birr', 0)
    photo_file = user_data.get('photo_file')

    if user and photo_file:
        username_str = f"@{user.username}" if user.username else "No Username"
        admin_msg = (
            f"🚨 <b>አዲስ የ P2P BUY (የመግዛት) ጥያቄ!</b>\n"
            f"───────────────────\n"
            f"👤 <b>ተጠቃሚ፦</b> {username_str}\n"
            f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
            f"💵 <b>የሚገዛው USD:</b> <code>${usd_amount:,.2f} USD</code>\n"
            f"💰 <b>የከፈለው ETB:</b> <code>{total_birr:,.2f} ETB</code>\n"
            f"📍 <b>ተጠቃሚው የሰጠው Wallet Address:</b> <code>{wallet_address}</code>\n"
            f"───────────────────"
        )
        admin_keyboard = [
            [InlineKeyboardButton("✅ Approve Order", callback_data=f"approve_{user.id}_{usd_amount}"), InlineKeyboardButton("❌ Reject Order", callback_data=f"reject_{user.id}")],
            [InlineKeyboardButton("💬 Send Message", callback_data=f"msg_{user.id}")]
        ]
        admin_markup = InlineKeyboardMarkup(admin_keyboard)
        try:
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_file, caption=admin_msg, reply_markup=admin_markup, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to notify admin of BUY order: {e}")

    await update.message.reply_text(t['complete'], parse_mode="HTML")
    return ConversationHandler.END

async def receive_sell_telebirr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return SELL_TELEBIRR
    bank_and_account_info = update.message.text
    user = update.effective_user
    user_data = context.user_data or {}
    lang = user_data.get('lang', 'am')
    t = TEXTS[lang]

    usd_amount = user_data.get('usd_amount', 0)
    total_birr = user_data.get('total_birr', 0)
    photo_file = user_data.get('photo_file')

    if user and photo_file:
        username_str = f"@{user.username}" if user.username else "No Username"
        admin_msg = (
            f"🚨 <b>አዲስ የ P2P SELL (የመሸጥ) ጥያቄ!</b>\n"
            f"───────────────────\n"
            f"👤 <b>ተጠቃሚ፦</b> {username_str}\n"
            f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
            f"💵 <b>የሸጠው USD:</b> <code>${usd_amount:,.2f} USD</code>\n"
            f"💰 <b>የሚላክለት ETB:</b> <code>{total_birr:,.2f} ETB</code>\n"
            f"🏦 <b>የተጠቃሚው የባንክ መረጃ እና ሙሉ ስም፦</b>\n<code>{bank_and_account_info}</code>\n"
            f"───────────────────"
        )
        admin_keyboard = [
            [InlineKeyboardButton("✅ Approve & Paid", callback_data=f"approve_{user.id}_{usd_amount}"), InlineKeyboardButton("❌ Reject Order", callback_data=f"reject_{user.id}")],
            [InlineKeyboardButton("💬 Send Message", callback_data=f"msg_{user.id}")]
        ]
        admin_markup = InlineKeyboardMarkup(admin_keyboard)
        try:
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_file, caption=admin_msg, reply_markup=admin_markup, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to notify admin of SELL order: {e}")

    await update.message.reply_text(t['complete'], parse_mode="HTML")
    return ConversationHandler.END

async def trigger_support_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
    user_data = context.user_data or {}
    lang = user_data.get('lang', 'am')
    t = TEXTS[lang]

    keyboard = [[InlineKeyboardButton(t['btn_cancel'], callback_data="user_cancel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if query and query.message:
        await query.message.reply_text(t['support_prompt'], reply_markup=reply_markup, parse_mode="HTML")
    elif update.message:
        await update.message.reply_text(t['support_prompt'], reply_markup=reply_markup, parse_mode="HTML")

    return SUPPORT_MSG

async def receive_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user or not update.message:
        return SUPPORT_MSG

    user_data = context.user_data or {}
    lang = user_data.get('lang', 'am')
    t = TEXTS[lang]
    username_str = f"@{user.username}" if user.username else "No Username"
    
    admin_msg = (
        f"📩 <b>አዲስ የSupport መልእክት!</b>\n"
        f"👤 <b>ተጠቃሚ፦</b> {user.first_name} ({username_str})\n"
        f"🆔 <b>User ID:</b> <code>{user.id}</code>"
    )
    admin_keyboard = [[InlineKeyboardButton("💬 Reply to User", callback_data=f"msg_{user.id}")]]
    admin_markup = InlineKeyboardMarkup(admin_keyboard)

    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="HTML")
        if update.message.photo:
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=update.message.photo[-1].file_id, caption=update.message.caption or "", reply_markup=admin_markup)
        else:
            await context.bot.send_message(chat_id=ADMIN_ID, text=update.message.text or "", reply_markup=admin_markup)
    except Exception as e:
        logger.error(f"Failed to forward support message: {e}")

    await update.message.reply_text(t['support_sent'], parse_mode="HTML")
    return ConversationHandler.END

async def cancel_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if user:
        remove_timer_job(context, user.id)
        if user.id in active_orders:
            active_orders.remove(user.id)

    query = update.callback_query
    user_data = context.user_data or {}
    lang = user_data.get('lang', 'am')
    t = TEXTS[lang]

    if query and query.message:
        await query.answer()
        await query.message.edit_text(t['cancel'], parse_mode="HTML")
    return ConversationHandler.END

# -----------------------------------------------------------------------------
# ADMIN ADMINISTRATIVE HANDLERS
# -----------------------------------------------------------------------------
async def admin_set_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or update.effective_user.id != ADMIN_ID:
        return
    if not context.args or len(context.args) < 1:
        current_rate = db_get_rate()
        await update.message.reply_text(f"ℹ️ የዛሬው የምንዛሬ ተመን፦ <b>1 USD = {current_rate} Birr</b>\n\nለመቀየር፦ <code>/setrate 185</code>", parse_mode="HTML")
        return
    try:
        new_rate = float(context.args[0])
        db_set_rate(new_rate)
        await update.message.reply_text(f"✅ <b>አዲሱ ተመን፦ 1 USD = {new_rate} Birr</b>", parse_mode="HTML")
    except ValueError:
        await update.message.reply_text("❌ እባክዎን ትክክለኛ ቁጥር ያስገቡ!", parse_mode="HTML")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or update.effective_user.id != ADMIN_ID:
        return
    total_orders, total_volume = db_get_stats()
    msg = (
        f"📊 <b>የቦቱ አጠቃላይ Stats</b>\n"
        f"───────────────────\n"
        f"✅ የተጠናቀቁ ትዕዛዞች፦ <b>{total_orders}</b>\n"
        f"💵 የተሸጠ/የተገዛ ዶላር፦ <b>${total_volume:,.2f} USD</b>\n"
        f"🔄 በሂደት ላይ ያሉ፦ <b>{len(active_orders)}</b>"
    )
    if update.message:
        await update.message.reply_text(msg, parse_mode="HTML")

async def admin_toggle_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global maintenance_mode
    if not update.effective_user or update.effective_user.id != ADMIN_ID:
        return
    maintenance_mode = not maintenance_mode
    status_str = "🛑 ON" if maintenance_mode else "🟢 OFF"
    if update.message:
        await update.message.reply_text(f"🛠️ <b>Maintenance Mode:</b> {status_str}", parse_mode="HTML")

async def admin_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    data = query.data

    if data.startswith("approve_"):
        parts = data.split("_")
        target_user_id = int(parts[1])
        usd_amount = float(parts[2]) if len(parts) > 2 else 0.0

        if context.bot_data is not None:
            context.bot_data['target_user_id'] = target_user_id
            context.bot_data['admin_waiting_photo'] = True
            context.bot_data['current_usd_amount'] = usd_amount
        
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="🟢 <b>Status:</b> 🔄 <i>Payment Approved! Admin is processing your request...</i>",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to notify user {target_user_id}: {e}")

        await query.message.reply_text("📸 <b>የመላኪያ ማረጋገጫ ስክሪንሹት (Proof Screenshot) ይላኩ፦</b>", parse_mode="HTML")

    elif data.startswith("reject_"):
        target_user_id = int(data.split("_")[1])
        if target_user_id in active_orders:
            active_orders.remove(target_user_id)
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="🔴 <b>Status:</b> ❌ <i>Order Rejected!</i>\n\nYour request/payment could not be verified.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Error notifying user {target_user_id}: {e}")

    elif data.startswith("msg_"):
        target_user_id = int(data.split("_")[1])
        await query.message.reply_text(
            f"💬 <b>ለተጠቃሚው (ID: <code>{target_user_id}</code>) መልእክት ለመላክ፦</b>\n\n"
            f"<code>/send {target_user_id} መልእክትህ</code> ብለህ ፃፍ።",
            parse_mode="HTML"
        )

    elif data.startswith("userconfirm_"):
        parts = data.split("_")
        status = parts[1]
        user_id = int(parts[2])
        if user_id in active_orders:
            active_orders.remove(user_id)

        if status == "yes":
            await query.message.reply_text("✅ <b>Thank you for trading with us!</b>", parse_mode="HTML")
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🎉 User ID <code>{user_id}</code> ጉዳዩ መጠናቀቁን አረጋግጧል!", parse_mode="HTML")
        elif status == "no":
            await query.message.reply_text("⚠️ <b>Issue reported to admin!</b>", parse_mode="HTML")
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🚨 User ID <code>{user_id}</code> አልደረሰኝም ብሏል!", parse_mode="HTML")

async def handle_admin_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.photo:
        return
    if update.effective_user and update.effective_user.id == ADMIN_ID:
        bot_data = context.bot_data or {}
        if bot_data.get('admin_waiting_photo'):
            target_user_id = bot_data.get('target_user_id')
            usd_amount = bot_data.get('current_usd_amount', 0.0)
            proof_photo = update.message.photo[-1].file_id

            if target_user_id:
                try:
                    msg = (
                        "🟢 <b>Status:</b> ✅ <i>Completed</i>\n"
                        "───────────────────\n"
                        "Transaction finalized! Receipt attached above. 🚀\n\n"
                        "Did you receive it?"
                    )
                    user_keyboard = [
                        [
                            InlineKeyboardButton("✅ Received / ደርሶኛል", callback_data=f"userconfirm_yes_{target_user_id}"),
                            InlineKeyboardButton("❌ Not Received / አልደረሰኝም", callback_data=f"userconfirm_no_{target_user_id}")
                        ]
                    ]
                    user_markup = InlineKeyboardMarkup(user_keyboard)
                    await context.bot.send_photo(chat_id=target_user_id, photo=proof_photo, caption=msg, reply_markup=user_markup, parse_mode="HTML")
                    await update.message.reply_text("✅ <b>የመላኪያ ማረጋገጫው ለተጠቃሚው ተልኳል!</b>", parse_mode="HTML")
                    db_update_stats(usd_amount)
                except Exception as e:
                    await update.message.reply_text(f"❌ ለተጠቃሚው መላክ አልተቻለም፦ {e}")
                
                bot_data['admin_waiting_photo'] = False

async def admin_send_direct_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or update.effective_user.id != ADMIN_ID:
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ <code>/send <USER_ID> <መልእክት></code>", parse_mode="HTML")
        return
    try:
        target_id = int(context.args[0])
        text_to_send = " ".join(context.args[1:])
        await context.bot.send_message(chat_id=target_id, text=f"💬 <b>ከ Support የተላከ መልእክት፦</b>\n───────────────────\n{text_to_send}", parse_mode="HTML")
        await update.message.reply_text(f"✅ መልእክቱ ለ ID <code>{target_id}</code> ተልኳል!", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ መላክ አልተቻለም፦ {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if user:
        remove_timer_job(context, user.id)
        if user.id in active_orders:
            active_orders.remove(user.id)
    if update.message:
        await update.message.reply_text("Cancelled. /start to restart.")
    return ConversationHandler.END

# -----------------------------------------------------------------------------
# APPLICATION ENTRY POINT & ENGINE
# -----------------------------------------------------------------------------
def main() -> None:
    if not BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN is not set. Exiting process.")
        return

    # Start Flask Web Server Thread
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # Build Telegram Application
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    restart_handler = MessageHandler(filters.Regex("^🔄 Main Menu / Restart$"), start)

    conv_handler: Any = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            restart_handler,
            CallbackQueryHandler(trigger_support_flow, pattern="^bot_support$")
        ],
        states={
            LANG: [CallbackQueryHandler(select_language, pattern="^lang_")],
            TRADE_TYPE: [
                CallbackQueryHandler(select_trade_type, pattern="^trade_"),
                CallbackQueryHandler(trigger_support_flow, pattern="^bot_support$"),
                CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$")
            ],
            AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔄 Main Menu / Restart$"), get_amount),
                CallbackQueryHandler(trigger_support_flow, pattern="^bot_support$"),
                CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$")
            ],
            PAYMENT: [
                CallbackQueryHandler(payment_selected, pattern="^proceed_pay$"),
                CallbackQueryHandler(trigger_support_flow, pattern="^bot_support$"),
                CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$")
            ],
            SCREENSHOT: [
                MessageHandler(filters.PHOTO, receive_screenshot),
                CallbackQueryHandler(trigger_support_flow, pattern="^bot_support$"),
                CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$")
            ],
            WALLET_ADDRESS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔄 Main Menu / Restart$"), receive_wallet),
                CallbackQueryHandler(trigger_support_flow, pattern="^bot_support$"),
                CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$")
            ],
            SELL_SCREENSHOT: [
                MessageHandler(filters.PHOTO, receive_sell_screenshot),
                CallbackQueryHandler(trigger_support_flow, pattern="^bot_support$"),
                CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$")
            ],
            SELL_TELEBIRR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔄 Main Menu / Restart$"), receive_sell_telebirr),
                CallbackQueryHandler(trigger_support_flow, pattern="^bot_support$"),
                CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$")
            ],
            SUPPORT_MSG: [
                MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND & ~filters.Regex("^🔄 Main Menu / Restart$"), receive_support_message),
                CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            restart_handler,
            CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$")
        ],
        per_message=False
    )

    # Register Handlers
    app.add_handler(restart_handler)
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("send", admin_send_direct_message))
    app.add_handler(CommandHandler("setrate", admin_set_rate))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("maintenance", admin_toggle_maintenance))
    app.add_handler(CallbackQueryHandler(admin_action_handler, pattern="^(approve|reject|msg|userconfirm)_"))
    app.add_handler(MessageHandler(filters.PHOTO & filters.User(user_id=ADMIN_ID), handle_admin_photo))

    logger.info("OKXETH P2P Trading Bot is active and listening...")
    app.run_polling()

if __name__ == "__main__":
    main()
