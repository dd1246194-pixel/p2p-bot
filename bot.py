# type: ignore
import os
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

app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "OKXETH P2P Bot is Alive and Running 24/7!", 200

def run_flask():
    app_web.run(host='0.0.0.0', port=8080)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_ID = 7798227927
RATE = 184
TELEBIRR_NUMBER = "0900253321"

LANG, AMOUNT, PAYMENT, SCREENSHOT, WALLET_ADDRESS = range(5)

TEXTS = {
    'am': {
        'welcome': "👋 **ወደ OKXETH P2P ቦት እንኳን ደህና መጡ!**\n\n💱 የዛሬው የምንዛሬ ተመን፦ **1 USD = 184 Birr**\n\nእባክዎን መግዛት የሚፈልጉትን የዶላር (USD) መጠን ያስገቡ፦\n(ለምሳሌ፦ 10 ወይም 50)",
        'invalid_num': "እባክዎን ከ 0 በላይ የሆነ ትክክለኛ ቁጥር ያስገቡ፦",
        'summary': "📊 **የስሌት ማጠቃለያ**፦\n\n💵 የሚገዙት መጠን፦ **${usd:,.2f} USD**\n💰 የሚከፍሉት ጠቅላላ ብር፦ **{birr:,.2f} ETB**\n\nእባክዎን የክፍያ አማራጭ ይምረጡ፦",
        'pay_instruct': "✅ **Telebirr ክፍያ መረጠዋል**\n\n💳 የሚከፍሉት መጠን፦ **{birr:,.2f} ETB** (ለ ${usd:,.2f} USD)\n📞 የTelebirr ስልክ ቁጥር፦ `{num}`\n\n⏱️ **ማስጠንቀቂያ፦** ክፍያውን በ **15 ደቂቃ** ውስጥ ፈጽመው ደረሰኝ መላክ አለብዎት!\n\n📌 **ትዕዛዝ**፦\n1. በላይ በተጠቀሰው ቁጥር **{birr:,.2f} ETB** በTelebirr ይላኩ።\n2. ክፍያውን እንደፈጸሙ **ትክክለኛ የደረሰኝ ስክሪንሹት (Screenshot)** በዚህ ይላኩ።\n\n⚠️ *የውሸት ደረሰኝ ወይም የተሰራጨ ፎቶ መላክ ከስርዓቱ ያግድዎታል።*",
        'got_ss': "📥 የክፍያ ደረሰኝዎ ተቀብለናል!\n\nአሁን ዶላሩ (USD) እንዲላክሎት የሚፈልጉበትን **የዋልሌት አድራሻ (Wallet Address)** ያስገቡ፦",
        'complete': "🎉 **ትዕዛዝዎ በስርዓት ደርሶናል!**\n\n🟡 **የክፍያ ሁኔታ (Status):** ⏳ *በግምገማ ላይ (Pending)*\n\nአድሚኑ በቴሌብር ሂሳቡ የደረሰውን ክፍያ አረጋግጦ ዶላሩን ሲልክልዎ በቦቱ በኩል ወዲያውኑ መልእክት ይደርስዎታል።",
        'cancel': "❌ **ትዕዛዝዎ ተሰርዟል።**\n\nእንደገና ለመጀመር **/start** ብለው ይፃፉ።",
        'timeout': "⏰ **ጊዜዎ አልቋል!**\n\nበ15 ደቂቃ ውስጥ ክፍያ ስላላጠናቀቁ ትዕዛዝዎ በራስ-ሰር ተሰርዟል። እንደገና ለመጀመር **/start** ይበሉ።",
        'btn_cancel': "❌ Cancel (ሰርዝ)"
    },
    'om': {
        'welcome': "👋 **Baga gara OKXETH P2P Bot nagaan dhuftan!**\n\n💱 Gatiin har'aa፦ **1 USD = 184 Birr**\n\nMallaqa Doolara (USD) bitachuu barbaaddan galchaa፦\n(Fakkeenyaaf፦ 10 ykn 50)",
        'invalid_num': "Maaloo lakkoofsa sirrii 0 olii ta'e galchaa፦",
        'summary': "📊 **Shallaggii Mallaqaa**፦\n\n💵 Hangam bittan፦ **${usd:,.2f} USD**\n💰 Kan kafaltan walumaagala፦ **{birr:,.2f} ETB**\n\nMaaloo karaa kafaltii filadhaa፦",
        'pay_instruct': "✅ **Kafaltii Telebirr filattaniirtu**\n\n💳 Mallaqa kafaltan፦ **{birr:,.2f} ETB** (${usd:,.2f} USD 'f)\n📞 Lakkoofsa Telebirr፦ `{num}`\n\n⏱️ **Akeekkachiisa፦** Dakiiqaa **15** keessatti kafaltii raawwattanii nagahee erguu qabdu!\n\n📌 **Ajaja**፦\n1. Lakkoofsa armaan oliitti **{birr:,.2f} ETB** Telebirriin ergaa.\n2. Kafaltii erga raawwattanii booda **Nagahee (Screenshot)** suuraadhaan asitti ergaa.\n\n⚠️ *Nagahee sobatti fayyadamuu fi gowwoosuun accounts keessan ni cufa.*",
        'got_ss': "📥 Nagaheen kafaltii keessani nu gaheera!\n\nAmma **Teessoo Wallet (Wallet Address)** Doolarri (USD) irratti isiniif ergamuu galchaa፦",
        'complete': "🎉 **Ajajni keessan nu gaheera!**\n\n🟡 **Haala Kafaltii (Status):** ⏳ *Madaallii irra jira (Pending)*\n\nAdmin-ni kafaltii keessan mirkaneesse Mallaqa p2p isiniif ergaan booda ergaa isiniif erga.",
        'cancel': "❌ **Ajajni keessan haqameera.**\n\nIrra deebitanii eegaluuf **/start** jedhaa barreessaa.",
        'timeout': "⏰ **Yeroon keessan dhumateera!**\n\nDaqiiqaa 15 keessatti kafaltii waan hin xumurreef ajajni keessan haqameera. Irra deebitanii eegaluuf **/start** jedhaa.",
        'btn_cancel': "❌ Haqi (Cancel)"
    },
    'en': {
        'welcome': "👋 **Welcome to OKXETH P2P BOT!**\n\n💱 Today's Exchange Rate: **1 USD = 184 Birr**\n\nPlease enter the amount of USD you want to buy:\n(Example: 10 or 50)",
        'invalid_num': "Please enter a valid number greater than 0:",
        'summary': "📊 **Order Summary**:\n\n💵 Buying Amount: **${usd:,.2f} USD**\n💰 Total Payable: **{birr:,.2f} ETB**\n\nPlease select your payment method:",
        'pay_instruct': "✅ **Telebirr Selected**\n\n💳 Amount to Pay: **{birr:,.2f} ETB** (for ${usd:,.2f} USD)\n📞 Telebirr Number: `{num}`\n\n⏱️ **Warning:** You must complete the payment within **15 minutes**!\n\n📌 **Instructions**:\n1. Send **{birr:,.2f} ETB** via Telebirr to the number above.\n2. Once paid, send the valid **Payment Receipt (Screenshot)** here.\n\n⚠️ *Sending fake or reused receipts will result in a permanent ban.*",
        'got_ss': "📥 Payment receipt received!\n\nNow enter your **Wallet Address** where you wish to receive the USD:",
        'complete': "🎉 **Your order has been placed!**\n\n🟡 **Status:** ⏳ *Pending Approval*\n\nOnce the admin verifies payment and transfers the crypto, you will be notified.",
        'cancel': "❌ **Order cancelled.**\n\nType **/start** to begin again.",
        'timeout': "⏰ **Time expired!**\n\nYour order was automatically cancelled because 15 minutes passed. Type **/start** to try again.",
        'btn_cancel': "❌ Cancel"
    },
    'so': {
        'welcome': "👋 **Ku soo dhawoow OKXETH P2P BOT!**\n\n💱 Sarrifka maanta: **1 USD = 184 Birr**\n\nFadlan geli xaddiga USD ee aad rabto inaad compraso:\n(Tusaale: 10 ama 50)",
        'invalid_num': "Fadlan geli nambarkeeda saxda ah oo ka weyn 0:",
        'summary': "📊 **Kooban ee Dalabka**:\n\n💵 Xaddiga Magacaaba: **${usd:,.2f} USD**\n💰 Wadarta Bixinta: **{birr:,.2f} ETB**\n\nFadlan dooro habka lacag bixinta:",
        'pay_instruct': "✅ **Waxaad dooratay Telebirr**\n\n💳 Lacagta Bixinta: **{birr:,.2f} ETB** (${usd:,.2f} USD)\n📞 Nambarka Telebirr: `{num}`\n\n⏱️ **Digniin:** Waad ku bixin kartaa lacagta **15 daqiiqo** gudaheed!\n\n📌 **Awaamiirta**:\n1. U dir **{birr:,.2f} ETB** nambarka sare ku quran Telebirr.\n2. Markaad bixiso ka dib, halkan ku soo dir **Sawirka Risidka (Screenshot)**.\n\n⚠️ *Soo dirtada risid been ah waxay keeni doontaa in lagaa mamnuuco bot-ka.*",
        'got_ss': "📥 Risidka lacag bixinta waa la helay!\n\nHada geli **Cinwaanka Wallet-ka** aad ku heli karto USD:",
        'complete': "🎉 **Dalabkaaga waa la guddoomay!**\n\n🟡 **Xaaladda (Status):** ⏳ *Dib u eegis (Pending)*\n\nMarkii maamuluhu xaqiijiyo lacag bixinta oo uu kugu diro crypto, farriin ayaa ku soo gaari doonta.",
        'cancel': "❌ **Dalabka waa la joojiyay.**\n\nQor **/start** si aad dib ugu bilaabto.",
        'timeout': "⏰ **Xilligii waa dhacay!**\n\nDalabkaagii waa la joojiyay sababtoo ah 15 daqiiqo ayaa ka soo wareegtay. Qor **/start** si aad dib ugu bilaabto.",
        'btn_cancel': "❌ Jooji (Cancel)"
    }
}

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
    try:
        await context.bot.send_message(chat_id=user_id, text=t['timeout'], parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Failed to send timeout message to {user_id}: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user:
        remove_timer_job(context, update.effective_user.id)

    keyboard = [
        [InlineKeyboardButton("🌳 Afaan Oromoo", callback_data="lang_om"), InlineKeyboardButton("🇪🇹 አማርኛ", callback_data="lang_am")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"), InlineKeyboardButton("🇸🇴 Soomaali", callback_data="lang_so")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(
            "🌐 **Please select your language / ቋንቋ ይምረጡ / Maaloo afaan filadhaa / Fadlan dooro luqadaada:**",
            reply_markup=reply_markup,
            parse_mode="Markdown"
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
    keyboard = [[InlineKeyboardButton(t['btn_cancel'], callback_data="user_cancel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.edit_text(t['welcome'], reply_markup=reply_markup, parse_mode="Markdown")
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return AMOUNT
    user_data = context.user_data or {}
    lang = user_data.get('lang', 'am')
    t = TEXTS[lang]

    try:
        usd_amount = float(update.message.text)
        if usd_amount <= 0:
            await update.message.reply_text(t['invalid_num'])
            return AMOUNT
        total_birr = usd_amount * RATE
        user_data['usd_amount'] = usd_amount
        user_data['total_birr'] = total_birr

        keyboard = [
            [InlineKeyboardButton("📱 Only Telebirr", callback_data="telebirr")],
            [InlineKeyboardButton(t['btn_cancel'], callback_data="user_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        msg = t['summary'].format(usd=usd_amount, birr=total_birr)
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
        return PAYMENT
    except ValueError:
        await update.message.reply_text(t['invalid_num'])
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
    if user and context.job_queue:
        remove_timer_job(context, user.id)
        # Set 15 minutes timer (15 * 60 = 900 seconds)
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
        await getattr(query.message, 'reply_text')(msg, reply_markup=reply_markup, parse_mode="Markdown")
    return SCREENSHOT

async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.photo:
        return SCREENSHOT

    user = update.effective_user
    if user:
        remove_timer_job(context, user.id)

    user_data = context.user_data or {}
    lang = user_data.get('lang', 'am')
    t = TEXTS[lang]

    photo_file = update.message.photo[-1].file_id
    user_data['photo_file'] = photo_file

    keyboard = [[InlineKeyboardButton(t['btn_cancel'], callback_data="user_cancel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(t['got_ss'], reply_markup=reply_markup, parse_mode="Markdown")
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
            f"📥 **አዲስ የትዕዛዝ ጥያቄ ደርሷል!**\n\n"
            f"🌐 Language: `{lang.upper()}`\n"
            f"👤 ተጠቃሚ፦ {username_str}\n"
            f"🆔 User ID: `{user.id}`\n"
            f"💵 የዶላር መጠን፦ **${usd_amount:,.2f} USD**\n"
            f"💰 የክፍያ መጠን፦ **{total_birr:,.2f} ETB**\n"
            f"📍 የዋልሌት አድራሻ፦ `{wallet_address}`\n\n"
            f"⚠️ **አድሚን አስተውል፦** በቴሌብር አካውንትህ ውስጥ ጥሬ ብሩ በጥቅሉ **{total_birr:,.2f} ETB** መግባቱን ሳታረጋግጥ 'Approve' እንዳታደርግ!"
        )
        admin_keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user.id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}")
            ],
            [
                InlineKeyboardButton("💬 Send Message", callback_data=f"msg_{user.id}")
            ]
        ]
        admin_markup = InlineKeyboardMarkup(admin_keyboard)
        try:
            await context.bot.send_photo(
                chat_id=ADMIN_ID, photo=photo_file, caption=admin_msg, reply_markup=admin_markup, parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Failed to send to admin: {e}")

    await update.message.reply_text(t['complete'], parse_mode="Markdown")
    return ConversationHandler.END

async def cancel_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if user:
        remove_timer_job(context, user.id)

    query = update.callback_query
    user_data = context.user_data or {}
    lang = user_data.get('lang', 'am')
    t = TEXTS[lang]

    if query:
        await query.answer()
        await query.message.edit_text(t['cancel'], parse_mode="Markdown")
    return ConversationHandler.END

async def admin_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    data = query.data

    if data.startswith("approve_"):
        target_user_id = int(data.split("_")[1])
        if context.bot_data is not None:
            context.bot_data['target_user_id'] = target_user_id
            context.bot_data['admin_waiting_photo'] = True
        
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="🟢 **Status:** 🔄 *Payment Approved! Admin is sending your Crypto...*",
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Failed to notify user: {e}")

        await query.message.reply_text("📸 **እባክዎን የዶላር (Crypto) መላኪያውን ስክሪንሹት (Screenshot) ይላኩ፦**")

    elif data.startswith("reject_"):
        target_user_id = int(data.split("_")[1])
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="🔴 **Status:** ❌ *Order Rejected!*\n\nYour payment could not be verified.",
                parse_mode="Markdown"
            )
            if query.message and hasattr(query.message, 'edit_caption'):
                await getattr(query.message, 'edit_caption')(
                    caption=query.message.caption + "\n\n🔴 **STATUS: REJECTED ❌**", parse_mode="Markdown"
                )
        except Exception as e:
            logging.error(f"Error notifying user: {e}")

    elif data.startswith("msg_"):
        target_user_id = int(data.split("_")[1])
        await query.message.reply_text(
            f"💬 **ለዚህ ተጠቃሚ (ID: `{target_user_id}`) መልእክት ለመላክ፦**\n\n"
            f"`/send {target_user_id} መልእክትህ` ብለህ ፃፍ።",
            parse_mode="Markdown"
        )

    elif data.startswith("userconfirm_"):
        parts = data.split("_")
        status = parts[1]
        user_id = parts[2]
        
        if status == "yes":
            await query.message.edit_reply_markup(reply_markup=None)
            await query.message.reply_text("✅ **Thank you for using our service!**")
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🎉 **የተጠቃሚ ማረጋገጫ፦** ID `{user_id}` ዶላሩ **በስኬት እንደደረሰው** አረጋግጧል!",
                parse_mode="Markdown"
            )
        elif status == "no":
            await query.message.edit_reply_markup(reply_markup=None)
            await query.message.reply_text("⚠️ **Issue reported to admin!**")
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🚨 **ማስጠንቀቂያ፦** ID `{user_id}` ዶላሩ **አልደረሰኝም** ብሏል!",
                parse_mode="Markdown"
            )

async def handle_admin_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.photo:
        return
    if update.effective_user and update.effective_user.id == ADMIN_ID:
        bot_data = context.bot_data or {}
        if bot_data.get('admin_waiting_photo'):
            target_user_id = bot_data.get('target_user_id')
            proof_photo = update.message.photo[-1].file_id
            if target_user_id:
                try:
                    msg = (
                        "🟢 **Status:** ✅ *Completed*\n\n"
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
                    await context.bot.send_photo(chat_id=target_user_id, photo=proof_photo, caption=msg, reply_markup=user_markup, parse_mode="Markdown")
                    await update.message.reply_text("✅ **የመላኪያ ስክሪንሹቱ እና ማረጋገጫው ለተጠቃሚው ተልኳል!**")
                except Exception as e:
                    await update.message.reply_text(f"❌ ለተጠቃሚው መላክ አልተቻለም፦ {e}")
                bot_data['admin_waiting_photo'] = False

async def admin_send_direct_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or update.effective_user.id != ADMIN_ID:
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ **የአጠቃቀም ስህተት!**\n\n`/send <USER_ID> <መልእክት>`", parse_mode="Markdown")
        return
    try:
        target_id = int(context.args[0])
        text_to_send = " ".join(context.args[1:])
        await context.bot.send_message(
            chat_id=target_id,
            text=f"💬 **ከ አድሚን የተላከ መልእክት፦**\n\n{text_to_send}",
            parse_mode="Markdown"
        )
        await update.message.reply_text(f"✅ መልእክቱ ለ ID `{target_id}` ተልኳል!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ መላክ አልተቻለም፦ {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user:
        remove_timer_job(context, update.effective_user.id)
    if update.message:
        await update.message.reply_text("Cancelled. /start to restart.")
    return ConversationHandler.END

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
    app.add_handler(CommandHandler("send", admin_send_direct_message))
    app.add_handler(CallbackQueryHandler(admin_action_handler, pattern="^(approve|reject|msg|userconfirm)_"))
    app.add_handler(MessageHandler(filters.PHOTO & filters.User(user_id=ADMIN_ID), handle_admin_photo))
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
