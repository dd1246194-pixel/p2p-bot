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

# -----------------------------------------------------------------------------
# LOGGING CONFIGURATION
# -----------------------------------------------------------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
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
) = range(8)

# -----------------------------------------------------------------------------
# DATABASE MANAGEMENT
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
        logger.error(f"Error fetching rate: {e}")
        return DEFAULT_RATE

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
            "⚡ <i>ፈጣን፣ አስተማማኝ እና ሙሉ ደህንነቱ የተጠበቀ አገልግሎት!</i>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "👇 <b>እባክዎን ማድረግ የሚፈልጉትን ይምረጡ፦</b>"
        ),
        'enter_amount_buy': (
            "🟢 <b>የግዢ መጠን ያስገቡ (BUY USD)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 <b>የግዢ ወሰን፦</b>\n"
            "├ <b>አነስተኛ:</b> <code>${min:,.2f} USD</code>\n"
            "└ <b>ከፍተኛ:</b> <code>${max:,.2f} USD</code>\n\n"
            "✍️ <i>መግዛት የሚፈልጉትን የ USD መጠን በቁጥር ብቻ ያስገቡ፦</i>"
        ),
        'enter_amount_sell': (
            "🔴 <b>የመሸጫ መጠን ያስገቡ (SELL USD)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 <b>የመሸጫ ወሰን፦</b>\n"
            "├ <b>አነስተኛ:</b> <code>${min:,.2f} USD</code>\n"
            "└ <b>ከፍተኛ:</b> <code>${max:,.2f} USD</code>\n\n"
            "✍️ <i>መሸጥ የሚፈልጉትን የ USD መጠን በቁጥር ብቻ ያስገቡ፦</i>"
        ),
        'invalid_num': "⚠️ <b>የተሳሳተ ቁጥር!</b>\nእባክዎን ከ <b>${min:,.2f}</b> እስከ <b>${max:,.2f} USD</b> ባለው ወሰን ውስጥ ብቻ ያስገቡ፦",
        'summary_buy': (
            "🧾 <b>የግዢ ትዕዛዝ ማጠቃለያ (BUY RECEIPT)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💵 <b>የሚገዙት መጠን:</b> <code>${usd:,.2f} USD</code>\n"
            "📈 <b>የምንዛሬ ተመን:</b> <code>{rate:,.2f} ETB</code>\n"
            "💰 <b>ጠቅላላ የሚከፍሉት:</b> <code>{birr:,.2f} ETB</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "ለማረጋገጥና ወደ ክፍያ ለመሄድ ከታች ያለውን አዝራር ይጫኑ፦"
        ),
        'summary_sell': (
            "🧾 <b>የመሸጫ ትዕዛዝ ማጠቃለያ (SELL RECEIPT)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💵 <b>የሚሸጡት መጠን:</b> <code>${usd:,.2f} USD</code>\n"
            "📈 <b>የምንዛሬ ተመን:</b> <code>{rate:,.2f} ETB</code>\n"
            "💰 <b>ጠቅላላ የሚቀበሉት:</b> <code>{birr:,.2f} ETB</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "ለማረጋገጥና ወደ ክፍያ ለመሄድ ከታች ያለውን አዝራር ይጫኑ፦"
        ),
        'pay_instruct_buy': (
            "📱 <b>የ TELEBIRR ክፍያ መመሪያ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "1️⃣ ወደ Telebirr መተግበሪያዎ ወይም *127# ይሂዱ።\n"
            "2️⃣ ወደሚከተለው ስልክ ቁጥር ክፍያ ይፈጽሙ፦\n"
            "👉 <code>{num}</code>\n"
            "👤 <b>ስም:</b> <code>{name}</code>\n\n"
            "💵 <b>የሚከፍሉት ትክክለኛ መጠን:</b> <code>{birr:,.2f} ETB</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "3️⃣ ክፍያውን እንደፈጸሙ የደረሰኙን <b>Screenshot (ፎቶ)</b> እዚህ ይላኩ።"
        ),
        'pay_instruct_sell': (
            "🌐 <b>የ USDT (TRC20) መላኪያ መመሪያ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "1️⃣ ወደ የትኛውም ዋሌትዎ (Binance, Trust Wallet, etc.) ይሂዱ።\n"
            "2️⃣ ወደሚከተለው TRC20 Wallet Address ይላኩ፦\n"
            "👉 <code>{wallet}</code>\n\n"
            "💵 <b>የሚልኩት ትክክለኛ መጠን:</b> <code>${usd:,.2f} USDT</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "3️⃣ ዶላሩን እንደላኩ የመላኪያውን <b>Screenshot (ፎቶ)</b> እዚህ ይላኩ።"
        ),
        'got_ss_buy': "✅ <b>ደረሰኝዎ ደርሶናል!</b>\n\n🎯 አሁን ዶላሩ (USDT) ገቢ የሚደረግበትን የ <b>TRC20 Wallet Address</b> ጽፈው ይላኩልን፦",
        'got_ss_sell': "✅ <b>ደረሰኝዎ ደርሶናል!</b>\n\n📱 አሁን ብር ገቢ የሚደረግበትን የ<b>Telebirr ስልክ ቁጥር እና ሙሉ ስም</b> ጽፈው ይላኩልን፦",
        'complete': (
            "🎉 <b>ትዕዛዝዎ በስኬት ተላኳል!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⏳ አድሚኖቻችን መረጃዎን በማረጋገጥ ላይ ናቸው። እንደተጠናቀቀ መልእክት ይደርስዎታል።\n"
            "እናመሰግናለን!"
        ),
        'btn_cancel': "❌ ሰርዝ (Cancel)",
        'btn_support': "💬 እገዛና ቅሬታ (Support)"
    }
}

