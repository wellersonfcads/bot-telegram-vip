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

# --- Configurações Lidas das Variáveis de Ambiente ---
ADMIN_ID_STR = os.environ.get('ADMIN_ID')
if ADMIN_ID_STR:
    try:
        ADMIN_ID = int(ADMIN_ID_STR)
    except ValueError:
        logger.error("ERRO CRÍTICO: A variável de ambiente ADMIN_ID não é um número inteiro válido.")
        exit(1)
else:
    logger.error("ERRO CRÍTICO: Variável de ambiente ADMIN_ID não definida.")
    exit(1)

CANAL_VIP_ID = os.environ.get('CANAL_VIP_ID')
if not CANAL_VIP_ID:
    logger.error("ERRO CRÍTICO: Variável de ambiente CANAL_VIP_ID não definida.")
    exit(1)

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    logger.error("ERRO CRÍTICO: Variável de ambiente TELEGRAM_BOT_TOKEN não definida.")
    exit(1)

# Links PIX
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
user_states = {} # Considere persistir estados críticos no DB para maior robustez

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
            "Vou te enviar um vídeo especial em alguns segundos! 💕",
            parse_mode='Markdown'
        )
        
        # Aguarda 3 segundos e envia o próximo passo
        context.application.job_queue.run_once(
            enviar_video_apresentacao, 
            3, 
            data={"chat_id": query.message.chat_id, "user_id": user_id}
        )

