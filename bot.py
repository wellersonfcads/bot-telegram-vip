import os
import asyncio
import logging
from datetime import datetime, timedelta
import json
from typing import Dict, List
import aiohttp
from aiohttp import web
import sqlite3
from contextlib import asynccontextmanager

# Telegram Bot API
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Configurações
TOKEN = "7963030995:AAE8K5RIFJpaOhxLnDxJ4k614wnq4n549AQ"
CHANNEL_ID = -1002280243232  # ID do canal VIP
ADMIN_USER_ID = 6150001511
CHANNEL_INVITE_LINK = "https://t.me/+9TBR6fK429tiMmRh"

# Planos disponíveis
PLANS = {
    "1mes": {"name": "Plano VIP 1 mês", "price": "R$ 39,90", "days": 30, "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540539.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***63044086"},
    "3meses": {"name": "Plano VIP 3 meses", "price": "R$ 99,90", "days": 90, "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540599.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***63041E24"},
    "6meses": {"name": "Plano VIP 6 meses", "price": "R$ 179,90", "days": 180, "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406179.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***63043084"},
    "12meses": {"name": "Plano VIP 12 meses", "price": "R$ 289,90", "days": 365, "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406289.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***6304CD13"}
}

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SubscriptionBot:
    def __init__(self):
        self.application = None
        self.bot = None
        self.init_database()
        
    def init_database(self):
        """Inicializa o banco de dados SQLite"""
        conn = sqlite3.connect('subscriptions.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                plan_type TEXT,
                start_date TEXT,
                end_date TEXT,
                status TEXT DEFAULT 'pending',
                payment_confirmed BOOLEAN DEFAULT FALSE
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_subscription(self, user_id: int, username: str, plan_type: str):
        """Adiciona uma nova assinatura"""
        conn = sqlite3.connect('subscriptions.db')
        cursor = conn.cursor()
        
        start_date = datetime.now()
        end_date = start_date + timedelta(days=PLANS[plan_type]["days"])
        
        cursor.execute('''
            INSERT OR REPLACE INTO subscriptions 
            (user_id, username, plan_type, start_date, end_date, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        ''', (user_id, username, plan_type, start_date.isoformat(), end_date.isoformat()))
        
        conn.commit()
        conn.close()
    
    def confirm_payment(self, user_id: int):
        """Confirma o pagamento e ativa a assinatura"""
        conn = sqlite3.connect('subscriptions.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE subscriptions 
            SET status = 'active', payment_confirmed = TRUE
            WHERE user_id = ?
        ''', (user_id,))
        
        conn.commit()
        conn.close()
    
    def get_expired_subscriptions(self):
        """Retorna assinaturas expiradas"""
        conn = sqlite3.connect('subscriptions.db')
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        cursor.execute('''
            SELECT user_id, username FROM subscriptions 
            WHERE end_date < ? AND status = 'active'
        ''', (now,))
        
        expired = cursor.fetchall()
        conn.close()
        return expired
    
    def deactivate_subscription(self, user_id: int):
        """Desativa uma assinatura"""
        conn = sqlite3.connect('subscriptions.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE subscriptions 
            SET status = 'expired'
            WHERE user_id = ?
        ''', (user_id,))
        
        conn.commit()
        conn.close()

# Instância global do bot
subscription_bot = SubscriptionBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start - Mostra opções de planos"""
    keyboard = []
    
    for plan_id, plan_info in PLANS.items():
        keyboard.append([InlineKeyboardButton(
            f"{plan_info['name']} - {plan_info['price']}", 
            callback_data=f"select_{plan_id}"
        )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔥 **Escolha seu plano VIP:**\n\n"
        "📱 Acesso completo ao conteúdo exclusivo\n"
        "🎯 Conteúdo atualizado diariamente\n"
        "💎 Qualidade premium garantida\n\n"
        "👇 Selecione o plano desejado:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gerencia callbacks dos botões"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    username = query.from_user.username or f"user_{user_id}"
    
    if query.data.startswith("select_"):
        plan_id = query.data.replace("select_", "")
        plan = PLANS[plan_id]
        
        # Salva a assinatura no banco
        subscription_bot.add_subscription(user_id, username, plan_id)
        
        # Cria botões de pagamento
        keyboard = [
            [InlineKeyboardButton("💳 Gerar PIX", callback_data=f"pix_{plan_id}")],
            [InlineKeyboardButton("◀️ Voltar", callback_data="back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📋 **Resumo do Pedido:**\n\n"
            f"🎯 Plano: {plan['name']}\n"
            f"💰 Valor: {plan['price']}\n"
            f"⏰ Duração: {plan['days']} dias\n\n"
            f"👇 Clique em 'Gerar PIX' para finalizar:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    elif query.data.startswith("pix_"):
        plan_id = query.data.replace("pix_", "")
        plan = PLANS[plan_id]
        
        keyboard = [
            [InlineKeyboardButton("✅ Pagamento Realizado", callback_data=f"confirm_{plan_id}")],
            [InlineKeyboardButton("◀️ Voltar", callback_data=f"select_{plan_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"💳 **PIX Copia e Cola:**\n\n"
            f"`{plan['pix']}`\n\n"
            f"📱 **Ou escaneie o QR Code acima**\n\n"
            f"💰 Valor: **{plan['price']}**\n\n"
            f"⚠️ Após realizar o pagamento, clique em 'Pagamento Realizado'",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    elif query.data.startswith("confirm_"):
        plan_id = query.data.replace("confirm_", "")
        
        # Confirma o pagamento
        subscription_bot.confirm_payment(user_id)
        
        # Envia link do canal
        await query.edit_message_text(
            f"✅ **Pagamento confirmado!**\n\n"
            f"🎉 Bem-vindo ao VIP!\n\n"
            f"👇 **Clique no link abaixo para entrar:**\n"
            f"{CHANNEL_INVITE_LINK}\n\n"
            f"📱 Salve este link para acessar sempre que precisar!\n\n"
            f"⏰ Sua assinatura é válida por {PLANS[plan_id]['days']} dias",
            parse_mode='Markdown'
        )
        
        # Notifica admin
        try:
            await context.bot.send_message(
                ADMIN_USER_ID,
                f"💰 **Novo Pagamento!**\n\n"
                f"👤 Usuário: @{username} (ID: {user_id})\n"
                f"📋 Plano: {PLANS[plan_id]['name']}\n"
                f"💵 Valor: {PLANS[plan_id]['price']}\n"
                f"📅 Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                parse_mode='Markdown'
            )
        except:
            pass
    
    elif query.data == "back":
        await start(query, context)

async def check_expired_subscriptions():
    """Verifica e remove usuários com assinaturas expiradas"""
    while True:
        try:
            expired_users = subscription_bot.get_expired_subscriptions()
            
            for user_id, username in expired_users:
                try:
                    # Remove do canal
                    bot = Bot(TOKEN)
                    await bot.ban_chat_member(CHANNEL_ID, user_id)
                    await bot.unban_chat_member(CHANNEL_ID, user_id)
                    
                    # Desativa no banco
                    subscription_bot.deactivate_subscription(user_id)
                    
                    # Notifica o usuário
                    await bot.send_message(
                        user_id,
                        "⏰ **Sua assinatura VIP expirou!**\n\n"
                        "😢 Você foi removido do canal VIP\n\n"
                        "🔄 Para renovar, use /start\n\n"
                        "💎 Não perca mais conteúdo exclusivo!",
                        parse_mode='Markdown'
                    )
                    
                    # Notifica admin
                    await bot.send_message(
                        ADMIN_USER_ID,
                        f"⏰ **Assinatura Expirada**\n\n"
                        f"👤 @{username} (ID: {user_id}) foi removido do VIP",
                        parse_mode='Markdown'
                    )
                    
                    logger.info(f"Usuário {user_id} removido por expiração")
                    
                except Exception as e:
                    logger.error(f"Erro ao remover usuário {user_id}: {e}")
            
            # Aguarda 1 hora antes de verificar novamente
            await asyncio.sleep(3600)
            
        except Exception as e:
            logger.error(f"Erro na verificação de expiração: {e}")
            await asyncio.sleep(300)  # Aguarda 5 min em caso de erro

# Servidor web para health check (evita hibernação no Render)
async def health_check(request):
    return web.Response(text="Bot is running!")

async def webhook_handler(request):
    """Handler para webhook do Telegram"""
    try:
        update_data = await request.json()
        update = Update.de_json(update_data, subscription_bot.bot)
        await subscription_bot.application.process_update(update)
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        return web.Response(text="Error", status=400)

async def init_web_server():
    """Inicializa servidor web para health check"""
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    app.router.add_post('/webhook', webhook_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get('PORT', 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logger.info(f"Servidor web iniciado na porta {port}")

async def main():
    """Função principal"""
    try:
        # Inicializa o bot
        subscription_bot.application = Application.builder().token(TOKEN).build()
        subscription_bot.bot = subscription_bot.application.bot
        
        # Handlers
        subscription_bot.application.add_handler(CommandHandler("start", start))
        subscription_bot.application.add_handler(CallbackQueryHandler(button_callback))
        
        # Inicializa o bot
        await subscription_bot.application.initialize()
        
        # Inicializa servidor web
        await init_web_server()
        
        # Inicia verificação de expiração em background
        asyncio.create_task(check_expired_subscriptions())
        
        # Inicia o bot
        logger.info("Bot iniciado com sucesso!")
        await subscription_bot.application.start()
        await subscription_bot.application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
        # Mantém rodando
        while True:
            await asyncio.sleep(1)
        
    except Exception as e:
        logger.error(f"Erro ao iniciar bot: {e}")
    finally:
        if subscription_bot.application:
            await subscription_bot.application.stop()
            await subscription_bot.application.shutdown()

def run_bot():
    """Executa o bot de forma segura"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot interrompido pelo usuário")
    except Exception as e:
        logger.error(f"Erro fatal: {e}")

if __name__ == "__main__":
    run_bot()
