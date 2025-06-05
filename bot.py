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
    keyboard_lembrete = None  # Teclado começa como nulo
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

    elif estado_esperado_no_job == "visualizando_planos":
        if delay == "1min":
            mensagem = "Ei, vi que você está de olho nos meus planos VIP 👀\\! Para continuar, **clique no botão '⭐ GRUPO VIP' na mensagem acima** e escolha o plano que mais combina com você\\. O conteúdo exclusivo te espera\\! 🔥"
        elif delay == "5min":
            mensagem = "Psst\\! Só passando para lembrar que o acesso ao paraíso está a um clique de distância\\. **Use o botão '⭐ GRUPO VIP' que te enviei antes** para ver as opções e garantir sua vaga\\. 😉"
        elif delay == "10min":
            mensagem = "Amor, não quero que você fique de fora\\! Essa é sua última chance de garantir o acesso\\. **Clique no botão '⭐ GRUPO VIP' lá em cima** e venha se divertir comigo\\! 🔞"
        
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
                mensagem = f"Amor, seu PIX para o *{plano_nome_escapado}* foi gerado\\! 🎉 Após pagar, **clique no botão '✅ Já Paguei' na mensagem acima** para me enviar o comprovante\\! Estou te esperando\\! 😉"
            elif delay == "5min_pix":
                mensagem = f"Só um lembrete carinhoso, seu PIX para o *{plano_nome_escapado}* ainda está aguardando o pagamento\\. Assim que pagar, é só clicar no botão '✅ Já Paguei' lá em cima para enviar seu comprovante\\! 🔥"
            elif delay == "10min_pix":
                mensagem = f"Última chamada, amor\\! Seu acesso ao *{plano_nome_escapado}* está quase lá\\. Faça o pagamento e **clique no botão '✅ Já Paguei' na mensagem anterior** para não ficar de fora da diversão\\! 😈"
            
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
    
    delays_lembrete = {"1min_idade": 1*60, "5min_idade": 5*60, "10min_idade": 10*60}

    jobs_agendados = []
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
    
    remover_jobs_lembrete_anteriores(user_id, context)
    
    if user_id in user_states and isinstance(user_states.get(user_id), dict):
        last_msg_id = user_states[user_id].get('last_reminder_message_id')
        if last_msg_id and query.message and last_msg_id != query.message.message_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=last_msg_id)
                logger.info(f"Última mensagem de verificação (ID: {last_msg_id}) deletada para user {user_id}.")
            except Exception as e:
                logger.warning(f"Não foi possível deletar última mensagem de verificação (ID: {last_msg_id}): {e}")

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
        sent_message = await context.bot.send_message(
            chat_id=chat_id,
            text=texto_segunda_msg,
            reply_markup=reply_markup_vip,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.info(f"Convite VIP inicial enviado para user {user_id}")
        if user_id in user_states and isinstance(user_states[user_id], dict):
             user_states[user_id]['last_reminder_message_id'] = sent_message.message_id
    except Exception as e:
        logger.error(f"Erro ao enviar convite VIP inicial para user {user_id}: {e}", exc_info=True)
        return
    
    user_states[user_id] = {"state": "convite_vip_enviado"}


# ... (O restante do código permanece o mesmo)
