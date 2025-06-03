import sqlite3
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    JobQueue,
    MessageHandler,
    filters
)

# ... (mantenha todas as configurações iniciais e a classe Database igual)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (mantenha a função start igual)

async def handle_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("plan_"):
        plan_id = query.data.split("_")[1]
        plan = PLANS[plan_id]
        
        keyboard = [
            [InlineKeyboardButton("💳 Gerar PIX", callback_data=f"pix_{plan_id}")],
            [InlineKeyboardButton("🔙 Voltar", callback_data="back")]
        ]
        
        await query.edit_message_text(
            f"📝 *Resumo do Pedido*\n\n"
            f"📋 Plano: {plan['name']}\n"
            f"💰 Valor: {plan['price']}\n"
            f"⏳ Duração: {plan['days']} dias\n\n"
            f"Clique em *Gerar PIX* para prosseguir:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    elif query.data.startswith("pix_"):
        plan_id = query.data.split("_")[1]
        plan = PLANS[plan_id]
        
        keyboard = [
            [InlineKeyboardButton("✅ Paguei/Enviar Comprovante", callback_data=f"paid_{plan_id}")],
            [InlineKeyboardButton("🔄 Escolher Outro Plano", callback_data="back")]
        ]
        
        await query.edit_message_text(
            f"💳 *Pagamento via PIX*\n\n"
            f"Chave PIX:\n`{plan['pix']}`\n\n"
            f"💰 Valor: *{plan['price']}*\n\n"
            f"1. Efetue o pagamento\n"
            f"2. Clique em *Paguei/Enviar Comprovante*\n"
            f"3. Envie o comprovante neste chat",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    elif query.data.startswith("paid_"):
        plan_id = query.data.split("_")[1]
        context.user_data['awaiting_proof'] = plan_id
        
        await query.edit_message_text(
            "📤 *Envie seu comprovante agora*\n\n"
            "Por favor, envie uma foto ou print do comprovante de pagamento "
            "diretamente neste chat.\n\n"
            "⚠️ Certifique-se que os dados da transferência estão visíveis",
            parse_mode='Markdown'
        )
    
    elif query.data == "back":
        await start(update, context)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_proof' in context.user_data:
        plan_id = context.user_data['awaiting_proof']
        user = update.message.from_user
        
        # Notifica o admin
        await context.bot.send_message(
            ADMIN_ID,
            f"⚠️ *NOVO COMPROVANTE RECEBIDO!*\n\n"
            f"👤 Usuário: @{user.username or 'sem_username'} (ID: {user.id})\n"
            f"📋 Plano: {PLANS[plan_id]['name']}\n"
            f"💵 Valor: {PLANS[plan_id]['price']}\n\n"
            f"Para aprovar, use:\n"
            f"`/aprovar {user.id} {plan_id}`",
            parse_mode='Markdown'
        )
        
        # Confirmação para o usuário
        await update.message.reply_text(
            "✅ *Comprovante recebido!*\n\n"
            "Seu comprovante foi enviado para análise. "
            "Você receberá o acesso em até 15 minutos.\n\n"
            "Obrigado pela preferência!",
            parse_mode='Markdown'
        )
        
        del context.user_data['awaiting_proof']

async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id == ADMIN_ID:
        try:
            user_id = int(context.args[0])
            plan_id = context.args[1]
            
            db.confirm_payment(user_id)
            await context.bot.send_message(
                user_id,
                f"🎉 *Pagamento aprovado!*\n\n"
                f"Agora você tem acesso ao conteúdo VIP!\n\n"
                f"👉 {CHANNEL_INVITE_LINK}\n\n"
                f"⏳ Validade: {PLANS[plan_id]['days']} dias",
                parse_mode='Markdown'
            )
            
            await update.message.reply_text(f"✅ Usuário {user_id} aprovado com sucesso!")
        except:
            await update.message.reply_text("Formato incorreto. Use: /aprovar USER_ID PLANO")

async def check_expired_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    # ... (mantenha esta função igual)

def main():
    application = Application.builder().token(TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("aprovar", approve_payment))
    application.add_handler(CallbackQueryHandler(handle_plans))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_document))
    
    # JobQueue
    job_queue = application.job_queue
    job_queue.run_repeating(check_expired_subscriptions, interval=3600, first=10)
    
    application.run_polling()

if __name__ == '__main__':
    main()