# -----------------------------------------------------------------------------
# FLOW HANDLERS
# -----------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton("🇪🇹 አማርኛ", callback_data="lang_am"), InlineKeyboardButton("🇬🇧 English", callback_data="lang_am")]
    ]
    if update.message:
        await update.message.reply_text("🌐 <b>Select Language / ቋንቋ ይምረጡ፦</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        await update.message.reply_text("💡 <i>ዋናው ሜኑ ላይ ለመመለስ ሁልጊዜ ከታች 'Main Menu' የሚለውን ይጠቀሙ።</i>", reply_markup=PERMANENT_KEYBOARD, parse_mode="HTML")
    return LANG

async def select_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        rate = db_get_rate()
        keyboard = [
            [InlineKeyboardButton("🟢 Buy USD (መግዛት)", callback_data="trade_buy"), InlineKeyboardButton("🔴 Sell USD (መሸጥ)", callback_data="trade_sell")],
            [InlineKeyboardButton(TEXTS['am']['btn_support'], callback_data="bot_support")]
        ]
        await query.message.edit_text(TEXTS['am']['welcome'].format(rate=rate), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return TRADE_TYPE

async def select_trade_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        trade_type = query.data.split("_")[1]
        context.user_data['trade_type'] = trade_type
        
        keyboard = [[InlineKeyboardButton(TEXTS['am']['btn_cancel'], callback_data="user_cancel")]]
        msg = TEXTS['am']['enter_amount_buy'].format(min=MIN_USD, max=MAX_USD) if trade_type == 'buy' else TEXTS['am']['enter_amount_sell'].format(min=MIN_USD, max=MAX_USD)
        await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
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
        trade_type = context.user_data.get('trade_type', 'buy')

        keyboard = [
            [InlineKeyboardButton("አረጋግጥና ቀጥል ➡️", callback_data="proceed_pay")],
            [InlineKeyboardButton(TEXTS['am']['btn_cancel'], callback_data="user_cancel")]
        ]
        msg = TEXTS['am']['summary_buy'].format(usd=usd_amount, rate=rate, birr=total_birr) if trade_type == 'buy' else TEXTS['am']['summary_sell'].format(usd=usd_amount, rate=rate, birr=total_birr)
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return PAYMENT_CHOICE
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

        keyboard = [[InlineKeyboardButton(TEXTS['am']['btn_cancel'], callback_data="user_cancel")]]

        if trade_type == 'buy':
            msg = TEXTS['am']['pay_instruct_buy'].format(birr=total_birr, num=TELEBIRR_NUMBER, name=ADMIN_NAME)
            await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
            return SCREENSHOT
        else:
            msg = TEXTS['am']['pay_instruct_sell'].format(usd=usd_amount, wallet=ADMIN_WALLET_ADDRESS)
            await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
            return SELL_SCREENSHOT

async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message and update.message.photo:
        context.user_data['photo_file'] = update.message.photo[-1].file_id
        await update.message.reply_text(TEXTS['am']['got_ss_buy'], parse_mode="HTML")
        return WALLET_ADDRESS
    return SCREENSHOT

async def receive_sell_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message and update.message.photo:
        context.user_data['photo_file'] = update.message.photo[-1].file_id
        await update.message.reply_text(TEXTS['am']['got_ss_sell'], parse_mode="HTML")
        return SELL_TELEBIRR
    return SELL_SCREENSHOT

async def receive_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message and update.message.text:
        wallet = update.message.text
        user = update.effective_user

        if user:
            admin_msg = (
                f"🚨 <b>NEW BUY ORDER RECEIVED!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>User:</b> @{user.username} (<code>{user.id}</code>)\n"
                f"💵 <b>Amount:</b> <code>${context.user_data.get('usd_amount'):,.2f} USD</code>\n"
                f"💰 <b>Total Birr:</b> <code>{context.user_data.get('total_birr'):,.2f} ETB</code>\n"
                f"📱 <b>Payment Method:</b> <code>Telebirr</code>\n"
                f"📍 <b>Payout Wallet:</b> <code>{wallet}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            )
            admin_btn = [[
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user.id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}")
            ]]
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=context.user_data['photo_file'], caption=admin_msg, reply_markup=InlineKeyboardMarkup(admin_btn), parse_mode="HTML")
        await update.message.reply_text(TEXTS['am']['complete'], parse_mode="HTML")
        return ConversationHandler.END
    return WALLET_ADDRESS

async def receive_sell_telebirr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message and update.message.text:
        telebirr_info = update.message.text
        user = update.effective_user
        if user:
            admin_msg = (
                f"🚨 <b>NEW SELL ORDER RECEIVED!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>User:</b> @{user.username} (<code>{user.id}</code>)\n"
                f"💵 <b>Amount:</b> <code>${context.user_data.get('usd_amount'):,.2f} USD</code>\n"
                f"💰 <b>Total Birr:</b> <code>{context.user_data.get('total_birr'):,.2f} ETB</code>\n"
                f"📱 <b>Payout Telebirr:</b> <code>{telebirr_info}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            )
            admin_btn = [[
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user.id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}")
            ]]
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=context.user_data['photo_file'], caption=admin_msg, reply_markup=InlineKeyboardMarkup(admin_btn), parse_mode="HTML")
        await update.message.reply_text(TEXTS['am']['complete'], parse_mode="HTML")
        return ConversationHandler.END
    return SELL_TELEBIRR

