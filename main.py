import os
import sqlite3
import logging
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
    SUPPORT_MSG,
) = range(9)

# -----------------------------------------------------------------------------
# DATABASE MANAGEMENT (WITH VACUUM & WAL FOR SPACE OPTIMIZATION)
# -----------------------------------------------------------------------------
DB_FILE = "bot_data.db"

def init_db() -> None:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")  # Speed & Space optimization
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value REAL
                )
            ''')
            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('rate', ?)", (DEFAULT_RATE,))
            conn.commit()
            cursor.execute("VACUUM;")  # Shrink database size
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
            "💳 <b>የክፍያ መንገድ:</b> <code>Telebirr (ቴሌብር ብቻ)</code>\n"
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
            "📱 <b>የክፍያ መንገድ:</b> <code>Telebirr</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "ለማረጋገጥና ወደ ክፍያ ለመሄድ ከታች ያለውን አዝራር ይጫኑ፦"
        ),
        'summary_sell': (
            "🧾 <b>የመሸጫ ትዕዛዝ ማጠቃለያ (SELL RECEIPT)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💵 <b>የሚሸጡት መጠን:</b> <code>${usd:,.2f} USD</code>\n"
            "📈 <b>የምንዛሬ ተመን:</b> <code>{rate:,.2f} ETB</code>\n"
            "💰 <b>ጠቅላላ የሚቀበሉት:</b> <code>{birr:,.2f} ETB</code>\n"
            "📱 <b>የክፍያ መንገድ:</b> <code>Telebirr</code>\n"
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
            "⏳ አድሚኖቻችን መረጃዎን በማረጋገጥ ላይ ናቸው። እንደተጠናቀቀ መልእክትና የክፍያ Proof ይደርስዎታል።\n"
            "እናመሰግናለን!"
        ),
        'support_prompt': "💬 <b>እገዛና ጥያቄ መስመር</b>\n━━━━━━━━━━━━━━━━━━━━━━\nያልገባዎትን ነገር፣ ጥያቄዎን ወይም አስተያየትዎን እዚህ ጽፈው ይላኩልን። አድሚኖቻችን በፍጥነት ይመልሱልዎታል።",
        'support_sent': "✅ መልእክትዎ ለአድሚን ተልኳል! በአጭር ጊዜ ውስጥ መልስ ይደርስዎታል።",
        'btn_cancel': "❌ ሰርዝ (Cancel)",
        'btn_support': "💬 እገዛና ጥያቄ (Support)"
    },
    'om': {
        'welcome': (
            "🏦 <b>OKXETH OFFICIAL P2P TRADING BOT</b> 🏦\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "👋 <b>Baga gara Bootii Jijjiarraa Gabaa P2P nagaadaan dhuftan!</b>\n\n"
            "📊 <b>Gattii Jijjiarraa Har'aa፦</b>\n"
            "└ <code>1 USD = {rate:,.2f} ETB</code>\n\n"
            "💳 <b>Kaffaltii:</b> <code>Telebirr Qofa</code>\n"
            "⚡ <i>Saffisaa, Amanamaa fi Nageenyi isa kan eegame!</i>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "👇 <b>Maaloo waan raawwachuu barbaaddan filadhaa፦</b>"
        ),
        'enter_amount_buy': (
            "🟢 <b>Hanga Bitachuu Barbaaddan Galchaa (BUY USD)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 <b>Hanga Bitinsa፦</b>\n"
            "├ <b>Xiqqaa:</b> <code>${min:,.2f} USD</code>\n"
            "└ <b>Guddaa:</b> <code>${max:,.2f} USD</code>\n\n"
            "✍️ <i>Hanga USD bitachuu barbaaddan lakkoofsaan galchaa፦</i>"
        ),
        'enter_amount_sell': (
            "🔴 <b>Hanga Gurguruu Barbaaddan Galchaa (SELL USD)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 <b>Hanga Gurgurtaaa፦</b>\n"
            "├ <b>Xiqqaa:</b> <code>${min:,.2f} USD</code>\n"
            "└ <b>Guddaa:</b> <code>${max:,.2f} USD</code>\n\n"
            "✍️ <i>Hanga USD gurguruu barbaaddan lakkoofsaan galchaa፦</i>"
        ),
        'invalid_num': "⚠️ <b>Lakkoofsa Dogoggoraa!</b>\nMaaloo <b>${min:,.2f}</b> hanga <b>${max:,.2f} USD</b> jiddutti galchaa፦",
        'summary_buy': (
            "🧾 <b>Cuunfaa Ajaja Bitinsaa (BUY RECEIPT)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💵 <b>Hanga Bittaatan:</b> <code>${usd:,.2f} USD</code>\n"
            "📈 <b>Gattii Jijjiarraa:</b> <code>{rate:,.2f} ETB</code>\n"
            "💰 <b>Waliigala Kaffaltii:</b> <code>{birr:,.2f} ETB</code>\n"
            "📱 <b>Kaffaltii:</b> <code>Telebirr</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Mirkaneessuufi gara kaffaltiitti darbuuf button gadii cuqaasaa፦"
        ),
        'summary_sell': (
            "🧾 <b>Cuunfaa Ajaja Gurgurtaaa (SELL RECEIPT)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💵 <b>Hanga Gurgurtan:</b> <code>${usd:,.2f} USD</code>\n"
            "📈 <b>Gattii Jijjiarraa:</b> <code>{rate:,.2f} ETB</code>\n"
            "💰 <b>Waliigala Fudhattan:</b> <code>{birr:,.2f} ETB</code>\n"
            "📱 <b>Kaffaltii:</b> <code>Telebirr</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Mirkaneessuufi gara kaffaltiitti darbuuf button gadii cuqaasaa፦"
        ),
        'pay_instruct_buy': (
            "📱 <b>Qajeelfama Kaffaltii TELEBIRR</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "1️⃣ Gara Appii Telebirr ykn *127# deemaa.\n"
            "2️⃣ Lakkoofsa kanaan kaffaltii raawwadhaa፦\n"
            "👉 <code>{num}</code>\n"
            "👤 <b>Maqaa:</b> <code>{name}</code>\n\n"
            "💵 <b>Hanga Kaffaltii:</b> <code>{birr:,.2f} ETB</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "3️⃣ Kaffaltii raawwattanii <b>Screenshot (Suraa)</b> asitti ergaa."
        ),
        'pay_instruct_sell': (
            "🌐 <b>Qajeelfama Ergaa USDT (TRC20)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "1️⃣ Gara Teessoo Wallet keessanii deemaa.\n"
            "2️⃣ Teessoo TRC20 kanatti ergaa፦\n"
            "👉 <code>{wallet}</code>\n\n"
            "💵 <b>Hanga Ergtan:</b> <code>${usd:,.2f} USDT</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "3️⃣ Ergtanii <b>Screenshot (Suraa)</b> asitti ergaa."
        ),
        'got_ss_buy': "✅ <b>Nagaheen keessan nu gaheera!</b>\n\n🎯 Amma Teessoo <b>TRC20 Wallet Address</b> keessan barreessitanii ergaa፦",
        'got_ss_sell': "✅ <b>Nagaheen keessan nu gaheera!</b>\n\n📱 Amma Lakkoofsa <b>Telebirr fi Maqaa Guutuu</b> keessan barreessitanii ergaa፦",
        'complete': (
            "🎉 <b>Ajajni keessan milkaa'inaan ergameera!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⏳ Adminoonni keenya mirkaneessaa jiru. Erga xumuramee deebii fi Proof isiniif ergana.\n"
            "Galatoomaa!"
        ),
        'support_prompt': "💬 <b>Gaaffii fi Deeggersa</b>\n━━━━━━━━━━━━━━━━━━━━━━\nGaaffii ykn yaada qabdan asitti barreessitanii ergaa. Adminiin keenya saffisaan isiniif deebisa.",
        'support_sent': "✅ Ergaan keessan Adminif ergameera! Yeroo dhiyootti deebiin isiniif ergama.",
        'btn_cancel': "❌ Haqi (Cancel)",
        'btn_support': "💬 Deeggersa (Support)"
    },
    'en': {
        'welcome': (
            "🏦 <b>OKXETH OFFICIAL P2P TRADING BOT</b> 🏦\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "👋 <b>Welcome to the trusted P2P Exchange Bot!</b>\n\n"
            "📊 <b>Today's Exchange Rate:</b>\n"
            "└ <code>1 USD = {rate:,.2f} ETB</code>\n\n"
            "💳 <b>Payment Method:</b> <code>Telebirr Only</code>\n"
            "⚡ <i>Fast, Secure, and Reliable Service!</i>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "👇 <b>Please select an option below:</b>"
        ),
        'enter_amount_buy': (
            "🟢 <b>Enter Amount to Buy (BUY USD)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 <b>Trading Limits:</b>\n"
            "├ <b>Min:</b> <code>${min:,.2f} USD</code>\n"
            "└ <b>Max:</b> <code>${max:,.2f} USD</code>\n\n"
            "✍️ <i>Type the amount in USD (numbers only):</i>"
        ),
        'enter_amount_sell': (
            "🔴 <b>Enter Amount to Sell (SELL USD)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 <b>Trading Limits:</b>\n"
            "├ <b>Min:</b> <code>${min:,.2f} USD</code>\n"
            "└ <b>Max:</b> <code>${max:,.2f} USD</code>\n\n"
            "✍️ <i>Type the amount in USD (numbers only):</i>"
        ),
        'invalid_num': "⚠️ <b>Invalid Amount!</b>\nPlease enter between <b>${min:,.2f}</b> and <b>${max:,.2f} USD</b>:",
        'summary_buy': (
            "🧾 <b>BUY RECEIPT SUMMARY</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💵 <b>Buying Amount:</b> <code>${usd:,.2f} USD</code>\n"
            "📈 <b>Exchange Rate:</b> <code>{rate:,.2f} ETB</code>\n"
            "💰 <b>Total Payable:</b> <code>{birr:,.2f} ETB</code>\n"
            "📱 <b>Payment Method:</b> <code>Telebirr</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Click the button below to confirm and proceed to payment:"
        ),
        'summary_sell': (
            "🧾 <b>SELL RECEIPT SUMMARY</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💵 <b>Selling Amount:</b> <code>${usd:,.2f} USD</code>\n"
            "📈 <b>Exchange Rate:</b> <code>{rate:,.2f} ETB</code>\n"
            "💰 <b>Total Receivable:</b> <code>{birr:,.2f} ETB</code>\n"
            "📱 <b>Payment Method:</b> <code>Telebirr</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Click the button below to confirm and proceed:"
        ),
        'pay_instruct_buy': (
            "📱 <b>TELEBIRR PAYMENT INSTRUCTIONS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "1️⃣ Open your Telebirr App or dial *127#.\n"
            "2️⃣ Make payment to this phone number:\n"
            "👉 <code>{num}</code>\n"
            "👤 <b>Name:</b> <code>{name}</code>\n\n"
            "💵 <b>Exact Amount to Pay:</b> <code>{birr:,.2f} ETB</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "3️⃣ Send the payment <b>Screenshot (Image)</b> here."
        ),
        'pay_instruct_sell': (
            "🌐 <b>USDT (TRC20) TRANSFER INSTRUCTIONS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "1️⃣ Go to your crypto wallet (Binance, Trust Wallet, etc.).\n"
            "2️⃣ Send to the following TRC20 Wallet Address:\n"
            "👉 <code>{wallet}</code>\n\n"
            "💵 <b>Exact Amount to Send:</b> <code>${usd:,.2f} USDT</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "3️⃣ Send the transfer <b>Screenshot (Image)</b> here."
        ),
        'got_ss_buy': "✅ <b>Screenshot received!</b>\n\n🎯 Now reply with your <b>TRC20 Wallet Address</b> to receive the USD:",
        'got_ss_sell': "✅ <b>Screenshot received!</b>\n\n📱 Now reply with your <b>Telebirr Phone Number & Full Name</b>:",
        'complete': (
            "🎉 <b>Your order has been submitted successfully!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⏳ Our admins are verifying your request. You will be notified with payment proof shortly.\n"
            "Thank you!"
        ),
        'support_prompt': "💬 <b>Help & Support</b>\n━━━━━━━━━━━━━━━━━━━━━━\nPlease type your message or question below. Our support team will reply shortly.",
        'support_sent': "✅ Your message has been sent to Admin! You will get a response soon.",
        'btn_cancel': "❌ Cancel",
        'btn_support': "💬 Support"
    }
}

# Helper to get current user language
def get_txt(context: ContextTypes.DEFAULT_TYPE) -> dict:
    lang = context.user_data.get('lang', 'am')
    return TEXTS.get(lang, TEXTS['am'])

# -----------------------------------------------------------------------------
# FLOW HANDLERS
# -----------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()  # Clear cache to save memory
    keyboard = [
        [
            InlineKeyboardButton("🇪🇹 አማርኛ", callback_data="lang_am"),
            InlineKeyboardButton("🇪🇹 Afaan Oromoo", callback_data="lang_om"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")
        ]
    ]
    if update.message:
        await update.message.reply_text("🌐 <b>Select Language / ቋንቋ ይምረጡ / Lugha Filadhaa፦</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        await update.message.reply_text("💡 <i>Main Menu / Restart</i>", reply_markup=PERMANENT_KEYBOARD, parse_mode="HTML")
    return LANG

async def select_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        lang_code = query.data.split("_")[1]
        context.user_data['lang'] = lang_code
        txt = get_txt(context)
        rate = db_get_rate()
        
        keyboard = [
            [InlineKeyboardButton("🟢 Buy USD (መግዛት)", callback_data="trade_buy"), InlineKeyboardButton("🔴 Sell USD (መሸጥ)", callback_data="trade_sell")],
            [InlineKeyboardButton(txt['btn_support'], callback_data="bot_support")]
        ]
        await query.message.edit_text(txt['welcome'].format(rate=rate), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return TRADE_TYPE

async def select_trade_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        txt = get_txt(context)
        if query.data == "bot_support":
            await query.message.edit_text(txt['support_prompt'], parse_mode="HTML")
            return SUPPORT_MSG

        trade_type = query.data.split("_")[1]
        context.user_data['trade_type'] = trade_type
        
        keyboard = [[InlineKeyboardButton(txt['btn_cancel'], callback_data="user_cancel")]]
        msg = txt['enter_amount_buy'].format(min=MIN_USD, max=MAX_USD) if trade_type == 'buy' else txt['enter_amount_sell'].format(min=MIN_USD, max=MAX_USD)
        await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return AMOUNT

async def handle_support_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message and update.message.text:
        user = update.effective_user
        txt = get_txt(context)
        if user:
            admin_msg = (
                f"📩 <b>NEW SUPPORT QUESTION/MESSAGE!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>From:</b> @{user.username} (<code>{user.id}</code>)\n"
                f"📝 <b>Message:</b> {update.message.text}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            )
            admin_btn = [[InlineKeyboardButton("💬 Reply to User", callback_data=f"reply_{user.id}")]]
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, reply_markup=InlineKeyboardMarkup(admin_btn), parse_mode="HTML")
        await update.message.reply_text(txt['support_sent'], parse_mode="HTML")
        context.user_data.clear()
        return ConversationHandler.END
    return SUPPORT_MSG

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
            [InlineKeyboardButton("አረጋግጥና ቀጥል ➡️ / Proceed", callback_data="proceed_pay")],
            [InlineKeyboardButton(txt['btn_cancel'], callback_data="user_cancel")]
        ]
        msg = txt['summary_buy'].format(usd=usd_amount, rate=rate, birr=total_birr) if trade_type == 'buy' else txt['summary_sell'].format(usd=usd_amount, rate=rate, birr=total_birr)
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
            await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
            return SCREENSHOT
        else:
            msg = txt['pay_instruct_sell'].format(usd=usd_amount, wallet=ADMIN_WALLET_ADDRESS)
            await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
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
            admin_btn = [
                [InlineKeyboardButton("📸 Approve with Proof", callback_data=f"proof_{user.id}")],
                [InlineKeyboardButton("✅ Quick Approve", callback_data=f"approve_{user.id}"), InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}")],
                [InlineKeyboardButton("💬 Message User", callback_data=f"reply_{user.id}")]
            ]
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=context.user_data['photo_file'], caption=admin_msg, reply_markup=InlineKeyboardMarkup(admin_btn), parse_mode="HTML")
        await update.message.reply_text(txt['complete'], parse_mode="HTML")
        context.user_data.clear()
        return ConversationHandler.END
    return WALLET_ADDRESS

async def receive_sell_telebirr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = get_txt(context)
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
            admin_btn = [
                [InlineKeyboardButton("📸 Approve with Proof", callback_data=f"proof_{user.id}")],
                [InlineKeyboardButton("✅ Quick Approve", callback_data=f"approve_{user.id}"), InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}")],
                [InlineKeyboardButton("💬 Message User", callback_data=f"reply_{user.id}")]
            ]
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=context.user_data['photo_file'], caption=admin_msg, reply_markup=InlineKeyboardMarkup(admin_btn), parse_mode="HTML")
        await update.message.reply_text(txt['complete'], parse_mode="HTML")
        context.user_data.clear()
        return ConversationHandler.END
    return SELL_TELEBIRR

# -----------------------------------------------------------------------------
# ADMIN ACTIONS HANDLER
# -----------------------------------------------------------------------------
async def admin_decision_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query:
        await query.answer()
        data = query.data.split("_")
        action = data[0]
        target_user_id = int(data[1])

        if action == "proof":
            context.bot_data['proof_target_id'] = target_user_id
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"📸 <b>ለተጠቃሚ ID <code>{target_user_id}</code> የምትልከውን የክፍያ ደረሰኝ/Proof (Screenshot) አሁን ላክ፦</b>",
                parse_mode="HTML"
            )
        elif action == "approve":
            await context.bot.send_message(chat_id=target_user_id, text="🎉 <b>ትዕዛዝዎ በአድሚን ተረጋግጦ ተጠናቋል! / Your order has been APPROVED!</b>", parse_mode="HTML")
            await query.edit_message_caption(caption=(query.message.caption or query.message.text or "") + "\n\n✅ <b>STATUS: APPROVED (No Proof)</b>", parse_mode="HTML")
        elif action == "reject":
            await context.bot.send_message(chat_id=target_user_id, text="❌ <b>ትዕዛዝዎ አልፀደቀም። / Your order has been REJECTED.</b>", parse_mode="HTML")
            await query.edit_message_caption(caption=(query.message.caption or query.message.text or "") + "\n\n❌ <b>STATUS: REJECTED</b>", parse_mode="HTML")
        elif action == "reply":
            context.bot_data['reply_target_id'] = target_user_id
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"✍️ <b>ለተጠቃሚ ID <code>{target_user_id}</code> መላክ የሚፈልጉትን መልእክት ጽፈው ይላኩ፦</b>", parse_mode="HTML")

async def admin_media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.from_user or update.message.from_user.id != ADMIN_ID:
        return

    # Handle Sending Proof Photo
    proof_target_id = context.bot_data.get('proof_target_id')
    if proof_target_id and update.message.photo:
        photo_id = update.message.photo[-1].file_id
        caption_text = (
            "🎉 <b>ትዕዛዝዎ በስኬት ተጠናቋል! (ORDER COMPLETED)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🧾 <b>የክፍያ ማረጋገጫ ደረሰኝ (Payment Proof) ከላይ ተያይዟል።</b>\n"
            "ስላገለገልንዎት ደስተኞች ነን! 🙏"
        )
        await context.bot.send_photo(chat_id=proof_target_id, photo=photo_id, caption=caption_text, parse_mode="HTML")
        await update.message.reply_text(f"✅ የክፍያ Proof ደረሰኝ ለተጠቃሚ ID <code>{proof_target_id}</code> በስኬት ተላኳል!", parse_mode="HTML")
        context.bot_data.pop('proof_target_id', None)
        return

    # Handle Text Reply
    reply_target_id = context.bot_data.get('reply_target_id')
    if reply_target_id and update.message.text:
        reply_text = update.message.text
        await context.bot.send_message(
            chat_id=reply_target_id,
            text=f"💬 <b>ከአድሚን የተላከ መልእክት / Admin Message:</b>\n━━━━━━━━━━━━━━━━━━━━━━\n{reply_text}",
            parse_mode="HTML"
        )
        await update.message.reply_text(f"✅ መልእክትዎ ለተጠቃሚ ID <code>{reply_target_id}</code> በስኬት ተላኳል!", parse_mode="HTML")
        context.bot_data.pop('reply_target_id', None)

async def cancel_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query and update.callback_query.message:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text("❌ <b>ትዕዛዙ ተሰርዟል። / Cancelled.</b>\nእንደገና ለመጀመር /start ይበሉ።", parse_mode="HTML")
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text("❌ ትዕዛዙ ተሰርዟል።")
    context.user_data.clear()
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
            TRADE_TYPE: [CallbackQueryHandler(select_trade_type, pattern="^(trade_|bot_support)")],
            SUPPORT_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔄 Main Menu / Restart$"), handle_support_msg)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔄 Main Menu / Restart$"), get_amount)],
            PAYMENT_CHOICE: [CallbackQueryHandler(payment_selected, pattern="^proceed_pay$")],
            SCREENSHOT: [MessageHandler(filters.PHOTO, receive_screenshot)],
            WALLET_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔄 Main Menu / Restart$"), receive_wallet)],
            SELL_SCREENSHOT: [MessageHandler(filters.PHOTO, receive_sell_screenshot)],
            SELL_TELEBIRR: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔄 Main Menu / Restart$"), receive_sell_telebirr)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$"),
            restart_handler,
        ],
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(admin_decision_handler, pattern="^(proof_|approve_|reject_|reply_)"))
    app.add_handler(MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), admin_media_handler))

    logger.info("Bot started successfully...")
    app.run_polling()

if __name__ == "__main__":
    main()
