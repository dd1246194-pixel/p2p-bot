import os
import re
import logging
import sqlite3
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
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
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("OKXETH_P2P_BOT")

# -----------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_ID = 7798227927
DEFAULT_RATE = 184.0
TELEBIRR_NUMBER = "0900253321"
ADMIN_NAME = "Bereket"
ADMIN_WALLET_ADDRESS = "TMAbfELuLH7gGyjp6YgUV1WWpPYwhaE27V"

MIN_USD = 10.0
MAX_USD = 2100.0
ORDER_TIMEOUT_SECONDS = 30 * 60  # 30 ደቂቃ (1800 ሰከንድ)

DB_FILE = "bot_data.db"
TRC20_REGEX = r"^T[a-zA-Z0-9]{33}$"

# -----------------------------------------------------------------------------
# CONVERSATION STATES
# -----------------------------------------------------------------------------
(
    LANG,
    TRADE_TYPE,
    AMOUNT,
    PAYMENT_CHOICE,
    SCREENSHOT,
    WALLET_ADDRESS,
    SELL_SCREENSHOT,
    SELL_TELEBIRR,
    SUPPORT_MSG,
) = range(9)

# -----------------------------------------------------------------------------
# DATABASE MANAGEMENT
# -----------------------------------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value REAL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admin_actions (
                    admin_id INTEGER PRIMARY KEY,
                    action_type TEXT,
                    target_user_id INTEGER
                )
            ''')
            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('rate', ?)", (DEFAULT_RATE,))
            conn.commit()
    except Exception as e:
        logger.error(f"Error initializing DB: {e}")

init_db()

def db_get_rate() -> float:
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'rate'")
            row = cursor.fetchone()
            return float(row["value"]) if row else DEFAULT_RATE
    except Exception as e:
        logger.error(f"Error fetching rate: {e}")
        return DEFAULT_RATE

def db_set_rate(new_rate: float) -> bool:
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE settings SET value = ? WHERE key = 'rate'", (new_rate,))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error updating rate: {e}")
        return False

# -----------------------------------------------------------------------------
# AUTO-CLEAR / TIMEOUT JOB FUNCTION
# -----------------------------------------------------------------------------
async def order_timeout_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """ከ30 ደቂቃ በኋላ መልእክቱን አውቶማቲክ ያጥፋል (Clear ያደርጋል)"""
    job = context.job
    chat_id = job.data["chat_id"]
    message_id = job.data.get("message_id")

    # የቀደመውን የክፍያ መልእክት ማጥፋት
    if message_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Could not delete message {message_id}: {e}")

    # ለተጠቃሚው ጊዜው ማለቁን ማሳወቅ
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
    """ነባር Timer ካለ ማቆም"""
    current_jobs = context.job_queue.get_jobs_by_name("order_timer")
    for job in current_jobs:
        job.schedule_removal()

# -----------------------------------------------------------------------------
# KEYBOARDS & LOCALIZATION
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
            "👋 <b>እንኳን ወደ P2P የምንዛሬ ቦት በሰላም መጡ!</b>\n\n"
            "📊 <b>የዛሬው የምንዛሬ ተመን፦</b>\n"
            "└ <code>1 USD = {rate:,.2f} ETB</code>\n\n"
            "💳 <b>የክፍያ መንገድ:</b> <code>Telebirr (ቴሌብር ብቻ)</code>\n"
            "⏱ <b>የትዕዛዝ ጊዜ ወሰን:</b> <code>30 ደቂቃ</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "👇 <b>እባክዎን ማድረግ የሚፈልጉትን ይምረጡ፦</b>"
        ),
        'enter_amount_buy': "🟢 <b>የግዢ መጠን ያስገቡ (BUY USD)</b>\n📌 ወሰን: <code>${min:,.2f}</code> - <code>${max:,.2f} USD</code>፦",
        'enter_amount_sell': "🔴 <b>የመሸጫ መጠን ያስገቡ (SELL USD)</b>\n📌 ወሰን: <code>${min:,.2f}</code> - <code>${max:,.2f} USD</code>፦",
        'invalid_num': "⚠️ <b>የተሳሳተ ቁጥር!</b> ከ <b>${min:,.2f}</b> እስከ <b>${max:,.2f} USD</b> ያስገቡ፦",
        'summary_buy': "🧾 <b>የግዢ ትዕዛዝ ማጠቃለያ</b>\n💵 መጠን: <code>${usd:,.2f} USD</code>\n💰 ክፍያ: <code>{birr:,.2f} ETB</code>\n⏱ <i>ይህንን ክፍያ ለመፈጸም <b>30 ደቂቃ</b> አለዎት!</i>",
        'summary_sell': "🧾 <b>የመሸጫ ትዕዛዝ ማጠቃለያ</b>\n💵 መጠን: <code>${usd:,.2f} USD</code>\n💰 የሚቀበሉት: <code>{birr:,.2f} ETB</code>\n⏱ <i>ይህንን ክፍያ ለመፈጸም <b>30 ደቂቃ</b> አለዎት!</i>",
        'pay_instruct_buy': (
            "⏳ <b>የ 30 ደቂቃ ቆጠራ ጀምሯል!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📱 <b>Telebirr:</b> <code>{num}</code>\n"
            "👤 <b>ስም:</b> <code>{name}</code>\n"
            "💵 <b>የሚከፍሉት:</b> <code>{birr:,.2f} ETB</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ <i>በ 30 ደቂቃ ውስጥ ካልከፈሉ ይህ መልእክት አውቶማቲክ ይጸዳል (Clear ይሆናል)።</i>\n"
            "ከከፈሉ በኋላ የደረሰኙን Screenshot ይላኩ፦"
        ),
        'pay_instruct_sell': (
            "⏳ <b>የ 30 ደቂቃ ቆጠራ ጀምሯል!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🌐 <b>TRC20 Wallet:</b> <code>{wallet}</code>\n"
            "💵 <b>የሚልኩት:</b> <code>${usd:,.2f} USDT</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ <i>በ 30 ደቂቃ ውስጥ ካልላኩ ይህ መልእክት አውቶማቲክ ይጸዳል (Clear ይሆናል)።</i>\n"
            "ከተላከ በኋላ Screenshot ይላኩ፦"
        ),
        'got_ss_buy': "✅ ደረሰኝ ደርሶናል። አሁን ዶላሩ የሚላክበትን <b>TRC20 Wallet Address</b> ይላኩ፦",
        'got_ss_sell': "✅ ደረሰኝ ደርሶናል። አሁን ብር የሚላክበትን የ <b>Telebirr ስልክ ቁጥር እና ስም</b> ይላኩ፦",
        'invalid_wallet': "⚠️ የተሳሳተ የ TRC20 አድራሻ! በ 'T' የሚጀምር አድራሻ ያስገቡ፦",
        'complete': "🎉 <b>ትዕዛዝዎ ገብቷል!</b> አድሚኖቻችን አረጋግጠው በቅርቡ ይልካሉ። እናመሰግናለን!",
        'btn_cancel': "❌ ሰርዝ (Cancel)"
    }
}

def get_txt(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return TEXTS['am']

# -----------------------------------------------------------------------------
# FLOW HANDLERS
# -----------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cancel_existing_timer(context)
    context.user_data.clear()
    rate = db_get_rate()
    txt = get_txt(context)

    keyboard = [
        [InlineKeyboardButton("🟢 Buy USD (መግዛት)", callback_data="trade_buy"), InlineKeyboardButton("🔴 Sell USD (መሸጥ)", callback_data="trade_sell")]
    ]
    
    if update.message:
        await update.message.reply_text(txt['welcome'].format(rate=rate), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        await update.message.reply_text("💡 <i>Main Menu / Restart</i>", reply_markup=PERMANENT_KEYBOARD, parse_mode="HTML")
    return TRADE_TYPE

async def select_trade_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        txt = get_txt(context)
        trade_type = query.data.split("_")[1]
        context.user_data['trade_type'] = trade_type
        
        keyboard = [[InlineKeyboardButton(txt['btn_cancel'], callback_data="user_cancel")]]
        msg = txt['enter_amount_buy'].format(min=MIN_USD, max=MAX_USD) if trade_type == 'buy' else txt['enter_amount_sell'].format(min=MIN_USD, max=MAX_USD)
        await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = get_txt(context)
    if not update.message or not update.message.text:
        return AMOUNT
    try:
        usd_amount = float(update.message.text)
        if usd_amount < MIN_USD or usd_amount > MAX_USD:
            await update.message.reply_text(txt['invalid_num'].format(min=MIN_USD, max=MAX_USD), parse_mode="HTML")
            return AMOUNT
        
        rate = db_get_rate()
        total_birr = usd_amount * rate
        context.user_data['usd_amount'] = usd_amount
        context.user_data['total_birr'] = total_birr
        trade_type = context.user_data.get('trade_type', 'buy')

        keyboard = [
            [InlineKeyboardButton("አረጋግጥና ቀጥል ➡️", callback_data="proceed_pay")],
            [InlineKeyboardButton(txt['btn_cancel'], callback_data="user_cancel")]
        ]
        msg = txt['summary_buy'].format(usd=usd_amount, birr=total_birr) if trade_type == 'buy' else txt['summary_sell'].format(usd=usd_amount, birr=total_birr)
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return PAYMENT_CHOICE
    except ValueError:
        await update.message.reply_text(txt['invalid_num'].format(min=MIN_USD, max=MAX_USD), parse_mode="HTML")
        return AMOUNT

async def payment_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        txt = get_txt(context)
        trade_type = context.user_data.get('trade_type', 'buy')
        total_birr = context.user_data.get('total_birr', 0)
        usd_amount = context.user_data.get('usd_amount', 0)

        keyboard = [[InlineKeyboardButton(txt['btn_cancel'], callback_data="user_cancel")]]

        if trade_type == 'buy':
            msg = txt['pay_instruct_buy'].format(birr=total_birr, num=TELEBIRR_NUMBER, name=ADMIN_NAME)
            sent_msg = await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
            
            # ⏱ START 30-MINUTE TIMER
            context.job_queue.run_once(
                order_timeout_callback,
                when=ORDER_TIMEOUT_SECONDS,
                data={"chat_id": update.effective_chat.id, "message_id": sent_msg.message_id},
                name="order_timer"
            )
            return SCREENSHOT
        else:
            msg = txt['pay_instruct_sell'].format(usd=usd_amount, wallet=ADMIN_WALLET_ADDRESS)
            sent_msg = await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
            
            # ⏱ START 30-MINUTE TIMER
            context.job_queue.run_once(
                order_timeout_callback,
                when=ORDER_TIMEOUT_SECONDS,
                data={"chat_id": update.effective_chat.id, "message_id": sent_msg.message_id},
                name="order_timer"
            )
            return SELL_SCREENSHOT

async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = get_txt(context)
    if update.message and update.message.photo:
        context.user_data['photo_file'] = update.message.photo[-1].file_id
        await update.message.reply_text(txt['got_ss_buy'], parse_mode="HTML")
        return WALLET_ADDRESS
    return SCREENSHOT

async def receive_sell_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = get_txt(context)
    if update.message and update.message.photo:
        context.user_data['photo_file'] = update.message.photo[-1].file_id
        await update.message.reply_text(txt['got_ss_sell'], parse_mode="HTML")
        return SELL_TELEBIRR
    return SELL_SCREENSHOT

async def receive_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = get_txt(context)
    if update.message and update.message.text:
        wallet = update.message.text.strip()
        if not re.match(TRC20_REGEX, wallet):
            await update.message.reply_text(txt['invalid_wallet'], parse_mode="HTML")
            return WALLET_ADDRESS

        # ትዕዛዙ ስለተጠናቀቀ 30 min timer ማስቆም
        cancel_existing_timer(context)

        user = update.effective_user
        if user:
            username = f"@{user.username}" if user.username else "No Username"
            admin_msg = (
                f"🚨 <b>NEW BUY ORDER!</b>\n"
                f"👤 <b>User:</b> {username} (<code>{user.id}</code>)\n"
                f"💵 <b>Amount:</b> <code>${context.user_data.get('usd_amount'):,.2f} USD</code>\n"
                f"💰 <b>Total Birr:</b> <code>{context.user_data.get('total_birr'):,.2f} ETB</code>\n"
                f"📍 <b>Wallet:</b> <code>{wallet}</code>"
            )
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=context.user_data['photo_file'], caption=admin_msg, parse_mode="HTML")
        
        await update.message.reply_text(txt['complete'], parse_mode="HTML")
        context.user_data.clear()
        return ConversationHandler.END
    return WALLET_ADDRESS

async def receive_sell_telebirr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = get_txt(context)
    if update.message and update.message.text:
        telebirr_info = update.message.text.strip()
        
        # ትዕዛዙ ስለተጠናቀቀ 30 min timer ማስቆም
        cancel_existing_timer(context)

        user = update.effective_user
        if user:
            username = f"@{user.username}" if user.username else "No Username"
            admin_msg = (
                f"🚨 <b>NEW SELL ORDER!</b>\n"
                f"👤 <b>User:</b> {username} (<code>{user.id}</code>)\n"
                f"💵 <b>Amount:</b> <code>${context.user_data.get('usd_amount'):,.2f} USD</code>\n"
                f"💰 <b>Total Birr:</b> <code>{context.user_data.get('total_birr'):,.2f} ETB</code>\n"
                f"📱 <b>Telebirr:</b> <code>{telebirr_info}</code>"
            )
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=context.user_data['photo_file'], caption=admin_msg, parse_mode="HTML")
        
        await update.message.reply_text(txt['complete'], parse_mode="HTML")
        context.user_data.clear()
        return ConversationHandler.END
    return SELL_TELEBIRR

async def cancel_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cancel_existing_timer(context)
    if update.callback_query and update.callback_query.message:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text("❌ <b>ትዕዛዙ ተሰርዟል።</b>\nእንደገና ለመጀመር /start ይበሉ።", parse_mode="HTML")
    context.user_data.clear()
    return ConversationHandler.END

# -----------------------------------------------------------------------------
# MAIN EXECUTION
# -----------------------------------------------------------------------------
def main() -> None:
    if not BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN missing!")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    restart_handler = MessageHandler(filters.Regex("^🔄 Main Menu / Restart$"), start)

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start), restart_handler],
        states={
            LANG: [CallbackQueryHandler(select_trade_type, pattern="^trade_")],
            TRADE_TYPE: [CallbackQueryHandler(select_trade_type, pattern="^trade_")],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔄 Main Menu / Restart$"), get_amount)],
            PAYMENT_CHOICE: [CallbackQueryHandler(payment_selected, pattern="^proceed_pay$")],
            SCREENSHOT: [MessageHandler(filters.PHOTO, receive_screenshot)],
            WALLET_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔄 Main Menu / Restart$"), receive_wallet)],
            SELL_SCREENSHOT: [MessageHandler(filters.PHOTO, receive_sell_screenshot)],
            SELL_TELEBIRR: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔄 Main Menu / Restart$"), receive_sell_telebirr)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$"),
            restart_handler,
        ],
    )

    app.add_handler(conv_handler)
    logger.info("Bot started successfully...")
    app.run_polling()

if __name__ == "__main__":
    main()
