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

AMOUNT, PAYMENT, SCREENSHOT, WALLET_ADDRESS = range(4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text(
            "👋 **Welcome to OKXETH P2P BOT!**\n\n"
            "💱 የዛሬው የምንዛሬ ተመን፦ **1 USD = 184 Birr**\n\n"
            "እባክዎን መግዛት የሚፈልጉትን የዶላር (USD) መጠን ያስገቡ፦\n"
            "(ለምሳሌ፦ 10 ወይም 50)",
            parse_mode="Markdown"
        )
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return AMOUNT
    text = update.message.text
    try:
        usd_amount = float(text)
        if usd_amount <= 0:
            await update.message.reply_text("እባክዎን ከ 0 በላይ የሆነ ትክክለኛ ቁጥር ያስገቡ፦")
            return AMOUNT
        total_birr = usd_amount * RATE
        if context.user_data is not None:
            context.user_data['usd_amount'] = usd_amount
            context.user_data['total_birr'] = total_birr

        keyboard = [[InlineKeyboardButton("📱 Only Telebirr", callback_data="telebirr")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        msg = (
            f"📊 **የስሌት ማጠቃለያ**፦\n\n"
            f"💵 የሚገዙት መጠን፦ **${usd_amount:,.2f} USD**\n"
            f"💰 የሚከፍሉት ጠቅላላ ብር፦ **{total_birr:,.2f} ETB**\n\n"
            f"እባክዎን የክፍያ አማራጭ ይምረጡ፦"
        )
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
        return PAYMENT
    except ValueError:
        await update.message.reply_text("እባክዎን ትክክለኛ ቁጥር ብቻ ያስገቡ (ለምሳሌ፦ 25)፦")
        return AMOUNT

async def payment_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return PAYMENT
    await query.answer()
    user_data = context.user_data or {}
    total_birr = user_data.get('total_birr', 0)
    usd_amount = user_data.get('usd_amount', 0)

    msg = (
        f"✅ **Telebirr ክፍያ መረጠዋል**\n\n"
        f"💳 የሚከፍሉት መጠን፦ **{total_birr:,.2f} ETB** (ለ ${usd_amount:,.2f} USD)\n"
        f"📞 የTelebirr ስልክ ቁጥር፦ `{TELEBIRR_NUMBER}`\n\n"
        f"📌 **ትዕዛዝ**፦\n"
        f"1. በላይ በተጠቀሰው ቁጥር **{total_birr:,.2f} ETB** በTelebirr ይላኩ።\n"
        f"2. ክፍያውን እንደፈጸሙ **የደረሰኝ ስክሪንሹት (Screenshot)** ወይም ፎቶ በዚህ ይላኩ።"
    )
    if query.message and hasattr(query.message, 'reply_text'):
        await getattr(query.message, 'reply_text')(msg, parse_mode="Markdown")
    return SCREENSHOT

async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.photo:
        return SCREENSHOT
    photo_file = update.message.photo[-1].file_id
    if context.user_data is not None:
        context.user_data['photo_file'] = photo_file

    await update.message.reply_text(
        "📥 የክፍያ ደረሰኝዎ ተቀብለናል!\n\n"
        "አሁን ዶላሩ (USD) እንዲላክሎት የሚፈልጉበትን **የዋልሌት አድራሻ (Wallet Address)** ያስገቡ፦"
    )
    return WALLET_ADDRESS

async def receive_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return WALLET_ADDRESS
    wallet_address = update.message.text
    user = update.effective_user
    user_data = context.user_data or {}
    usd_amount = user_data.get('usd_amount', 0)
    total_birr = user_data.get('total_birr', 0)
    photo_file = user_data.get('photo_file')

    if user and photo_file:
        username_str = f"@{user.username}" if user.username else "Username የለውም"
        admin_msg = (
            f"📥 **አዲስ የትዕዛዝ ጥያቄ ደርሷል!**\n\n"
            f"👤 ተጠቃሚ፦ {username_str} (ID: `{user.id}`)\n"
            f"💵 የዶላር መጠን፦ **${usd_amount:,.2f} USD**\n"
            f"💰 የክፍያ መጠን፦ **{total_birr:,.2f} ETB**\n"
            f"📍 የዋልሌት አድራሻ፦ `{wallet_address}`"
        )
        admin_keyboard = [[
            InlineKeyboardButton("✅ Approve (ላክሁት)", callback_data=f"approve_{user.id}"),
            InlineKeyboardButton("❌ Reject (ሰርዝ)", callback_data=f"reject_{user.id}")
        ]]
        admin_markup = InlineKeyboardMarkup(admin_keyboard)
        try:
            await context.bot.send_photo(
                chat_id=ADMIN_ID, photo=photo_file, caption=admin_msg, reply_markup=admin_markup, parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Failed to send to admin: {e}")

    await update.message.reply_text(
        "🎉 **ትዕዛዝዎ በተሳካ ሁኔታ ተጠናቋል!**\n\n"
        "የክፍያ ደረሰኝዎ እና የዋልሌት አድራሻዎ ለአድሚን ተልኳል። አድሚኑ ክፍያውን አረጋግጦ ዶላሩን በጥቂት ደቂቃዎች ውስጥ ገቢ ያደርግልዎታል።\n\n"
        "ስለተጠቀሙ እናመሰግናለን! 🙏",
        parse_mode="Markdown"
    )
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
        await query.message.reply_text(
            "📸 **እባክዎን የዶላር (Crypto) መላኪያውን ስክሪንሹት (Screenshot) ይላኩ፦**\n"
            "(ፎቶውን ሲልኩ ቀጥታ ከነማረጋገጫው ለተጠቃሚው ይላካል)"
        )
    elif data.startswith("reject_"):
        target_user_id = int(data.split("_")[1])
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="❌ **ትዕዛዝዎ ተሰርዟል!**\n\nየላኩት ክፍያ አልተረጋገጠም። እባክዎን ችግር ካለ አድሚኑን ያናግሩ።",
                parse_mode="Markdown"
            )
            if query.message and hasattr(query.message, 'edit_caption'):
                await getattr(query.message, 'edit_caption')(
                    caption=query.message.caption + "\n\n🔴 **STATUS: REJECTED ❌**", parse_mode="Markdown"
                )
        except Exception as e:
            logging.error(f"Error notifying user: {e}")

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
                        "✅ **ክፍያዎ ተረጋግጧል!**\n\n"
                        "ዶላሩ (USD) ወደ ሰጡት የዋልሌት አድራሻ በተሳካ ሁኔታ ተልኳል። "
                        "የመላኪያ ማረጋገጫው (Receipt) ከላይ ተያይዟል! 🚀\n\n"
                        "ስለተጠቀሙ እናመሰግናለን!"
                    )
                    await context.bot.send_photo(chat_id=target_user_id, photo=proof_photo, caption=msg, parse_mode="Markdown")
                    await update.message.reply_text("✅ **የመላኪያ ስክሪንሹቱ እና ማረጋገጫው ለተጠቃሚው ተልኳል!**")
                except Exception as e:
                    await update.message.reply_text(f"❌ ለተጠቃሚው መላክ አልተቻለም፦ {e}")
                bot_data['admin_waiting_photo'] = False

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text("ሂደቱ ተሰርዟል። እንደገና ለመጀመር /start ብለው ይፃፉ።")
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
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
            PAYMENT: [CallbackQueryHandler(payment_selected, pattern="^telebirr$")],
            SCREENSHOT: [MessageHandler(filters.PHOTO, receive_screenshot)],
            WALLET_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_wallet)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False
    )
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(admin_action_handler, pattern="^(approve|reject)_"))
    app.add_handler(MessageHandler(filters.PHOTO & filters.User(user_id=ADMIN_ID), handle_admin_photo))
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
