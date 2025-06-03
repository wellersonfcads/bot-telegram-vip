import logging
import sqlite3
import asyncio
import threading
from datetime import datetime, timedelta
from typing import Optional
import json
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from aiohttp import web
import requests

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configurações do bot
BOT_TOKEN = "7963030995:AAE8K5RIFJpaOhxLnDxJ4k614wnq4n549AQ"
ADMIN_USER_ID = 6150001511
VIP_CHANNEL_ID = -1002280243232
VIP_INVITE_LINK = "https://t.me/+9TBR6fK429tiMmRh"

# Configuração dos planos
PLANS = {
    "1": {"name": "Plano VIP 1 mês", "price": "R$ 39,90", "days": 30,
          "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540539.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA6207050363044086"},
    "3": {"name": "Plano VIP 3 meses", "price": "R$ 99,90", "days": 90,
          "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540599.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA6207050363041E24"},
    "6": {"name": "Plano VIP 6 meses", "price": "R$ 179,90", "days": 180,
          "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406179.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA6207050363043084"},
    "12": {"name": "Plano VIP 12 meses", "price": "R$ 289,90", "days": 365,
           "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406289.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA620705036304CD13"}
}

class DatabaseManager:
    def __init__(self):
        self.init_db()
    
    def init_db(self):
        conn = sqlite3.connect('subscriptions.db')
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                plan_type TEXT,
                start_date TEXT,
                end_date TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    
    def add_subscription(self, user_id: int, username: str, plan_type: str, days: int):
        conn = sqlite3.connect('subscriptions.db')
        cursor = conn.cursor()
        
        start_date = datetime.now()
        end_date = start_date + timedelta(days=days)
        
        cursor.execute('''
            INSERT OR REPLACE INTO subscriptions 
            (user_id, username, plan_type, start_date, end_date, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
        ''', (user_id, username, plan_type, start_date.isoformat(), end_date.isoformat()))
        
        conn.commit()
        conn.close()
        logger.info(f"Subscription added for user {user_id} - Plan: {plan_type}")
    
    def get_expired_users(self):
        conn = sqlite3.connect('subscriptions.db')
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        cursor.execute('''
            SELECT user_id, username, plan_type FROM subscriptions 
            WHERE end_date < ? AND is_active = 1
        ''', (now,))
        
        expired_users = cursor.fetchall()
        conn.close()
        return expired_users
    
    def deactivate_subscription(self, user_id: int):
        conn = sqlite3.connect('subscriptions.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE subscriptions SET is_active = 0 WHERE user_id = ?
        ''', (user_id,))
        
        conn.commit()
        conn.close()
        logger.info(f"Subscription deactivated for user {user_id}")

# Instância do gerenciador de banco
db_manager = DatabaseManager()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start - Mostra os planos disponíveis"""
    user = update.effective_user
    
    welcome_text = f"""
🔞 **Bem-vindo ao Canal VIP da Clarinha!** 🔞

Olá {user.first_name}! 👋

Escolha seu plano de acesso ao conteúdo exclusivo:

💎 **PLANOS DISPONÍVEIS:**
• 1 mês - R$ 39,90
• 3 meses - R$ 99,90  
• 6 meses - R$ 179,90
• 12 meses - R$ 289,90

🎁 **O QUE VOCÊ TERÁ ACESSO:**
• Conteúdo exclusivo diário
• Fotos e vídeos em alta qualidade
• Acesso ao canal VIP privado
• Suporte direto

Selecione o plano desejado abaixo:
    """
    
    keyboard = [
        [InlineKeyboardButton("💎 1 Mês - R$ 39,90", callback_data="plan_1")],
        [InlineKeyboardButton("💎 3 Meses - R$ 99,90", callback_data="plan_3")],  
        [InlineKeyboardButton("💎 6 Meses - R$ 179,90", callback_data="plan_6")],
        [InlineKeyboardButton("💎 12 Meses - R$ 289,90", callback_data="plan_12")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def plan_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback quando um plano é selecionado"""
    query = update.callback_query
    await query.answer()
    
    plan_id = query.data.split("_")[1]
    plan = PLANS[plan_id]
    
    # Armazenar o plano selecionado no contexto do usuário
    context.user_data['selected_plan'] = plan_id
    
    plan_text = f"""
💎 **{plan['name']}**
💰 **Valor:** {plan['price']}
⏰ **Duração:** {plan['days']} dias

Para pagar, clique no botão abaixo para gerar o PIX:
    """
    
    keyboard = [
        [InlineKeyboardButton("💳 Gerar PIX", callback_data=f"generate_pix_{plan_id}")],
        [InlineKeyboardButton("⬅️ Voltar aos Planos", callback_data="back_to_plans")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(plan_text, reply_markup=reply_markup, parse_mode='Markdown')

async def generate_pix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gera o código PIX para pagamento"""
    query = update.callback_query
    await query.answer()
    
    plan_id = query.data.split("_")[2]
    plan = PLANS[plan_id]
    
    pix_text = f"""
💳 **PIX PARA PAGAMENTO**

**Plano:** {plan['name']}
**Valor:** {plan['price']}

**Código PIX:**
```
{plan['pix']}
```

📱 **Como pagar:**
1. Copie o código PIX acima
2. Abra seu app do banco
3. Vá em PIX → Colar código
4. Confirme o pagamento
5. Clique em "Pagamento Realizado" abaixo

⚠️ **Importante:** Após o pagamento, clique no botão abaixo para receber o acesso!
    """
    
    keyboard = [
        [InlineKeyboardButton("✅ Pagamento Realizado", callback_data=f"payment_done_{plan_id}")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data=f"plan_{plan_id}")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(pix_text, reply_markup=reply_markup, parse_mode='Markdown')

async def payment_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa o pagamento realizado"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    plan_id = query.data.split("_")[2]
    plan = PLANS[plan_id]
    
    try:
        # Adicionar usuário ao canal VIP
        await context.bot.unban_chat_member(
            chat_id=VIP_CHANNEL_ID,
            user_id=user.id
        )
        
        # Salvar assinatura no banco
        username = user.username or user.first_name
        db_manager.add_subscription(user.id, username, plan['name'], plan['days'])
        
        # Notificar admin
        admin_message = f"""
🔔 **NOVA ASSINATURA!**

👤 **Usuário:** @{username} ({user.id})
💎 **Plano:** {plan['name']}
💰 **Valor:** {plan['price']}
📅 **Data:** {datetime.now().strftime('%d/%m/%Y %H:%M')}
        """
        
        try:
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=admin_message,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Erro ao notificar admin: {e}")
        
        # Confirmar para o usuário
        success_text = f"""
🎉 **PAGAMENTO CONFIRMADO!**

Parabéns! Seu acesso foi liberado!

💎 **Plano Ativo:** {plan['name']}
⏰ **Duração:** {plan['days']} dias
📅 **Válido até:** {(datetime.now() + timedelta(days=plan['days'])).strftime('%d/%m/%Y')}

🔗 **Link do Canal VIP:**
{VIP_INVITE_LINK}

⚠️ **Importante:**
• Salve este link!
• Não compartilhe com outras pessoas
• Em caso de dúvidas, entre em contato

Aproveite o conteúdo exclusivo! 🔥
        """
        
        await query.edit_message_text(success_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Erro ao processar pagamento: {e}")
        error_text = """
❌ **Erro ao processar pagamento**

Ocorreu um erro ao liberar seu acesso. Entre em contato com o suporte.
        """
        await query.edit_message_text(error_text, parse_mode='Markdown')

async def back_to_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Volta para a seleção de planos"""
    await start(update, context)

async def check_expired_subscriptions():
    """Verifica e remove usuários com assinatura expirada"""
    while True:
        try:
            expired_users = db_manager.get_expired_users()
            
            if expired_users:
                # Criar instância da aplicação para usar o bot
                application = Application.builder().token(BOT_TOKEN).build()
                
                for user_id, username, plan_type in expired_users:
                    try:
                        # Remover do canal VIP
                        await application.bot.ban_chat_member(
                            chat_id=VIP_CHANNEL_ID,
                            user_id=user_id
                        )
                        
                        # Desativar assinatura no banco
                        db_manager.deactivate_subscription(user_id)
                        
                        # Notificar usuário
                        try:
                            await application.bot.send_message(
                                chat_id=user_id,
                                text=f"""
⏰ **ASSINATURA EXPIRADA**

Olá! Sua assinatura do **{plan_type}** expirou.

Para renovar seu acesso, use o comando /start e escolha um novo plano.

Obrigado por fazer parte da nossa comunidade! 💎
                                """,
                                parse_mode='Markdown'
                            )
                        except:
                            pass  # Usuário pode ter bloqueado o bot
                        
                        # Notificar admin
                        try:
                            await application.bot.send_message(
                                chat_id=ADMIN_USER_ID,
                                text=f"""
⏰ **ASSINATURA EXPIRADA**

👤 **Usuário:** @{username} ({user_id})
💎 **Plano:** {plan_type}
📅 **Data:** {datetime.now().strftime('%d/%m/%Y %H:%M')}

Usuário removido automaticamente do canal VIP.
                                """,
                                parse_mode='Markdown'
                            )
                        except:
                            pass
                            
                        logger.info(f"Usuário {user_id} removido - assinatura expirada")
                        
                    except Exception as e:
                        logger.error(f"Erro ao remover usuário {user_id}: {e}")
                
                await application.stop()
            
        except Exception as e:
            logger.error(f"Erro na verificação de assinaturas: {e}")
        
        # Verificar a cada hora
        await asyncio.sleep(3600)

async def health_check(request):
    """Health check endpoint para o Render"""
    return web.Response(text="Bot is running!")

async def start_web_server():
    """Inicia o servidor web para health check"""
    app = web.Application()
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    logger.info("Servidor web iniciado na porta 10000")

def run_subscription_checker():
    """Executa o verificador de assinaturas em thread separada"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(check_expired_subscriptions())

async def delete_webhook_and_start():
    """Deleta webhook antes de iniciar o bot"""
    try:
        # Tentar deletar webhook
        response = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
        if response.status_code == 200:
            logger.info("Webhook deletado com sucesso")
        else:
            logger.warning("Não foi possível deletar webhook, continuando...")
    except Exception as e:
        logger.warning(f"Erro ao deletar webhook: {e}")

async def main():
    """Função principal"""
    # Deletar webhook primeiro
    await delete_webhook_and_start()
    
    # Criar aplicação
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .get_updates_read_timeout(30)
        .get_updates_write_timeout(30)
        .get_updates_connect_timeout(30)
        .get_updates_pool_timeout(30)
        .build()
    )
    
    # Adicionar handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(plan_selected, pattern="^plan_"))
    application.add_handler(CallbackQueryHandler(generate_pix, pattern="^generate_pix_"))
    application.add_handler(CallbackQueryHandler(payment_done, pattern="^payment_done_"))
    application.add_handler(CallbackQueryHandler(back_to_plans, pattern="^back_to_plans"))
    
    # Iniciar servidor web
    await start_web_server()
    
    # Iniciar verificador de assinaturas em thread separada
    subscription_thread = threading.Thread(target=run_subscription_checker, daemon=True)
    subscription_thread.start()
    
    logger.info("Bot iniciado com sucesso!")
    
    # Iniciar bot com polling
    await application.run_polling(poll_interval=2, bootstrap_retries=5)

if __name__ == '__main__':
    asyncio.run(main())
