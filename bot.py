import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, BotCommandScopeDefault, BotCommandScopeChat
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

# Links PIX
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

DB_PATH = os.environ.get('DB_PATH', 'vip_bot.db')


def init_db():
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
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
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_sessions (
                user_id INTEGER PRIMARY KEY,
                state TEXT,
                plano_selecionado TEXT,
                last_update TEXT
            )
        ''')
        
        try:
            cursor.execute('PRAGMA table_info(usuarios_vip)')
            columns = [col[1] for col in cursor.fetchall()]
            if 'lembrete_enviado_dias' not in columns:
                cursor.execute('ALTER TABLE usuarios_vip ADD COLUMN lembrete_enviado_dias INTEGER')
                logger.info("Coluna 'lembrete_enviado_dias' adicionada à tabela 'usuarios_vip'.")
        except Exception as e:
            logger.error(f"Erro ao tentar migrar o schema do DB: {e}")
            
        conn.commit()

def set_user_state(user_id: int, state: str, plano_key: str = None):
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO user_sessions (user_id, state, plano_selecionado, last_update)
            VALUES (?, ?, ?, ?)
        ''', (user_id, state, plano_key, datetime.now().isoformat()))
        conn.commit()
    logger.info(f"Estado do user {user_id} salvo no DB: {state}, Plano: {plano_key}")

def get_user_state(user_id: int) -> dict:
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT state, plano_selecionado FROM user_sessions WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        if row:
            return {"state": row[0], "plano_selecionado": row[1]}
        return {}


def escape_markdown_v2(text: str) -> str:
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return "".join(f"\\{char}" if char in escape_chars else char for char in text)

# ... (O restante das funções que já estavam corretas permanecem aqui) ...

async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    msg = await update.message.reply_text("📊 Analisando os dados e montando seu dashboard...")

    try:
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            cursor = conn.cursor()

            # 1. Total de membros ativos
            cursor.execute("SELECT COUNT(*) FROM usuarios_vip WHERE ativo = 1")
            total_ativos = cursor.fetchone()[0]

            # 2. Novos assinantes nos últimos 7 dias
            cursor.execute("SELECT COUNT(*) FROM usuarios_vip WHERE data_entrada >= date('now', '-7 days')")
            novos_na_semana = cursor.fetchone()[0]

            # 3. Vendas nos últimos 7 dias
            cursor.execute("SELECT plano FROM pagamentos_pendentes WHERE aprovado = 1 AND data_solicitacao >= date('now', '-7 days')")
            planos_vendidos_semana = cursor.fetchall()
            
            vendas_semana = 0.0
            for (plano_key,) in planos_vendidos_semana:
                valor_str = PLANOS.get(plano_key, {}).get('valor', 'R$ 0')
                try:
                    # Converte o valor 'R$ 39,90' para o float 39.90
                    valor_float = float(valor_str.replace('R$ ', '').replace(',', '.'))
                    vendas_semana += valor_float
                except (ValueError, TypeError):
                    logger.warning(f"Não foi possível converter o valor '{valor_str}' para float.")


            # 4. Distribuição de planos entre membros ativos
            cursor.execute("SELECT plano, COUNT(*) FROM usuarios_vip WHERE ativo = 1 GROUP BY plano")
            distribuicao_planos = cursor.fetchall()
            
            distribuicao_texto = ""
            if not distribuicao_planos:
                distribuicao_texto = "Nenhum membro ativo com plano definido\\."
            else:
                for plano_key, count in distribuicao_planos:
                    nome_plano = PLANOS.get(plano_key, {}).get('nome', plano_key)
                    distribuicao_texto += f"• {escape_markdown_v2(nome_plano)}: *{count}* membro(s)\n"

        # --- CORRIGIDO: Adicionado \ antes de ( e ) e . ---
        texto_dashboard = (
            f"📊 *Dashboard \\- Resumo do Negócio*\n\n"
            f"👥 *Total de Membros VIP Ativos:* {total_ativos}\n"
            f"📈 *Novos Assinantes \\(últimos 7 dias\\):* {novos_na_semana}\n"
            f"💰 *Vendas \\(últimos 7 dias\\):* R$ {vendas_semana:.2f}\\.\n\n"
            f"💎 *Distribuição de Planos Ativos:*\n"
            f"{distribuicao_texto}"
        )

        await msg.edit_text(texto_dashboard, parse_mode=ParseMode.MARKDOWN_V2)

    except Exception as e:
        logger.error(f"Erro ao gerar o dashboard: {e}", exc_info=True)
        await msg.edit_text("❌ Ops, ocorreu um erro ao gerar seu dashboard. Tente novamente mais tarde.")

# (Cole aqui o restante do seu código, desde 'def configure_application():' até o final)
# ...
# Como o código é muito longo, vou omitir as partes que não mudaram para a resposta ficar mais curta,
# mas no seu arquivo final, você deve ter todo o resto do código que já estava funcionando.
# A única alteração foi na função dashboard_command acima.

# ... (cole todo o resto do seu código aqui)

# --- Exemplo de como ficaria a função configure_application ---
def configure_application():
    init_db()
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("meu_plano", meu_plano_command))
    application.add_handler(CommandHandler("usuarios", listar_usuarios))
    application.add_handler(CommandHandler("dashboard", dashboard_command)) # Handler já estava correto
    application.add_handler(CommandHandler("remover", remover_usuario))
    
    #... e assim por diante
    return application

# (todo o resto do arquivo)
