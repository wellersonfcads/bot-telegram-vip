import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ChatMemberHandler, filters, ContextTypes
import os # Adicionado para os.environ
import http.server
import socketserver
import urllib.request

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Desativa logs HTTP desnecessários
logging.getLogger('httpx').setLevel(logging.WARNING)

# --- Configurações Lidas das Variáveis de Ambiente ---
# Carrega o ID do administrador do Telegram da variável de ambiente
ADMIN_ID_STR = os.environ.get('ADMIN_ID')
if ADMIN_ID_STR:
    try:
        ADMIN_ID = int(ADMIN_ID_STR)
    except ValueError:
        logger.error("ERRO CRÍTICO: A variável de ambiente ADMIN_ID não é um número inteiro válido.")
        exit() # Ou outra forma de parar a execução segura
else:
    logger.error("ERRO CRÍTICO: Variável de ambiente ADMIN_ID não definida.")
    exit() # Ou outra forma de parar a execução segura

# Carrega o ID do canal VIP da variável de ambiente
CANAL_VIP_ID = os.environ.get('CANAL_VIP_ID')
if not CANAL_VIP_ID:
    logger.error("ERRO CRÍTICO: Variável de ambiente CANAL_VIP_ID não definida.")
    exit()

# Carrega o token do bot do Telegram da variável de ambiente
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    logger.error("ERRO CRÍTICO: Variável de ambiente TELEGRAM_BOT_TOKEN não definida.")
    exit()

# Links PIX (seus códigos originais - mantenha como está ou considere movê-los para uma config se forem mudar muito)
LINKS_PIX = {
    "1_mes": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540539.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA6207050363044086",
    "3_meses": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540599.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA6207050363041E24",
    "6_meses": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406179.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA6207050363043084",
    "12_meses": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406289.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA620705036304CD13"
}

# Planos e valores (mantenha como está ou considere movê-los para uma config)
PLANOS = {
    "1_mes": {"nome": "Plano VIP 1 mês", "valor": "R$ 39,90", "dias": 30},
    "3_meses": {"nome": "Plano VIP 3 meses", "valor": "R$ 99,90", "dias": 90},
    "6_meses": {"nome": "Plano VIP 6 meses", "valor": "R$ 179,90", "dias": 180},
    "12_meses": {"nome": "Plano VIP 12 meses", "valor": "R$ 289,90", "dias": 365}
}

# Estados do usuário
user_states = {}
# pending_payments = {} # Removido pois não estava sendo utilizado e a gestão é feita pelo DB

# ... (restante do seu código) ...

# Agora, em todo o lugar do seu código onde você usava:
# SEU_USER_ID, você usará ADMIN_ID
# BOT_TOKEN, você usará TELEGRAM_BOT_TOKEN
# CANAL_VIP_ID, o nome da variável já está correto, ele apenas será carregado do ambiente.

# Exemplo de alteração na função gerar_pix:
async def gerar_pix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (código anterior) ...
    # Notifica você sobre a nova solicitação
    await context.bot.send_message(
        chat_id=ADMIN_ID,  # Alterado de SEU_USER_ID para ADMIN_ID
        text=f"🔔 *NOVA SOLICITAÇÃO DE PAGAMENTO*\n\n"
             f"👤 Usuário: @{username} (ID: {user_id})\n"
             f"💎 Plano: {plano['nome']}\n"
             f"💰 Valor: {plano['valor']}\n"
             f"⏰ Horário: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        parse_mode='Markdown'
    )
    # ... (restante da função) ...

# Exemplo de alteração na função receber_comprovante:
async def receber_comprovante(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (código anterior) ...
    # Encaminha a imagem do comprovante
    if update.message.photo:
        await context.bot.send_photo(
            chat_id=ADMIN_ID, # Alterado de SEU_USER_ID para ADMIN_ID
            photo=update.message.photo[-1].file_id,
            caption=f"📎 *COMPROVANTE RECEBIDO*\n\n"
                    # ... (restante da caption)
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    elif update.message.document:
        await context.bot.send_document(
            chat_id=ADMIN_ID, # Alterado de SEU_USER_ID para ADMIN_ID
            document=update.message.document.file_id,
            caption=f"📎 *COMPROVANTE RECEBIDO*\n\n"
                    # ... (restante da caption)
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    # ... (restante da função) ...

# Exemplo de alteração na função listar_usuarios:
async def listar_usuarios(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: # Alterado de SEU_USER_ID para ADMIN_ID
        return
    # ... (restante da função) ...

# Exemplo de alteração na função remover_usuario:
async def remover_usuario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: # Alterado de SEU_USER_ID para ADMIN_ID
        return
    # ... (restante da função) ...

# Exemplo de alteração na função verificar_novo_membro:
async def verificar_novo_membro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.chat_member and str(update.chat_member.chat.id) == CANAL_VIP_ID:
        if update.chat_member.new_chat_member.status in ["member", "restricted"]:
            user_id = update.chat_member.new_chat_member.user.id
            
            if user_id == ADMIN_ID or user_id == context.bot.id: # Alterado de SEU_USER_ID para ADMIN_ID
                return
            # ... (restante da função) ...

# Exemplo de alteração na função remover_usuario_nao_autorizado:
async def remover_usuario_nao_autorizado(user_id, bot): # bot é passado como argumento
    try:
        await bot.ban_chat_member(CANAL_VIP_ID, user_id)
        await bot.unban_chat_member(CANAL_VIP_ID, user_id)
        logger.info(f"Usuário não autorizado {user_id} removido do canal automaticamente")
        
        # ... (notificação para o usuário) ...
        
        await bot.send_message(
            chat_id=ADMIN_ID, # Alterado de SEU_USER_ID para ADMIN_ID
            text=f"🚫 *Usuário não autorizado removido*\n\n"
                 f"O usuário com ID {user_id} tentou acessar o canal VIP sem autorização e foi removido automaticamente.",
            parse_mode='Markdown'
        )
        return True
    except Exception as e:
        logger.error(f"Erro ao remover usuário não autorizado {user_id}: {e}")
        return False

# Na função main(), para inicializar a aplicação:
def main():
    # ... (código anterior) ...
    # Cria a aplicação com configurações para evitar conflitos
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build() # Alterado de BOT_TOKEN para TELEGRAM_BOT_TOKEN
    # ... (restante da função) ...
    return application

# No bloco if __name__ == '__main__':
if __name__ == '__main__':
    try:
        app = main()
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "chat_member"]
        )
    except telegram.error.Conflict:
        logger.error("Conflito detectado: outra instância do bot já está em execução.")
        # Não é ideal tentar reiniciar aqui sem uma estratégia mais robusta.
        # Se você tem certeza que o conflito é resolvível com uma nova tentativa simples,
        # pode manter a segunda tentativa, mas geralmente é melhor investigar a causa.
        # logger.info("Tentando reiniciar com configurações diferentes...")
        # app = main() # Se for tentar de novo, certifique-se que main() pode ser chamada múltiplas vezes
        # app.run_polling(
        #     drop_pending_updates=True,
        #     allowed_updates=["message", "callback_query", "chat_member"]
        # )
    except Exception as e:
        # Loga o erro específico que causou a falha na inicialização,
        # que pode ser uma das variáveis de ambiente não encontradas.
        logger.error(f"Erro fatal ao iniciar o bot: {e}", exc_info=True)
