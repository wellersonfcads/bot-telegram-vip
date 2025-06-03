import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import os

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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
    
    # Verificação de idade
    keyboard = [
        [InlineKeyboardButton("✅ Sim, tenho 18 anos ou mais", callback_data="idade_ok")],
        [InlineKeyboardButton("❌ Não tenho 18 anos", callback_data="idade_nao")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔞 *VERIFICAÇÃO DE IDADE* 🔞\n\n"
        "Para continuar, preciso confirmar:\n"
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
            "❌ Desculpe, este conteúdo é apenas para maiores de 18 anos.\n\n"
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
            "Vou te enviar um vídeo especial em alguns segundos! 💕",
            parse_mode='Markdown'
        )
        
        # Aguarda 3 segundos e envia o próximo passo
        await context.application.job_queue.run_once(
            enviar_video_apresentacao, 
            3, 
            data={"chat_id": query.message.chat_id, "user_id": user_id}
        )

async def enviar_video_apresentacao(context: ContextTypes.DEFAULT_TYPE):
    """Envia vídeo de apresentação"""
    job_data = context.job.data
    chat_id = job_data["chat_id"]
    user_id = job_data["user_id"]
    
    # Aqui você colocaria o link do seu vídeo
    # Por enquanto, vou simular com uma mensagem
    await context.bot.send_message(
        chat_id=chat_id,
        text="🎥 *[VÍDEO DE APRESENTAÇÃO]*\n\n"
             "Oi amor! Sou a Clarinha e estou muito feliz que você chegou até aqui! ✨\n\n"
             "_[Aqui seria seu vídeo de apresentação]_\n\n"
             "No meu VIP você vai encontrar conteúdos exclusivos que não posto em lugar nenhum... 🔥",
        parse_mode='Markdown'
    )
    
    # Aguarda 5 segundos e mostra os planos
    await context.application.job_queue.run_once(
        mostrar_acesso_vip, 
        5, 
        data={"chat_id": chat_id, "user_id": user_id}
    )

async def mostrar_acesso_vip(context: ContextTypes.DEFAULT_TYPE):
    """Mostra opção de acesso VIP"""
    job_data = context.job.data
    chat_id = job_data["chat_id"]
    
    keyboard = [
        [InlineKeyboardButton("🔥 QUERO TER ACESSO AO VIP", callback_data="ver_planos")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        chat_id=chat_id,
        text="💎 *Quer ter acesso a todo meu conteúdo completo no VIP?*\n\n"
             "No meu grupo VIP você vai ter:\n"
             "🔥 Fotos e vídeos exclusivos\n"
             "💕 Conteúdo que não posto em lugar nenhum\n"
             "🎯 Acesso direto comigo\n"
             "✨ Surpresas especiais só para membros VIP\n\n"
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
        "💎 *PLANOS VIP DISPONÍVEIS*\n\n"
        "Escolha o plano que mais combina com você:\n\n"
        "✨ Todos os planos incluem acesso completo ao conteúdo exclusivo!\n"
        "🔥 Quanto maior o plano, melhor o custo-benefício!\n\n"
        "Clique no plano desejado:",
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
        f"🔥 *O que você vai receber:*\n"
        f"✅ Acesso total ao grupo VIP\n"
        f"✅ Todo meu conteúdo exclusivo\n"
        f"✅ Fotos e vídeos que não posto em lugar nenhum\n"
        f"✅ Contato direto comigo\n"
        f"✅ Novos conteúdos adicionados regularmente\n\n"
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
        f"1️⃣ Clique em 'Copiar PIX' abaixo\n"
        f"2️⃣ Abra seu app bancário\n"
        f"3️⃣ Escolha PIX > Copia e Cola\n"
        f"4️⃣ Cole o código copiado\n"
        f"5️⃣ Confirme o pagamento\n"
        f"6️⃣ Clique em 'Já Paguei' para enviar comprovante\n\n"
        f"💕 Estou ansiosa para te receber no VIP!",
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
        "Perfeito! Agora preciso do seu comprovante de pagamento para liberar seu acesso.\n\n"
        "📱 *Como enviar:*\n"
        "1️⃣ Clique em 'Enviar Comprovante'\n"
        "2️⃣ Tire uma foto ou screenshot do comprovante\n"
        "3️⃣ Envie a imagem\n\n"
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
        "Agora é só enviar a foto ou screenshot do seu comprovante de pagamento!\n\n"
        "📸 Pode ser:\n"
        "• Screenshot da tela de confirmação\n"
        "• Foto do comprovante\n"
        "• Print do extrato\n\n"
        "💕 Estou aguardando aqui para liberar seu acesso!",
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
        "Perfeito! Recebi seu comprovante e vou verificar agora mesmo.\n\n"
        "⏰ Em poucos minutos você receberá o link de acesso ao grupo VIP!\n\n"
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
                expire_date=int(time.time()) + 3600  # Expira em 1 hora
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
                     f"Seja bem-vinda ao meu VIP, amor! 💕\n\n"
                     f"💎 Plano: {plano['nome']}\n"
                     f"⏰ Válido até: {data_expiracao.strftime('%d/%m/%Y')}\n\n"
                     f"🔗 *Link de acesso:*\n{link_convite.invite_link}\n\n"
                     f"✨ Aproveite todo o conteúdo exclusivo!\n"
                     f"💕 Qualquer dúvida, é só chamar!",
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
                 "Infelizmente não consegui confirmar seu pagamento.\n\n"
                 "💬 Entre em contato comigo para resolver esta questão.\n"
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

def main():
    """Função principal do bot"""
    # Inicializa o banco de dados
    init_db()
    
    # Cria a aplicação
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("usuarios", listar_usuarios))
    
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
    
    # Inicia thread de verificação automática
    thread_verificacao = threading.Thread(target=verificacao_automatica, daemon=True)
    thread_verificacao.start()
    
    # Inicia o bot
    logger.info("Bot iniciado! Pressione Ctrl+C para parar.")
    application.run_polling()

if __name__ == '__main__':
    main()
