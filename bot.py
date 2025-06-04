import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ChatMemberHandler, filters, ContextTypes
import os
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

# Configurações - ALTERE AQUI
SEU_USER_ID = 6150001511  # Seu user ID do Telegram
CANAL_VIP_ID = "-1002280243232"  # ID do seu canal VIP
BOT_TOKEN = "7963030995:AAE8K5RIFJpaOhxLnDxJ4k614wnq4n549AQ"

# Links PIX (seus códigos originais)
LINKS_PIX = {
    "1_mes": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540539.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA6207050363044086",
    "3_meses": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540599.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA6207050363041E24",
    "6_meses": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406179.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA6207050363043084",
    "12_meses": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406289.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA620705036304CD13"
}

# Planos e valores
PLANOS = {
    "1_mes": {"nome": "Plano VIP 1 mês", "valor": "R$ 39,90", "dias": 30},
    "3_meses": {"nome": "Plano VIP 3 meses", "valor": "R$ 99,90", "dias": 90},
    "6_meses": {"nome": "Plano VIP 6 meses", "valor": "R$ 179,90", "dias": 180},
    "12_meses": {"nome": "Plano VIP 12 meses", "valor": "R$ 289,90", "dias": 365}
}

# Estados do usuário
user_states = {}
pending_payments = {}  # Para armazenar pagamentos pendentes

