# type: ignore
import os
import sqlite3
import logging
from typing import Any
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# ----------------- FLASK WEB SERVER -----------------
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "OKXETH P2P Bot is Alive and Running 24/7!", 200

def run_flask():
    app_web.run(host='0.0.0.0', port=8080)

# ----------------- LOGGING & CONFIG -----------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_ID = 7798227927
DEFAULT_RATE = 184.0
TELEBIRR_NUMBER = "0900253321"
ADMIN_USERNAME = "@your_admin_username"  # 📌 የአድሚን ዩዘርኔም
PROOF_CHANNEL = "@your_channel_username" # 📌 የቻናል ዩዘርኔም

MIN_USD = 10.0
MAX_USD = 2100.0

LANG, AMOUNT, PAYMENT, SCREENSHOT, WALLET_ADDRESS = range(5)

# ----------------- DATABASE SETUP -----------------
DB_FILE = "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
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
    conn.close()

init_db()

def db_get_rate() -> float:
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'rate'")
        row = cursor.fetchone()
        conn.close()
        return float(row[0]) if row else DEFAULT_RATE
    except Exception:
        return DEFAULT_RATE

def db_set_rate(new_rate: float):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET value = ? WHERE key = 'rate'", (new_rate,))
    conn.commit()
    conn.close()

def db_update_stats(usd_amount: float):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE stats SET total_orders = total_orders + 1, total_usd_volume = total_usd_volume + ? WHERE id = 1", (usd_amount,))
    conn.commit()
    conn.close()

def db_get_stats():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT total_orders, total_usd_volume FROM stats WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return row if row else (0, 0.0)

# Memory locks & flags
active_orders = set()
maintenance_mode = False

