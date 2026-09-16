# type: ignore
import os
import sqlite3
import logging
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
# FLASK WEB SERVER (FOR KEEP-ALIVE ON REPLIT/RAILWAY)
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
# GLOBAL STATE & KEYBOARD
# -----------------------------------------------------------------------------
active_orders: set[int] = set()
maintenance_mode: bool = False

PERMANENT_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("🔄 Main Menu / Restart")]],
    resize_keyboard=True
)

# -----------------------------------------------------------------------------
# MULTI-LANGUAGE RESOURCES
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
            "📊 <b>የግዢ ወሰን፦</b>\n"
            "├ 🟢 <b>አነስተኛ:</b> <code>${min:,.0f} USD</code>\n"
            "└ 🔴 <b>ከፍተኛ:</b> <code>${max:,.0f} USD</code>\n"
            "───────────────────\n\n"
            "✍️ <b>መግዛት የሚፈልጉትን መጠን (USD) ያስገቡ፦</b>"
        ),
        'enter_amount_sell': (
            "📊 <b>የመሸጫ ወሰን፦</b>\n"
            "├ 🟢 <b>አነስተኛ:</b> <code>${min:,.0f} USD</code>\n"
            "└ 🔴 <b>ከፍተኛ:</b> <code>${max:,.0f} USD</code>\n"
            "───────────────────\n\n"
            "✍️ <b>መሸጥ የሚፈልጉትን መጠን (USD) ያስገቡ፦</b>"
        ),
        'invalid_num': "⚠️ <b>የተሳሳተ ቁጥር!</b>\nእባክዎን ከ <b>${min:,.0f}</b> እስከ <b>${max:,.0f} USD</b> ባለው ወሰን ውስጥ ብቻ ያስገቡ፦",
        'summary_buy': "📋 <b>የግዢ ማጠቃለያ</b>\n\n💵 <b>የሚገዙት፦</b> <code>${usd:,.2f} USD</code>\n💰 <b>የሚከፍሉት፦</b> <code>{birr:,.2f} ETB</code>",
        'summary_sell': "📋 <b>የመሸጫ ማጠቃለያ</b>\n\n💵 <b>የሚሸጡት፦</b> <code>${usd:,.2f} USD</code>\n💰 <b>የሚቀበሉት፦</b> <code>{birr:,.2f} ETB</code>",
        'pay_instruct_buy': "📱 <b>Telebirr ክፍያ መመሪያ</b>\n\n💳 <b>የሚከፈለው፦</b> <code>{birr:,.2f} ETB</code>\n📞 <b>Telebirr፦</b> <code>{num}</code>\n\n1️⃣ ክፍያውን ይላኩ።\n2️⃣ የደረሰኙን <b>Screenshot</b> እዚህ ይላኩ።",
        'pay_instruct_sell': "🌐 <b>USD (TRC20) መላኪያ መመሪያ</b>\n\n💵 <b>የሚልኩት፦</b> <code>${usd:,.2f} USD</code>\n📍 <b>TRC20 Wallet:</b>\n<code>{wallet}</code>\n\n1️⃣ ዶላሩን ይላኩ።\n2️⃣ የመላኪያውን <b>Screenshot</b> እዚህ ይላኩ።",
        'got_ss_buy': "📥 <b>ደረሰኝ ተቀብለናል!</b> ✅\n\n🎯 ዶላሩ የሚላክበትን <b>TRC20 Wallet Address</b> ያስገቡ፦",
        'got_ss_sell': "📥 <b>ደረሰኝ ተቀብለናል!</b> ✅\n\n🏦 ብር ገቢ የሚደረግበትን <b>የባንክ ስም፣ አካውንት ቁጥር እና ሙሉ ስም</b> ያስገቡ፦",
        'complete': "🎉 <b>ትዕዛዝዎ በስኬት ተላኳል!</b>\n\n⏳ አድሚኑ አረጋግጦ ወዲያውኑ ይጨርሳል።",
        'cancel': "❌ <b>ትዕዛዝዎ ተሰርዟል።</b>",
        'timeout': "⏰ <b>ጊዜዎ አልቋል!</b> ትዕዛዙ ተሰርዟል።",
        'active_exists': "⚠️ <b>ያልተጠናቀቀ ትዕዛዝ አለዎት!</b>",
        'maintenance': "🛠️ <b>ቦቱ በስራ ማሻሻያ ላይ ነው!</b>",
        'support_prompt': "💬 ጥያቄ ወይም ቅሬታዎን እዚህ ይፃፉልን፦",
        'support_sent': "✅ <b>መልእክትዎ ለአድሚን ተልኳል!</b>",
        'btn_cancel': "❌ ሰርዝ (Cancel)",
        'btn_contact': "💬 Help & Support"
    },
    'en': {
        'welcome': "✨ <b>OKXETH P2P BOT</b> ✨\n\n📈 Rate: <code>1 USD = {rate} ETB</code>\n\n👇 Select trade option:",
        'enter_amount_buy': "✍️ Enter USD amount to <b>BUY</b> (${min}-${max}):",
        'enter_amount_sell': "✍️ Enter USD amount to <b>SELL</b> (${min}-${max}):",
        'invalid_num': "⚠️ Enter between <b>${min}</b> and <b>${max} USD</b>:",
        'summary_buy': "📋 Buy Order\nUSD: <code>${usd}</code>\nPay: <code>{birr} ETB</code>",
        'summary_sell': "📋 Sell Order\nUSD: <code>${usd}</code>\nReceive: <code>{birr} ETB</code>",
        'pay_instruct_buy': "📱 Pay Telebirr: <code>{num}</code>\nAmount: <code>{birr} ETB</code>\n\nUpload Screenshot after payment.",
        'pay_instruct_sell': "🌐 Send USD (TRC20): <code>{wallet}</code>\nAmount: <code>${usd} USD</code>\n\nUpload Screenshot after sending.",
        'got_ss_buy': "📥 Enter your <b>TRC20 Wallet Address</b>:",
        'got_ss_sell': "📥 Enter your <b>Bank Name, Account Number & Full Name</b>:",
        'complete': "🎉 Order Placed! Pending Admin Approval.",
        'cancel': "❌ Order Cancelled.",
        'timeout': "⏰ Order Timed Out.",
        'active_exists': "⚠️ Active order exists!",
        'maintenance': "🛠️ Under maintenance!",
        'support_prompt': "💬 Send your message below:",
        'support_sent': "✅ Message sent to Support!",
        'btn_cancel': "❌ Cancel",
        'btn_contact': "💬 Help & Support"
    }
}
TEXTS['om'] = TEXTS['am']
TEXTS['so'] = TEXTS['en']