async def enviar_video_apresentacao(context: ContextTypes.DEFAULT_TYPE):
    """Envia vídeo de apresentação"""
    job_data = context.job.data
    chat_id = job_data["chat_id"]
    user_id = job_data["user_id"] # Não utilizado diretamente aqui, mas pode ser útil para lógica futura
    
    await context.bot.send_message(
        chat_id=chat_id,
        text="🎥 *[VÍDEO DE APRESENTAÇÃO]*\n\n"
             "Oi amor! Sou a Clarinha e estou muito feliz que você chegou até aqui! ✨\n\n"
             "_[Aqui seria seu vídeo de apresentação]_\n\n"
             "No meu VIP você vai encontrar conteúdos exclusivos que não posto em lugar nenhum... 🔥",
        parse_mode='Markdown'
    )
    
    # Aguarda 5 segundos e mostra os planos
    context.application.job_queue.run_once(
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
    if plano_key not in PLANOS:
        logger.error(f"Chave de plano inválida '{plano_key}' em detalhes_plano.")
        await query.edit_message_text("❌ Ops! Algo deu errado ao selecionar o plano. Tente novamente.")
        return
        
    plano = PLANOS[plano_key]
    
    user_id = query.from_user.id
    user_states[user_id] = {"plano_selecionado": plano_key} # Estado para saber qual plano foi selecionado
    
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
    if plano_key not in PLANOS or plano_key not in LINKS_PIX:
        logger.error(f"Chave de plano inválida '{plano_key}' em gerar_pix.")
        await query.edit_message_text("❌ Ops! Algo deu errado ao gerar o PIX. Tente novamente.")
        return

    plano = PLANOS[plano_key]
    pix_code = LINKS_PIX[plano_key]
    
    user_id = query.from_user.id
    username = query.from_user.username or "Não informado"
    
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
    
    await context.bot.send_message(
        chat_id=ADMIN_ID,
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
    # A ação de copiar é feita pelo cliente Telegram ao ver o código.
    # Este callback pode ser usado apenas para dar feedback.
    await query.answer("PIX copiado! 📋\nCole no seu app bancário na opção PIX > Copia e Cola", show_alert=True)


async def ja_paguei(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Solicita envio de comprovante"""
    query = update.callback_query
    await query.answer()
    
    plano_key = query.data.replace("ja_paguei_", "")
    user_id = query.from_user.id
    user_states[user_id] = {"aguardando_comprovante": plano_key} # Estado crucial
    
    # Não há botão "Enviar Comprovante" aqui, o bot instrui a enviar a imagem/documento diretamente.
    # Se quiser um botão, pode adicionar, mas a lógica de `solicitar_comprovante` já faz isso.
    # Vou simplificar e ir direto para a instrução de envio.
    await query.edit_message_text(
        "📎 *Envio de Comprovante*\n\n"
        "Perfeito, amor! Agora preciso do seu comprovante de pagamento para liberar seu acesso ao meu VIP.\n\n"
        "📸 *Como me enviar:*\n"
        "Envie diretamente nesta conversa a foto ou screenshot do seu comprovante.\n\n"
        "Pode ser:\n"
        "• Screenshot da tela de confirmação\n"
        "• Foto do comprovante\n"
        "• Print do extrato\n\n"
        "✅ Assim que eu verificar, vou liberar seu acesso imediatamente!\n\n"
        "💕 Obrigada pela confiança, amor!",
        # reply_markup=reply_markup, # Removido pois não há botões aqui
        parse_mode='Markdown'
    )

async def solicitar_comprovante(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manipulador para o botão 'Enviar Comprovante', apenas edita a mensagem."""
    # Esta função parece redundante se ja_paguei já instrui.
    # Se 'enviar_comprovante' for um callback de um botão, esta é a função.
    query = update.callback_query
    await query.answer()
    
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
        await update.message.reply_text("❌ Erro: Não encontrei sua solicitação de pagamento. Por favor, inicie o processo novamente com /start ou contate o suporte se já pagou.")
        return
    
    plano_key = user_states[user_id]["aguardando_comprovante"]

    if plano_key not in PLANOS:
        await update.message.reply_text("❌ Erro: Plano não reconhecido ao processar comprovante. Contate o suporte.")
        logger.error(f"Plano_key '{plano_key}' não encontrado em PLANOS ao receber comprovante do user {user_id}")
        # Limpar estado para evitar loop de erro
        if user_id in user_states:
            del user_states[user_id]
        return
    plano = PLANOS[plano_key]
    
    conn = sqlite3.connect('vip_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE pagamentos_pendentes 
        SET comprovante_enviado = 1 
        WHERE user_id = ? AND plano = ? AND aprovado = 0 
        ORDER BY id DESC LIMIT 1 
    ''', (user_id, plano_key)) # Adicionado ORDER BY e LIMIT para pegar o mais recente se houver duplicatas
    conn.commit()
    conn.close()
    
    if user_id in user_states: # Limpa o estado após o processamento
        del user_states[user_id]
    
    await update.message.reply_text(
        "✅ *Comprovante Recebido!*\n\n"
        "Perfeito, amor! Recebi seu comprovante e vou verificar agora mesmo.\n\n"
        "⏰ Em poucos minutos você receberá o link de acesso ao meu grupo VIP!\n\n"
        "💕 Obrigada pela paciência, amor!",
        parse_mode='Markdown'
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Aprovar Acesso", callback_data=f"aprovar_{user_id}_{plano_key}")],
        [InlineKeyboardButton("❌ Rejeitar", callback_data=f"rejeitar_{user_id}_{plano_key}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    caption_text = (
        f"📎 *COMPROVANTE RECEBIDO*\n\n"
        f"👤 Usuário: @{username} (ID: {user_id})\n"
        f"💎 Plano: {plano['nome']}\n"
        f"💰 Valor: {plano['valor']}\n"
        f"⏰ Horário: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        f"Clique em uma das opções abaixo:"
    )

    if update.message.photo:
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=update.message.photo[-1].file_id,
            caption=caption_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    elif update.message.document:
        await context.bot.send_document(
            chat_id=ADMIN_ID,
            document=update.message.document.file_id,
            caption=caption_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def processar_aprovacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa aprovação ou rejeição do pagamento"""
    query = update.callback_query
    await query.answer()
    
    data_parts = query.data.split("_")
    acao = data_parts[0]
    try:
        user_id_pagante = int(data_parts[1])
    except (IndexError, ValueError) as e:
        logger.error(f"Erro ao parsear user_id_pagante de callback_data '{query.data}': {e}")
        await query.edit_message_caption(caption=f"❌ Erro ao processar callback: dados inválidos. ({query.data})")
        return

    plano_key = "_".join(data_parts[2:])
    
    if plano_key not in PLANOS:
        logger.error(f"Plano '{plano_key}' não encontrado ao processar aprovação para user {user_id_pagante}.")
        await query.edit_message_caption(
            caption=f"❌ Erro: Plano '{plano_key}' não encontrado para usuário {user_id_pagante}."
        )
        return
    
    plano = PLANOS[plano_key]
    
    if acao == "aprovar":
        try:
            link_convite = await context.bot.create_chat_invite_link(
                chat_id=CANAL_VIP_ID,
                member_limit=1,
                expire_date=int(time.time()) + (7 * 24 * 60 * 60) # Expira em 7 dias
            )
            
            data_expiracao = datetime.now() + timedelta(days=plano['dias'])
            conn = sqlite3.connect('vip_bot.db')
            cursor = conn.cursor()
            
            # Tenta buscar username atual do usuário
            try:
                chat_user_pagante = await context.bot.get_chat(user_id_pagante)
                username_pagante = chat_user_pagante.username or "Não informado"
            except Exception:
                username_pagante = "Não recuperado"


            cursor.execute('''
                INSERT OR REPLACE INTO usuarios_vip 
                (user_id, username, plano, data_entrada, data_expiracao, ativo) 
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (user_id_pagante, username_pagante, plano_key, datetime.now().isoformat(), data_expiracao.isoformat()))
            
            cursor.execute('''
                UPDATE pagamentos_pendentes 
                SET aprovado = 1 
                WHERE user_id = ? AND plano = ? AND comprovante_enviado = 1 AND aprovado = 0
                ORDER BY id DESC LIMIT 1
            ''', (user_id_pagante, plano_key))
            
            conn.commit()
            conn.close()
            
            await context.bot.send_message(
                chat_id=user_id_pagante,
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
            
            await query.edit_message_caption(
                caption=f"✅ *ACESSO APROVADO*\n\n"
                        f"👤 Usuário: @{username_pagante} (ID: {user_id_pagante})\n"
                        f"💎 Plano: {plano['nome']}\n"
                        f"💰 Valor: {plano['valor']}\n"
                        f"⏰ Aprovado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
                        f"📅 Expira em: {data_expiracao.strftime('%d/%m/%Y')}",
                parse_mode='Markdown'
            )
            
        except telegram.error.TelegramError as te:
            logger.error(f"Erro Telegram ao aprovar acesso para {user_id_pagante}: {te}")
            await query.edit_message_caption(
                caption=f"❌ Erro Telegram ao aprovar acesso para {user_id_pagante}: {te}",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Erro geral ao aprovar acesso para {user_id_pagante}: {e}", exc_info=True)
            await query.edit_message_caption(
                caption=f"❌ Erro geral ao aprovar acesso para {user_id_pagante}: {e}",
                parse_mode='Markdown'
            )
    
    elif acao == "rejeitar":
        conn = sqlite3.connect('vip_bot.db')
        cursor = conn.cursor()
        # Em vez de deletar, podemos marcar como rejeitado para histórico, ou deletar se preferir.
        # Vou deletar para manter simples, como no original.
        cursor.execute('''
            DELETE FROM pagamentos_pendentes 
            WHERE user_id = ? AND plano = ? AND comprovante_enviado = 1 AND aprovado = 0
            ORDER BY id DESC LIMIT 1
        ''', (user_id_pagante, plano_key))
        conn.commit()
        conn.close()
        
        await context.bot.send_message(
            chat_id=user_id_pagante,
            text="❌ *Pagamento não aprovado*\n\n"
                 "Infelizmente não consegui confirmar seu pagamento, amor.\n\n"
                 "💬 Entre em contato comigo para resolvermos esta questão.\n"
                 "🔄 Ou tente fazer um novo pagamento.",
            parse_mode='Markdown'
        )
        
        await query.edit_message_caption(
            caption=f"❌ *ACESSO REJEITADO*\n\n"
                    f"👤 Usuário: ID {user_id_pagante}\n"
                    f"💎 Plano: {plano['nome']}\n"
                    f"⏰ Rejeitado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            parse_mode='Markdown'
        )

async def listar_usuarios(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista usuários VIP ativos"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    conn = sqlite3.connect('vip_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, plano, data_expiracao FROM usuarios_vip WHERE ativo = 1 ORDER BY data_expiracao')
    usuarios = cursor.fetchall()
    conn.close()
    
    if not usuarios:
        await update.message.reply_text("📋 Nenhum usuário VIP ativo no momento.")
        return
    
    texto = "📋 *USUÁRIOS VIP ATIVOS*\n\n"
    for usuario_data in usuarios:
        uid, uname, pkey, data_exp_iso = usuario_data
        if pkey not in PLANOS:
            logger.warning(f"Plano {pkey} do usuário {uid} não encontrado em PLANOS ao listar.")
            plano_nome = f"Plano '{pkey}' (Desconhecido)"
        else:
            plano_nome = PLANOS[pkey]['nome']

        data_exp = datetime.fromisoformat(data_exp_iso)
        dias_restantes = (data_exp - datetime.now()).days
        
        texto += f"👤 ID: {uid} (@{uname if uname else 'N/A'})\n"
        texto += f"💎 Plano: {plano_nome}\n"
        texto += f"📅 Expira em: {data_exp.strftime('%d/%m/%Y')}\n"
        texto += f"⏰ Dias restantes: {dias_restantes if dias_restantes >= 0 else 'Expirado'}\n\n"
    
    texto += "\n💡 *Para remover um usuário, use:*\n"
    texto += "/remover ID_DO_USUARIO"
    
    if len(texto) > 4096: # Limite de mensagem do Telegram
        partes = [texto[i:i+4000] for i in range(0, len(texto), 4000)] # Divide em partes menores
        for parte in partes:
            await update.message.reply_text(parte, parse_mode='Markdown')
    else:
        await update.message.reply_text(texto, parse_mode='Markdown')

# Modificado para ser um job do JobQueue
async def remover_usuarios_expirados_job(context: ContextTypes.DEFAULT_TYPE):
    """Remove usuários expirados do grupo VIP e DB (executado pelo JobQueue)"""
    logger.info("Executando job de remoção de usuários expirados...")
    conn = sqlite3.connect('vip_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT user_id, username, plano, data_expiracao 
        FROM usuarios_vip 
        WHERE ativo = 1 AND data_expiracao < ?
    ''', (datetime.now().isoformat(),))
    
    usuarios_expirados = cursor.fetchall()
    
    if not usuarios_expirados:
        logger.info("Nenhum usuário expirado encontrado.")
    
    for usuario_db in usuarios_expirados:
        user_id_exp, username_exp, _, _ = usuario_db
        try:
            logger.info(f"Tentando remover usuário expirado {user_id_exp} (@{username_exp}) do canal {CANAL_VIP_ID}")
            await context.bot.ban_chat_member(chat_id=CANAL_VIP_ID, user_id=user_id_exp)
            await context.bot.unban_chat_member(chat_id=CANAL_VIP_ID, user_id=user_id_exp) # Para remover sem banir permanentemente
            
            cursor.execute('UPDATE usuarios_vip SET ativo = 0 WHERE user_id = ?', (user_id_exp,))
            conn.commit() # Commit dentro do loop para cada usuário processado com sucesso
            logger.info(f"Usuário {user_id_exp} (@{username_exp}) removido do canal e marcado como inativo no DB.")
            
            try:
                await context.bot.send_message(
                    chat_id=user_id_exp,
                    text="😢 *Sua assinatura VIP expirou!*\n\n"
                         "Seu acesso ao meu conteúdo exclusivo foi encerrado, amor.\n"
                         "Mas não se preocupe! Você pode renovar a qualquer momento usando o comando /start.\n\n"
                         "Espero te ver de volta em breve! 💕"
                )
            except Exception as e_msg:
                logger.warning(f"Não foi possível notificar usuário {user_id_exp} sobre expiração: {e_msg}")

        except telegram.error.TelegramError as te:
            if "user not found" in str(te).lower() or "chat member not found" in str(te).lower():
                logger.warning(f"Usuário {user_id_exp} não encontrado no canal ao tentar remover por expiração (provavelmente já saiu). Marcando como inativo. Erro: {te}")
                cursor.execute('UPDATE usuarios_vip SET ativo = 0 WHERE user_id = ?', (user_id_exp,))
                conn.commit()
            else:
                logger.error(f"Erro Telegram ao remover usuário expirado {user_id_exp} do canal: {te}")
        except Exception as e:
            logger.error(f"Erro geral ao processar remoção do usuário expirado {user_id_exp}: {e}", exc_info=True)
            
    conn.close()
    logger.info("Job de remoção de usuários expirados concluído.")


async def remover_usuario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove um usuário específico do canal VIP (comando de admin)"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ *Erro: ID do usuário não fornecido*\n\n"
            "Use o comando assim: /remover ID_DO_USUARIO",
            parse_mode='Markdown'
        )
        return
    
    try:
        user_id_remover = int(context.args[0])
        
        conn = sqlite3.connect('vip_bot.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM usuarios_vip WHERE user_id = ? AND ativo = 1', (user_id_remover,))
        usuario_db = cursor.fetchone()
        
        if not usuario_db:
            await update.message.reply_text(
                f"❌ *Erro: Usuário {user_id_remover} não encontrado ou já está inativo*",
                parse_mode='Markdown'
            )
            conn.close()
            return
        
        try:
            await context.bot.ban_chat_member(CANAL_VIP_ID, user_id_remover)
            await context.bot.unban_chat_member(CANAL_VIP_ID, user_id_remover)
            logger.info(f"Admin removeu usuário {user_id_remover} do canal com sucesso")
            
            cursor.execute('UPDATE usuarios_vip SET ativo = 0 WHERE user_id = ?', (user_id_remover,))
            conn.commit()
            logger.info(f"Status do usuário {user_id_remover} atualizado para inativo no banco de dados por remoção manual.")
            
            try:
                await context.bot.send_message(
                    chat_id=user_id_remover,
                    text="⚠️ *Seu acesso ao canal VIP foi revogado*\n\n"
                         "Seu acesso ao conteúdo VIP foi encerrado pelo administrador.\n\n"
                         "Para mais informações, entre em contato com o suporte.",
                    parse_mode='Markdown'
                )
                logger.info(f"Usuário {user_id_remover} notificado sobre a remoção manual.")
            except Exception as e_msg:
                logger.warning(f"Erro ao notificar usuário {user_id_remover} sobre remoção manual: {e_msg}")
            
            await update.message.reply_text(
                f"✅ *Usuário {user_id_remover} removido com sucesso!*\n\n"
                f"O usuário foi removido do canal VIP e seu status foi atualizado no banco de dados.",
                parse_mode='Markdown'
            )
            
        except telegram.error.TelegramError as te:
             await update.message.reply_text(
                f"⚠️ *Erro Telegram ao remover usuário {user_id_remover}:* {te}\n\n"
                f"Verifique se o bot é administrador do canal com permissões para banir membros.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Erro geral ao remover usuário {user_id_remover} manualmente: {e}", exc_info=True)
            await update.message.reply_text(
                f"⚠️ *Erro geral ao remover usuário {user_id_remover}:* {e}",
                parse_mode='Markdown'
            )
        finally:
            conn.close()
            
    except ValueError:
        await update.message.reply_text(
            "❌ *Erro: ID do usuário inválido*\n\n"
            "O ID do usuário deve ser um número inteiro.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Erro ao processar comando /remover: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ *Erro ao processar o comando:* {e}",
            parse_mode='Markdown'
        )

async def verificar_usuario_autorizado(user_id_verificar):
    """Verifica se um usuário está autorizado a acessar o canal VIP"""
    conn = sqlite3.connect('vip_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM usuarios_vip WHERE user_id = ? AND ativo = 1 AND data_expiracao >= ?', 
                   (user_id_verificar, datetime.now().isoformat()))
    usuario_autorizado = cursor.fetchone()
    conn.close()
    return usuario_autorizado is not None

async def remover_usuario_nao_autorizado(user_id_remover, bot_instance: telegram.Bot):
    """Remove um usuário não autorizado do canal VIP"""
    try:
        await bot_instance.ban_chat_member(CANAL_VIP_ID, user_id_remover)
        await bot_instance.unban_chat_member(CANAL_VIP_ID, user_id_remover)
        logger.info(f"Usuário não autorizado {user_id_remover} removido do canal {CANAL_VIP_ID} automaticamente")
        
        try:
            await bot_instance.send_message(
                chat_id=user_id_remover,
                text="⚠️ *Acesso não autorizado*\n\n"
                     "Você foi removido do meu canal VIP porque seu acesso não foi autorizado ou sua assinatura expirou.\n\n"
                     "Para obter acesso, você precisa adquirir um dos meus planos VIP através do bot.\n"
                     "Use o comando /start para iniciar o processo de compra.",
                parse_mode='Markdown'
            )
        except Exception as e_msg:
            logger.warning(f"Erro ao notificar usuário não autorizado {user_id_remover}: {e_msg}")
        
        await bot_instance.send_message(
            chat_id=ADMIN_ID,
            text=f"🚫 *Usuário não autorizado removido*\n\n"
                 f"O usuário com ID {user_id_remover} tentou acessar o canal VIP {CANAL_VIP_ID} sem autorização e foi removido automaticamente.",
            parse_mode='Markdown'
        )
        return True
    except telegram.error.TelegramError as te:
        logger.error(f"Erro Telegram ao remover usuário não autorizado {user_id_remover} do canal {CANAL_VIP_ID}: {te}")
    except Exception as e:
        logger.error(f"Erro geral ao remover usuário não autorizado {user_id_remover} do canal {CANAL_VIP_ID}: {e}", exc_info=True)
    return False

async def verificar_novo_membro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verifica se um novo membro do canal está autorizado"""
    if update.chat_member and str(update.chat_member.chat.id) == str(CANAL_VIP_ID): # Comparar como string é mais seguro
        new_member_status = update.chat_member.new_chat_member.status
        user = update.chat_member.new_chat_member.user
        
        if new_member_status in [telegram.constants.ChatMemberStatus.MEMBER, telegram.constants.ChatMemberStatus.RESTRICTED]:
            user_id_novo = user.id
            
            if user_id_novo == ADMIN_ID or user_id_novo == context.bot.id:
                return
            
            logger.info(f"Novo membro detectado no canal VIP {CANAL_VIP_ID}: ID {user_id_novo} (@{user.username})")
            
            autorizado = await verificar_usuario_autorizado(user_id_novo)
            
            if not autorizado:
                logger.warning(f"Usuário NÃO AUTORIZADO detectado no canal VIP {CANAL_VIP_ID}: ID {user_id_novo} (@{user.username}). Removendo...")
                await remover_usuario_nao_autorizado(user_id_novo, context.bot)
            else:
                logger.info(f"Novo membro ID {user_id_novo} (@{user.username}) está AUTORIZADO no canal VIP {CANAL_VIP_ID}.")


def keep_alive_ping(): # Renomeado para evitar conflito com a função keep_alive do Render
    """Função para manter o serviço ativo fazendo auto-ping (se necessário)"""
    host_url = os.environ.get('RENDER_EXTERNAL_URL')
    if not host_url:
        logger.info("RENDER_EXTERNAL_URL não definida. Auto-ping desativado.")
        return

    while True:
        try:
            with urllib.request.urlopen(host_url, timeout=10) as response: # Adicionado timeout
                if response.status == 200:
                    logger.info(f"Keep-alive ping para {host_url} enviado com sucesso.")
                else:
                    logger.warning(f"Keep-alive ping para {host_url} retornou status {response.status}.")
        except Exception as e:
            logger.error(f"Erro no keep-alive ping para {host_url}: {e}")
        
        time.sleep(14 * 60) # Ping a cada 14 minutos (Render free tier sleeps after 15 min inactivity)

class KeepAliveHandler(http.server.SimpleHTTPRequestHandler):
    """Handler para o servidor HTTP de keep-alive"""
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Bot is running!')

def start_keep_alive_server():
    """Inicia o servidor HTTP para keep-alive (para Render e similares)"""
    port = int(os.environ.get('PORT', 8080)) # Render define a PORT env var
    
    # Tenta reusar o endereço para evitar problemas em reinícios rápidos
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("", port), KeepAliveHandler) as httpd:
            logger.info(f"Servidor keep-alive HTTP iniciado na porta {port}")
            httpd.serve_forever()
    except OSError as e:
        logger.error(f"Erro ao iniciar servidor keep-alive na porta {port}: {e}. A porta pode já estar em uso.")
    except Exception as e:
        logger.error(f"Exceção não esperada ao iniciar servidor keep-alive: {e}", exc_info=True)


def main():
    """Função principal do bot"""
    init_db()
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Handlers de Comando
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("usuarios", listar_usuarios))
    application.add_handler(CommandHandler("remover", remover_usuario))
    
    # Handlers de CallbackQuery
    application.add_handler(CallbackQueryHandler(handle_idade, pattern="^idade_"))
    application.add_handler(CallbackQueryHandler(mostrar_planos, pattern="^ver_planos$"))
    application.add_handler(CallbackQueryHandler(detalhes_plano, pattern="^plano_"))
    application.add_handler(CallbackQueryHandler(gerar_pix, pattern="^gerar_pix_"))
    application.add_handler(CallbackQueryHandler(copiar_pix, pattern="^copiar_pix_"))
    application.add_handler(CallbackQueryHandler(ja_paguei, pattern="^ja_paguei_"))
    application.add_handler(CallbackQueryHandler(solicitar_comprovante, pattern="^enviar_comprovante$")) # Se ainda usar este botão
    application.add_handler(CallbackQueryHandler(processar_aprovacao, pattern="^(aprovar|rejeitar)_"))
    
    # Handler para receber comprovantes (imagens e documentos que podem ser imagens)
    application.add_handler(MessageHandler(
        filters.PHOTO | filters.Document.IMAGE, 
        receber_comprovante
    ))
    
    # Handler para verificar novos membros no canal
    application.add_handler(ChatMemberHandler(verificar_novo_membro, ChatMemberHandler.CHAT_MEMBER))
    
    # JobQueue para tarefas agendadas
    job_queue = application.job_queue
    # Executa a cada hora (3600s), começando 10s após o bot iniciar.
    job_queue.run_repeating(remover_usuarios_expirados_job, interval=3600, first=10) 
    
    # Inicia o servidor HTTP para keep-alive em uma thread separada
    # Isso é necessário para que o bot continue rodando e respondendo
    if os.environ.get('RENDER'): # Inicia o servidor HTTP apenas se estiver no Render (ou similar que precise)
        server_thread = threading.Thread(target=start_keep_alive_server, daemon=True)
        server_thread.start()

        # O auto-ping é opcional se a plataforma já pinga o servidor HTTP exposto.
        # Se RENDER_EXTERNAL_URL estiver definida, o ping pode ser uma garantia extra.
        if os.environ.get('RENDER_EXTERNAL_URL'):
            keep_alive_ping_thread = threading.Thread(target=keep_alive_ping, daemon=True)
            keep_alive_ping_thread.start()
    
    logger.info("Bot iniciado! Pressione Ctrl+C para parar.")
    return application

if __name__ == '__main__':
    try:
        app = main()
        # allowed_updates especifica quais tipos de updates seu bot vai processar
        app.run_polling(
            drop_pending_updates=True, 
            allowed_updates=Update.ALL_TYPES # Ou especifique os tipos que você realmente precisa
        )
    except telegram.error.Conflict:
        logger.error("Conflito detectado: outra instância do bot já está em execução. Verifique se não há outro processo rodando.")
    except Exception as e:
        logger.error(f"Erro fatal ao iniciar ou executar o bot: {e}", exc_info=True)