# ----------------- LOCALIZATION TEXTS (BEAUTIFIED) -----------------
TEXTS = {
    'am': {
        'welcome': (
            "✨ <b>ወደ OKXETH P2P ቦት እንኳን ደህና መጡ!</b> ✨\n\n"
            "───────────────\n"
            "💱 <b>የዛሬ የምንዛሬ ተመን፦</b> <code>1 USD = {rate} Birr</code>\n"
            "📊 <b>የግዢ ወሰን፦</b>\n"
            "├ 🟢 አነስተኛ፦ <b>${min:,.0f} USD</b>\n"
            "└ 🔴 ከፍተኛ፦ <b>${max:,.0f} USD</b>\n"
            "───────────────\n\n"
            "✍️ <i>እባክዎን መግዛት የሚፈልጉትን የዶላር (USD) መጠን ያስገቡ፦</i>\n"
            "💡 <i>ለምሳሌ፦ 10 ወይም 50</i>"
        ),
        'invalid_num': (
            "⚠️ <b>የተሳሳተ መጠን ያስገቡት!</b>\n\n"
            "እባክዎን ከ <b>${min:,.0f}</b> እስከ <b>${max:,.0f} USD</b> ባለው ወሰን ውስጥ ትክክለኛ ቁጥር ያስገቡ፦"
        ),
        'summary': (
            "💎 <b>የትዕዛዝዎ ማጠቃለያ</b> 💎\n\n"
            "┌ 💵 <b>የሚገዙት መጠን፦</b> <code>${usd:,.2f} USD</code>\n"
            "└ 💰 <b>የሚከፍሉት ጠቅላላ ብር፦</b> <code>{birr:,.2f} ETB</code>\n\n"
            "👇 <i>እባክዎን ከታች ያለውን የክፍያ አማራጭ ይጫኑ፦</i>"
        ),
        'pay_instruct': (
            "📱 <b>የቴሌብር (Telebirr) ክፍያ መመሪያ</b>\n\n"
            "───────────────\n"
            "💳 <b>የሚከፍሉት መጠን፦</b> <code>{birr:,.2f} ETB</code>\n"
            "📞 <b>የTelebirr ቁጥር፦</b> <code>{num}</code>\n"
            "───────────────\n\n"
            "⏱️ <b>የጊዜ ገደብ፦</b> ክፍያውን በ <b>15 ደቂቃ</b> ውስጥ ፈጽመው ደረሰኝ መላክ አለብዎት!\n\n"
            "📌 <b>ተከተል፦</b>\n"
            "1️⃣ በላይ በተጠቀሰው ቁጥር ክፍያውን በቴሌብር ይላኩ።\n"
            "2️⃣ ክፍያው ሲጠናቀቅ የደረሰኙን <b>ስክሪንሹት (Screenshot)</b> እዚህ ይላኩ።"
        ),
        'got_ss': (
            "📥 <b>የክፍያ ደረሰኝዎ ተቀብለናል!</b> ✅\n\n"
            "🎯 አሁን ዶላሩ (USD) እንዲላክሎት የሚፈልጉበትን <b>የዋልሌት አድራሻ (Wallet Address)</b> ይፃፉልን፦"
        ),
        'complete': (
            "🎉 <b>ትዕዛዝዎ በስኬት ደርሶናል!</b>\n\n"
            "⏳ <b>የክፍያ ሁኔታ፦</b> <i>በግምገማ ላይ (Pending Verification)</i>\n\n"
            "🔄 አድሚኑ ክፍያውን አረጋግጦ ዶላሩን ወዲያውኑ ይልክልዎታል። እናመሰግናለን!"
        ),
        'cancel': "❌ <b>ትዕዛዝዎ ተሰርዟል።</b>\n\nእንደገና ለመጀመር <b>/start</b> ይበሉ።",
        'timeout': "⏰ <b>ጊዜዎ አልቋል!</b>\n\nበ15 ደቂቃ ውስጥ ክፍያ ስላላጠናቀቁ ትዕዛዝዎ ተሰርዟል። እንደገና ለመጀመር <b>/start</b> ይበሉ።",
        'active_exists': "⚠️ <b>ያልተጠናቀቀ ትዕዛዝ አለዎት!</b>\n\nእባክዎን ነባሩን ትዕዛዝ ያጠናቅቁ ወይም በ <b>/start</b> እንደገና ይጀምሩ።",
        'maintenance': "🛠️ <b>ቦቱ በአሁኑ ወቅት በስራ ማሻሻያ ላይ ነው!</b>\n\nእባክዎን ከጥቂት ደቂቃዎች በኋላ እንደገና ይሞክሩ።",
        'btn_cancel': "❌ ሰርዝ (Cancel)",
        'btn_contact': "💬 Contact Admin"
    },
    'om': {
        'welcome': (
            "✨ <b>Baga gara OKXETH P2P Bot nagaan dhuftan!</b> ✨\n\n"
            "───────────────\n"
            "💱 <b>Gatiin Har'aa፦</b> <code>1 USD = {rate} Birr</code>\n"
            "📊 <b>Daangaa Bitahaa፦</b>\n"
            "├ 🟢 Xiqqaangaa፦ <b>${min:,.0f} USD</b>\n"
            "└ 🔴 Guddaangaa፦ <b>${max:,.0f} USD</b>\n"
            "───────────────\n\n"
            "✍️ <i>Mallaqa Doolara (USD) bitachuu barbaaddan galchaa፦</i>\n"
            "💡 <i>Fakkeenyaaf፦ 10 ykn 50</i>"
        ),
        'invalid_num': "⚠️ <b>Gatiin galchitan sirrii miti!</b>\n\nMaaloo <b>${min:,.0f}</b> fi <b>${max:,.0f} USD</b> intala jiru galchaa፦",
        'summary': (
            "💎 <b>Gabaasa Ajaja Keessanii</b> 💎\n\n"
            "┌ 💵 <b>Hangam bittan፦</b> <code>${usd:,.2f} USD</code>\n"
            "└ 💰 <b>Kan kafaltan walumaagala፦</b> <code>{birr:,.2f} ETB</code>\n\n"
            "👇 <i>Maaloo karaa kafaltii filadhaa፦</i>"
        ),
        'pay_instruct': (
            "📱 <b>Qajeelfama Kafaltii Telebirr</b>\n\n"
            "───────────────\n"
            "💳 <b>Mallaqa Kafaltan፦</b> <code>{birr:,.2f} ETB</code>\n"
            "📞 <b>Lakkoofsa Telebirr፦</b> <code>{num}</code>\n"
            "───────────────\n\n"
            "⏱️ <b>Yeroo፦</b> Daqiiqaa <b>15</b> keessatti kafaltii raawwattanii nagahee erguu qabdu!\n\n"
            "📌 <b>Tarkaanfii፦</b>\n"
            "1️⃣ Lakkoofsa armaan oliitti Telebirriin ergaa.\n"
            "2️⃣ Kafaltii erga raawwattanii booda <b>Nagahee (Screenshot)</b> asitti ergaa."
        ),
        'got_ss': "📥 <b>Nagaheen kafaltii nu gaheera!</b> ✅\n\nAmma <b>Teessoo Wallet (Wallet Address)</b> Doolarri (USD) irratti ergamuu galchaa፦",
        'complete': "🎉 <b>Ajajni keessan nu gaheera!</b>\n\n⏳ <b>Haala Kafaltii፦</b> <i>Madaallii irra jira (Pending)</i>\n\nAdmin-ni mirkaneesse Mallaqa p2p isiniif erga. Galatoomaa!",
        'cancel': "❌ <b>Ajajni keessan haqameera.</b>\n\nIrra deebitanii eegaluuf <b>/start</b> jedhaa.",
        'timeout': "⏰ <b>Yeroon keessan dhumateera!</b>\n\nDaqiiqaa 15 keessatti waan hin xumurreef ajajni haqameera. Irra deebitanii eegaluuf <b>/start</b> jedhaa.",
        'active_exists': "⚠️ <b>Ajaja hin xumuramne qabdu!</b>\n\nMaaloo ajaja duraa xumuraa ykn <b>/start</b> jedhaa.",
        'maintenance': "🛠️ <b>Bottiin ammaan tana suphaa irra jira!</b>\n\nMaaloo daqiiqaa muraasa booda irra deebi'aa yaalaa.",
        'btn_cancel': "❌ Haqi (Cancel)",
        'btn_contact': "💬 Contact Admin"
    },
    'en': {
        'welcome': (
            "✨ <b>Welcome to OKXETH P2P BOT!</b> ✨\n\n"
            "───────────────\n"
            "💱 <b>Exchange Rate:</b> <code>1 USD = {rate} Birr</code>\n"
            "📊 <b>Buying Limits:</b>\n"
            "├ 🟢 Min: <b>${min:,.0f} USD</b>\n"
            "└ 🔴 Max: <b>${max:,.0f} USD</b>\n"
            "───────────────\n\n"
            "✍️ <i>Please enter the USD amount you want to buy:</i>\n"
            "💡 <i>Example: 10 or 50</i>"
        ),
        'invalid_num': "⚠️ <b>Invalid Amount!</b>\n\nPlease enter a value between <b>${min:,.0f}</b> and <b>${max:,.0f} USD</b>:",
        'summary': (
            "💎 <b>Order Summary</b> 💎\n\n"
            "┌ 💵 <b>Buying Amount:</b> <code>${usd:,.2f} USD</code>\n"
            "└ 💰 <b>Total Payable:</b> <code>{birr:,.2f} ETB</code>\n\n"
            "👇 <i>Please select your payment method below:</i>"
        ),
        'pay_instruct': (
            "📱 <b>Telebirr Payment Instructions</b>\n\n"
            "───────────────\n"
            "💳 <b>Amount to Pay:</b> <code>{birr:,.2f} ETB</code>\n"
            "📞 <b>Telebirr Number:</b> <code>{num}</code>\n"
            "───────────────\n\n"
            "⏱️ <b>Time Limit:</b> Complete payment within <b>15 minutes</b>!\n\n"
            "📌 <b>Steps:</b>\n"
            "1️⃣ Send the exact Birr amount to the Telebirr number.\n"
            "2️⃣ Upload the <b>Payment Screenshot</b> here."
        ),
        'got_ss': "📥 <b>Payment receipt received!</b> ✅\n\nNow enter your <b>Wallet Address</b> to receive USD:",
        'complete': "🎉 <b>Your order has been placed!</b>\n\n⏳ <b>Status:</b> <i>Pending Verification</i>\n\nOnce the admin verifies payment and transfers the crypto, you will be notified.",
        'cancel': "❌ <b>Order cancelled.</b>\n\nType <b>/start</b> to restart.",
        'timeout': "⏰ <b>Time expired!</b>\n\nOrder auto-cancelled after 15 mins. Type <b>/start</b> to try again.",
        'active_exists': "⚠️ <b>You have an active pending order!</b>\n\nPlease complete or cancel your existing order before starting a new one.",
        'maintenance': "🛠️ <b>Bot is currently under maintenance!</b>\n\nPlease try again shortly.",
        'btn_cancel': "❌ Cancel",
        'btn_contact': "💬 Contact Admin"
    },
    'so': {
        'welcome': (
            "✨ <b>Ku soo dhawoow OKXETH P2P BOT!</b> ✨\n\n"
            "───────────────\n"
            "💱 <b>Sarrifka Maanta:</b> <code>1 USD = {rate} Birr</code>\n"
            "📊 <b>Xaddidaada:</b>\n"
            "├ 🟢 Min: <b>${min:,.0f} USD</b>\n"
            "└ 🔴 Max: <b>${max:,.0f} USD</b>\n"
            "───────────────\n\n"
            "✍️ <i>Fadlan geli xaddiga USD ee aad rabto:</i>\n"
            "💡 <i>Tusaale: 10 ama 50</i>"
        ),
        'invalid_num': "⚠️ <b>Xaddiga uusan sax ahayn!</b>\n\nFadlan geli xaddiga u dhexeeya <b>${min:,.0f}</b> iyo <b>${max:,.0f} USD</b>:",
        'summary': (
            "💎 <b>Kooban ee Dalabka</b> 💎\n\n"
            "┌ 💵 <b>Xaddiga USD:</b> <code>${usd:,.2f} USD</code>\n"
            "└ 💰 <b>Wadarta Birr:</b> <code>{birr:,.2f} ETB</code>\n\n"
            "👇 <i>Fadlan dooro habka lacag bixinta:</i>"
        ),
        'pay_instruct': (
            "📱 <b>Awaamiirta Telebirr</b>\n\n"
            "───────────────\n"
            "💳 <b>Lacagta Bixinta:</b> <code>{birr:,.2f} ETB</code>\n"
            "📞 <b>Nambarka Telebirr:</b> <code>{num}</code>\n"
            "───────────────\n\n"
            "⏱️ <b>Xaddiga Waqtiga:</b> Ku bixi lacagta <b>15 daqiiqo</b> gudaheed!\n\n"
            "📌 <b>Tallaabooyinka:</b>\n"
            "1️⃣ U dir lacagta nambarka Telebirr.\n"
            "2️⃣ Halkan ku soo dir <b>Sawirka Risidka (Screenshot)</b>."
        ),
        'got_ss': "📥 <b>Risidka waa la helay!</b> ✅\n\nHada geli <b>Cinwaanka Wallet-ka</b> aad ku heli karto USD:",
        'complete': "🎉 <b>Dalabkaaga waa la guddoomay!</b>\n\n⏳ <b>Xaaladda:</b> <i>Dib u eegis (Pending)</i>\n\nMarkii maamuluhu xaqiijiyo lacagta, crypto ayaa lagu soo diri doonaa.",
        'cancel': "❌ <b>Dalabka waa la joojiyay.</b>\n\nQor <b>/start</b> si aad dib ugu bilaabto.",
        'timeout': "⏰ <b>Xilligii waa dhacay!</b>\n\nDalabkaagii waa la joojiyay. Qor <b>/start</b> si aad dib ugu bilaabto.",
        'active_exists': "⚠️ <b>Waxaad leedahay dalab weli furan!</b>\n\nFadlan dhameystir ama jooji dalabkaagii hore.",
        'maintenance': "🛠️ <b>Bot-ku wuxuu ku jiraa dayactir!</b>\n\nFadlan isku day dib marka ay xoogaa daqiiqado ah ka soo wareegaan.",
        'btn_cancel': "❌ Jooji (Cancel)",
        'btn_contact': "💬 Contact Admin"
    }
}

