[9/12/2026 6:56 AM] Se: import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# --- 1. CONFIGURATION ---
BOT_TOKEN = "8048106014:AAHBx1WraAgYQNUdZBr0m1Dup1HdxwjWJNQ"
ADMIN_ID = 7798227927

logging.basicConfig(level=logging.INFO)

# --- 2. DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect("p2p_bot.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            amount TEXT,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- 3. HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💳 መግዛት (Buy)", callback_data="buy")],
        [InlineKeyboardButton("💵 መሸጥ (Sell)", callback_data="sell")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("እንኳን ወደ P2P አገልግሎት በሰላም መጡ! ምን ማድረግ ይፈልጋሉ?", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data in ["buy", "sell"]:
        context.user_data['action'] = query.data
        await query.edit_message_text(f"እባክዎን የወሰኑትን የገንዘብ መጠን/አማውንት ያስገቡ፦")

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if 'action' in context.user_data:
        action = context.user_data['action']
        
        # Save order to database
        conn = sqlite3.connect("p2p_bot.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO orders (user_id, action, amount, status) VALUES (?, ?, ?, ?)",
                       (user_id, action, text, "PENDING"))
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Send to Admin for review
        admin_keyboard = [
            [InlineKeyboardButton("✅ አጽድቅ (Approve)", callback_data=f"approve_{order_id}_{user_id}")],
            [InlineKeyboardButton("❌ ሰርዝ (Reject)", callback_data=f"reject_{order_id}_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(admin_keyboard)
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🚨 አዲስ P2P ጥያቄ!\n\nOrder ID: #{order_id}\nUser ID: {user_id}\nዓይነት: {action.upper()}\nመጠን: {text}",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        
        await update.message.reply_text("ጥያቄዎ ለአድሚን ተልኳል! አድሚኑ አረጋግጦ እስኪያጸድቀው ድረስ ትንሽ ይታገሱ።")
        del context.user_data['action']

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("_")
    action, order_id, user_id = data[0], data[1], data[2]

    conn = sqlite3.connect("p2p_bot.db")
    cursor = conn.cursor()

    if action == "approve":
        cursor.execute("UPDATE orders SET status = 'APPROVED' WHERE id = ?", (order_id,))
        await context.bot.send_message(chat_id=user_id, text=f"✅ የጥያቄ ቁጥር #{order_id} ግብይትዎ ጸድቋል/ተጠናቋል!")
        await query.edit_message_text(f"Order #{order_id} ጸድቋል።")
    elif action == "reject":
        cursor.execute("UPDATE orders SET status = 'REJECTED' WHERE id = ?", (order_id,))
        await context.bot.send_message(chat_id=user_id, text=f"❌ የጥያቄ ቁጥር #{order_id} ግብይትዎ ተሰርዟል።")
        await query.edit_message_text(f"Order #{order_id} ተሰርዟል።")

    conn.commit()
    conn.close()

# --- 4. MAIN FUNCTION ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()
[9/12/2026 6:56 AM] Se: app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^(approve|reject)_"))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_message))

    app.run_polling()

if name == "main":
    main()
