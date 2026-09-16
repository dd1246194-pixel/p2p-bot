# type: ignore
# 1. የክፍያ አማራጮች ዲክሽነሪ (ባንክ እና Telebirr)
PAYMENT_METHODS = {
    'telebirr': {
        'name': 'Telebirr',
        'details': '📱 Telebirr: <code>0900253321</code>\nስም: Dawit Eshetu'
    },
    'cbe': {
        'name': 'CBE (የኢትዮጵያ ንግድ ባንክ)',
        'details': '🏦 CBE: <code>1000123456789</code>\nስም: Dawit Eshetu'
    },
    'boa': {
        'name': 'Bank of Abyssinia',
        'details': '🏦 Abyssinia: <code>987654321</code>\nስም: Dawit Eshetu'
    }
}

# 2. ተጠቃሚው ክፍያ ሲመርጥ የሚሰራው Handler
async def select_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        method_key = query.data.split("_")[1] # telebirr, cbe, boa
        context.user_data['selected_payment'] = method_key
        
        selected = PAYMENT_METHODS.get(method_key, PAYMENT_METHODS['telebirr'])
        usd_amount = context.user_data.get('usd_amount', 0)
        total_birr = context.user_data.get('total_birr', 0)
        lang = context.user_data.get('lang', 'am')

        # ለተጠቃሚው የተመረጠውን ባንክ እና የሚከፍለውን ብር መላክ
        msg = (
            f"💳 <b>የክፍያ መመሪያ ({selected['name']})</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{selected['details']}\n\n"
            f"💵 <b>የሚከፍሉት መጠን:</b> <code>{total_birr:,.2f} ETB</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"3️⃣ ክፍያውን እንደፈጸሙ የደረሰኙን <b>Screenshot (ፎቶ)</b> እዚህ ይላኩ።"
        )
        await query.message.reply_text(msg, parse_mode="HTML")
        return SCREENSHOT

# 3. አድሚን ጋር ተጠቃሚው የመረጠው ባንክ እንዲደርስ ማድረግ
async def receive_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message and update.message.text:
        wallet = update.message.text
        user = update.effective_user
        method_key = context.user_data.get('selected_payment', 'telebirr')
        payment_name = PAYMENT_METHODS.get(method_key, {}).get('name', 'Telebirr')

        if user:
            admin_msg = (
                f"🚨 <b>NEW BUY ORDER!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>User:</b> @{user.username} (<code>{user.id}</code>)\n"
                f"💵 <b>Amount:</b> <code>${context.user_data.get('usd_amount'):,.2f} USD</code>\n"
                f"💰 <b>Total Birr:</b> <code>{context.user_data.get('total_birr'):,.2f} ETB</code>\n"
                f"🏦 <b>የመረጠው የክፍያ መንገድ:</b> <code>{payment_name}</code>\n"
                f"📍 <b>Payout Wallet:</b> <code>{wallet}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            )
            admin_btn = [[
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user.id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}")
            ]]
            await context.bot.send_photo(
                chat_id=ADMIN_ID, 
                photo=context.user_data['photo_file'], 
                caption=admin_msg, 
                reply_markup=InlineKeyboardMarkup(admin_btn), 
                parse_mode="HTML"
            )
        await update.message.reply_text("🎉 ትዕዛዝዎ በስኬት ተላኳል!", parse_mode="HTML")
        return ConversationHandler.END
    return WALLET_ADDRESS