# ----------------- HELPER FUNCTIONS -----------------
def remove_timer_job(context: ContextTypes.DEFAULT_TYPE, user_id: int):
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
        logging.error(f"Failed to send timeout message to {user_id}: {e}")

# ----------------- HANDLERS -----------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "❓ <b>እርዳታና ድጋፍ (Help & Support)</b>\n\n"
        "የቦት አጠቃቀም ላይ ችግር ካጋጠመዎት ወይም ተጨማሪ ጥያቄ ካለዎት አድሚኑን ያናግሩ፦\n"
        f"👨‍💻 <b>Admin:</b> {ADMIN_USERNAME}\n\n"
        "📌 <b>ትዕዛዞች፦</b>\n"
        "• <b>/start</b> - አዲስ የዶላር ግዢ መጀመር\n"
        "• <b>/cancel</b> - ያለውን ትዕዛዝ መሰረዝ\n"
        "• <b>/help</b> - ድጋፍ ማግኘት"
    )
    if update.message:
        await update.message.reply_text(help_text, parse_mode="HTML")

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

    if update.message:
        await update.message.reply_text(
            "🌐 <b>Please select your language / ቋንቋ ይምረጡ / Maaloo afaan filadhaa / Fadlan dooro luqadaada:</b>",
            reply_markup=reply_markup,
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
        [InlineKeyboardButton(t['btn_cancel'], callback_data="user_cancel")],
        [InlineKeyboardButton(t['btn_contact'], url=f"https://t.me/{ADMIN_USERNAME.replace('@', '')}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = t['welcome'].format(rate=rate, min=MIN_USD, max=MAX_USD)
    await query.message.edit_text(msg, reply_markup=reply_markup, parse_mode="HTML")
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return AMOUNT
    user_data = context.user_data or {}
    lang = user_data.get('lang', 'am')
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
            [InlineKeyboardButton("📲 Pay with Telebirr", callback_data="telebirr")],
            [InlineKeyboardButton(t['btn_cancel'], callback_data="user_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        msg = t['summary'].format(usd=usd_amount, birr=total_birr)
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

    msg = t['pay_instruct'].format(birr=total_birr, usd=usd_amount, num=TELEBIRR_NUMBER)
    if query.message and hasattr(query.message, 'reply_text'):
        await getattr(query.message, 'reply_text')(msg, reply_markup=reply_markup, parse_mode="HTML")
    return SCREENSHOT

async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.photo:
        return SCREENSHOT

    user_data = context.user_data or {}
    lang = user_data.get('lang', 'am')
    t = TEXTS[lang]

    photo_file = update.message.photo[-1].file_id
    user_data['photo_file'] = photo_file

    keyboard = [[InlineKeyboardButton(t['btn_cancel'], callback_data="user_cancel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(t['got_ss'], reply_markup=reply_markup, parse_mode="HTML")
    return WALLET_ADDRESS

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
            f"📥 <b>አዲስ የትዕዛዝ ጥያቄ ደርሷል!</b>\n\n"
            f"🌐 <b>Language:</b> <code>{lang.upper()}</code>\n"
            f"👤 <b>ተጠቃሚ፦</b> {username_str}\n"
            f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
            f"💵 <b>የዶላር መጠን፦</b> <code>${usd_amount:,.2f} USD</code>\n"
            f"💰 <b>የክፍያ መጠን፦</b> <code>{total_birr:,.2f} ETB</code>\n"
            f"📍 <b>የዋልሌት አድራሻ፦</b> <code>{wallet_address}</code>\n\n"
            f"⚠️ <b>አድሚን አስተውል፦</b> በቴሌብር ሂሳብህ ውስጥ <b>{total_birr:,.2f} ETB</b> መግባቱን ሳታረጋግጥ Approve እንዳታደርግ!"
        )
        admin_keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user.id}_{usd_amount}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}")
            ],
            [
                InlineKeyboardButton("💬 Send Message", callback_data=f"msg_{user.id}")
            ]
        ]
        admin_markup = InlineKeyboardMarkup(admin_keyboard)
        try:
            await context.bot.send_photo(
                chat_id=ADMIN_ID, photo=photo_file, caption=admin_msg, reply_markup=admin_markup, parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Failed to send to admin: {e}")

    await update.message.reply_text(t['complete'], parse_mode="HTML")
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

    if query:
        await query.answer()
        await query.message.edit_text(t['cancel'], parse_mode="HTML")
    return ConversationHandler.END

# ----------------- ADMIN COMMANDS -----------------
async def admin_set_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or update.effective_user.id != ADMIN_ID:
        return
    if not context.args or len(context.args) < 1:
        current_rate = db_get_rate()
        await update.message.reply_text(f"ℹ️ የዛሬው የምንዛሬ ተመን፦ <b>1 USD = {current_rate} Birr</b>\n\nለመቀየር፦ <code>/setrate 185</code> ብለህ ፃፍ።", parse_mode="HTML")
        return
    try:
        new_rate = float(context.args[0])
        db_set_rate(new_rate)
        await update.message.reply_text(f"✅ <b>የምንዛሬ ተመን በተሳካ ሁኔታ ተቀይሯል!</b>\n\nአዲሱ ተመን፦ <b>1 USD = {new_rate} Birr</b>", parse_mode="HTML")
    except ValueError:
        await update.message.reply_text("❌ እባክዎን ትክክለኛ ቁጥር ያስገቡ! (ለምሳሌ፦ <code>/setrate 185</code>)", parse_mode="HTML")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or update.effective_user.id != ADMIN_ID:
        return
    total_orders, total_volume = db_get_stats()
    msg = (
        f"📊 <b>የቦቱ አጠቃላይ ስታቲስቲክስ (Stats)</b>\n\n"
        f"✅ የተጠናቀቁ ትዕዛዞች፦ <b>{total_orders}</b>\n"
        f"💵 የተሸጠ አጠቃላይ ዶላር፦ <b>${total_volume:,.2f} USD</b>\n"
        f"🔄 አሁን በሂደት ላይ ያሉ ትዕዛዞች፦ <b>{len(active_orders)}</b>"
    )
    if update.message:
        await update.message.reply_text(msg, parse_mode="HTML")

async def admin_toggle_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global maintenance_mode
    if not update.effective_user or update.effective_user.id != ADMIN_ID:
        return
    maintenance_mode = not maintenance_mode
    status_str = "🛑 ON (ቦቱ ለተጠቃሚዎች ተዘግቷል)" if maintenance_mode else "🟢 OFF (ቦቱ ክፍት ነው)"
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
                text="🟢 <b>Status:</b> 🔄 <i>Payment Approved! Admin is sending your Crypto...</i>",
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Failed to notify user: {e}")

        await query.message.reply_text("📸 <b>እባክዎን የዶላር (Crypto) መላኪያውን ስክሪንሹት (Screenshot) ይላኩ፦</b>", parse_mode="HTML")

    elif data.startswith("reject_"):
        target_user_id = int(data.split("_")[1])
        if target_user_id in active_orders:
            active_orders.remove(target_user_id)
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="🔴 <b>Status:</b> ❌ <i>Order Rejected!</i>\n\nYour payment could not be verified.",
                parse_mode="HTML"
            )
            if query.message and hasattr(query.message, 'edit_caption'):
                await getattr(query.message, 'edit_caption')(
                    caption=query.message.caption + "\n\n🔴 <b>STATUS: REJECTED ❌</b>", parse_mode="HTML"
                )
        except Exception as e:
            logging.error(f"Error notifying user: {e}")

    elif data.startswith("msg_"):
        target_user_id = int(data.split("_")[1])
        await query.message.reply_text(
            f"💬 <b>ለዚህ ተጠቃሚ (ID: <code>{target_user_id}</code>) መልእክት ለመላክ፦</b>\n\n"
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
            await query.message.edit_reply_markup(reply_markup=None)
            await query.message.reply_text("✅ <b>Thank you for using our service!</b>", parse_mode="HTML")
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🎉 <b>የተጠቃሚ ማረጋገጫ፦</b> ID <code>{user_id}</code> ዶላሩ <b>በስኬት እንደደረሰው</b> አረጋግጧል!",
                parse_mode="HTML"
            )
        elif status == "no":
            await query.message.edit_reply_markup(reply_markup=None)
            await query.message.reply_text("⚠️ <b>Issue reported to admin!</b>", parse_mode="HTML")
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🚨 <b>ማስጠንቀቂያ፦</b> ID <code>{user_id}</code> ዶላሩ <b>አልደረሰኝም</b> ብሏል!",
                parse_mode="HTML"
            )

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
                        "🟢 <b>Status:</b> ✅ <i>Completed</i>\n\n"
                        "USD has been sent to your wallet. Receipt attached above! 🚀\n\n"
                        "Did you receive the crypto?"
                    )
                    user_keyboard = [
                        [
                            InlineKeyboardButton("✅ Received / ደርሶኛል", callback_data=f"userconfirm_yes_{target_user_id}"),
                            InlineKeyboardButton("❌ Not Received / አልደረሰኝም", callback_data=f"userconfirm_no_{target_user_id}")
                        ]
                    ]
                    user_markup = InlineKeyboardMarkup(user_keyboard)
                    await context.bot.send_photo(chat_id=target_user_id, photo=proof_photo, caption=msg, reply_markup=user_markup, parse_mode="HTML")
                    await update.message.reply_text("✅ <b>የመላኪያ ስክሪንሹቱ እና ማረጋገጫው ለተጠቃሚው ተልኳል!</b>", parse_mode="HTML")

                    # Save to DB
                    db_update_stats(usd_amount)

                    # Auto post proof to Public Channel if configured
                    if PROOF_CHANNEL and PROOF_CHANNEL != "@your_channel_username":
                        try:
                            channel_msg = (
                                f"🎉 <b>አዲስ የተጠናቀቀ የ P2P ትዕዛዝ!</b>\n\n"
                                f"💵 የተሸጠ መጠን፦ <b>${usd_amount:,.2f} USD</b>\n"
                                f"✅ የትራንዛክሽን ሁኔታ፦ <b>Completed</b>\n"
                                f"🤖 በቦታችን በፍጥነት ይግዙ፦ @{context.bot.username}"
                            )
                            await context.bot.send_photo(chat_id=PROOF_CHANNEL, photo=proof_photo, caption=channel_msg, parse_mode="HTML")
                        except Exception as ch_err:
                            logging.error(f"Failed to post to channel: {ch_err}")

                except Exception as e:
                    await update.message.reply_text(f"❌ ለተጠቃሚው መላክ አልተቻለም፦ {e}")
                
                bot_data['admin_waiting_photo'] = False

async def admin_send_direct_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or update.effective_user.id != ADMIN_ID:
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ <b>የአጠቃቀም ስህተት!</b>\n\n<code>/send <USER_ID> <መልእክት></code>", parse_mode="HTML")
        return
    try:
        target_id = int(context.args[0])
        text_to_send = " ".join(context.args[1:])
        await context.bot.send_message(
            chat_id=target_id,
            text=f"💬 <b>ከ አድሚን የተላከ መልእክት፦</b>\n\n{text_to_send}",
            parse_mode="HTML"
        )
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

# ----------------- MAIN RUNNER -----------------
def main() -> None:
    if not BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN missing.")
        return
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    conv_handler: Any = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LANG: [CallbackQueryHandler(select_language, pattern="^lang_")],
            AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount),
                CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$")
            ],
            PAYMENT: [
                CallbackQueryHandler(payment_selected, pattern="^telebirr$"),
                CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$")
            ],
            SCREENSHOT: [
                MessageHandler(filters.PHOTO, receive_screenshot),
                CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$")
            ],
            WALLET_ADDRESS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_wallet),
                CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$")
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$")
        ],
        per_message=False
    )
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("send", admin_send_direct_message))
    app.add_handler(CommandHandler("setrate", admin_set_rate))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("maintenance", admin_toggle_maintenance))
    app.add_handler(CallbackQueryHandler(admin_action_handler, pattern="^(approve|reject|msg|userconfirm)_"))
    app.add_handler(MessageHandler(filters.PHOTO & filters.User(user_id=ADMIN_ID), handle_admin_photo))
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
