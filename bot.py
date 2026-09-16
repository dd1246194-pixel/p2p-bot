# type: ignore
import os
import sqlite3
import logging
from typing import Any
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

# LOGGING CONFIGURATION
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("OKXETH_P2P_BOT")

# CONFIGURATION
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_ID = 7798227927
DEFAULT_RATE = 184.0
TELEBIRR_NUMBER = "0900253321"
ADMIN_WALLET_ADDRESS = "TMAbfELuLH7gGyjp6YgUV1WWpPYwhaE27V"

MIN_USD = 10.0
MAX_USD = 2100.0

# CONVERSATION STATES
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

# DATABASE MANAGEMENT
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
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('rate', ?)", (DEFAULT_RATE,))
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

PERMANENT_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("🔄 Main Menu / Restart")]],
    resize_keyboard=True
)

TEXTS = {
    'am': {
        'welcome': "✨ <b>OKXETH P2P TRADING BOT</b> ✨\n\n📈 <b>ተመን፦</b> <code>1 USD = {rate} Birr</code>\n\n👇 ምረጡ፦",
        'enter_amount_buy': "✍️ መግዛት የሚፈልጉትን መጠን (USD) ያስገቡ (${min}-${max}):",
        'enter_amount_sell': "✍️ መሸጥ የሚፈልጉትን መጠን (USD) ያስገቡ (${min}-${max}):",
        'invalid_num': "⚠️ ከ <b>${min}</b> እስከ <b>${max} USD</b> ያስገቡ፦",
        'summary_buy': "📋 <b>የግዢ ማጠቃለያ</b>\nUSD: <code>${usd:,.2f}</code>\nETB: <code>{birr:,.2f}</code>",
        'summary_sell': "📋 <b>የመሸጫ ማጠቃለያ</b>\nUSD: <code>${usd:,.2f}</code>\nETB: <code>{birr:,.2f}</code>",
        'pay_instruct_buy': "📱 Telebirr: <code>{num}</code>\nክፍያ: <code>{birr:,.2f} ETB</code>\n\nየደረሰኝ Screenshot ይላኩ።",
        'pay_instruct_sell': "🌐 TRC20 Wallet: <code>{wallet}</code>\nመጠን: <code>${usd:,.2f} USD</code>\n\nየመላኪያ Screenshot ይላኩ።",
        'got_ss_buy': "📥 የ TRC20 Wallet Address ያስገቡ፦",
        'got_ss_sell': "📥 የባንክ ስም፣ አካውንት እና ሙሉ ስም ያስገቡ፦",
        'complete': "🎉 ትዕዛዝዎ ተልኳል! አድሚኑ አረጋግጦ ይጨርሳል።",
        'btn_cancel': "❌ ሰርዝ",
        'btn_contact': "💬 Help & Support"
    }
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton("🇪🇹 አማርኛ", callback_data="lang_am"), InlineKeyboardButton("🇬🇧 English", callback_data="lang_am")]
    ]
    if update.message:
        await update.message.reply_text("🌐 <b>Select Language / ቋንቋ ይምረጡ፦</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        await update.message.reply_text("💡 ለማስተካከል 'Main Menu' ይጫኑ።", reply_markup=PERMANENT_KEYBOARD)
    return LANG

async def select_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        rate = db_get_rate()
        keyboard = [
            [InlineKeyboardButton("🟢 Buy USD", callback_data="trade_buy"), InlineKeyboardButton("🔴 Sell USD", callback_data="trade_sell")]
        ]
        await query.message.edit_text(TEXTS['am']['welcome'].format(rate=rate), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return TRADE_TYPE

async def select_trade_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        trade_type = query.data.split("_")[1]
        context.user_data['trade_type'] = trade_type
        msg = TEXTS['am']['enter_amount_buy'].format(min=MIN_USD, max=MAX_USD) if trade_type == 'buy' else TEXTS['am']['enter_amount_sell'].format(min=MIN_USD, max=MAX_USD)
        await query.message.edit_text(msg, parse_mode="HTML")
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return AMOUNT
    try:
        usd_amount = float(update.message.text)
        if usd_amount < MIN_USD or usd_amount > MAX_USD:
            await update.message.reply_text(TEXTS['am']['invalid_num'].format(min=MIN_USD, max=MAX_USD), parse_mode="HTML")
            return AMOUNT
        
        rate = db_get_rate()
        total_birr = usd_amount * rate
        context.user_data['usd_amount'] = usd_amount
        context.user_data['total_birr'] = total_birr

        keyboard = [[InlineKeyboardButton("ቀጥል ➡️", callback_data="proceed_pay")]]
        msg = TEXTS['am']['summary_buy'].format(usd=usd_amount, birr=total_birr)
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return PAYMENT
    except ValueError:
        await update.message.reply_text(TEXTS['am']['invalid_num'].format(min=MIN_USD, max=MAX_USD), parse_mode="HTML")
        return AMOUNT

async def payment_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        trade_type = context.user_data.get('trade_type', 'buy')
        total_birr = context.user_data.get('total_birr', 0)
        usd_amount = context.user_data.get('usd_amount', 0)

        if trade_type == 'buy':
            msg = TEXTS['am']['pay_instruct_buy'].format(birr=total_birr, num=TELEBIRR_NUMBER)
            await query.message.reply_text(msg, parse_mode="HTML")
            return SCREENSHOT
        else:
            msg = TEXTS['am']['pay_instruct_sell'].format(usd=usd_amount, wallet=ADMIN_WALLET_ADDRESS)
            await query.message.reply_text(msg, parse_mode="HTML")
            return SELL_SCREENSHOT

async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message and update.message.photo:
        context.user_data['photo_file'] = update.message.photo[-1].file_id
        await update.message.reply_text(TEXTS['am']['got_ss_buy'], parse_mode="HTML")
        return WALLET_ADDRESS
    return SCREENSHOT

async def receive_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message and update.message.text:
        wallet = update.message.text
        user = update.effective_user
        if user:
            admin_msg = f"🚨 <b>NEW BUY ORDER!</b>\nUser: @{user.username}\nUSD: ${context.user_data.get('usd_amount')}\nWallet: <code>{wallet}</code>"
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=context.user_data['photo_file'], caption=admin_msg, parse_mode="HTML")
        await update.message.reply_text(TEXTS['am']['complete'], parse_mode="HTML")
        return ConversationHandler.END
    return WALLET_ADDRESS

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text("❌ ትዕዛዙ ተሰርዟል።")
    return ConversationHandler.END

def main() -> None:
    if not BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN missing.")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    restart_handler = MessageHandler(filters.Regex("^🔄 Main Menu / Restart$"), start)

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start), restart_handler],
        states={
            LANG: [CallbackQueryHandler(select_language, pattern="^lang_")],
            TRADE_TYPE: [CallbackQueryHandler(select_trade_type, pattern="^trade_")],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
            PAYMENT: [CallbackQueryHandler(payment_selected, pattern="^proceed_pay$")],
            SCREENSHOT: [MessageHandler(filters.PHOTO, receive_screenshot)],
            WALLET_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_wallet)],
        },
        fallbacks=[CommandHandler("cancel", cancel), restart_handler],
        per_message=False
    )

    app.add_handler(restart_handler)
    app.add_handler(conv_handler)

    logger.info("Bot starting with auto-reconnect...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
