import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, constants as TGConstants
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ChatMemberHandler, filters, ContextTypes, Job
from telegram.constants import ParseMode
import os
import http.server
import socketserver
import urllib.request
import asyncio
import html

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.WARNING)

# --- Configurações Lidas das Variáveis de Ambiente ---
ADMIN_ID_STR = os.environ.get('ADMIN_ID')
if ADMIN_ID_STR:
    try:
        ADMIN_ID = int(ADMIN_ID_STR)
    except ValueError:
        logger.critical("ERRO CRÍTICO: A variável de ambiente ADMIN_ID não é um número inteiro válido.")
        exit(1)
else:
    logger.critical("ERRO CRÍTICO: Variável de ambiente ADMIN_ID não definida.")
    exit(1)

CANAL_VIP_ID = os.environ.get('CANAL_VIP_ID')
if not CANAL_VIP_ID:
    logger.critical("ERRO CRÍTICO: Variável de ambiente CANAL_VIP_ID não definida.")
    exit(1)

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    logger.critical("ERRO CRÍTICO: Variável de ambiente TELEGRAM_BOT_TOKEN não definida.")
    exit(1)

# Links PIX (CORRIGIDOS)
LINKS_PIX = {
    "1_mes": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540539.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***63044086",
    "3_meses": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540599.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***63041E24",
    "6_meses": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406179.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***63043084",
    "12_meses": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406289.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***6304CD13"
}

# Planos e valores
PLANOS = {
    "1_mes": {"nome": "Plano VIP 1 mês", "valor": "R$ 39,90", "dias": 30},
    "3_meses": {"nome": "Plano VIP 3 meses", "valor": "R$ 99,90", "dias": 90},
    "6_meses": {"nome": "Plano VIP 6 meses", "valor": "R$ 179,90", "dias": 180},
    "12_meses": {"nome": "Plano VIP 12 meses", "valor": "R$ 289,90", "dias": 365}
}
user_states = {}

# Constantes para nomes/prefixos de jobs de lembrete
JOB_LEMBRETE_IDADE_PREFIX = "lembrete_idade_user_"
JOB_LEMBRETE_PLANOS_PREFIX = "lembrete_planos_user_"
JOB_LEMBRETE_DETALHES_PREFIX = "lembrete_detalhes_user_"
JOB_LEMBRETE_PIX_GERADO_PREFIX = "lembrete_pix_gerado_user_"


