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

MIN_USD = 10.0
MAX_USD = 2100.0

LANG, AMOUNT, PAYMENT, SCREENSHOT, WALLET_ADDRESS, SUPPORT_MSG = range(6)

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
            "💎 ─────────────── 💎\n"
            "✨ <b>OKXETH P2P TRADING BOT</b> ✨\n"
            "💎 ─────────────── 💎\n\n"
            "📈 <b>የዛሬ የምንዛሬ ተመን፦</b> <code>1 USD = {rate} Birr</code>\n\n"
            "📊 <b>የግዢ ወሰን (Trading Limits)፦</b>\n"
            "├ 🟢 <b>አነስተኛ (Min):</b> <code>${min:,.0f} USD</code>\n"
            "└ 🔴 <b>ከፍተኛ (Max):</b> <code>${max:,.0f} USD</code>\n"
            "───────────────────\n\n"
            "✍️ <b>መግዛት የሚፈልጉትን መጠን ያስገቡ፦</b>\n"
            "💡 <i>ምሳሌ፦ 10, 50, 100</i>"
        ),
        'invalid_num': (
            "⚠️ <b>የተሳሳተ የቁጥር መጠን!</b>\n"
            "───────────────────\n"
            "እባክዎን ከ <b>${min:,.0f}</b> እስከ <b>${max:,.0f} USD</b> ባለው ወሰን ውስጥ ብቻ ያስገቡ፦"
        ),
        'summary': (
            "📋 <b>የግዢ ማጠቃለያ (Order Invoice)</b>\n"
            "───────────────────\n"
            "💵 <b>የሚገዙት መጠን፦</b> <code>${usd:,.2f} USD</code>\n"
            "💰 <b>የሚከፍሉት ብር፦</b> <code>{birr:,.2f} ETB</code>\n"
            "───────────────────\n\n"
            "👇 <i>ለመቀጠል የክፍያ አማራጩን ይጫኑ፦</i>"
        ),
        'pay_instruct': (
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
        'got_ss': (
            "📥 <b>የክፍያ ደረሰኝዎ ተቀብለናል!</b> ✅\n"
            "───────────────────\n"
            "🎯 ዶላሩ እንዲላክሎት የሚፈልጉበትን <b>Wallet Address</b> ይፃፉልን፦"
        ),
        'complete': (
            "🎉 <b>ትዕዛዝዎ በስኬት ተላኳል!</b>\n"
            "───────────────────\n"
            "⏳ <b>ሁኔታ፦</b> <i>በግምገማ ላይ (Pending)</i>\n\n"
            "🔄 አድሚኑ ክፍያውን አረጋግጦ ዶላሩን ወዲያውኑ ይልክልዎታል። እናመሰግናለን!"
        ),
        'cancel': "❌ <b>ትዕዛዝዎ ተሰርዟል።</b>\n\nእንደገና ለመጀመር 👉 <b>/start</b> ይበሉ።",
        'timeout': "⏰ <b>ጊዜዎ አልቋል!</b>\n\nበ15 ደቂቃ ውስጥ ክፍያ ስላላጠናቀቁ ትዕዛዙ ተሰርዟል። እንደገና ለመጀመር 👉 <b>/start</b> ይበሉ።",
        'active_exists': "⚠️ <b>ያልተጠናቀቀ ትዕዛዝ አለዎት!</b>\n\nእባክዎን ነባሩን ትዕዛዝ ያጠናቅቁ ወይም በ <b>/start</b> እንደገና ይጀምሩ።",
        'maintenance': "🛠️ <b>ቦቱ በአሁኑ ወቅት በስራ ማሻሻያ ላይ ነው!</b>\n\nእባክዎን ከጥቂት ደቂቃዎች በኋላ እንደገና ይሞክሩ።",
        'support_prompt': (
            "💬 <b>የእርዳታና ድጋፍ መስጫ (Support Center)</b>\n"
            "───────────────────\n"
            "ያለዎትን ጥያቄ፣ አስተያየት ወይም ቅሬታ እዚህ ይፃፉልን። አድሚኑ አይቶ ወዲያውኑ ምላሽ ይሰጥዎታል።"
        ),
        'support_sent': "✅ <b>መልእክትዎ ለአድሚን ተልኳል!</b>\n\nበቅርቡ ምላሽ ይደርስዎታል።",
        'btn_cancel': "❌ ሰርዝ (Cancel)",
        'btn_contact': "💬 Help & Support"
    },
    'om': {
        'welcome': (
            "💎 ─────────────── 💎\n"
            "✨ <b>OKXETH P2P TRADING BOT</b> ✨\n"
            "💎 ─────────────── 💎\n\n"
            "📈 <b>Gatiin Har'aa፦</b> <code>1 USD = {rate} Birr</code>\n\n"
            "📊 <b>Daangaa Bitahaa (Limits)፦</b>\n"
            "├ 🟢 <b>Xiqqaangaa (Min):</b> <code>${min:,.0f} USD</code>\n"
            "└ 🔴 <b>Guddaangaa (Max):</b> <code>${max:,.0f} USD</code>\n"
            "───────────────────\n\n"
            "✍️ <b>Mallaqa Doolara (USD) bitachuu barbaaddan galchaa፦</b>\n"
            "💡 <i>Fakkeenyaaf፦ 10, 50, 100</i>"
        ),
        'invalid_num': (
            "⚠️ <b>Gatiin galchitan sirrii miti!</b>\n"
            "───────────────────\n"
            "Maaloo <b>${min:,.0f}</b> fi <b>${max:,.0f} USD</b> intera jiru galchaa፦"
        ),
        'summary': (
            "📋 <b>Gabaasa Ajaja Keessanii</b>\n"
            "───────────────────\n"
            "💵 <b>Hangam bittan፦</b> <code>${usd:,.2f} USD</code>\n"
            "💰 <b>Kan kafaltan፦</b> <code>{birr:,.2f} ETB</code>\n"
            "───────────────────\n\n"
            "👇 <i>Maaloo karaa kafaltii filadhaa፦</i>"
        ),
        'pay_instruct': (
            "📱 <b>Qajeelfama Kafaltii Telebirr</b>\n"
            "───────────────────\n"
            "💳 <b>Mallaqa Kafaltan፦</b> <code>{birr:,.2f} ETB</code>\n"
            "📞 <b>Lakkoofsa Telebirr፦</b> <code>{num}</code>\n"
            "───────────────────\n"
            "⏱️ <b>Yeroo፦</b> <b>Daqiiqaa 15</b>\n\n"
            "<b>Tarkaanfii፦</b>\n"
            "1️⃣ Lakkoofsa armaan oliitti Telebirriin ergaa.\n"
            "2️⃣ Kafaltii erga raawwattanii booda <b>Screenshot</b> asitti ergaa."
        ),
        'got_ss': (
            "📥 <b>Nagaheen kafaltii nu gaheera!</b> ✅\n"
            "───────────────────\n"
            "Amma <b>Teessoo Wallet (Wallet Address)</b> Doolarri (USD) irratti ergamuu galchaa፦"
        ),
        'complete': (
            "🎉 <b>Ajajni keessan nu gaheera!</b>\n"
            "───────────────────\n"
            "⏳ <b>Haala Kafaltii፦</b> <i>Madaallii irra jira (Pending)</i>\n\n"
            "Admin-ni mirkaneesse Mallaqa p2p isiniif erga. Galatoomaa!"
        ),
        'cancel': "❌ <b>Ajajni keessan haqameera.</b>\n\nIrra deebitanii eegaluuf 👉 <b>/start</b> jedhaa.",
        'timeout': "⏰ <b>Yeroon keessan dhumateera!</b>\n\nDaqiiqaa 15 keessatti waan hin xumurreef ajajni haqameera. 👉 <b>/start</b> jedhaa.",
        'active_exists': "⚠️ <b>Ajaja hin xumuramne qabdu!</b>\n\nMaaloo ajaja duraa xumuraa ykn <b>/start</b> jedhaa.",
        'maintenance': "🛠️ <b>Bottiin ammaan tana suphaa irra jira!</b>\n\nMaaloo daqiiqaa muraasa booda irra deebi'aa yaalaa.",
        'support_prompt': (
            "💬 <b>Gargaarsa / Deeggarsa (Support Center)</b>\n"
            "───────────────────\n"
            "Gaaffii ykn rakkoo qabdan asitti barreessaa. Admin dafee isiniif deebisa."
        ),
        'support_sent': "✅ <b>Ergaandhaan keessan ergameera!</b>\n\nAdmin dafee deebii isiniif erga.",
        'btn_cancel': "❌ Haqi (Cancel)",
        'btn_contact': "💬 Help & Support"
    },
    'en': {
        'welcome': (
            "💎 ─────────────── 💎\n"
            "✨ <b>OKXETH P2P TRADING BOT</b> ✨\n"
            "💎 ─────────────── 💎\n\n"
            "📈 <b>Exchange Rate:</b> <code>1 USD = {rate} Birr</code>\n\n"
            "📊 <b>Trading Limits:</b>\n"
            "├ 🟢 <b>Min Amount:</b> <code>${min:,.0f} USD</code>\n"
            "└ 🔴 <b>Max Amount:</b> <code>${max:,.0f} USD</code>\n"
            "───────────────────\n\n"
            "✍️ <b>Enter the USD amount you want to buy:</b>\n"
            "💡 <i>Example: 10, 50, 100</i>"
        ),
        'invalid_num': (
            "⚠️ <b>Invalid Amount!</b>\n"
            "───────────────────\n"
            "Please enter a value between <b>${min:,.0f}</b> and <b>${max:,.0f} USD</b>:"
        ),
        'summary': (
            "📋 <b>Order Invoice</b>\n"
            "───────────────────\n"
            "💵 <b>Buying Amount:</b> <code>${usd:,.2f} USD</code>\n"
            "💰 <b>Total Payable:</b> <code>{birr:,.2f} ETB</code>\n"
            "───────────────────\n\n"
            "👇 <i>Select your payment method below:</i>"
        ),
        'pay_instruct': (
            "📱 <b>Telebirr Payment Instructions</b>\n"
            "───────────────────\n"
            "💳 <b>Amount to Pay:</b> <code>{birr:,.2f} ETB</code>\n"
            "📞 <b>Telebirr Number:</b> <code>{num}</code>\n"
            "───────────────────\n"
            "⏱️ <b>Time Limit:</b> <b>15 Minutes</b>\n\n"
            "<b>Steps to Complete:</b>\n"
            "1️⃣ Send the exact Birr amount to the Telebirr number.\n"
            "2️⃣ Upload the payment <b>Screenshot</b> here."
        ),
        'got_ss': (
            "📥 <b>Payment receipt received!</b> ✅\n"
            "───────────────────\n"
            "Now enter your <b>Wallet Address</b> to receive USD:"
        ),
        'complete': (
            "🎉 <b>Order Placed Successfully!</b>\n"
            "───────────────────\n"
            "⏳ <b>Status:</b> <i>Pending Verification</i>\n\n"
            "Once admin verifies payment, your crypto will be sent immediately."
        ),
        'cancel': "❌ <b>Order cancelled.</b>\n\nType 👉 <b>/start</b> to restart.",
        'timeout': "⏰ <b>Time Expired!</b>\n\nOrder auto-cancelled after 15 mins. Type 👉 <b>/start</b> to try again.",
        'active_exists': "⚠️ <b>You have an active pending order!</b>\n\nPlease complete or cancel your existing order before starting a new one.",
        'maintenance': "🛠️ <b>Bot is currently under maintenance!</b>\n\nPlease try again shortly.",
        'support_prompt': (
            "💬 <b>Help & Support Desk</b>\n"
            "───────────────────\n"
            "Please send your query or issue below (text or photo). Admin will get back to you shortly."
        ),
        'support_sent': "✅ <b>Message sent to Support!</b>\n\nAdmin will review and reply soon.",
        'btn_cancel': "❌ Cancel Order",
        'btn_contact': "💬 Help & Support"
    },
    'so': {
        'welcome': (
            "💎 ─────────────── 💎\n"
            "✨ <b>OKXETH P2P TRADING BOT</b> ✨\n"
            "💎 ─────────────── 💎\n\n"
            "📈 <b>Sarrifka Maanta:</b> <code>1 USD = {rate} Birr</code>\n\n"
            "📊 <b>Xaddidaada (Limits):</b>\n"
            "├ 🟢 <b>Min Amount:</b> <code>${min:,.0f} USD</code>\n"
            "└ 🔴 <b>Max Amount:</b> <code>${max:,.0f} USD</code>\n"
            "───────────────────\n\n"
            "✍️ <b>Geli xaddiga USD ee aad rabto:</b>\n"
            "💡 <i>Tusaale: 10, 50, 100</i>"
        ),
        'invalid_num': (
            "⚠️ <b>Xaddiga uusan sax ahayn!</b>\n"
            "───────────────────\n"
            "Fadlan geli xaddiga u dhexeeya <b>${min:,.0f}</b> iyo <b>${max:,.0f} USD</b>:"
        ),
        'summary': (
            "📋 <b>Kooban ee Dalabka</b>\n"
            "───────────────────\n"
            "💵 <b>Xaddiga USD:</b> <code>${usd:,.2f} USD</code>\n"
            "💰 <b>Wadarta Birr:</b> <code>{birr:,.2f} ETB</code>\n"
            "───────────────────\n\n"
            "👇 <i>Dooro habka lacag bixinta:</i>"
        ),
        'pay_instruct': (
            "📱 <b>Awaamiirta Telebirr</b>\n"
            "───────────────────\n"
            "💳 <b>Lacagta Bixinta:</b> <code>{birr:,.2f} ETB</code>\n"
            "📞 <b>Nambarka Telebirr:</b> <code>{num}</code>\n"
            "───────────────────\n"
            "⏱️ <b>Waqtiga:</b> <b>15 Daqiiqo</b>\n\n"
            "<b>Tallaabooyinka:</b>\n"
            "1️⃣ U dir lacagta nambarka Telebirr.\n"
            "2️⃣ Halkan ku soo dir <b>Screenshot</b> risidka."
        ),
        'got_ss': (
            "📥 <b>Risidka waa la helay!</b> ✅\n"
            "───────────────────\n"
            "Hada geli <b>Wallet Address</b> aad ku heli karto USD:"
        ),
        'complete': (
            "🎉 <b>Dalabkaaga waa la guddoomay!</b>\n"
            "───────────────────\n"
            "⏳ <b>Xaaladda:</b> <i>Dib u eegis (Pending)</i>\n\n"
            "Markii maamuluhu xaqiijiyo lacagta, crypto ayaa lagu soo diri doonaa."
        ),
        'cancel': "❌ <b>Dalabka waa la joojiyay.</b>\n\nQor 👉 <b>/start</b> si aad dib ugu bilaabto.",
        'timeout': "⏰ <b>Xilligii waa dhacay!</b>\n\nDalabkaagii waa la joojiyay. Qor 👉 <b>/start</b> si aad dib ugu bilaabto.",
        'active_exists': "⚠️ <b>Waxaad leedahay dalab weli furan!</b>\n\nFadlan dhameystir ama jooji dalabkaagii hore.",
        'maintenance': "🛠️ <b>Bot-ku wuxuu ku jiraa dayactir!</b>\n\nFadlan isku day dib marka ay xoogaa daqiiqado ah ka soo wareegaan.",
        'support_prompt': (
            "💬 <b>Caawinaada & Taageerada</b>\n"
            "───────────────────\n"
            "Fadlan halkan ku qor su'aashaada ama dhibaatadaada. Maamulaha ayaa kaga jawaabi doona."
        ),
        'support_sent': "✅ <b>Fariintaadii waa la diray!</b>\n\nMaamulaha ayaa dhawaan kugu soo jawaabi doona.",
        'btn_cancel': "❌ Jooji (Cancel)",
        'btn_contact': "💬 Help & Support"
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
        "❓ <b>እርዳታና ድጋፍ (Help Center)</b>\n"
        "───────────────────\n"
        "የቦት አጠቃቀም ላይ ችግር ካጋጠመዎት ወይም ጥያቄ ካለዎት ከታች ያለውን <b>Support</b> ቁልፍ በመጫን መፃፍ ይችላሉ።\n\n"
        "📌 <b>ትዕዛዞች፦</b>\n"
        "• <b>/start</b> - አዲስ ትዕዛዝ መጀመር\n"
        "• <b>/cancel</b> - ያለውን ትዕዛዝ መሰረዝ\n"
        "• <b>/help</b> - ድጋፍ ማግኘት"
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
        [InlineKeyboardButton(t['btn_contact'], callback_data="bot_support")],
        [InlineKeyboardButton(t['btn_cancel'], callback_data="user_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = t['welcome'].format(rate=rate, min=MIN_USD, max=MAX_USD)
    await query.message.edit_text(msg, reply_markup=reply_markup, parse_mode="HTML")
    return AMOUNT

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
        f"───────────────────\n"
        f"👤 <b>ተጠቃሚ፦</b> {user.first_name} ({username_str})\n"
        f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
        f"───────────────────\n"
        f"👇 <b>መልእክት፦</b>"
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
        logging.error(f"Failed to forward support msg: {e}")

    await update.message.reply_text(t['support_sent'], parse_mode="HTML")
    return ConversationHandler.END

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
            f"🚨 <b>አዲስ የ P2P ግዢ ጥያቄ!</b>\n"
            f"───────────────────\n"
            f"🌐 <b>ቋንቋ፦</b> <code>{lang.upper()}</code>\n"
            f"👤 <b>ተጠቃሚ፦</b> {username_str}\n"
            f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
            f"💵 <b>የዶላር መጠን፦</b> <code>${usd_amount:,.2f} USD</code>\n"
            f"💰 <b>የክፍያ መጠን፦</b> <code>{total_birr:,.2f} ETB</code>\n"
            f"📍 <b>Wallet Address:</b> <code>{wallet_address}</code>\n"
            f"───────────────────\n"
            f"⚠️ <b>ማሳሰቢያ፦</b> በቴሌብር ሂሳብህ ውስጥ <b>{total_birr:,.2f} ETB</b> መግባቱን ሳታረጋግጥ Approve እንዳታደርግ!"
        )
        admin_keyboard = [
            [
                InlineKeyboardButton("✅ Approve Order", callback_data=f"approve_{user.id}_{usd_amount}"),
                InlineKeyboardButton("❌ Reject Order", callback_data=f"reject_{user.id}")
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
        await update.message.reply_text(f"✅ <b>የምንዛሬ ተመን ተቀይሯል!</b>\n\nአዲሱ ተመን፦ <b>1 USD = {new_rate} Birr</b>", parse_mode="HTML")
    except ValueError:
        await update.message.reply_text("❌ እባክዎን ትክክለኛ ቁጥር ያስገቡ! (ለምሳሌ፦ <code>/setrate 185</code>)", parse_mode="HTML")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or update.effective_user.id != ADMIN_ID:
        return
    total_orders, total_volume = db_get_stats()
    msg = (
        f"📊 <b>የቦቱ አጠቃላይ Stats</b>\n"
        f"───────────────────\n"
        f"✅ የተጠናቀቁ ትዕዛዞች፦ <b>{total_orders}</b>\n"
        f"💵 የተሸጠ አጠቃላይ ዶላር፦ <b>${total_volume:,.2f} USD</b>\n"
        f"🔄 በሂደት ላይ ያሉ፦ <b>{len(active_orders)}</b>"
    )
    if update.message:
        await update.message.reply_text(msg, parse_mode="HTML")

async def admin_toggle_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global maintenance_mode
    if not update.effective_user or update.effective_user.id != ADMIN_ID:
        return
    maintenance_mode = not maintenance_mode
    status_str = "🛑 ON (ለተጠቃሚዎች ተዘግቷል)" if maintenance_mode else "🟢 OFF (ቦቱ ክፍት ነው)"
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
                text="🟢 <b>Status:</b> 🔄 <i>Payment Approved! Admin is transferring your USD...</i>",
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Failed to notify user: {e}")

        await query.message.reply_text("📸 <b>የመላኪያ ስክሪንሹት (Proof Screenshot) ይላኩ፦</b>", parse_mode="HTML")

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
            await query.message.edit_reply_markup(reply_markup=None)
            await query.message.reply_text("✅ <b>Thank you for trading with us!</b>", parse_mode="HTML")
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🎉 <b>ማረጋገጫ፦</b> User ID <code>{user_id}</code> ዶላሩ <b>መድረሱን</b> አረጋግጧል!",
                parse_mode="HTML"
            )
        elif status == "no":
            await query.message.edit_reply_markup(reply_markup=None)
            await query.message.reply_text("⚠️ <b>Issue reported to admin!</b>", parse_mode="HTML")
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🚨 <b>ማስጠንቀቂያ፦</b> User ID <code>{user_id}</code> ዶላሩ <b>አልደረሰኝም</b> ብሏል!",
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
                        "🟢 <b>Status:</b> ✅ <i>Completed</i>\n"
                        "───────────────────\n"
                        "USD has been sent to your wallet address! Receipt attached above. 🚀\n\n"
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
                    await update.message.reply_text("✅ <b>የመላኪያ ማረጋገጫው ለተጠቃሚው ተልኳል!</b>", parse_mode="HTML")

                    # Save to DB
                    db_update_stats(usd_amount)

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
            text=f"💬 <b>ከ Support የተላከ መልእክት፦</b>\n───────────────────\n{text_to_send}",
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
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(trigger_support_flow, pattern="^bot_support$")
        ],
        states={
            LANG: [CallbackQueryHandler(select_language, pattern="^lang_")],
            AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount),
                CallbackQueryHandler(trigger_support_flow, pattern="^bot_support$"),
                CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$")
            ],
            PAYMENT: [
                CallbackQueryHandler(payment_selected, pattern="^telebirr$"),
                CallbackQueryHandler(trigger_support_flow, pattern="^bot_support$"),
                CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$")
            ],
            SCREENSHOT: [
                MessageHandler(filters.PHOTO, receive_screenshot),
                CallbackQueryHandler(trigger_support_flow, pattern="^bot_support$"),
                CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$")
            ],
            WALLET_ADDRESS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_wallet),
                CallbackQueryHandler(trigger_support_flow, pattern="^bot_support$"),
                CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$")
            ],
            SUPPORT_MSG: [
                MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, receive_support_message),
                CallbackQueryHandler(cancel_button_handler, pattern="^user_cancel$")
            ]
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
