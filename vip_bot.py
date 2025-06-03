import logging
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)

TOKEN = "7963030995:AAE8K5RIFJpaOhxLnDxJ4k614wnq4n549AQ"
VIP_CHANNEL_LINK = "https://t.me/+9TBR6fK429tiMmRh"

plans = {
    "1": {"label": "1 Mês", "price": "R$ 39,90", "pix": "000201...390.90", "days": 30},
    "3": {"label": "3 Meses", "price": "R$ 99,90", "pix": "000201...999.90", "days": 90},
    "6": {"label": "6 Meses", "price": "R$ 179,90", "pix": "000201...179.90", "days": 180},
    "12": {"label": "12 Meses", "price": "R$ 289,90", "pix": "000201...289.90", "days": 365},
}

logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(f"Plano {plans[p]['label']} - {plans[p]['price']}", callback_data=f"plan_{p}")]
        for p in plans
    ]
    await update.message.reply_text(
        "👋 Bem-vindo! Escolha seu plano VIP:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_plan_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_key = query.data.split("_")[1]
    plan = plans[plan_key]
    context.user_data["selected_plan"] = plan
    await query.message.reply_text(
        f"""💳 Plano escolhido: {plan['label']}
Valor: {plan['price']}

Copie o código Pix abaixo para pagamento:

🔢 Código Pix:
{plan['pix']}

Após o pagamento, clique no botão abaixo para confirmar.""",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Já paguei", callback_data="confirm_payment")]
        ])
    )

async def handle_payment_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan = context.user_data.get("selected_plan")
    await query.message.reply_text(
        f"""🔍 Aguarde! Seu pagamento será verificado manualmente.
Assim que for aprovado, você receberá acesso ao canal VIP.

✅ Após verificar, o admin adicionará você no canal:
{VIP_CHANNEL_LINK}"""
    )

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_plan_selection, pattern="^plan_"))
    app.add_handler(CallbackQueryHandler(handle_payment_confirmation, pattern="^confirm_payment$"))
    app.run_polling()