# -----------------------------------------------------------------------------
# HANDLERS & FLOW
# -----------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    global maintenance_mode
    user = update.effective_user
    if not user:
        return ConversationHandler.END

    if maintenance_mode and user.id != ADMIN_ID:
        if update.message:
            await update.message.reply_text(TEXTS['am']['maintenance'], parse_mode="HTML")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("🌳 Oromoo", callback_data="lang_om"), InlineKeyboardButton("🇪🇹 አማርኛ", callback_data="lang_am")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"), InlineKeyboardButton("🇸🇴 Soomaali", callback_data="lang_so")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    start_msg = "🌐 <b>Select Language / ቋንቋ ይምረጡ፦</b>"

    if update.message:
        await update.message.reply_text(start_msg, reply_markup=reply_markup, parse_mode="HTML")
        await update.message.reply_text("💡 <i>ለማስተካከል/ለመጀመር ከታች 'Main Menu' የሚለውን ይጫኑ።</i>", reply_markup=PERMANENT_KEYBOARD, parse_mode="HTML")
    return LANG

async def select_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return LANG
    await query.answer()

    lang_code = query.data.split("_")[1]
    if context.user_data is not None:
        context.user_data['lang'] = lang_code

    t = TEXTS.get(lang_code, TEXTS['am'])
    rate = db_get_rate()
    
    keyboard = [
        [InlineKeyboardButton("🟢 Buy USD (መግዛት)", callback_data="trade_buy"), InlineKeyboardButton("🔴 Sell USD (መሸጥ)", callback_data="trade_sell")],
        [InlineKeyboardButton(t['btn_contact'], callback_data="bot_support")],
        [InlineKeyboardButton(t['btn_cancel'], callback_data="user_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if query.message:
        await query.message.edit_text(t['welcome'].format(rate=rate), reply_markup=reply_markup, parse_mode="HTML")
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
    t = TEXTS.get(lang, TEXTS['am'])

    keyboard = [[InlineKeyboardButton(t['btn_cancel'], callback_data="user_cancel")]]
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
    t = TEXTS.get(lang, TEXTS['am'])

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
    t = TEXTS.get(lang, TEXTS['am'])

    total_birr = user_data.get('total_birr', 0)
    usd_amount = user_data.get('usd_amount', 0)

    keyboard = [[InlineKeyboardButton(t['btn_cancel'], callback_data="user_cancel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if trade_type == 'buy':
        msg = t['pay_instruct_buy'].format(birr=total_birr, num=TELEBIRR_NUMBER)
        if query.message:
            await query.message.reply_text(msg, reply_markup=reply_markup, parse_mode="HTML")
        return SCREENSHOT
    else:
        msg = t['pay_instruct_sell'].format(usd=usd_amount, wallet=ADMIN_WALLET_ADDRESS)
        if query.message:
            await query.message.reply_text(msg, reply_markup=reply_markup, parse_mode="HTML")
        return SELL_SCREENSHOT

async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.photo:
        return SCREENSHOT
    user_data = context.user_data or {}
    t = TEXTS.get(user_data.get('lang', 'am'), TEXTS['am'])
    user_data['photo_file'] = update.message.photo[-1].file_id

    keyboard = [[InlineKeyboardButton(t['btn_cancel'], callback_data="user_cancel")]]
    await update.message.reply_text(t['got_ss_buy'], reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return WALLET_ADDRESS

async def receive_sell_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.photo:
        return SELL_SCREENSHOT
    user_data = context.user_data or {}
    t = TEXTS.get(user_data.get('lang', 'am'), TEXTS['am'])
    user_data['photo_file'] = update.message.photo[-1].file_id

    keyboard = [[InlineKeyboardButton(t['btn_cancel'], callback_data="user_cancel")]]
    await update.message.reply_text(t['got_ss_sell'], reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return SELL_TELEBIRR

async def receive_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return WALLET_ADDRESS
    wallet = update.message.text
    user = update.effective_user
    user_data = context.user_data or {}
    t = TEXTS.get(user_data.get('lang', 'am'), TEXTS['am'])

    if user and user_data.get('photo_file'):
        admin_msg = f"🚨 <b>NEW BUY ORDER!</b>\nUser: @{user.username} ({user.id})\nUSD: ${user_data.get('usd_amount')}\nETB: {user_data.get('total_birr')}\nWallet: <code>{wallet}</code>"
        admin_keyboard = [[InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user.id}_{user_data.get('usd_amount')}"), InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}")]]
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=user_data['photo_file'], caption=admin_msg, reply_markup=InlineKeyboardMarkup(admin_keyboard), parse_mode="HTML")

    await update.message.reply_text(t['complete'], parse_mode="HTML")
    return ConversationHandler.END

async def receive_sell_telebirr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return SELL_TELEBIRR
    bank_info = update.message.text
    user = update.effective_user
    user_data = context.user_data or {}
    t = TEXTS.get(user_data.get('lang', 'am'), TEXTS['am'])

    if user and user_data.get('photo_file'):
        admin_msg = f"🚨 <b>NEW SELL ORDER!</b>\nUser: @{user.username} ({user.id})\nUSD: ${user_data.get('usd_amount')}\nETB: {user_data.get('total_birr')}\nBank Info: <code>{bank_info}</code>"
        admin_keyboard = [[InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user.id}_{user_data.get('usd_amount')}"), InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}")]]
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=user_data['photo_file'], caption=admin_msg, reply_markup=InlineKeyboardMarkup(admin_keyboard), parse_mode="HTML")

    await update.message.reply_text(t['complete'], parse_mode="HTML")
    return ConversationHandler.END

async def trigger_support_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_data = context.user_data or {}
    t = TEXTS.get(user_data.get('lang', 'am'), TEXTS['am'])
    msg = t['support_prompt']
    if update.callback_query and update.callback_query.message:
        await update.callback_query.message.reply_text(msg, parse_mode="HTML")
    elif update.message:
        await update.message.reply_text(msg, parse_mode="HTML")
    return SUPPORT_MSG

async def receive_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if user and update.message:
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"💬 <b>Message from @{user.username} ({user.id}):</b>\n\n{update.message.text}", parse_mode="HTML")
        await update.message.reply_text("✅ Message sent to Support!", parse_mode="HTML")
    return ConversationHandler.END

async def cancel_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query and update.callback_query.message:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text("❌ Cancelled.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text("Cancelled. Send /start to restart.")
    return ConversationHandler.END

# -----------------------------------------------------------------------------
# MAIN ENGINE
# -----------------------------------------------------------------------------
def main() -> None:
    if not BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN environment variable missing.")
        return

    # Start Flask Web Server
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

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
            TRADE_TYPE: [CallbackQueryHandler(select_trade_type, pattern="^trade_")],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔄 Main Menu / Restart$"), get_amount)],
            PAYMENT: [CallbackQueryHandler(payment_selected, pattern="^proceed_pay$")],
            SCREENSHOT: [MessageHandler(filters.PHOTO, receive_screenshot)],
            WALLET_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔄 Main Menu / Restart$"), receive_wallet)],
            SELL_SCREENSHOT: [MessageHandler(filters.PHOTO, receive_sell_screenshot)],
            SELL_TELEBIRR: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔄 Main Menu / Restart$"), receive_sell_telebirr)],
            SUPPORT_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔄 Main Menu / Restart$"), receive_support_message)]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            restart_handler,
            CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$")
        ],
        per_message=False
    )

    app.add_handler(restart_handler)
    app.add_handler(conv_handler)

    logger.info("Bot started successfully!")
    app.run_polling()

if __name__ == "__main__":
    main()