async def admin_decision_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query:
        await query.answer()
        data = query.data.split("_")
        action = data[0]
        user_id = int(data[1])

        if action == "approve":
            await context.bot.send_message(chat_id=user_id, text="🎉 <b>ትዕዛዝዎ በአድሚን ተረጋግጦ ተጠናቋል!</b>\nስላገለገልንዎት ደስ ብሎናል።", parse_mode="HTML")
            await query.edit_message_caption(caption=query.message.caption + "\n\n✅ <b>STATUS: APPROVED</b>", parse_mode="HTML")
        elif action == "reject":
            await context.bot.send_message(chat_id=user_id, text="❌ <b>ትዕዛዝዎ በአድሚን አልፀደቀም።</b>\nእባክዎን ለበለጠ መረጃ አድሚኑን ያነጋግሩ።", parse_mode="HTML")
            await query.edit_message_caption(caption=query.message.caption + "\n\n❌ <b>STATUS: REJECTED</b>", parse_mode="HTML")

async def cancel_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query and update.callback_query.message:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text("❌ <b>ትዕዛዙ ተሰርዟል።</b>\nእንደገና ለመጀመር /start ይበሉ።", parse_mode="HTML")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text("❌ ትዕዛዙ ተሰርዟል።")
    return ConversationHandler.END

# -----------------------------------------------------------------------------
# MAIN EXECUTION
# -----------------------------------------------------------------------------
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
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔄 Main Menu / Restart$"), get_amount)],
            PAYMENT_CHOICE: [CallbackQueryHandler(payment_selected, pattern="^proceed_pay$")],
            SCREENSHOT: [MessageHandler(filters.PHOTO, receive_screenshot)],
            WALLET_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔄 Main Menu / Restart$"), receive_wallet)],
            SELL_SCREENSHOT: [MessageHandler(filters.PHOTO, receive_sell_screenshot)],
            SELL_TELEBIRR: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔄 Main Menu / Restart$"), receive_sell_telebirr)],
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
    app.add_handler(CallbackQueryHandler(admin_decision_handler, pattern="^(approve|reject)_"))

    logger.info("Bot starting with auto-reconnect...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
