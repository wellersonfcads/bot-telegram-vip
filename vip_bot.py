import logging
import sqlite3
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import schedule
import time
from threading import Thread

# Configuração do logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurações do bot
TOKEN = "7963030995:AAE8K5RIFJpaOhxLnDxJ4k614wnq4n549AQ"
CANAL_VIP_LINK = "https://t.me/+9TBR6fK429tiMmRh"
CANAL_VIP_ID = "-1002280243232"  # ID do seu canal VIP

# Dados dos planos
PLANOS = {
    "1mes": {
        "nome": "Plano VIP 1 mês",
        "valor": "R$ 39,90",
        "duracao": 30,
        "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540539.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***63044086"
    },
    "3meses": {
        "nome": "Plano VIP 3 meses",
        "valor": "R$ 99,90",
        "duracao": 90,
        "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540599.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***63041E24"
    },
    "6meses": {
        "nome": "Plano VIP 6 meses",
        "valor": "R$ 179,90",
        "duracao": 180,
        "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406179.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***63043084"
    },
    "12meses": {
        "nome": "Plano VIP 12 meses",
        "valor": "R$ 289,90",
        "duracao": 365,
        "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406289.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***6304CD13"
    }
}

# Inicialização do banco de dados
def init_db():
    conn = sqlite3.connect('usuarios_vip.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            plano TEXT,
            data_entrada TEXT,
            data_expiracao TEXT,
            ativo INTEGER DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()

# Funções do banco de dados
def adicionar_usuario(user_id, username, plano):
    conn = sqlite3.connect('usuarios_vip.db')
    cursor = conn.cursor()
    
    data_entrada = datetime.now()
    data_expiracao = data_entrada + timedelta(days=PLANOS[plano]["duracao"])
    
    cursor.execute('''
        INSERT OR REPLACE INTO usuarios (user_id, username, plano, data_entrada, data_expiracao, ativo)
        VALUES (?, ?, ?, ?, ?, 1)
    ''', (user_id, username, plano, data_entrada.isoformat(), data_expiracao.isoformat()))
    
    conn.commit()
    conn.close()
    return data_expiracao

def verificar_usuarios_expirados():
    conn = sqlite3.connect('usuarios_vip.db')
    cursor = conn.cursor()
    
    agora = datetime.now().isoformat()
    cursor.execute('''
        SELECT user_id, username, plano FROM usuarios 
        WHERE data_expiracao < ? AND ativo = 1
    ''', (agora,))
    
    usuarios_expirados = cursor.fetchall()
    
    # Marcar como inativos
    cursor.execute('''
        UPDATE usuarios SET ativo = 0 
        WHERE data_expiracao < ? AND ativo = 1
    ''', (agora,))
    
    conn.commit()
    conn.close()
    
    return usuarios_expirados

def listar_usuarios_ativos():
    conn = sqlite3.connect('usuarios_vip.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT user_id, username, plano, data_entrada, data_expiracao 
        FROM usuarios WHERE ativo = 1
        ORDER BY data_expiracao
    ''')
    
    usuarios = cursor.fetchall()
    conn.close()
    return usuarios

# Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💎 Ver Planos VIP", callback_data="ver_planos")],
        [InlineKeyboardButton("📞 Suporte", url="https://t.me/seusupporte")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔥 *Bem-vindo ao VIP da Clarinha!* 🔥\n\n"
        "Aqui você tem acesso ao conteúdo mais exclusivo! 💋\n\n"
        "Escolha seu plano e tenha acesso completo:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Mostrar planos disponíveis
async def ver_planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    
    for plano_id, dados in PLANOS.items():
        texto_botao = f"{dados['nome']} - {dados['valor']}"
        keyboard.append([InlineKeyboardButton(texto_botao, callback_data=f"plano_{plano_id}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ Voltar", callback_data="voltar_inicio")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    texto = (
        "💎 *PLANOS VIP DISPONÍVEIS* 💎\n\n"
        "🔥 **Conteúdo 100% exclusivo**\n"
        "📸 **Fotos e vídeos inéditos**\n"
        "💬 **Interação direta**\n"
        "🎁 **Surpresas semanais**\n\n"
        "Escolha o plano ideal para você:"
    )
    
    query = update.callback_query
    await query.edit_message_text(texto, reply_markup=reply_markup, parse_mode='Markdown')

# Mostrar detalhes de um plano específico
async def mostrar_plano(update: Update, context: ContextTypes.DEFAULT_TYPE, plano_id: str):
    plano = PLANOS[plano_id]
    
    keyboard = [
        [InlineKeyboardButton("💳 Gerar PIX", callback_data=f"gerar_pix_{plano_id}")],
        [InlineKeyboardButton("⬅️ Voltar aos Planos", callback_data="ver_planos")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    texto = (
        f"💎 *{plano['nome']}*\n\n"
        f"💰 **Valor:** {plano['valor']}\n"
        f"⏰ **Duração:** {plano['duracao']} dias\n\n"
        f"🔥 **O que você vai receber:**\n"
        f"• Acesso completo ao canal VIP\n"
        f"• Conteúdo exclusivo diário\n"
        f"• Fotos e vídeos em alta qualidade\n"
        f"• Interação direta comigo\n"
        f"• Pedidos personalizados\n\n"
        f"Clique em 'Gerar PIX' para finalizar sua compra!"
    )
    
    query = update.callback_query
    await query.edit_message_text(texto, reply_markup=reply_markup, parse_mode='Markdown')

# Gerar PIX para pagamento
async def gerar_pix(update: Update, context: ContextTypes.DEFAULT_TYPE, plano_id: str):
    plano = PLANOS[plano_id]
    
    keyboard = [
        [InlineKeyboardButton("✅ Já Paguei - Solicitar Acesso", callback_data=f"solicitar_acesso_{plano_id}")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data=f"plano_{plano_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Aqui você pode gerar um QR Code se quiser
    texto = (
        f"💳 *PIX PARA PAGAMENTO*\n\n"
        f"📋 **Plano:** {plano['nome']}\n"
        f"💰 **Valor:** {plano['valor']}\n\n"
        f"**Chave PIX (Copia e Cola):**\n"
        f"`{plano['pix']}`\n\n"
        f"⚠️ **IMPORTANTE:**\n"
        f"• Após o pagamento, clique em 'Já Paguei'\n"
        f"• Seu acesso será liberado em até 5 minutos\n"
        f"• Guarde o comprovante de pagamento"
    )
    
    query = update.callback_query
    await query.edit_message_text(texto, reply_markup=reply_markup, parse_mode='Markdown')

# Solicitar acesso após pagamento
async def solicitar_acesso(update: Update, context: ContextTypes.DEFAULT_TYPE, plano_id: str):
    query = update.callback_query
    user = query.from_user
    
    # Adicionar usuário no banco de dados
    data_expiracao = adicionar_usuario(user.id, user.username, plano_id)
    
    plano = PLANOS[plano_id]
    
    # Enviar link do canal VIP
    keyboard = [
        [InlineKeyboardButton("🔥 ENTRAR NO VIP", url=CANAL_VIP_LINK)],
        [InlineKeyboardButton("📞 Suporte", url="https://t.me/seusupporte")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    texto = (
        f"🎉 **PAGAMENTO CONFIRMADO!** 🎉\n\n"
        f"✅ Seu {plano['nome']} foi ativado!\n"
        f"📅 **Válido até:** {data_expiracao.strftime('%d/%m/%Y às %H:%M')}\n\n"
        f"🔥 **Clique no botão abaixo para entrar no VIP:**\n\n"
        f"⚠️ **IMPORTANTE:**\n"
        f"• Salve este link: {CANAL_VIP_LINK}\n"
        f"• Seu acesso expira automaticamente\n"
        f"• Entre em contato com o suporte se tiver dúvidas"
    )
    
    await query.edit_message_text(texto, reply_markup=reply_markup, parse_mode='Markdown')
    
    # Notificar administrador sobre nova venda
    try:
        await context.bot.send_message(
            chat_id=SEU_USER_ID,  # Substitua pelo seu user ID
            text=f"💰 NOVA VENDA!\n\n"
                 f"👤 Usuário: @{user.username or 'Sem username'}\n"
                 f"📋 Plano: {plano['nome']}\n"
                 f"💰 Valor: {plano['valor']}\n"
                 f"📅 Expira em: {data_expiracao.strftime('%d/%m/%Y')}"
        )
    except:
        pass

# Voltar ao início
async def voltar_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💎 Ver Planos VIP", callback_data="ver_planos")],
        [InlineKeyboardButton("📞 Suporte", url="https://t.me/seusupporte")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query = update.callback_query
    await query.edit_message_text(
        "🔥 *Bem-vindo ao VIP da Clarinha!* 🔥\n\n"
        "Aqui você tem acesso ao conteúdo mais exclusivo! 💋\n\n"
        "Escolha seu plano e tenha acesso completo:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Handler para botões inline
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "ver_planos":
        await ver_planos(update, context)
    elif query.data == "voltar_inicio":
        await voltar_inicio(update, context)
    elif query.data.startswith("plano_"):
        plano_id = query.data.replace("plano_", "")
        await mostrar_plano(update, context, plano_id)
    elif query.data.startswith("gerar_pix_"):
        plano_id = query.data.replace("gerar_pix_", "")
        await gerar_pix(update, context, plano_id)
    elif query.data.startswith("solicitar_acesso_"):
        plano_id = query.data.replace("solicitar_acesso_", "")
        await solicitar_acesso(update, context, plano_id)

# Comandos administrativos
async def admin_usuarios(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Verificar se é admin (substitua pelo seu user ID)
    if update.effective_user.id != SEU_USER_ID:
        return
    
    usuarios = listar_usuarios_ativos()
    
    if not usuarios:
        await update.message.reply_text("📊 Nenhum usuário ativo no momento.")
        return
    
    texto = "📊 **USUÁRIOS ATIVOS:**\n\n"
    
    for user_id, username, plano, entrada, expiracao in usuarios:
        data_exp = datetime.fromisoformat(expiracao)
        dias_restantes = (data_exp - datetime.now()).days
        
        texto += (
            f"👤 @{username or 'Sem username'}\n"
            f"📋 Plano: {PLANOS[plano]['nome']}\n"
            f"⏰ Expira em: {dias_restantes} dias\n"
            f"📅 Data: {data_exp.strftime('%d/%m/%Y')}\n\n"
        )
    
    await update.message.reply_text(texto, parse_mode='Markdown')

# Função para remover usuários expirados
async def remover_usuarios_expirados(context: ContextTypes.DEFAULT_TYPE):
    usuarios_expirados = verificar_usuarios_expirados()
    
    if not usuarios_expirados:
        return
    
    for user_id, username, plano in usuarios_expirados:
        try:
            # Remover do canal VIP
            await context.bot.ban_chat_member(CANAL_VIP_ID, user_id)
            # Desbanir para que possa entrar novamente se comprar outro plano
            await context.bot.unban_chat_member(CANAL_VIP_ID, user_id)
            
            # Notificar o usuário
            await context.bot.send_message(
                chat_id=user_id,
                text=f"⏰ Seu {PLANOS[plano]['nome']} expirou!\n\n"
                     f"Para continuar tendo acesso ao conteúdo VIP, "
                     f"escolha um novo plano:\n\n"
                     f"/start"
            )
            
            logger.info(f"Usuário {username} ({user_id}) removido por expiração do plano {plano}")
            
        except Exception as e:
            logger.error(f"Erro ao remover usuário {user_id}: {e}")
    
    # Notificar admin sobre remoções
    if usuarios_expirados:
        try:
            await context.bot.send_message(
                chat_id=SEU_USER_ID,
                text=f"🔄 {len(usuarios_expirados)} usuários removidos por expiração de plano."
            )
        except:
            pass

# Configurar verificação automática
def configurar_verificacao_automatica(application):
    # Verificar a cada hora
    job_queue = application.job_queue
    if job_queue is not None:
        job_queue.run_repeating(remover_usuarios_expirados, interval=3600, first=10)
    else:
        logger.warning("JobQueue não disponível. Verificação automática desabilitada.")

# Função principal
def main():
    # Inicializar banco de dados
    init_db()
    
    # Criar aplicação
    application = Application.builder().token(TOKEN).build()
    
    # Configurar handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("usuarios", admin_usuarios))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Configurar verificação automática
    configurar_verificacao_automatica(application)
    
    # Iniciar bot
    logger.info("Bot iniciado!")
    application.run_polling()

# Configurações que você precisa alterar:
SEU_USER_ID = 6150001511  # Seu user ID do Telegram

if __name__ == '__main__':
    main()
