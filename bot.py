import os
import sqlite3
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Configurações
TOKEN = "7963030995:AAE8K5RIFJpaOhxLnDxJ4k614wnq4n549AQ"
CHANNEL_ID = -1002280243232
ADMIN_ID = 6150001511
CHANNEL_INVITE_LINK = "https://t.me/+9TBR6fK429tiMmRh"

# Planos
PLANS = {
    "1mes": {
        "name": "Plano VIP 1 mês",
        "price": "R$ 39,90",
        "days": 30,
        "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540539.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***63044086"
    },
    "3meses": {
        "name": "Plano VIP 3 meses",
        "price": "R$ 99,90",
        "days": 90,
        "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540599.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***63041E24"
    },
    "6meses": {
        "name": "Plano VIP 6 meses",
        "price": "R$ 179,90",
        "days": 180,
        "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406179.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***63043084"
    },
    "12meses": {
        "name": "Plano VIP 12 meses",
        "price": "R$ 289,90",
        "days": 365,
        "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406289.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***6304CD13"
    }
}

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('subscriptions.db', check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                join_date TEXT,
                last_payment_date TEXT,
                plan_type TEXT,
                status TEXT DEFAULT 'pending'
            )
        ''')
        self.conn.commit()
    
    def add_user(self, user_id, username, plan_type):
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, username, join_date, last_payment_date, plan_type, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        ''', (user_id, username, now, now, plan_type))
        self.conn.commit()
    
    def confirm_payment(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE users SET status = 'active' 
            WHERE user_id = ?
        ''', (user_id,))
        self.conn.commit()
    
    def get_expired_users(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT user_id, username, plan_type FROM users 
            WHERE status = 'active' AND 
            date(last_payment_date, '+' || (SELECT days FROM plans WHERE id = plan_type) || ' days') < date('now')
        ''')
        return cursor.fetchall()
    
    def remove_user(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE users SET status = 'expired' 
            WHERE user_id = ?
        ''', (user_id,))
        self.conn.commit()

db = Database()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    for plan_id, plan in PLANS.items():
        keyboard.append([InlineKeyboardButton(
            f"{plan['name']} - {plan['price']}", 
            callback_data=f"plan_{plan_id}"
        )])
    
    await update.message.reply_text(
        "🔞 *Escolha seu plano VIP:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

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
            [InlineKeyboardButton("📤 Enviar Comprovante", url=f"https://t.me/oiclarinhaalves")],
            [InlineKeyboardButton("🔄 Escolher Outro Plano", callback_data="back")]
        ]
        
        await query.edit_message_text(
            f"💳 *Pagamento via PIX*\n\n"
            f"Chave PIX:\n`{plan['pix']}`\n\n"
            f"💰 Valor: *{plan['price']}*\n\n"
            f"1. Copie o código PIX acima\n"
            f"2. Abra seu app de pagamentos\n"
            f"3. Cole o código e efetue o pagamento\n"
            f"4. Clique em *Enviar Comprovante*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    elif query.data == "back":
        await start(update, context)

async def check_expired_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    expired_users = db.get_expired_users()
    for user_id, username, plan_type in expired_users:
        try:
            # Remove do canal VIP
            await context.bot.ban_chat_member(CHANNEL_ID, user_id)
            await context.bot.unban_chat_member(CHANNEL_ID, user_id)
            
            # Atualiza status no banco
            db.remove_user(user_id)
            
            # Notifica usuário
            await context.bot.send_message(
                user_id,
                "⚠️ *Seu acesso VIP expirou!*\n\n"
                "Para renovar, use /start\n\n"
                "🔞 Não perca nosso conteúdo exclusivo!",
                parse_mode='Markdown'
            )
            
            # Notifica admin
            await context.bot.send_message(
                ADMIN_ID,
                f"⏰ Usuário removido do VIP\n\n"
                f"👤 @{username}\n"
                f"📋 Plano: {PLANS[plan_type]['name']}\n"
                f"🆔 ID: {user_id}",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Erro ao remover usuário {user_id}: {e}")

def main():
    # Cria aplicação
    application = Application.builder().token(TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_plans))
    
    # Job para verificar expirações a cada hora
    job_queue = application.job_queue
    job_queue.run_repeating(check_expired_subscriptions, interval=3600, first=10)
    
    # Inicia o bot
    application.run_polling()

if __name__ == '__main__':
    main()