def init_db():
    with sqlite3.connect('vip_bot.db', timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios_vip (
                user_id INTEGER PRIMARY KEY, username TEXT, plano TEXT,
                data_entrada TEXT, data_expiracao TEXT, ativo INTEGER DEFAULT 1
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pagamentos_pendentes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT,
                plano TEXT, valor TEXT, data_solicitacao TEXT,
                comprovante_enviado INTEGER DEFAULT 0, aprovado INTEGER DEFAULT 0
            )
        ''')
        conn.commit()

def escape_markdown_v2(text: str) -> str:
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return "".join(f"\\{char}" if char in escape_chars else char for char in text)

def remover_jobs_lembrete_anteriores(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    if user_id in user_states and isinstance(user_states[user_id], dict) and 'pending_reminder_jobs' in user_states[user_id]:
        current_jobs = user_states[user_id].get('pending_reminder_jobs', [])
        if current_jobs:
            logger.info(f"Tentando remover {len(current_jobs)} jobs de lembrete pendentes para user {user_id}.")
            for job_obj in current_jobs:
                if job_obj and isinstance(job_obj, Job):
                    try:
                        job_obj.schedule_removal()
                    except Exception as e_remove:
                        if "No job by the id of" not in str(e_remove).lower() and \
                           "Job has already been removed" not in str(e_remove).lower() and \
                           "trigger has been changed" not in str(e_remove).lower() and \
                           "job has already been scheduled for removal" not in str(e_remove).lower() :
                            logger.warning(f"Erro inesperado ao tentar remover job {job_obj.name}: {e_remove}")
            user_states[user_id]['pending_reminder_jobs'] = []
    elif user_id in user_states:
        logger.warning(f"Estrutura de user_states[{user_id}] inesperada ao tentar remover jobs: {user_states[user_id]}")


async def callback_lembrete(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    if not job or not job.data:
        logger.warning("Job de lembrete sem dados.")
        return

    chat_id = job.data.get("chat_id")
    user_id = job.data.get("user_id")
    estado_esperado_no_job = job.data.get("contexto_job")
    delay = job.data.get("delay")
    plano_key_lembrete = job.data.get("plano_key")
    # Novo: obter o ID da mensagem anterior a ser deletada
    msg_id_para_deletar = job.data.get("previous_message_id")

    if not all([chat_id, user_id, estado_esperado_no_job, delay]):
        logger.error(f"Dados incompletos no job de lembrete: {job.data} para user {user_id}")
        return

    estado_atual_usuario_info = user_states.get(user_id, {})
    estado_atual_usuario = estado_atual_usuario_info.get("state")

    if estado_atual_usuario != estado_esperado_no_job:
        logger.info(f"Lembrete {delay} para user {user_id} no contexto '{estado_esperado_no_job}' ignorado. Estado atual: '{estado_atual_usuario}'.")
        return

    logger.info(f"Executando lembrete {delay} para user {user_id} no contexto '{estado_esperado_no_job}'.")
    
    # --- NOVO: Deletar a mensagem anterior ---
    if msg_id_para_deletar:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id_para_deletar)
            logger.info(f"Mensagem anterior (ID: {msg_id_para_deletar}) deletada para user {user_id} antes de enviar novo lembrete.")
        except Exception as e:
            logger.warning(f"Não foi possível deletar mensagem de lembrete anterior (ID: {msg_id_para_deletar}): {e}")

    mensagem = ""
    keyboard_lembrete = None
    sent_reminder_message = None

    if estado_esperado_no_job == "aguardando_verificacao_idade":
        if delay == "1min_idade":
            mensagem = "Oi, amor\\! 😊 Notei que você ainda não confirmou sua idade\\. Para continuar e ter acesso a todas as surpresas que preparei, preciso dessa confirmação rapidinho\\! Clique abaixo se tiver 18 anos ou mais\\. 😉"
        elif delay == "5min_idade":
            mensagem = "Psst\\! 🔥 A curiosidade tá batendo aí, né? Eu sei como é\\! Confirme que tem mais de 18 para não ficar de fora do que realmente interessa\\! 😉"
        elif delay == "10min_idade":
            mensagem = "Amor, o tempo está passando e você está perdendo a chance de me conhecer melhor\\! 🔞 Se você tem 18 anos ou mais, é só um clique para começar a diversão\\! Não vai se arrepender\\! 😘"
        
        if mensagem:
            keyboard_lembrete = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Sim, tenho 18 anos ou mais", callback_data="idade_ok")],
                [InlineKeyboardButton("❌ Não tenho 18 anos", callback_data="idade_nao")]
            ])

    # ... (outros elif para visualizando_planos, visualizando_detalhes_)
    elif estado_esperado_no_job == "visualizando_planos":
        if delay == "1min":
            mensagem = "Ei, vi que você está de olho nos meus planos VIP 👀\\! Qual deles chamou mais sua atenção, amor? Não perca tempo, o conteúdo exclusivo te espera\\! 🔥"
        elif delay == "5min":
            mensagem = "Psst\\! Só passando para lembrar que os planos VIP estão com uma oferta imperdível e o acesso é imediato após a confirmação\\! 😉 Que tal dar uma olhadinha de novo?"
        elif delay == "10min":
            mensagem = "Amor, essa pode ser sua última chance de garantir acesso ao meu paraíso particular com condições especiais\\! ✨ Escolha seu plano e venha se divertir comigo\\! 🔞"
        
        if mensagem:
            keyboard_lembrete = InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Ver Planos Novamente", callback_data="ver_planos")]
            ])
    
    elif estado_esperado_no_job.startswith("visualizando_detalhes_"):
        if plano_key_lembrete and plano_key_lembrete in PLANOS:
            plano_nome = PLANOS[plano_key_lembrete]['nome']
            plano_nome_escapado = escape_markdown_v2(plano_nome)
            if delay == "1min":
                mensagem = f"Percebi que você curtiu o *{plano_nome_escapado}*, hein? 😉 Ele é incrível mesmo\\! Que tal gerar o PIX agora e garantir seu lugarzinho no céu? 🔞"
            elif delay == "5min":
                mensagem = f"Amor, o *{plano_nome_escapado}* está te esperando\\! Imagina só todo o conteúdo que você vai ter acesso\\.\\.\\. Não deixe para depois o que pode te dar prazer agora\\! 🔥"
            elif delay == "10min":
                mensagem = f"Última chamada para o paraíso com o *{plano_nome_escapado}*\\! 🚀 Clique em 'Gerar PIX' e venha matar sua curiosidade\\.\\.\\. prometo que vale a pena\\! 😏"
            
            if mensagem:
                keyboard_lembrete = InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"💳 Gerar PIX para {PLANOS[plano_key_lembrete]['nome']}", callback_data=f"gerar_pix_{plano_key_lembrete}")],
                    [InlineKeyboardButton("⬅️ Ver Outros Planos", callback_data="ver_planos")]
                ])
        else:
            logger.warning(f"Chave de plano inválida '{plano_key_lembrete}' no callback_lembrete para detalhes.")
            return
            
    elif estado_esperado_no_job.startswith("gerou_pix_"):
        if plano_key_lembrete and plano_key_lembrete in PLANOS:
            plano_nome_escapado = escape_markdown_v2(PLANOS[plano_key_lembrete]['nome'])
            if delay == "1min_pix":
                mensagem = f"Amor, seu PIX para o *{plano_nome_escapado}* foi gerado com sucesso\\! 🎉 Agora é só pagar e me enviar o comprovante para liberar seu acesso total\\! Estou te esperando\\! 😉"
            elif delay == "5min_pix":
                mensagem = f"Só um lembrete carinhoso, seu PIX para o *{plano_nome_escapado}* ainda está aguardando o pagamento\\. Não perca a chance de entrar no meu mundo exclusivo\\! 🔥"
            elif delay == "10min_pix":
                mensagem = f"Última chamada, amor\\! Seu acesso ao *{plano_nome_escapado}* está quase lá\\. Faça o pagamento do PIX e me envie o comprovante para não ficar de fora da diversão\\! 😈"
            
            if mensagem:
                keyboard_lembrete = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Já Paguei - Enviar Comprovante", callback_data=f"ja_paguei_{plano_key_lembrete}")],
                    [InlineKeyboardButton("📋 Ver PIX Novamente", callback_data=f"gerar_pix_{plano_key_lembrete}")]
                ])
        else:
            logger.warning(f"Chave de plano inválida '{plano_key_lembrete}' no callback_lembrete para PIX gerado.")
            return

    if mensagem:
        try:
            sent_reminder_message = await context.bot.send_message(
                chat_id=chat_id,
                text=mensagem,
                reply_markup=keyboard_lembrete,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            # Armazena o ID da nova mensagem de lembrete no estado do usuário
            # para que o PRÓXIMO lembrete possa deletá-la.
            if user_id in user_states and isinstance(user_states[user_id], dict):
                user_states[user_id]['last_reminder_message_id'] = sent_reminder_message.message_id
                logger.info(f"Lembrete {delay} (MsgID: {sent_reminder_message.message_id}) enviado e ID armazenado para user {user_id}.")

        except telegram.error.BadRequest as br_err:
            logger.error(f"BadRequest ao enviar lembrete {delay} para user {user_id}: {br_err}", exc_info=True)
        except Exception as e:
            logger.error(f"Erro geral ao enviar lembrete {delay} para user {user_id}: {e}", exc_info=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    remover_jobs_lembrete_anteriores(user_id, context)
    
    if user_id not in user_states or not isinstance(user_states.get(user_id), dict):
        user_states[user_id] = {}
    
    user_states[user_id].update({
        "state": "aguardando_verificacao_idade",
        "pending_reminder_jobs": [],
        # "age_verification_message_ids" não é mais necessário, usaremos last_reminder_message_id
        "last_reminder_message_id": None
    })
    logger.info(f"[START] User {user_id} iniciou. Estado definido para 'aguardando_verificacao_idade'.")

    keyboard = [
        [InlineKeyboardButton("✅ Sim, tenho 18 anos ou mais", callback_data="idade_ok")],
        [InlineKeyboardButton("❌ Não tenho 18 anos", callback_data="idade_nao")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    texto_start = (
        "🔞 *VERIFICAÇÃO DE IDADE* 🔞\n\n"
        "Oi amor\\! Antes de continuarmos, preciso confirmar:\n"
        "Você tem 18 anos ou mais?"
    )
    try:
        sent_message = await update.message.reply_text(
            texto_start,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        if sent_message and user_id in user_states and isinstance(user_states[user_id], dict):
            user_states[user_id]['last_reminder_message_id'] = sent_message.message_id
            logger.info(f"[START] Mensagem inicial de verificação (MsgID: {sent_message.message_id}) enviada e ID armazenado para user {user_id}.")

    except Exception as e:
        logger.error(f"[START] Erro ao enviar mensagem inicial para user {user_id}: {e}", exc_info=True)
        return

    job_context_name_base = f"{JOB_LEMBRETE_IDADE_PREFIX}{user_id}"
    
    # ATENÇÃO: Delays para PRODUÇÃO (1min, 5min, 10min). Mude para valores menores para TESTE rápido (ex: 10, 20, 30).
    delays_lembrete = {"1min_idade": 1*60, "5min_idade": 5*60, "10min_idade": 10*60}

    jobs_agendados = []
    # MODIFICADO: Passar o ID da mensagem anterior para o próximo job
    previous_msg_id = user_states[user_id]['last_reminder_message_id']
    for delay_tag, delay_seconds in delays_lembrete.items():
        job_data = {
            "chat_id": chat_id,
            "user_id": user_id,
            "contexto_job": "aguardando_verificacao_idade",
            "delay": delay_tag,
            "previous_message_id": previous_msg_id
        }
        job = context.application.job_queue.run_once(
            callback_lembrete,
            delay_seconds,
            data=job_data,
            name=f"{job_context_name_base}_{delay_tag}"
        )
        jobs_agendados.append(job)
        # O ID da mensagem para o *próximo* job será o ID da mensagem que este job *vai* criar.
        # No entanto, não sabemos o ID da mensagem futura. A lógica de deletar no início do callback é mais simples.
    
    if user_id in user_states and isinstance(user_states[user_id], dict):
        user_states[user_id]['pending_reminder_jobs'] = jobs_agendados
    else:
        logger.warning(f"Estado para user {user_id} não era um dicionário ou não existia ao tentar armazenar jobs de lembrete de idade. Cancelando jobs.")
        for job_obj in jobs_agendados:
            if job_obj: job_obj.schedule_removal()

async def handle_idade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id if query.message else user_id
    if not chat_id:
        chat_id = user_id
        logger.warning(f"[HANDLE_IDADE] query.message é None para user {user_id}. Usando user_id como chat_id.")

    logger.info(f"[HANDLE_IDADE] Triggered. User: {user_id}, Data: {query.data}, Message ID: {query.message.message_id if query.message else 'N/A'}")
    await query.answer()
    
    # Remover jobs de lembrete futuros
    remover_jobs_lembrete_anteriores(user_id, context)
    
    # Deletar a última mensagem de verificação de idade que está na tela (que não é a que foi clicada)
    if user_id in user_states and isinstance(user_states.get(user_id), dict):
        last_msg_id = user_states[user_id].get('last_reminder_message_id')
        if last_msg_id and query.message and last_msg_id != query.message.message_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=last_msg_id)
                logger.info(f"Última mensagem de verificação (ID: {last_msg_id}) deletada para user {user_id}.")
            except Exception as e:
                logger.warning(f"Não foi possível deletar última mensagem de verificação (ID: {last_msg_id}): {e}")

        # Limpa o estado relacionado
        user_states[user_id].pop('last_reminder_message_id', None)

    if query.data == "idade_nao":
        texto_idade_nao = (
            "❌ Desculpe amor, meu conteúdo é apenas para maiores de 18 anos\\.\n\n"
            "Volte quando completar 18 anos\\! 😊"
        )
        try:
            if query.message:
                await query.edit_message_text(text=texto_idade_nao, parse_mode=ParseMode.MARKDOWN_V2)
        except telegram.error.BadRequest as e:
            logger.warning(f"Não foi possível editar mensagem 'idade_nao' para user {user_id}: {e}")
        
        user_states[user_id] = {"state": "idade_recusada"}
        return
    
    if query.data == "idade_ok":
        user_states[user_id] = {"state": "idade_ok_proximo_passo"}
        
        texto_boas_vindas = "🥰 Bom te ver por aqui\\.\\.\\."
        try:
            if query.message:
                await query.edit_message_text(texto_boas_vindas, parse_mode=ParseMode.MARKDOWN_V2)
        except telegram.error.BadRequest as e:
            if "message is not modified" not in str(e).lower():
                logger.error(f"Erro ao editar mensagem de boas_vindas para user {user_id}: {e}", exc_info=True)
        
        context.application.job_queue.run_once(
            enviar_convite_vip_inicial,
            1,
            data={"chat_id": chat_id, "user_id": user_id},
            name=f"convite_vip_inicial_{user_id}"
        )

async def enviar_convite_vip_inicial(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id = job_data["chat_id"]
    user_id = job_data["user_id"]

    if user_states.get(user_id, {}).get("state") != "idade_ok_proximo_passo":
        logger.info(f"Envio do convite VIP inicial para user {user_id} cancelado (estado mudou).")
        return

    texto_segunda_msg = "No meu VIP você vai encontrar conteúdos exclusivos que não posto em lugar nenhum\\.\\.\\. 🙊"
    
    keyboard_vip = [[InlineKeyboardButton("⭐ GRUPO VIP", callback_data="ver_planos")]]
    reply_markup_vip = InlineKeyboardMarkup(keyboard_vip)

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=texto_segunda_msg,
            reply_markup=reply_markup_vip,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.info(f"Convite VIP inicial enviado para user {user_id}")
    except Exception as e:
        logger.error(f"Erro ao enviar convite VIP inicial para user {user_id}: {e}", exc_info=True)
        return
    
    user_states[user_id] = {"state": "convite_vip_enviado"}


# O resto do código permanece o mesmo
async def mostrar_planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    await query.answer()

    remover_jobs_lembrete_anteriores(user_id, context)
    user_states[user_id] = {"state": "visualizando_planos", "pending_reminder_jobs": []}

    keyboard = [
        [InlineKeyboardButton(f"💎 {PLANOS['1_mes']['nome']} - {PLANOS['1_mes']['valor']}", callback_data="plano_1_mes")],
        [InlineKeyboardButton(f"💎 {PLANOS['3_meses']['nome']} - {PLANOS['3_meses']['valor']}", callback_data="plano_3_meses")],
        [InlineKeyboardButton(f"💎 {PLANOS['6_meses']['nome']} - {PLANOS['6_meses']['valor']}", callback_data="plano_6_meses")],
        [InlineKeyboardButton(f"💎 {PLANOS['12_meses']['nome']} - {PLANOS['12_meses']['valor']}", callback_data="plano_12_meses")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    texto_planos = (
        "💎 *MEUS PLANOS VIP DISPONÍVEIS*\n\n"
        "Escolhe o plano que mais combina com você, amor:\n\n"
        "✨ Todos os planos incluem acesso completo ao meu conteúdo exclusivo\\!\n"
        "🔥 Quanto maior o plano, melhor o custo\\-benefício\\!\n"
        "Clica no plano desejado:"
    )
    
    try:
        if query.message:
            await query.edit_message_text(
                text=texto_planos,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text=texto_planos,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        logger.info(f"Planos mostrados para user {user_id}")
    except telegram.error.BadRequest as e:
        if "message is not modified" in str(e).lower():
            logger.warning(f"Mensagem de planos não modificada para user {user_id}: {e}")
        elif "message to edit not found" in str(e).lower():
            logger.warning(f"Mensagem original para planos não encontrada para user {user_id}, enviando nova: {e}")
            await context.bot.send_message(chat_id=user_id, text=texto_planos, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        else:
            logger.error(f"Erro ao mostrar planos para user {user_id}: {e}", exc_info=True)
            return

    job_context_name_base = f"{JOB_LEMBRETE_PLANOS_PREFIX}{user_id}"
    
    delays_lembrete = {"1min": 1*60, "5min": 5*60, "10min": 10*60}

    jobs_agendados = []
    for delay_tag, delay_seconds in delays_lembrete.items():
        job = context.application.job_queue.run_once(
            callback_lembrete,
            delay_seconds,
            data={"chat_id": chat_id, "user_id": user_id, "contexto_job": "visualizando_planos", "delay": delay_tag},
            name=f"{job_context_name_base}_{delay_tag}"
        )
        jobs_agendados.append(job)
    
    if user_id in user_states and isinstance(user_states[user_id], dict):
        user_states[user_id]['pending_reminder_jobs'] = jobs_agendados
    else:
        logger.warning(f"Estado para user {user_id} não era um dicionário ou não existia ao tentar armazenar jobs de lembrete de planos. Cancelando jobs.")
        for job_obj in jobs_agendados:
            if job_obj: job_obj.schedule_removal()

async def detalhes_plano(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    await query.answer()
    
    remover_jobs_lembrete_anteriores(user_id, context)

    plano_key = query.data.replace("plano_", "")
    if plano_key not in PLANOS:
        logger.error(f"Chave de plano inválida '{plano_key}' em detalhes_plano.")
        await query.edit_message_text(escape_markdown_v2("❌ Ops! Algo deu errado ao selecionar o plano. Tente novamente."), parse_mode=ParseMode.MARKDOWN_V2)
        return
    plano = PLANOS[plano_key]
    
    estado_visualizando_detalhes = f"visualizando_detalhes_{plano_key}"
    user_states[user_id] = {"state": estado_visualizando_detalhes, "plano_selecionado": plano_key, "pending_reminder_jobs": []}
    
    keyboard = [
        [InlineKeyboardButton("💳 Gerar PIX", callback_data=f"gerar_pix_{plano_key}")],
        [InlineKeyboardButton("⬅️ Voltar aos Planos", callback_data="ver_planos")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    nome_plano_escapado = escape_markdown_v2(plano['nome'])
    valor_plano_escapado = escape_markdown_v2(plano['valor'])
    dias_plano_escapado = escape_markdown_v2(str(plano['dias']))

    texto_detalhes = (
        f"💎 *{nome_plano_escapado}*\n\n"
        f"💰 Valor: *{valor_plano_escapado}*\n"
        f"⏰ Duração: *{dias_plano_escapado} dias*\n\n"
        f"🔥 *O que você vai receber, amor:*\n"
        f"✅ Acesso total ao meu grupo VIP\n"
        f"✅ Todo meu conteúdo exclusivo\n"
        f"✅ Minhas fotos e vídeos que não posto em lugar nenhum\n"
        f"✅ Contato direto comigo\n"
        f"✅ Meus novos conteúdos adicionados regularmente\n\n"
        f"Clique em 'Gerar PIX' para continuar\\! 👇"
    )
    try:
        await query.edit_message_text(
            texto_detalhes,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.info(f"Detalhes do plano {plano_key} mostrados para user {user_id}")
    except telegram.error.BadRequest as e:
        if "message is not modified" in str(e).lower():
            logger.warning(f"Mensagem de detalhes do plano não modificada para user {user_id}: {e}")
        else:
            logger.error(f"Erro ao mostrar detalhes do plano {plano_key} para user {user_id}: {e}", exc_info=True)
            return

    job_context_name_base = f"{JOB_LEMBRETE_DETALHES_PREFIX}{user_id}_{plano_key}"
    
    delays_lembrete = {"1min": 1*60, "5min": 5*60, "10min": 10*60}

    jobs_agendados = []
    for delay_tag, delay_seconds in delays_lembrete.items():
        job = context.application.job_queue.run_once(
            callback_lembrete,
            delay_seconds,
            data={"chat_id": chat_id, "user_id": user_id, "contexto_job": estado_visualizando_detalhes, "delay": delay_tag, "plano_key": plano_key},
            name=f"{job_context_name_base}_{delay_tag}"
        )
        jobs_agendados.append(job)
    
    if user_id in user_states and isinstance(user_states[user_id], dict):
        user_states[user_id]['pending_reminder_jobs'] = jobs_agendados
    else:
        logger.warning(f"Estado para user {user_id} não era um dicionário ou não existia ao tentar armazenar jobs de lembrete de detalhes. Cancelando jobs.")
        for job_obj in jobs_agendados:
            if job_obj: job_obj.schedule_removal()


async def gerar_pix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    await query.answer()
    
    remover_jobs_lembrete_anteriores(user_id, context)

    plano_key = query.data.replace("gerar_pix_", "")
    if plano_key not in PLANOS or plano_key not in LINKS_PIX:
        logger.error(f"Chave de plano inválida '{plano_key}' em gerar_pix.")
        await query.edit_message_text(escape_markdown_v2("❌ Ops! Algo deu errado ao gerar o PIX. Tente novamente."), parse_mode=ParseMode.MARKDOWN_V2)
        return
        
    estado_pix_gerado = f"gerou_pix_{plano_key}"
    user_states[user_id] = {"state": estado_pix_gerado, "plano_selecionado": plano_key, "pending_reminder_jobs": []}
    
    plano = PLANOS[plano_key]
    pix_code = LINKS_PIX[plano_key]
    username = query.from_user.username or "Não informado"
    with sqlite3.connect('vip_bot.db', timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO pagamentos_pendentes (user_id, username, plano, valor, data_solicitacao)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, plano_key, plano['valor'], datetime.now().isoformat()))
        conn.commit()
        
    # BOTÃO "Copiar PIX" REMOVIDO DAQUI
    keyboard = [
        [InlineKeyboardButton("✅ Já Paguei - Enviar Comprovante", callback_data=f"ja_paguei_{plano_key}")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data=f"plano_{plano_key}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    nome_plano_escapado = escape_markdown_v2(plano['nome'])
    valor_plano_escapado = escape_markdown_v2(plano['valor'])

    # TEXTO DE INSTRUÇÃO MELHORADO
    texto_gerar_pix = (
        f"💳 *PIX para Pagamento \\- {nome_plano_escapado}*\n\n"
        f"💰 Valor: *{valor_plano_escapado}*\n\n"
        f"📋 *Toque no código abaixo para Copiar:*\n"
        f"`{pix_code}`\n\n"
        f"📱 *Como pagar:*\n"
        f"1️⃣ **Toque no código PIX acima** para copiar\\.\n"
        f"2️⃣ Abra seu app bancário e escolha a opção *PIX Copia e Cola*\\.\n"
        f"3️⃣ Cole o código e confirme o pagamento\\.\n"
        f"4️⃣ Após pagar, clique em *'Já Paguei'* para me enviar o comprovante\\.\n\n"
        f"💕 Estou ansiosa para te receber no meu VIP, amor\\!"
    )
    await query.edit_message_text(
        texto_gerar_pix,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )
    
    admin_notify_text = (
        f"🔔 *NOVA SOLICITAÇÃO DE PAGAMENTO*\n\n"
        f"👤 Usuário: @{escape_markdown_v2(username)} \\(ID: {user_id}\\)\n"
        f"💎 Plano: {nome_plano_escapado}\n"
        f"💰 Valor: {valor_plano_escapado}\n"
        f"⏰ Horário: {escape_markdown_v2(datetime.now().strftime('%d/%m/%Y %H:%M'))}"
    )
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=admin_notify_text,
        parse_mode=ParseMode.MARKDOWN_V2
    )
    
    job_context_name_base = f"{JOB_LEMBRETE_PIX_GERADO_PREFIX}{user_id}_{plano_key}"
    delays_lembrete = {"1min_pix": 1*60, "5min_pix": 5*60, "10min_pix": 10*60}

    jobs_agendados = []
    for delay_tag, delay_seconds in delays_lembrete.items():
        job = context.application.job_queue.run_once(
            callback_lembrete,
            delay_seconds,
            data={"chat_id": chat_id, "user_id": user_id, "contexto_job": estado_pix_gerado, "delay": delay_tag, "plano_key": plano_key},
            name=f"{job_context_name_base}_{delay_tag}"
        )
        jobs_agendados.append(job)
    
    if user_id in user_states and isinstance(user_states[user_id], dict):
        user_states[user_id]['pending_reminder_jobs'] = jobs_agendados
    else:
        logger.warning(f"Estado para user {user_id} não era um dicionário ou não existia ao tentar armazenar jobs de lembrete de PIX gerado. Cancelando jobs.")
        for job_obj in jobs_agendados:
            if job_obj: job_obj.schedule_removal()

# A FUNÇÃO copiar_pix FOI REMOVIDA POIS NÃO É MAIS NECESSÁRIA

async def ja_paguei(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    
    remover_jobs_lembrete_anteriores(user_id, context)

    plano_key = query.data.replace("ja_paguei_", "")
    user_states[user_id] = {"state": "aguardando_comprovante", "plano_key_comprovante": plano_key, "pending_reminder_jobs": []}
    
    texto_ja_paguei = (
        "📎 *Envio de Comprovante*\n\n"
        "Perfeito, amor\\! Agora preciso do seu comprovante de pagamento para liberar seu acesso ao meu VIP\\.\n\n"
        "📸 *Como me enviar:*\n"
        "Envie diretamente nesta conversa a foto ou screenshot do seu comprovante\\.\n\n"
        "Pode ser:\n"
        "• Screenshot da tela de confirmação\n"
        "• Foto do comprovante\n"
        "• Print do extrato\n\n"
        "✅ Assim que eu verificar, vou liberar seu acesso imediatamente\\!\n\n"
        "💕 Obrigada pela confiança, amor\\!"
    )
    await query.edit_message_text(
        texto_ja_paguei,
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def receber_comprovante(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Não informado"
    
    user_state_info = user_states.get(user_id, {})
    current_state = user_state_info.get("state")
    
    if current_state == "aguardando_comprovante":
        remover_jobs_lembrete_anteriores(user_id, context)
        plano_key = user_state_info.get("plano_key_comprovante")

        if not plano_key or plano_key not in PLANOS:
            await update.message.reply_text(escape_markdown_v2("❌ Erro: Não consegui identificar o plano do seu pagamento. Por favor, contate o suporte."), parse_mode=ParseMode.MARKDOWN_V2)
            return

        plano = PLANOS[plano_key]
        with sqlite3.connect('vip_bot.db', timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE pagamentos_pendentes SET comprovante_enviado = 1
                WHERE user_id = ? AND plano = ? AND aprovado = 0 AND comprovante_enviado = 0
                ORDER BY id DESC LIMIT 1
            ''', (user_id, plano_key))
            conn.commit()

        user_states[user_id] = {"state": "comprovante_enviado_admin"}

        await update.message.reply_text(
            "✅ *Comprovante Recebido\\!*\n\n"
            "Perfeito, amor\\! Recebi seu comprovante e vou verificar agora mesmo\\.\n\n"
            "⏰ Em poucos minutos você receberá o link de acesso ao meu grupo VIP\\!\n\n"
            "💕 Obrigada pela paciência, amor\\!",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Aprovar Acesso", callback_data=f"aprovar_{user_id}_{plano_key}")],
            [InlineKeyboardButton("❌ Rejeitar", callback_data=f"rejeitar_{user_id}_{plano_key}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        caption_text_admin = (
            f"📎 *COMPROVANTE RECEBIDO*\n\n"
            f"👤 Usuário: @{escape_markdown_v2(username)} \\(ID: {user_id}\\)\n"
            f"💎 Plano: {escape_markdown_v2(plano['nome'])}\n"
            f"💰 Valor: {escape_markdown_v2(plano['valor'])}\n"
            f"⏰ Horário: {escape_markdown_v2(datetime.now().strftime('%d/%m/%Y %H:%M'))}\n\n"
            f"Clique em uma das opções abaixo:"
        )
        if update.message.photo:
            await context.bot.send_photo(
                chat_id=ADMIN_ID, photo=update.message.photo[-1].file_id,
                caption=caption_text_admin, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2
            )
        elif update.message.document:
            await context.bot.send_document(
                chat_id=ADMIN_ID, document=update.message.document.file_id,
                caption=caption_text_admin, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2
            )
    
    elif current_state and current_state.startswith("gerou_pix_"):
        plano_key = current_state.replace("gerou_pix_", "")
        texto_orientacao = (
            "Oi, amor\\! Vi que você me enviou uma imagem, deve ser o seu comprovante, né? 🥰\n\n"
            "Para que eu possa registrar direitinho, por favor, clique primeiro no botão *\"✅ Já Paguei \\- Enviar Comprovante\"* na mensagem anterior, e *depois* me envie esta imagem novamente\\.\n\n"
            "Assim garantimos que seu acesso VIP seja liberado sem problemas\\! 😉"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Já Paguei - Enviar Comprovante", callback_data=f"ja_paguei_{plano_key}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            texto_orientacao,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    else:
        logger.info(f"User {user_id} enviou uma foto/documento fora de contexto (estado: {current_state}). Ignorando.")

async def processar_aprovacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin_user_id = query.from_user.id
    await query.answer()

    data_parts = query.data.split("_")
    acao = data_parts[0]
    try:
        user_id_pagante = int(data_parts[1])
    except (IndexError, ValueError) as e:
        logger.error(f"Erro ao parsear user_id_pagante de callback_data '{query.data}': {e}")
        await query.edit_message_caption(caption=escape_markdown_v2(f"❌ Erro ao processar callback: dados inválidos. ({query.data})"), parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    remover_jobs_lembrete_anteriores(user_id_pagante, context)
    if user_id_pagante in user_states and isinstance(user_states[user_id_pagante], dict):
        user_states[user_id_pagante]["state"] = f"pagamento_{acao}"
    else:
        user_states[user_id_pagante] = {"state": f"pagamento_{acao}", "pending_reminder_jobs": []}


    plano_key = "_".join(data_parts[2:])
    if plano_key not in PLANOS:
        logger.error(f"Plano '{plano_key}' não encontrado ao processar aprovação para user {user_id_pagante}.")
        await query.edit_message_caption(
            caption=escape_markdown_v2(f"❌ Erro: Plano '{plano_key}' não encontrado para usuário {user_id_pagante}."), parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    plano = PLANOS[plano_key]

    if acao == "aprovar":
        try:
            link_convite = await context.bot.create_chat_invite_link(
                chat_id=CANAL_VIP_ID, member_limit=1, expire_date=int(time.time()) + (7 * 24 * 60 * 60)
            )
            data_expiracao = datetime.now() + timedelta(days=plano['dias'])
            username_pagante = "Não recuperado"
            try:
                chat_user_pagante = await context.bot.get_chat(user_id_pagante)
                username_pagante = chat_user_pagante.username or "Não informado"
            except Exception as e_user:
                logger.warning(f"Não foi possível obter username para {user_id_pagante} ao aprovar: {e_user}")

            with sqlite3.connect('vip_bot.db', timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO usuarios_vip (user_id, username, plano, data_entrada, data_expiracao, ativo)
                    VALUES (?, ?, ?, ?, ?, 1)
                ''', (user_id_pagante, username_pagante, plano_key, datetime.now().isoformat(), data_expiracao.isoformat()))
                cursor.execute('''
                    UPDATE pagamentos_pendentes SET aprovado = 1
                    WHERE user_id = ? AND plano = ? AND comprovante_enviado = 1 AND aprovado = 0 ORDER BY id DESC LIMIT 1
                ''', (user_id_pagante, plano_key))
                conn.commit()
            
            link_esc = escape_markdown_v2(link_convite.invite_link)
            plano_nome_esc = escape_markdown_v2(plano['nome'])
            data_exp_user_esc = escape_markdown_v2(data_expiracao.strftime('%d/%m/%Y'))

            texto_para_usuario = (
                f"🎉 *PAGAMENTO APROVADO\\!*\n\n"
                f"Seja bem\\-vindo ao meu VIP, amor\\! 💕\n\n"
                f"💎 Seu plano: {plano_nome_esc}\n"
                f"⏰ Válido até: {data_exp_user_esc}\n\n"
                f"🔗 *Link de acesso ao meu VIP:*\n{link_esc}\n\n"
                f"⚠️ *Atenção, amor:*\n"
                f"\\- Este link expira em 7 dias e só pode ser usado uma vez\\.\n"
                f"\\- Apenas você está autorizado\\(a\\) a entrar no meu canal\\.\n"
                f"\\- Qualquer pessoa não autorizada que tentar entrar será removida automaticamente\\.\n\n"
                f"✨ Aproveite todo meu conteúdo exclusivo\\!\n"
                f"💕 Qualquer dúvida, é só me chamar\\!"
            )
            await context.bot.send_message(
                chat_id=user_id_pagante, text=texto_para_usuario, parse_mode=ParseMode.MARKDOWN_V2
            )
            
            username_pagante_esc = escape_markdown_v2(username_pagante)
            valor_plano_esc = escape_markdown_v2(plano['valor'])
            horario_aprov_esc = escape_markdown_v2(datetime.now().strftime('%d/%m/%Y %H:%M'))
            data_exp_admin_esc = escape_markdown_v2(data_expiracao.strftime('%d/%m/%Y'))

            caption_para_admin = (
                f"✅ *ACESSO APROVADO*\n\n"
                f"👤 Usuário: @{username_pagante_esc} \\(ID: {user_id_pagante}\\)\n"
                f"💎 Plano: {plano_nome_esc}\n"
                f"💰 Valor: {valor_plano_esc}\n"
                f"⏰ Aprovado em: {horario_aprov_esc}\n"
                f"📅 Expira em: {data_exp_admin_esc}"
            )
            await query.edit_message_caption(caption=caption_para_admin, parse_mode=ParseMode.MARKDOWN_V2)
            
        except telegram.error.TelegramError as te:
            logger.error(f"Erro Telegram ao aprovar acesso para {user_id_pagante}: {te}")
            await query.edit_message_caption(caption=escape_markdown_v2(f"❌ Erro Telegram ao aprovar acesso: {te}"), parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Erro geral ao aprovar acesso para {user_id_pagante}: {e}", exc_info=True)
            await query.edit_message_caption(caption=escape_markdown_v2(f"❌ Erro geral ao aprovar acesso: {e}"), parse_mode=ParseMode.MARKDOWN_V2)
            
    elif acao == "rejeitar":
        with sqlite3.connect('vip_bot.db', timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM pagamentos_pendentes
                WHERE user_id = ? AND plano = ? AND comprovante_enviado = 1 AND aprovado = 0 ORDER BY id DESC LIMIT 1
            ''', (user_id_pagante, plano_key))
            conn.commit()
        
        texto_rejeicao_user = (
            "❌ *Pagamento não aprovado*\n\n"
            "Infelizmente não consegui confirmar seu pagamento, amor\\.\n\n"
            "💬 Entre em contato comigo para resolvermos esta questão\\.\n"
            "🔄 Ou tente fazer um novo pagamento\\."
        )
        await context.bot.send_message(chat_id=user_id_pagante, text=texto_rejeicao_user, parse_mode=ParseMode.MARKDOWN_V2)
        
        plano_nome_escapado = escape_markdown_v2(plano['nome'])
        horario_rejeicao_escapado = escape_markdown_v2(datetime.now().strftime('%d/%m/%Y %H:%M'))
        caption_rejeicao_admin = (
            f"❌ *ACESSO REJEITADO*\n\n"
            f"👤 Usuário: ID {user_id_pagante}\n"
            f"💎 Plano: {plano_nome_escapado}\n"
            f"⏰ Rejeitado em: {horario_rejeicao_escapado}"
        )
        await query.edit_message_caption(caption=caption_rejeicao_admin, parse_mode=ParseMode.MARKDOWN_V2)

async def listar_usuarios(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    with sqlite3.connect('vip_bot.db', timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, username, plano, data_expiracao FROM usuarios_vip WHERE ativo = 1 ORDER BY data_expiracao')
        usuarios = cursor.fetchall()
    if not usuarios:
        await update.message.reply_text("📋 Nenhum usuário VIP ativo no momento\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    texto_final = "📋 *USUÁRIOS VIP ATIVOS*\n\n"
    for uid, uname, pkey, data_exp_iso in usuarios:
        plano_nome = PLANOS.get(pkey, {}).get('nome', f"Plano '{pkey}' (Desconhecido)")
        plano_nome_esc = escape_markdown_v2(plano_nome)
        uname_esc = escape_markdown_v2(uname if uname else 'N/A')
        
        try:
            data_exp = datetime.fromisoformat(data_exp_iso)
            dias_restantes = (data_exp - datetime.now()).days
            exp_formatada = escape_markdown_v2(data_exp.strftime('%d/%m/%Y'))
            dias_rest_texto = escape_markdown_v2(str(dias_restantes) if dias_restantes >= 0 else 'Expirado')
        except ValueError:
            exp_formatada = escape_markdown_v2("Data Inválida")
            dias_rest_texto = escape_markdown_v2("N/A")
            logger.warning(f"Data de expiração inválida '{data_exp_iso}' para usuário {uid}")

        texto_final += f"👤 ID: {uid} \\(@{uname_esc}\\)\n"
        texto_final += f"💎 Plano: {plano_nome_esc}\n"
        texto_final += f"📅 Expira em: {exp_formatada}\n"
        texto_final += f"⏰ Dias restantes: {dias_rest_texto}\n\n"
    
    texto_final += "\n💡 *Para remover um usuário, use:*\n"
    texto_final += f"`/remover ID_DO_USUARIO`"
    
    if len(texto_final) > 4096:
        for i in range(0, len(texto_final), 4000):
            await update.message.reply_text(texto_final[i:i+4000], parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text(texto_final, parse_mode=ParseMode.MARKDOWN_V2)

async def remover_usuarios_expirados_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Executando job de remoção de usuários expirados...")
    with sqlite3.connect('vip_bot.db', timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, username FROM usuarios_vip WHERE ativo = 1 AND data_expiracao < ?
        ''', (datetime.now().isoformat(),))
        usuarios_expirados = cursor.fetchall()
        if not usuarios_expirados:
            logger.info("Nenhum usuário expirado encontrado.")
            return

        for user_id_exp, username_exp in usuarios_expirados:
            try:
                logger.info(f"Tentando remover usuário expirado {user_id_exp} (@{username_exp}) do canal {CANAL_VIP_ID}")
                await context.bot.ban_chat_member(chat_id=CANAL_VIP_ID, user_id=user_id_exp)
                await context.bot.unban_chat_member(chat_id=CANAL_VIP_ID, user_id=user_id_exp)
                cursor.execute('UPDATE usuarios_vip SET ativo = 0 WHERE user_id = ?', (user_id_exp,))
                conn.commit()
                logger.info(f"Usuário {user_id_exp} (@{username_exp}) removido do canal e DB.")
                try:
                    texto_expiracao = (
                        "😢 *Sua assinatura VIP expirou\\!*\n\n"
                        "Seu acesso ao meu conteúdo exclusivo foi encerrado, amor\\.\n"
                        "Mas não se preocupe\\! Você pode renovar a qualquer momento usando o comando `/start`\\.\n\n"
                        "Espero te ver de volta em breve\\! 💕"
                    )
                    await context.bot.send_message(chat_id=user_id_exp, text=texto_expiracao, parse_mode=ParseMode.MARKDOWN_V2)
                except Exception as e_msg:
                    logger.warning(f"Não notificar {user_id_exp} sobre expiração: {e_msg}")
            except telegram.error.TelegramError as te:
                if "user not found" in str(te).lower() or "chat member not found" in str(te).lower() or "user_is_bot" in str(te).lower():
                    logger.warning(f"Usuário {user_id_exp} não encontrado/bot/não membro no canal. Marcando inativo. Erro: {te}")
                    cursor.execute('UPDATE usuarios_vip SET ativo = 0 WHERE user_id = ?', (user_id_exp,))
                    conn.commit()
                else:
                    logger.error(f"Erro Telegram ao remover {user_id_exp} expirado: {te}")
            except Exception as e:
                logger.error(f"Erro geral ao remover {user_id_exp} expirado: {e}", exc_info=True)
    logger.info("Job de remoção de usuários expirados concluído.")

async def remover_usuario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args:
        await update.message.reply_text(
            "❌ *Erro: ID do usuário não fornecido*\nUse: `/remover ID_DO_USUARIO`", parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    try:
        user_id_remover = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID inválido\\. Deve ser um número\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    with sqlite3.connect('vip_bot.db', timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM usuarios_vip WHERE user_id = ? AND ativo = 1', (user_id_remover,))
        if not cursor.fetchone():
            await update.message.reply_text(
                escape_markdown_v2(f"❌ Usuário {user_id_remover} não encontrado ou já inativo."), parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        try:
            await context.bot.ban_chat_member(CANAL_VIP_ID, user_id_remover)
            await context.bot.unban_chat_member(CANAL_VIP_ID, user_id_remover)
            logger.info(f"Admin removeu {user_id_remover} do canal.")
            cursor.execute('UPDATE usuarios_vip SET ativo = 0 WHERE user_id = ?', (user_id_remover,))
            conn.commit()
            logger.info(f"Status de {user_id_remover} atualizado para inativo (manual).")
            try:
                await context.bot.send_message(
                    chat_id=user_id_remover,
                    text=escape_markdown_v2("⚠️ *Seu acesso ao canal VIP foi revogado pelo administrador.*"), parse_mode=ParseMode.MARKDOWN_V2
                )
            except Exception as e_msg:
                logger.warning(f"Erro ao notificar {user_id_remover} sobre remoção manual: {e_msg}")
            await update.message.reply_text(escape_markdown_v2(f"✅ Usuário {user_id_remover} removido e marcado inativo."), parse_mode=ParseMode.MARKDOWN_V2)
        except telegram.error.TelegramError as te:
            await update.message.reply_text(
                escape_markdown_v2(f"⚠️ Erro Telegram ao remover {user_id_remover}: {te}\nVerifique permissões do bot no canal."),
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception as e:
            logger.error(f"Erro geral ao remover {user_id_remover} (manual): {e}", exc_info=True)
            await update.message.reply_text(escape_markdown_v2(f"⚠️ Erro geral ao remover: {e}"), parse_mode=ParseMode.MARKDOWN_V2)

async def verificar_usuario_autorizado(user_id_verificar):
    with sqlite3.connect('vip_bot.db', timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM usuarios_vip WHERE user_id = ? AND ativo = 1 AND data_expiracao >= ?',
                       (user_id_verificar, datetime.now().isoformat()))
        return cursor.fetchone() is not None

async def remover_usuario_nao_autorizado(user_id_remover, bot_instance: telegram.Bot):
    try:
        await bot_instance.ban_chat_member(CANAL_VIP_ID, user_id_remover)
        await bot_instance.unban_chat_member(CANAL_VIP_ID, user_id_remover)
        logger.info(f"Usuário não autorizado {user_id_remover} removido do canal {CANAL_VIP_ID}.")
        try:
            texto_nao_autorizado = (
                "⚠️ *Acesso não autorizado*\n\n"
                "Você foi removido do meu canal VIP \\(acesso não autorizado/expirado\\)\\.\n"
                "Use `/start` para adquirir um plano\\."
            )
            await bot_instance.send_message(chat_id=user_id_remover, text=texto_nao_autorizado, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e_msg:
            logger.warning(f"Erro ao notificar não autorizado {user_id_remover}: {e_msg}")
        
        admin_msg_nao_autorizado = f"🚫 Usuário ID {user_id_remover} removido do VIP {escape_markdown_v2(str(CANAL_VIP_ID))} \\(não autorizado\\)\\."
        await bot_instance.send_message(chat_id=ADMIN_ID, text=admin_msg_nao_autorizado, parse_mode=ParseMode.MARKDOWN_V2)
        return True
    except telegram.error.TelegramError as te:
        if "user_is_bot" in str(te).lower():
            logger.warning(f"Tentativa de remover bot {user_id_remover} do canal. Ignorando. Erro: {te}")
            return False
        logger.error(f"Erro Telegram ao remover não autorizado {user_id_remover}: {te}")
    except Exception as e:
        logger.error(f"Erro geral ao remover não autorizado {user_id_remover}: {e}", exc_info=True)
    return False

async def verificar_novo_membro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.chat_member or str(update.chat_member.chat.id) != str(CANAL_VIP_ID):
        return
    new_member_status = update.chat_member.new_chat_member.status
    user = update.chat_member.new_chat_member.user
    if new_member_status in [TGConstants.ChatMemberStatus.MEMBER, TGConstants.ChatMemberStatus.RESTRICTED]:
        user_id_novo = user.id
        if user_id_novo == ADMIN_ID or user_id_novo == context.bot.id:
            return
        username_novo_esc = escape_markdown_v2(user.username or 'N/A')
        logger.info(f"Novo membro no VIP {CANAL_VIP_ID}: ID {user_id_novo} (@{username_novo_esc})")
        if not await verificar_usuario_autorizado(user_id_novo):
            logger.warning(f"NÃO AUTORIZADO: {user_id_novo} (@{username_novo_esc}) no VIP {CANAL_VIP_ID}. Removendo...")
            await remover_usuario_nao_autorizado(user_id_novo, context.bot)
        else:
            logger.info(f"AUTORIZADO: {user_id_novo} (@{username_novo_esc}) no VIP {CANAL_VIP_ID}.")

# --- Funções de Keep-Alive ---
def keep_alive_ping():
    host_url = os.environ.get('RENDER_EXTERNAL_URL')
    if not host_url:
        logger.info("RENDER_EXTERNAL_URL não definida. Auto-ping desativado.")
        return
    
    time.sleep(45)
    logger.info(f"Keep-alive auto-ping iniciado para {host_url}.")

    while True:
        try:
            with urllib.request.urlopen(host_url, timeout=25) as response:
                logger.info(f"Keep-alive ping para {host_url} status {response.status}.")
        except Exception as e:
            logger.error(f"Erro no keep-alive ping para {host_url}: {e}")
        time.sleep(10 * 60)

class KeepAliveHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write('Bot VIP está ativo e operante!'.encode('utf-8'))
        logger.debug(f"KeepAliveHandler: Requisição GET de {self.client_address}, respondendo OK.")

def start_keep_alive_server():
    port = int(os.environ.get('PORT', 8080))
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("", port), KeepAliveHandler) as httpd:
            logger.info(f"Servidor keep-alive HTTP iniciado na porta {port}.")
            httpd.serve_forever()
    except OSError as e:
        logger.critical(f"OSError ao iniciar servidor keep-alive na porta {port}: {e}.")
    except Exception as e:
        logger.critical(f"Exceção não esperada ao iniciar servidor keep-alive: {e}", exc_info=True)

# --- Funções Principais de Configuração e Execução do Bot ---
def configure_application():
    init_db()
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("usuarios", listar_usuarios))
    application.add_handler(CommandHandler("remover", remover_usuario))
    
    application.add_handler(CallbackQueryHandler(handle_idade, pattern="^idade_"))
    application.add_handler(CallbackQueryHandler(mostrar_planos, pattern="^ver_planos$"))
    application.add_handler(CallbackQueryHandler(detalhes_plano, pattern="^plano_"))
    application.add_handler(CallbackQueryHandler(gerar_pix, pattern="^gerar_pix_"))
    # O handler para copiar_pix foi removido
    application.add_handler(CallbackQueryHandler(ja_paguei, pattern="^ja_paguei_"))
    application.add_handler(CallbackQueryHandler(processar_aprovacao, pattern="^(aprovar|rejeitar)_"))
    
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, receber_comprovante))
    application.add_handler(ChatMemberHandler(verificar_novo_membro, ChatMemberHandler.CHAT_MEMBER))
    
    job_queue = application.job_queue
    job_queue.run_repeating(remover_usuarios_expirados_job, interval=3600, first=60)
    
    if os.environ.get('RENDER'):
        logger.info("Ambiente RENDER detectado. Iniciando threads de keep-alive.")
        server_thread = threading.Thread(target=start_keep_alive_server, daemon=True)
        server_thread.start()
        
        if os.environ.get('RENDER_EXTERNAL_URL'):
            ping_thread = threading.Thread(target=keep_alive_ping, daemon=True)
            ping_thread.start()
        else:
            logger.warning("RENDER_EXTERNAL_URL não definida, auto-ping não será iniciado.")
    else:
        logger.info("Ambiente não RENDER. Threads de keep-alive não iniciadas.")
            
    return application

async def pre_run_bot_operations(application: Application):
    logger.info("Executando operações de pré-inicialização do bot (async)...")
    
    async def error_handler_callback(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error(msg="Exceção durante o processamento de um update:", exc_info=context.error)
        if isinstance(context.error, telegram.error.Conflict):
            logger.critical("CONFLITO TELEGRAM DURANTE OPERAÇÃO. Outra instância do bot provavelmente está rodando.")
        elif isinstance(context.error, telegram.error.BadRequest) and "Can't parse entities" in str(context.error):
            logger.error(f"Erro de parsing de Markdown/HTML: {context.error}")
            if update and hasattr(update, 'effective_chat') and update.effective_chat:
                try:
                    error_details = f"Erro: {html.escape(str(context.error))}\n"
                    if hasattr(update, 'message') and update.message and hasattr(update.message, 'text'):
                        error_details += f"Mensagem original (se houver): {html.escape(str(update.message.text))}\n"
                    elif hasattr(update, 'callback_query') and update.callback_query and hasattr(update.callback_query, 'data'):
                        error_details += f"Callback query data: {html.escape(str(update.callback_query.data))}\n"
                    
                    update_str = str(update)
                    max_len = 4096 - len(error_details) - 100
                    error_details += f"Update problemático: {html.escape(update_str[:max_len])}"
                    if len(update_str) > max_len: error_details += "..."

                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=f"⚠️ Erro de parsing de entidade ao tentar enviar/editar mensagem.\n{error_details}",
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e_notify:
                    logger.error(f"Falha ao notificar admin sobre erro de parsing: {e_notify}")

    application.add_error_handler(error_handler_callback)
    logger.info("Error handler global adicionado à aplicação.")

    try:
        logger.info("Tentando deletar webhook e limpar updates pendentes...")
        if await application.bot.delete_webhook(drop_pending_updates=True):
            logger.info("Webhook deletado/limpo com sucesso.")
        else:
            logger.info("delete_webhook retornou False (normal se nenhum webhook estava setado).")
    except telegram.error.RetryAfter as e:
        logger.warning(f"RetryAfter ao deletar webhook: {e}. Aguardando {e.retry_after}s e tentando novamente.")
        await asyncio.sleep(e.retry_after)
        try:
            if await application.bot.delete_webhook(drop_pending_updates=True):
                logger.info("Webhook deletado/limpo com sucesso na segunda tentativa.")
        except Exception as e2:
            logger.error(f"Erro na segunda tentativa de delete_webhook: {e2}", exc_info=True)
    except Exception as e:
        logger.error(f"Erro inesperado durante delete_webhook: {e}", exc_info=True)
    
    logger.info("Operações de pré-inicialização do bot (async) concluídas.")

async def run_bot_async():
    logger.info("Configurando a aplicação do bot...")
    application = configure_application()

    await pre_run_bot_operations(application)

    logger.info("Inicializando componentes da aplicação...")
    try:
        await application.initialize()
        logger.info("Iniciando polling de updates do Telegram...")
        await application.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        logger.info("Iniciando o dispatcher para processar updates...")
        await application.start()
        
        bot_info = await application.bot.get_me()
        logger.info(f"Bot @{bot_info.username} (ID: {bot_info.id}) iniciado e rodando! Aguardando por interrupção...")
        
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Sinal de interrupção recebido, iniciando shutdown gracioso...")
    except Exception as e:
        logger.critical(f"Erro crítico durante a execução do bot (polling/start): {e}", exc_info=True)
    finally:
        logger.info("Iniciando processo de shutdown do bot...")
        if 'application' in locals() and application:
            if hasattr(application, 'running') and application.running:
                logger.info("Parando o dispatcher de updates (application.stop())...")
                await application.stop()
            if hasattr(application, 'updater') and application.updater and hasattr(application.updater, 'is_running') and application.updater.is_running:
                logger.info("Parando o polling de updates (application.updater.stop())...")
                await application.updater.stop()
            if hasattr(application, 'shutdown'):
                logger.info("Realizando shutdown da aplicação (application.shutdown())...")
                await application.shutdown()
            else:
                logger.warning("Atributo 'shutdown' não encontrado no objeto application.")
        else:
            logger.warning("Objeto Application não definido ou não completamente inicializado para shutdown.")
        logger.info("Shutdown do bot concluído.")

if __name__ == '__main__':
    logger.info("========================================")
    logger.info("=== INICIANDO SCRIPT PRINCIPAL DO BOT ===")
    logger.info("========================================")
    try:
        asyncio.run(run_bot_async())
    except KeyboardInterrupt:
        logger.info("Bot encerrado manualmente via KeyboardInterrupt (nível principal).")
    except telegram.error.Conflict as e_conflict:
        logger.critical(f"CONFLITO TELEGRAM NA INICIALIZAÇÃO GERAL: {e_conflict}.")
    except RuntimeError as e_runtime:
        if "no current event loop" in str(e_runtime).lower():
            logger.critical(f"RUNTIME ERROR - NO CURRENT EVENT LOOP: {e_runtime}.")
        else:
            logger.critical(f"Erro fatal (RuntimeError) ao executar o bot: {e_runtime}", exc_info=True)
    except Exception as e_fatal:
        logger.critical(f"Erro fatal geral não capturado ao executar o bot: {e_fatal}", exc_info=True)
    finally:
        logger.info("========================================")
        logger.info("=== SCRIPT PRINCIPAL DO BOT FINALIZADO ===")
        logger.info("========================================")