def init_db():
    """Inicializa o banco de dados"""
    conn = sqlite3.connect('vip_bot.db')
    cursor = conn.cursor()
    
    # Tabela de usuários VIP
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios_vip (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            plano TEXT,
            data_entrada TEXT,
            data_expiracao TEXT,
            ativo INTEGER DEFAULT 1
        )
    ''')
    
    # Tabela de pagamentos pendentes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pagamentos_pendentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            plano TEXT,
            valor TEXT,
            data_solicitacao TEXT,
            comprovante_enviado INTEGER DEFAULT 0,
            aprovado INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start com verificação de idade"""
    user_id = update.effective_user.id
    
    # Mensagem de boas-vindas
    await update.message.reply_text(
        "Seja bem-vindo ao meu Canal VIP 🔥\n\n"
        "🌶 Interação com os assinantes\n\n"
        "🌶 Fotos/Vídeos Exclusivos\n\n"
        "🌶 Contos Eróticos\n\n"
        "🌶 Lives e Sorteios\n\n"
        "Para ter acesso, clique em /start agora mesmo!",
        parse_mode='Markdown'
    )
    
    # Verificação de idade
    keyboard = [
        [InlineKeyboardButton("✅ Sim, tenho 18 anos ou mais", callback_data="idade_ok")],
        [InlineKeyboardButton("❌ Não tenho 18 anos", callback_data="idade_nao")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔞 *VERIFICAÇÃO DE IDADE* 🔞\n\n"
        "Oi amor! Antes de continuarmos, preciso confirmar:\n"
        "Você tem 18 anos ou mais?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_idade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manipula a verificação de idade"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "idade_nao":
        await query.edit_message_text(
            "❌ Desculpe amor, meu conteúdo é apenas para maiores de 18 anos.\n\n"
            "Volte quando completar 18 anos! 😊"
        )
        return
    
    if query.data == "idade_ok":
        user_id = query.from_user.id
        user_states[user_id] = "idade_verificada"
        
        await query.edit_message_text(
            "🥰 *Bom te ver por aqui...*\n\n"
            "Que bom que você chegou até mim! "
            "Estou muito animada para te mostrar tudo que preparei especialmente para você...\n\n"
            "No meu VIP você vai encontrar conteúdos exclusivos que não posto em lugar nenhum... 🙊",
            parse_mode='Markdown'
        )
        
        # Aguarda 3 segundos e mostra os planos diretamente
        await context.application.job_queue.run_once(
            mostrar_acesso_vip, 
            3, 
            data={"chat_id": query.message.chat_id, "user_id": user_id}
        )

# Função de vídeo removida conforme solicitado

async def mostrar_acesso_vip(context: ContextTypes.DEFAULT_TYPE):
    """Mostra opção de acesso VIP"""
    job_data = context.job.data
    chat_id = job_data["chat_id"]
    
    keyboard = [
        [InlineKeyboardButton("⭐ GRUPO VIP", callback_data="ver_planos")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        chat_id=chat_id,
        text="💎 *Quer ter acesso a todo meu conteúdo completo no VIP?*\n\n"
             "No meu grupo VIP você vai ter:\n"
             "🔥 Minhas fotos e vídeos exclusivos\n"
             "💕 Conteúdo que não posto em lugar nenhum\n"
             "🎯 Acesso direto comigo\n"
             "✨ Surpresas especiais só para meus VIPs\n\n"
             "Clica no botão abaixo para ver os planos disponíveis! 👇",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def mostrar_planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra os planos VIP disponíveis"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton(f"💎 {PLANOS['1_mes']['nome']} - {PLANOS['1_mes']['valor']}", callback_data="plano_1_mes")],
        [InlineKeyboardButton(f"💎 {PLANOS['3_meses']['nome']} - {PLANOS['3_meses']['valor']}", callback_data="plano_3_meses")],
        [InlineKeyboardButton(f"💎 {PLANOS['6_meses']['nome']} - {PLANOS['6_meses']['valor']}", callback_data="plano_6_meses")],
        [InlineKeyboardButton(f"💎 {PLANOS['12_meses']['nome']} - {PLANOS['12_meses']['valor']}", callback_data="plano_12_meses")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "💎 *MEUS PLANOS VIP DISPONÍVEIS*\n\n"
        "Escolhe o plano que mais combina com você, amor:\n\n"
        "✨ Todos os planos incluem acesso completo ao meu conteúdo exclusivo!\n"
        "🔥 Quanto maior o plano, melhor o custo-benefício!\n\n"
        "Clica no plano desejado:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def detalhes_plano(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra detalhes do plano selecionado"""
    query = update.callback_query
    await query.answer()
    
    plano_key = query.data.replace("plano_", "")
    plano = PLANOS[plano_key]
    
    # Armazena o plano selecionado
    user_id = query.from_user.id
    user_states[user_id] = {"plano_selecionado": plano_key}
    
    keyboard = [
        [InlineKeyboardButton("💳 Gerar PIX", callback_data=f"gerar_pix_{plano_key}")],
        [InlineKeyboardButton("⬅️ Voltar aos Planos", callback_data="ver_planos")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"💎 *{plano['nome']}*\n\n"
        f"💰 Valor: *{plano['valor']}*\n"
        f"⏰ Duração: *{plano['dias']} dias*\n\n"
        f"🔥 *O que você vai receber, amor:*\n"
        f"✅ Acesso total ao meu grupo VIP\n"
        f"✅ Todo meu conteúdo exclusivo\n"
        f"✅ Minhas fotos e vídeos que não posto em lugar nenhum\n"
        f"✅ Contato direto comigo\n"
        f"✅ Meus novos conteúdos adicionados regularmente\n\n"
        f"Clique em 'Gerar PIX' para continuar! 👇",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def gerar_pix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gera o PIX para pagamento"""
    query = update.callback_query
    await query.answer()
    
    plano_key = query.data.replace("gerar_pix_", "")
    plano = PLANOS[plano_key]
    pix_code = LINKS_PIX[plano_key]
    
    user_id = query.from_user.id
    username = query.from_user.username or "Não informado"
    
    # Salva o pagamento pendente
    conn = sqlite3.connect('vip_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO pagamentos_pendentes 
        (user_id, username, plano, valor, data_solicitacao) 
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, username, plano_key, plano['valor'], datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("📋 Copiar PIX", callback_data=f"copiar_pix_{plano_key}")],
        [InlineKeyboardButton("✅ Já Paguei - Solicitar Acesso", callback_data=f"ja_paguei_{plano_key}")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data=f"plano_{plano_key}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"💳 *PIX para Pagamento - {plano['nome']}*\n\n"
        f"💰 Valor: *{plano['valor']}*\n\n"
        f"📋 *Código PIX (Copia e Cola):*\n"
        f"`{pix_code}`\n\n"
        f"📱 *Como pagar:*\n"
        f"1️⃣ Clica em 'Copiar PIX' abaixo\n"
        f"2️⃣ Abre seu app bancário\n"
        f"3️⃣ Escolhe PIX > Copia e Cola\n"
        f"4️⃣ Cola o código copiado\n"
        f"5️⃣ Confirma o pagamento\n"
        f"6️⃣ Clica em 'Já Paguei' para me enviar o comprovante\n\n"
        f"💕 Estou ansiosa para te receber no meu VIP, amor!",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    # Notifica você sobre a nova solicitação
    await context.bot.send_message(
        chat_id=SEU_USER_ID,
        text=f"🔔 *NOVA SOLICITAÇÃO DE PAGAMENTO*\n\n"
             f"👤 Usuário: @{username} (ID: {user_id})\n"
             f"💎 Plano: {plano['nome']}\n"
             f"💰 Valor: {plano['valor']}\n"
             f"⏰ Horário: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        parse_mode='Markdown'
    )

async def copiar_pix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Função para copiar PIX"""
    query = update.callback_query
    await query.answer("PIX copiado! 📋\nCole no seu app bancário na opção PIX > Copia e Cola", show_alert=True)

async def ja_paguei(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Solicita envio de comprovante"""
    query = update.callback_query
    await query.answer()
    
    plano_key = query.data.replace("ja_paguei_", "")
    user_id = query.from_user.id
    user_states[user_id] = {"aguardando_comprovante": plano_key}
    
    keyboard = [
        [InlineKeyboardButton("📎 Enviar Comprovante", callback_data="enviar_comprovante")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data=f"gerar_pix_{plano_key}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📎 *Envio de Comprovante*\n\n"
        "Perfeito, amor! Agora preciso do seu comprovante de pagamento para liberar seu acesso ao meu VIP.\n\n"
        "📱 *Como me enviar:*\n"
        "1️⃣ Clica em 'Enviar Comprovante'\n"
        "2️⃣ Tira uma foto ou screenshot do comprovante\n"
        "3️⃣ Me envia a imagem\n\n"
        "✅ Assim que eu verificar, vou liberar seu acesso imediatamente!\n\n"
        "💕 Obrigada pela confiança, amor!",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def solicitar_comprovante(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Solicita o envio do comprovante"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    await query.edit_message_text(
        "📎 *Aguardando Comprovante*\n\n"
        "Agora é só me enviar a foto ou screenshot do seu comprovante de pagamento!\n\n"
        "📸 Pode ser:\n"
        "• Screenshot da tela de confirmação\n"
        "• Foto do comprovante\n"
        "• Print do extrato\n\n"
        "💕 Estou aguardando aqui para liberar seu acesso ao meu VIP!",
        parse_mode='Markdown'
    )

async def receber_comprovante(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe e processa o comprovante enviado"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "Não informado"
    
    if user_id not in user_states or "aguardando_comprovante" not in user_states[user_id]:
        await update.message.reply_text("❌ Erro: Não encontrei sua solicitação de pagamento.")
        return
    
    plano_key = user_states[user_id]["aguardando_comprovante"]
    plano = PLANOS[plano_key]
    
    # Atualiza no banco que o comprovante foi enviado
    conn = sqlite3.connect('vip_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE pagamentos_pendentes 
        SET comprovante_enviado = 1 
        WHERE user_id = ? AND plano = ? AND aprovado = 0
    ''', (user_id, plano_key))
    conn.commit()
    conn.close()
    
    # Remove o estado do usuário
    del user_states[user_id]
    
    # Envia confirmação para o usuário
    await update.message.reply_text(
        "✅ *Comprovante Recebido!*\n\n"
        "Perfeito, amor! Recebi seu comprovante e vou verificar agora mesmo.\n\n"
        "⏰ Em poucos minutos você receberá o link de acesso ao meu grupo VIP!\n\n"
        "💕 Obrigada pela paciência, amor!",
        parse_mode='Markdown'
    )
    
    # Encaminha o comprovante para você com opções de aprovação
    keyboard = [
        [InlineKeyboardButton("✅ Aprovar Acesso", callback_data=f"aprovar_{user_id}_{plano_key}")],
        [InlineKeyboardButton("❌ Rejeitar", callback_data=f"rejeitar_{user_id}_{plano_key}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Encaminha a imagem do comprovante
    if update.message.photo:
        await context.bot.send_photo(
            chat_id=SEU_USER_ID,
            photo=update.message.photo[-1].file_id,
            caption=f"📎 *COMPROVANTE RECEBIDO*\n\n"
                   f"👤 Usuário: @{username} (ID: {user_id})\n"
                   f"💎 Plano: {plano['nome']}\n"
                   f"💰 Valor: {plano['valor']}\n"
                   f"⏰ Horário: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
                   f"Clique em uma das opções abaixo:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    elif update.message.document:
        await context.bot.send_document(
            chat_id=SEU_USER_ID,
            document=update.message.document.file_id,
            caption=f"📎 *COMPROVANTE RECEBIDO*\n\n"
                   f"👤 Usuário: @{username} (ID: {user_id})\n"
                   f"💎 Plano: {plano['nome']}\n"
                   f"💰 Valor: {plano['valor']}\n"
                   f"⏰ Horário: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
                   f"Clique em uma das opções abaixo:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def processar_aprovacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa aprovação ou rejeição do pagamento"""
    query = update.callback_query
    await query.answer()
    
    data_parts = query.data.split("_")
    acao = data_parts[0]  # aprovar ou rejeitar
    user_id = int(data_parts[1])
    
    # Reconstruir a chave do plano corretamente
    # Se tiver mais partes, é porque o plano tem underscore (como 1_mes)
    plano_key = "_".join(data_parts[2:])
    
    # Verificar se a chave existe no dicionário PLANOS
    if plano_key not in PLANOS:
        await query.edit_message_text(
            f"❌ Erro: Plano '{plano_key}' não encontrado. Por favor, contate o suporte."
        )
        return
    
    plano = PLANOS[plano_key]
    
    if acao == "aprovar":
        # Adiciona ao grupo VIP
        try:
            link_convite = await context.bot.create_chat_invite_link(
                chat_id=CANAL_VIP_ID,
                member_limit=1,
                expire_date=int(time.time()) + 604800  # Expira em 7 dias
            )
            
            # Adiciona ao banco de dados
            data_expiracao = datetime.now() + timedelta(days=plano['dias'])
            conn = sqlite3.connect('vip_bot.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO usuarios_vip 
                (user_id, username, plano, data_entrada, data_expiracao, ativo) 
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (user_id, "", plano_key, datetime.now().isoformat(), data_expiracao.isoformat()))
            
            # Marca como aprovado
            cursor.execute('''
                UPDATE pagamentos_pendentes 
                SET aprovado = 1 
                WHERE user_id = ? AND plano = ?
            ''', (user_id, plano_key))
            
            conn.commit()
            conn.close()
            
            # Envia link para o usuário
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 *PAGAMENTO APROVADO!*\n\n"
                     f"Seja bem-vindo ao meu VIP, amor! 💕\n\n"
                     f"💎 Seu plano: {plano['nome']}\n"
                     f"⏰ Válido até: {data_expiracao.strftime('%d/%m/%Y')}\n\n"
                     f"🔗 *Link de acesso ao meu VIP:*\n{link_convite.invite_link}\n\n"
                     f"⚠️ *Atenção, amor:*\n"
                     f"- Este link expira em 7 dias e só pode ser usado uma vez.\n"
                     f"- Apenas você está autorizado(a) a entrar no meu canal.\n"
                     f"- Qualquer pessoa não autorizada que tentar entrar será removida automaticamente.\n\n"
                     f"✨ Aproveite todo meu conteúdo exclusivo!\n"
                     f"💕 Qualquer dúvida, é só me chamar!",
                parse_mode='Markdown'
            )
            
            # Confirma para você
            await query.edit_message_caption(
                caption=f"✅ *ACESSO APROVADO*\n\n"
                       f"👤 Usuário: ID {user_id}\n"
                       f"💎 Plano: {plano['nome']}\n"
                       f"💰 Valor: {plano['valor']}\n"
                       f"⏰ Aprovado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
                       f"📅 Expira em: {data_expiracao.strftime('%d/%m/%Y')}",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            await query.edit_message_caption(
                caption=f"❌ Erro ao aprovar acesso: {str(e)}",
                parse_mode='Markdown'
            )
    
    elif acao == "rejeitar":
        # Marca como rejeitado
        conn = sqlite3.connect('vip_bot.db')
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM pagamentos_pendentes 
            WHERE user_id = ? AND plano = ?
        ''', (user_id, plano_key))
        conn.commit()
        conn.close()
        
        # Notifica o usuário
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ *Pagamento não aprovado*\n\n"
                 "Infelizmente não consegui confirmar seu pagamento, amor.\n\n"
                 "💬 Entre em contato comigo para resolvermos esta questão.\n"
                 "🔄 Ou tente fazer um novo pagamento.",
            parse_mode='Markdown'
        )
        
        # Confirma para você
        await query.edit_message_caption(
            caption=f"❌ *ACESSO REJEITADO*\n\n"
                   f"👤 Usuário: ID {user_id}\n"
                   f"💎 Plano: {plano['nome']}\n"
                   f"⏰ Rejeitado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            parse_mode='Markdown'
        )

async def listar_usuarios(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista usuários VIP ativos"""
    if update.effective_user.id != SEU_USER_ID:
        return
    
    conn = sqlite3.connect('vip_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM usuarios_vip WHERE ativo = 1 ORDER BY data_expiracao')
    usuarios = cursor.fetchall()
    conn.close()
    
    if not usuarios:
        await update.message.reply_text("📋 Nenhum usuário VIP ativo no momento.")
        return
    
    texto = "📋 *USUÁRIOS VIP ATIVOS*\n\n"
    for usuario in usuarios:
        user_id, username, plano, data_entrada, data_expiracao, ativo = usuario
        plano_info = PLANOS[plano]
        data_exp = datetime.fromisoformat(data_expiracao)
        dias_restantes = (data_exp - datetime.now()).days
        
        texto += f"👤 ID: {user_id}\n"
        texto += f"💎 Plano: {plano_info['nome']}\n"
        texto += f"📅 Expira em: {data_exp.strftime('%d/%m/%Y')}\n"
        texto += f"⏰ Dias restantes: {dias_restantes}\n\n"
    
    # Adiciona instruções para remover usuários
    texto += "\n💡 *Para remover um usuário, use:*\n"
    texto += "/remover ID_DO_USUARIO"
    
    await update.message.reply_text(texto, parse_mode='Markdown')

def remover_usuarios_expirados():
    """Remove usuários expirados do grupo VIP"""
    conn = sqlite3.connect('vip_bot.db')
    cursor = conn.cursor()
    
    # Busca usuários expirados
    cursor.execute('''
        SELECT user_id, username, plano, data_expiracao 
        FROM usuarios_vip 
        WHERE ativo = 1 AND data_expiracao < ?
    ''', (datetime.now().isoformat(),))
    
    usuarios_expirados = cursor.fetchall()
    
    for usuario in usuarios_expirados:
        user_id, username, plano, data_expiracao = usuario
        
        try:
            # Remove do grupo VIP
            # Note: Para remover usuários, o bot precisa ser admin do canal
            # bot.kick_chat_member(CANAL_VIP_ID, user_id)
            
            # Marca como inativo no banco
            cursor.execute('''
                UPDATE usuarios_vip 
                SET ativo = 0 
                WHERE user_id = ?
            ''', (user_id,))
            
            logger.info(f"Usuário {user_id} removido por expiração")
            
        except Exception as e:
            logger.error(f"Erro ao remover usuário {user_id}: {e}")
    
    conn.commit()
    conn.close()

def verificacao_automatica():
    """Thread para verificação automática de usuários expirados"""
    while True:
        try:
            remover_usuarios_expirados()
            time.sleep(3600)  # Verifica a cada hora
        except Exception as e:
            logger.error(f"Erro na verificação automática: {e}")
            time.sleep(300)  # Aguarda 5 minutos em caso de erro

async def remover_usuario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove um usuário específico do canal VIP"""
    # Verifica se é o administrador
    if update.effective_user.id != SEU_USER_ID:
        return
    
    # Verifica se o ID do usuário foi fornecido
    if not context.args:
        await update.message.reply_text(
            "❌ *Erro: ID do usuário não fornecido*\n\n"
            "Use o comando assim: /remover ID_DO_USUARIO",
            parse_mode='Markdown'
        )
        return
    
    try:
        # Obtém o ID do usuário a ser removido
        user_id = int(context.args[0])
        
        # Verifica se o usuário existe no banco de dados
        conn = sqlite3.connect('vip_bot.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM usuarios_vip WHERE user_id = ? AND ativo = 1', (user_id,))
        usuario = cursor.fetchone()
        
        if not usuario:
            await update.message.reply_text(
                f"❌ *Erro: Usuário {user_id} não encontrado ou já está inativo*",
                parse_mode='Markdown'
            )
            conn.close()
            return
        
        # Remove o usuário do canal VIP
        try:
            # Bane e depois desbane para remover do canal
            try:
                await context.bot.ban_chat_member(CANAL_VIP_ID, user_id)
                await context.bot.unban_chat_member(CANAL_VIP_ID, user_id)
                logger.info(f"Usuário {user_id} removido do canal com sucesso")
            except Exception as e:
                logger.error(f"Erro ao remover usuário {user_id} do canal: {e}")
                # Continua mesmo se falhar a remoção do canal
            
            # Atualiza o status no banco de dados
            cursor.execute('UPDATE usuarios_vip SET ativo = 0 WHERE user_id = ?', (user_id,))
            conn.commit()
            logger.info(f"Status do usuário {user_id} atualizado no banco de dados")
            
            # Notifica o usuário sobre a remoção
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="⚠️ *Seu acesso ao canal VIP foi revogado*\n\n"
                         "Seu acesso ao conteúdo VIP foi encerrado pelo administrador.\n\n"
                         "Para mais informações, entre em contato com o suporte.",
                    parse_mode='Markdown'
                )
                logger.info(f"Usuário {user_id} notificado sobre a remoção")
            except Exception as e:
                logger.error(f"Erro ao notificar usuário {user_id}: {e}")
            
            # Confirma a remoção para o administrador
            await update.message.reply_text(
                f"✅ *Usuário {user_id} removido com sucesso!*\n\n"
                f"O usuário foi removido do canal VIP e seu status foi atualizado no banco de dados.",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            await update.message.reply_text(
                f"⚠️ *Erro ao remover usuário:* {e}\n\n"
                f"Verifique se o bot é administrador do canal com permissões para remover membros.",
                parse_mode='Markdown'
            )
        
        conn.close()
        
    except ValueError:
        await update.message.reply_text(
            "❌ *Erro: ID do usuário inválido*\n\n"
            "O ID do usuário deve ser um número inteiro.",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ *Erro ao processar o comando:* {e}",
            parse_mode='Markdown'
        )

async def verificar_usuario_autorizado(user_id):
    """Verifica se um usuário está autorizado a acessar o canal VIP"""
    conn = sqlite3.connect('vip_bot.db')
    cursor = conn.cursor()
    
    # Verifica se o usuário existe e está ativo no banco de dados
    cursor.execute('SELECT * FROM usuarios_vip WHERE user_id = ? AND ativo = 1', (user_id,))
    usuario = cursor.fetchone()
    
    conn.close()
    return usuario is not None

async def remover_usuario_nao_autorizado(user_id, bot):
    """Remove um usuário não autorizado do canal VIP"""
    try:
        # Bane e depois desbane para remover do canal
        await bot.ban_chat_member(CANAL_VIP_ID, user_id)
        await bot.unban_chat_member(CANAL_VIP_ID, user_id)
        logger.info(f"Usuário não autorizado {user_id} removido do canal automaticamente")
        
        # Notifica o usuário sobre a remoção
        try:
            await bot.send_message(
                chat_id=user_id,
                text="⚠️ *Acesso não autorizado*\n\n"
                     "Você foi removido do meu canal VIP porque seu acesso não foi autorizado.\n\n"
                     "Para obter acesso, você precisa adquirir um dos meus planos VIP através do bot.\n"
                     "Use o comando /start para iniciar o processo de compra.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Erro ao notificar usuário não autorizado {user_id}: {e}")
        
        # Notifica o administrador
        await bot.send_message(
            chat_id=SEU_USER_ID,
            text=f"🚫 *Usuário não autorizado removido*\n\n"
                 f"O usuário com ID {user_id} tentou acessar o canal VIP sem autorização e foi removido automaticamente.",
            parse_mode='Markdown'
        )
        
        return True
    except Exception as e:
        logger.error(f"Erro ao remover usuário não autorizado {user_id}: {e}")
        return False

async def verificar_novo_membro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verifica se um novo membro do canal está autorizado"""
    # Verifica se é um evento de novo membro no canal VIP
    if update.chat_member and str(update.chat_member.chat.id) == CANAL_VIP_ID:
        if update.chat_member.new_chat_member.status in ["member", "restricted"]:
            user_id = update.chat_member.new_chat_member.user.id
            
            # Ignora o administrador e o próprio bot
            if user_id == SEU_USER_ID or user_id == context.bot.id:
                return
            
            logger.info(f"Novo membro detectado no canal VIP: {user_id}")
            
            # Verifica se o usuário está autorizado
            autorizado = await verificar_usuario_autorizado(user_id)
            
            if not autorizado:
                logger.warning(f"Usuário não autorizado detectado no canal: {user_id}")
                await remover_usuario_nao_autorizado(user_id, context.bot)

def keep_alive():
    """Função para manter o serviço ativo no Render"""
    # URL do próprio serviço
    host_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:8080')
    
    while True:
        try:
            # Faz uma requisição para o próprio serviço a cada 30 segundos
            urllib.request.urlopen(host_url)
            logger.info("Keep-alive ping enviado")
        except Exception as e:
            logger.error(f"Erro no keep-alive: {e}")
        
        # Aguarda 30 segundos antes do próximo ping
        time.sleep(30)

class KeepAliveHandler(http.server.SimpleHTTPRequestHandler):
    """Handler para o servidor HTTP de keep-alive"""
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Bot is running!')
        return

def start_keep_alive_server():
    """Inicia o servidor HTTP para keep-alive"""
    port = int(os.environ.get('PORT', 8080))
    handler = KeepAliveHandler
    
    with socketserver.TCPServer(("", port), handler) as httpd:
        logger.info(f"Servidor keep-alive iniciado na porta {port}")
        httpd.serve_forever()

def main():
    """Função principal do bot"""
    # Inicializa o banco de dados
    init_db()
    
    # Cria a aplicação com configurações para evitar conflitos
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("usuarios", listar_usuarios))
    application.add_handler(CommandHandler("remover", remover_usuario))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(handle_idade, pattern="^idade_"))
    application.add_handler(CallbackQueryHandler(mostrar_planos, pattern="^ver_planos$"))
    application.add_handler(CallbackQueryHandler(detalhes_plano, pattern="^plano_"))
    application.add_handler(CallbackQueryHandler(gerar_pix, pattern="^gerar_pix_"))
    application.add_handler(CallbackQueryHandler(copiar_pix, pattern="^copiar_pix_"))
    application.add_handler(CallbackQueryHandler(ja_paguei, pattern="^ja_paguei_"))
    application.add_handler(CallbackQueryHandler(solicitar_comprovante, pattern="^enviar_comprovante$"))
    application.add_handler(CallbackQueryHandler(processar_aprovacao, pattern="^(aprovar|rejeitar)_"))
    
    # Handler para receber comprovantes (imagens e documentos)
    application.add_handler(MessageHandler(
        filters.PHOTO | filters.Document.IMAGE, 
        receber_comprovante
    ))
    
    # Adiciona o handler para verificar novos membros no canal
    application.add_handler(ChatMemberHandler(verificar_novo_membro, ChatMemberHandler.CHAT_MEMBER))
    
    # Inicia thread de verificação automática
    thread_verificacao = threading.Thread(target=verificacao_automatica, daemon=True)
    thread_verificacao.start()
    
    # Inicia o servidor HTTP para keep-alive
    server_thread = threading.Thread(target=start_keep_alive_server, daemon=True)
    server_thread.start()
    
    # Inicia thread de keep-alive para fazer auto-ping
    keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
    keep_alive_thread.start()
    
    # Inicia o bot
    logger.info("Bot iniciado! Pressione Ctrl+C para parar.")
    return application

if __name__ == '__main__':
    # Configuração para evitar conflitos de múltiplas instâncias
    try:
        # Cria e inicia a aplicação
        app = main()
        # Usa drop_pending_updates para evitar processamento de mensagens antigas
        app.run_polling(
            drop_pending_updates=True, 
            allowed_updates=["message", "callback_query", "chat_member"]
        )
    except telegram.error.Conflict:
        logger.error("Conflito detectado: outra instância do bot já está em execução.")
        logger.info("Tentando reiniciar com configurações diferentes...")
        # Tenta novamente com configurações diferentes
        app = main()
        app.run_polling(
            drop_pending_updates=True, 
            allowed_updates=["message", "callback_query", "chat_member"]
        )
    except Exception as e:
        logger.error(f"Erro ao iniciar o bot: {e}")
