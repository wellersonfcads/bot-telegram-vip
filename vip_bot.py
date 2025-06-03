import logging
import sqlite3
import asyncio
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest, Conflict # Importar Conflict

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configurações - ALTERE AQUI
TOKEN = "7963030995:AAE8K5RIFJpaOhxLnDxJ4k614wnq4n549AQ"
SEU_USER_ID = 6150001511
CANAL_VIP_ID = "-1002280243232"

PLANOS = {
    "1mes": {"nome": "Plano VIP 1 mês", "valor": "R$ 39,90", "duracao": 30, "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540539.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA6207050363044086"},
    "3meses": {"nome": "Plano VIP 3 meses", "valor": "R$ 99,90", "duracao": 90, "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540599.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA6207050363041E24"},
    "6meses": {"nome": "Plano VIP 6 meses", "valor": "R$ 179,90", "duracao": 180, "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406179.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA6207050363043084"},
    "12meses": {"nome": "Plano VIP 12 meses", "valor": "R$ 289,90", "duracao": 365, "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406289.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA620705036304CD13"}
}

VIDEO_URL = "" # COLOQUE O FILE_ID DO SEU VÍDEO AQUI QUANDO TIVER

estados_usuarios = {}
DB_NAME = 'usuarios_vip.db' # Se estiver no Render, certifique-se que isso está em um disco persistente se necessário

def inicializar_banco():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False) # Adicionado check_same_thread para JobQueue
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS usuarios_vip (
        user_id INTEGER PRIMARY KEY, username TEXT, nome TEXT, plano_id TEXT,
        data_entrada TEXT, data_expiracao TEXT, ativo INTEGER DEFAULT 1, idade_verificada INTEGER DEFAULT 0 )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pagamentos_pendentes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, nome TEXT,
        plano_id TEXT, valor TEXT, data_solicitacao TEXT, comprovante_enviado INTEGER DEFAULT 0,
        aprovado INTEGER DEFAULT 0, mensagem_pix_id_principal INTEGER )
    ''')
    conn.commit()
    conn.close()

# --- Funções get_user_db_info, set_user_idade_verificada, start_command, boas_vindas_fluxo ---
# (Mantidas como na versão anterior, sem mudanças diretas aqui para este problema específico)
def get_user_db_info(user_id):
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT idade_verificada FROM usuarios_vip WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return {"idade_verificada": bool(result[0])}
    return {"idade_verificada": False}

def set_user_idade_verificada(user_id):
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO usuarios_vip (user_id, idade_verificada) VALUES (?, 0)", (user_id,))
    cursor.execute("UPDATE usuarios_vip SET idade_verificada = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    logger.info(f"Usuário {user_id} teve idade verificada e salva no DB.")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_db_info = get_user_db_info(user.id)
    estados_usuarios[user.id] = {}
    if user_db_info.get("idade_verificada", False):
        await boas_vindas_fluxo(update, context, user, is_callback=False)
    else:
        keyboard = [
            [InlineKeyboardButton("✅ Sim, tenho 18 anos ou mais", callback_data="idade_ok")],
            [InlineKeyboardButton("❌ Não tenho 18 anos", callback_data="idade_nok")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🔞 Olá! Antes de continuarmos, preciso confirmar uma coisinha...\n\n"
            "Você tem 18 anos ou mais?",
            reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN
        )

async def boas_vindas_fluxo(update: Update, context: ContextTypes.DEFAULT_TYPE, user, is_callback=True):
    mensagem_inicial_texto = ("Bom te ver por aqui... 🥰\n\nQue bom que você chegou até mim! ✨")
    if is_callback:
        try:
            await update.callback_query.edit_message_text(mensagem_inicial_texto, reply_markup=None)
        except BadRequest as e:
            logger.warning(f"Não foi possível editar mensagem em boas_vindas_fluxo para {user.id}: {e}. Enviando nova mensagem.")
            await context.bot.send_message(chat_id=user.id, text=mensagem_inicial_texto, reply_markup=None)
    else:
        await update.message.reply_text(mensagem_inicial_texto, reply_markup=None)
    await asyncio.sleep(1) # Reduzido para agilizar testes
    if VIDEO_URL:
        try:
            await context.bot.send_chat_action(chat_id=user.id, action="upload_video")
            await context.bot.send_video(chat_id=user.id, video=VIDEO_URL, caption="📹 Deixei um vídeo especial pra você...")
        except Exception as e:
            logger.error(f"Erro ao enviar vídeo ({VIDEO_URL}) para {user.id}: {e}.")
            await context.bot.send_message(chat_id=user.id, text="📹 Vídeo especial pra você... (Se não apareceu, me avise!)")
    else:
        logger.info(f"VIDEO_URL não configurado. Enviando texto alternativo para {user.id}.")
        await context.bot.send_message(chat_id=user.id, text="📹 Preparei algo especial pra você...")
    await asyncio.sleep(1) # Reduzido
    keyboard = [[InlineKeyboardButton("🔥 Quero ver os Planos VIP 🔥", callback_data="ver_planos")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=user.id,
        text="💎 Quer ter acesso a todo meu conteúdo completo no VIP?\n\n"
             "🔥 Conteúdos exclusivos\n📱 Fotos e vídeos inéditos\n"
             "💬 Interação e surpresas...\n\n"
             "👇 Clique e escolha seu plano:",
        reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data
    chat_id = user.id

    if chat_id not in estados_usuarios: estados_usuarios[chat_id] = {}
    await query.answer()

    if data == "idade_nok":
        await query.edit_message_text("❌ Que pena! Este cantinho é só para maiores de 18.\nVolte quando completar a maioridade! 😊")
        return
    elif data == "idade_ok":
        set_user_idade_verificada(user.id)
        estados_usuarios[chat_id]["idade_verificada"] = True
        await boas_vindas_fluxo(update, context, user)
        return

    if data == "ver_planos":
        keyboard = [[InlineKeyboardButton(f"💎 {p['nome']} - {p['valor']}", cb_data=f"plano_{pid}")] for pid, p in PLANOS.items()]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_text(
                "💎 **MEUS PLANOS VIP** 💎\nEscolha o que mais te agrada:\n\n"
                "🔥 **1 MÊS** - R$ 39,90\n🔥 **3 MESES** - R$ 99,90\n"
                "🔥 **6 MESES** - R$ 179,90\n🔥 **12 MESES** - R$ 289,90\n\n"
                "👇 É só clicar:",
                reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN
            )
            if "mensagem_pix_id_principal" in estados_usuarios[chat_id]:
                 del estados_usuarios[chat_id]["mensagem_pix_id_principal"]
        except BadRequest as e:
            logger.error(f"Erro ao editar para ver_planos: {e}.")

    elif data.startswith("plano_"):
        plano_id = data.replace("plano_", "")
        if plano_id in PLANOS:
            plano = PLANOS[plano_id]
            estados_usuarios[chat_id]["plano_escolhido"] = plano_id
            keyboard = [
                [InlineKeyboardButton("💳 Gerar PIX", callback_data=f"gerar_pix_{plano_id}")],
                [InlineKeyboardButton("⬅️ Voltar", callback_data="ver_planos")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"💎 **Você escolheu: {plano['nome']}**\n\n"
                f"💰 Valor: {plano['valor']}\n⏰ Duração: {plano['duracao']} dias\n\n"
                f"🔥 Acesso total, vídeos, fotos, interação e surpresas!\n\n"
                f"👇 Pronta(o)?",
                reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN
            )
            if "mensagem_pix_id_principal" in estados_usuarios[chat_id]:
                 del estados_usuarios[chat_id]["mensagem_pix_id_principal"]

    elif data.startswith("gerar_pix_"):
        plano_id = data.replace("gerar_pix_", "")
        if plano_id in PLANOS:
            plano = PLANOS[plano_id]
            pix_code = plano['pix']
            estados_usuarios[chat_id]["plano_escolhido"] = plano_id
            keyboard = [
                [InlineKeyboardButton("📋 Copiar Código PIX", callback_data=f"copiar_pix_{plano_id}")],
                [InlineKeyboardButton("✅ Já paguei! Enviar Comprovante", callback_data=f"solicitar_comprovante_{plano_id}")],
                [InlineKeyboardButton("⬅️ Voltar", callback_data="ver_planos")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"💳 **PIX - {plano['nome']}** ({plano['valor']})\n\n"
                f"🔑 **PIX (Copia e Cola):**\n`{pix_code}`\n\n"
                f"📱 **Como fazer:**\n1. Copie o código acima.\n2. Abra seu banco e cole na área PIX.\n"
                f"3. Confirme.\n4. Volte aqui e clique em 'Já paguei!'.\n\nTe espero! 😉",
                reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN
            )
            estados_usuarios[chat_id]["mensagem_pix_id_principal"] = query.message.message_id

    elif data.startswith("copiar_pix_"):
        plano_id = data.replace("copiar_pix_", "")
        if plano_id in PLANOS:
            plano = PLANOS[plano_id]
            await context.bot.send_message(chat_id=chat_id, text=f"PIX para {plano['nome']}:\n\n`{plano['pix']}`\n\nCopie e cole! 😉", parse_mode=ParseMode.MARKDOWN)
            await query.answer("Código PIX enviado no chat!", show_alert=True)

    elif data.startswith("solicitar_comprovante_"):
        plano_id = data.replace("solicitar_comprovante_", "")
        if plano_id in PLANOS:
            plano = PLANOS[plano_id]
            estados_usuarios[chat_id]["plano_escolhido"] = plano_id
            estados_usuarios[chat_id]["estado_atual"] = "aguardando_comprovante"
            try:
                await query.edit_message_text(
                    text=f"OK! {plano['nome']} ({plano['valor']}).\n\n"
                         f"Agora, por favor, me envie o print ou foto do comprovante aqui na conversa.\n\n"
                         f"Assim que eu receber e conferir, libero seu acesso! 🚀",
                    reply_markup=None, parse_mode=ParseMode.MARKDOWN
                )
                if "mensagem_pix_id_principal" in estados_usuarios[chat_id]:
                    del estados_usuarios[chat_id]["mensagem_pix_id_principal"]
            except BadRequest as e:
                logger.error(f"Erro ao editar msg para solicitar_comprovante: {e}. Enviando nova.")
                await context.bot.send_message(chat_id=chat_id, text=f"OK! {plano['nome']}.\nEnvie o comprovante aqui.")

            # LOG ADICIONAL: Confirmação de inserção no DB
            conn = sqlite3.connect(DB_NAME, check_same_thread=False)
            cursor = conn.cursor()
            try:
                cursor.execute('''
                INSERT INTO pagamentos_pendentes (user_id, username, nome, plano_id, valor, data_solicitacao, comprovante_enviado, aprovado)
                VALUES (?, ?, ?, ?, ?, ?, 0, 0)
                ''', (user.id, user.username or "N/A", user.full_name or "N/A", plano_id, plano['valor'], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                pag_pendente_id = cursor.lastrowid
                conn.commit()
                logger.info(f"CALLBACK solicitar_comprovante_: Pagamento pendente ID {pag_pendente_id} REGISTRADO para User: {user.id}, Plano: {plano_id}")
            except sqlite3.Error as e_sql:
                conn.rollback()
                logger.error(f"CALLBACK solicitar_comprovante_: ERRO SQL ao registrar pendente para User: {user.id}, Plano: {plano_id} - {e_sql}")
            finally:
                conn.close()

async def handle_comprovante(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = user.id

    if chat_id in estados_usuarios and estados_usuarios[chat_id].get("estado_atual") == "aguardando_comprovante":
        plano_id = estados_usuarios[chat_id].get("plano_escolhido")
        if not plano_id or plano_id not in PLANOS:
            await update.message.reply_text("Ops! Problema ao identificar seu plano. Tente de novo ou fale comigo.")
            return
        plano = PLANOS[plano_id]

        # LOG ADICIONAL: Confirmação de atualização do comprovante_enviado
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        cursor = conn.cursor()
        affected_rows = 0
        try:
            cursor.execute('''
            UPDATE pagamentos_pendentes SET comprovante_enviado = 1
            WHERE user_id = ? AND plano_id = ? AND aprovado = 0 ORDER BY id DESC LIMIT 1
            ''', (user.id, plano_id))
            affected_rows = cursor.rowcount
            conn.commit()
            logger.info(f"HANDLE_COMPROVANTE: Tentativa de marcar comprovante_enviado=1 para User: {user.id}, Plano: {plano_id}. Linhas afetadas: {affected_rows}")
            if affected_rows == 0:
                logger.warning(f"HANDLE_COMPROVANTE: Nenhuma linha atualizada para comprovante_enviado=1. User: {user.id}, Plano: {plano_id}. Pode já estar marcado ou não há registro pendente correspondente.")
        except sqlite3.Error as e_sql:
            conn.rollback()
            logger.error(f"HANDLE_COMPROVANTE: ERRO SQL ao marcar comprovante_enviado para User: {user.id}, Plano: {plano_id} - {e_sql}")
        finally:
            conn.close()

        if chat_id in estados_usuarios and "estado_atual" in estados_usuarios[chat_id]:
            del estados_usuarios[chat_id]["estado_atual"]

        admin_message = (
            f"🖼️💳 **NOVO COMPROVANTE!** 🎉\n\n"
            f"👤 De: {user.full_name or 'N/D'}\n🆔 ID: `{user.id}`\n📱 User: @{user.username or 'N/A'}\n"
            f"💎 Plano: {plano['nome']}\n💰 Valor: {plano['valor']}\n\n"
            f"Verifique e use:\n`/aprovar {user.id} {plano_id}`\nOu:\n`/rejeitar {user.id}`"
        )
        try:
            if update.message.photo:
                await context.bot.send_photo(SEU_USER_ID, update.message.photo[-1].file_id, caption=admin_message, parse_mode=ParseMode.MARKDOWN)
            elif update.message.document and update.message.document.mime_type.startswith("image/"):
                 await context.bot.send_document(SEU_USER_ID, update.message.document.file_id, caption=admin_message, parse_mode=ParseMode.MARKDOWN)
            else:
                await context.bot.send_message(SEU_USER_ID, f"⚠️ User {user.id} enviou arquivo não-imagem como comprovante.")
                await update.message.reply_text("📸 Humm, não parece uma imagem. Envie print ou foto do comprovante, por favor!")
                return
            await update.message.reply_text("✅ Comprovante recebido! 😊\nVou dar uma olhadinha e já te aviso sobre a liberação! ⚡")
        except Exception as e:
            logger.error(f"Erro ao encaminhar comprovante/responder user: {e}")
            await update.message.reply_text("Erro ao processar comprovante. Vou verificar!")
    else:
        logger.info(f"User {user.id} enviou mídia/doc fora do estado 'aguardando_comprovante'.")

async def aprovar_pagamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_user = update.effective_user
    if admin_user.id != SEU_USER_ID:
        await update.message.reply_text("❌ Acesso negado.")
        return
    logger.info(f"COMANDO /aprovar recebido. Args: {context.args}")

    try:
        user_id_aprovar = int(context.args[0])
        plano_id_aprovar = context.args[1]
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Formato: /aprovar <IDdoUsuario> <IDdoPlano>\nEx: /aprovar 123 1mes")
        return
    if plano_id_aprovar not in PLANOS:
        await update.message.reply_text(f"❌ ID Plano '{plano_id_aprovar}' inválido. Use: {', '.join(PLANOS.keys())}")
        return
    plano = PLANOS[plano_id_aprovar]
    logger.info(f"/aprovar: Tentando User: {user_id_aprovar}, Plano: {plano_id_aprovar} ({plano['nome']})")

    # LOG ADICIONAL PARA DIAGNÓSTICO DO ESTADO DO PAGAMENTO PENDENTE
    conn_diag = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor_diag = conn_diag.cursor()
    logger.info(f"/aprovar: DIAGNÓSTICO - Verificando pagamentos_pendentes para UserID {user_id_aprovar}, PlanoID {plano_id_aprovar}:")
    cursor_diag.execute("SELECT * FROM pagamentos_pendentes WHERE user_id = ? AND plano_id = ?", (user_id_aprovar, plano_id_aprovar))
    rows_diag = cursor_diag.fetchall()
    if rows_diag:
        for row_d in rows_diag: # id, user_id, username, nome, plano_id, valor, data_solicitacao, comprovante_enviado, aprovado
            logger.info(f"/aprovar: DIAGNÓSTICO DB - Encontrado: ID={row_d[0]}, UserID={row_d[1]}, PlanoID={row_d[4]}, ComprEnviado={row_d[7]}, Aprovado={row_d[8]}, DataSol: {row_d[6]}")
    else:
        logger.info(f"/aprovar: DIAGNÓSTICO DB - NENHUM registro encontrado em pagamentos_pendentes para UserID {user_id_aprovar} E PlanoID {plano_id_aprovar} (sem outros filtros).")
    conn_diag.close()
    # FIM DO LOG ADICIONAL

    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
    SELECT id, username, nome FROM pagamentos_pendentes
    WHERE user_id = ? AND plano_id = ? AND comprovante_enviado = 1 AND aprovado = 0
    ORDER BY id DESC LIMIT 1
    ''', (user_id_aprovar, plano_id_aprovar))
    pagamento = cursor.fetchone()

    if not pagamento:
        await update.message.reply_text(f"❌ Nenhum pagamento pendente (comprovante enviado, não aprovado) para User ID {user_id_aprovar}, Plano {plano['nome']}.\nVerifique IDs ou se já foi processado.")
        logger.warning(f"/aprovar: Pagamento não encontrado/já processado. User: {user_id_aprovar}, Plano: {plano_id_aprovar}")
        conn.close()
        return

    pagamento_db_id, user_username, user_nome = pagamento
    logger.info(f"/aprovar: Pagamento pendente (DB ID: {pagamento_db_id}) ENCONTRADO para User: {user_nome} (@{user_username})")
    data_entrada = datetime.now()
    data_expiracao = data_entrada + timedelta(days=plano['duracao'])

    try:
        cursor.execute('''
        INSERT INTO usuarios_vip (user_id, username, nome, plano_id, data_entrada, data_expiracao, ativo, idade_verificada)
        VALUES (?, ?, ?, ?, ?, ?, 1, COALESCE((SELECT idade_verificada FROM usuarios_vip WHERE user_id = ?), 0))
        ON CONFLICT(user_id) DO UPDATE SET
        username=excluded.username, nome=excluded.nome, plano_id=excluded.plano_id, data_entrada=excluded.data_entrada,
        data_expiracao=excluded.data_expiracao, ativo=1
        ''', (user_id_aprovar, user_username, user_nome, plano_id_aprovar,
              data_entrada.strftime("%Y-%m-%d %H:%M:%S"), data_expiracao.strftime("%Y-%m-%d %H:%M:%S"), user_id_aprovar))
        cursor.execute('UPDATE pagamentos_pendentes SET aprovado = 1 WHERE id = ?', (pagamento_db_id,))
        conn.commit()
        logger.info(f"/aprovar: User {user_id_aprovar} OK em usuarios_vip. Pagamento {pagamento_db_id} OK como aprovado.")
    except sqlite3.Error as e_sql:
        conn.rollback(); logger.error(f"/aprovar: ERRO SQL ao atualizar DB para {user_id_aprovar}: {e_sql}")
        await update.message.reply_text(f"❌ Erro DB ao aprovar. Tente de novo ou verifique logs. Erro: {e_sql}")
        conn.close(); return
    finally:
        conn.close()

    link_para_usuario = f"https://t.me/+9TBR6fK429tiMmRh" # Link principal como fallback
    invite_link_obj_created = False
    try:
        invite_link_obj = await context.bot.create_chat_invite_link(CANAL_VIP_ID, member_limit=1, expire_date=int(time.time()) + (3600*48))
        link_para_usuario = invite_link_obj.invite_link
        invite_link_obj_created = True
        logger.info(f"/aprovar: Link específico criado para {user_id_aprovar}: {link_para_usuario}")
    except Exception as e_link:
        logger.error(f"/aprovar: Falha ao criar link convite específico para {CANAL_VIP_ID} (User: {user_id_aprovar}): {e_link}. Usando principal.")

    msg_admin_confirm = (f"✅ **Pagamento APROVADO!**\n\n👤 User: {user_nome or user_username or 'N/A'} (ID: `{user_id_aprovar}`)\n"
                         f"💎 Plano: {plano['nome']}\n📅 Expira: {data_expiracao.strftime('%d/%m/%y %H:%M')}\n")
    msg_admin_confirm += f"🔗 Link {'específico' if invite_link_obj_created else 'principal'} enviado: {link_para_usuario}"

    try:
        await context.bot.send_message(user_id_aprovar,
            f"🎉 **PAGAMENTO APROVADO!** 🎉\n\nParabéns! Seu acesso ao VIP foi liberado! 🔥\n\n"
            f"💎 Plano: {plano['nome']}\n📅 Válido até: {data_expiracao.strftime('%d/%m/%y %H:%M')}\n\n"
            f"👇 **Clique para entrar:**\n{link_para_usuario}\n\nTe espero lá! 😘💕",
            parse_mode=ParseMode.MARKDOWN)
        logger.info(f"/aprovar: Mensagem de aprovação ENVIADA para User ID: {user_id_aprovar}")
        await update.message.reply_text(msg_admin_confirm, parse_mode=ParseMode.MARKDOWN)
    except Exception as e_msg:
        logger.error(f"/aprovar: Erro ao notificar user {user_id_aprovar} ou admin: {e_msg}")
        await update.message.reply_text(f"✅ Aprovado para {user_id_aprovar}, MAS FALHA ao enviar msg para ele(a).\nErro: {e_msg}\nEnvie o link manualmente: {link_para_usuario}")

# --- Funções rejeitar_pagamento, listar_usuarios_command, pendentes_command ---
# (Mantidas como na versão anterior, mas com check_same_thread=False para sqlite3.connect)
async def rejeitar_pagamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SEU_USER_ID: await update.message.reply_text("❌ Acesso negado."); return
    logger.info(f"COMANDO /rejeitar. Args: {context.args}")
    try: user_id_rejeitar = int(context.args[0])
    except (IndexError, ValueError): await update.message.reply_text("❌ Uso: /rejeitar <IDdoUsuario>"); return

    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pagamentos_pendentes WHERE user_id = ? AND comprovante_enviado = 1 AND aprovado = 0 ORDER BY id DESC LIMIT 1", (user_id_rejeitar,))
    deleted_rows = cursor.rowcount
    conn.commit(); conn.close()

    if deleted_rows > 0:
        logger.info(f"/rejeitar: Pagamento pendente para User {user_id_rejeitar} REMOVIDO.")
        try:
            await context.bot.send_message(user_id_rejeitar, "😔 **Pagamento não aprovado.** 😔\n\nOi! Verifiquei, mas não consegui confirmar seu pagamento.\nPor favor, verifique os dados e tente de novo, ou fale comigo pra gente resolver, tá? 😊")
            await update.message.reply_text(f"🗑️ Pagamento para {user_id_rejeitar} rejeitado/removido. Usuário notificado.")
        except Exception as e_notify_rej:
            logger.error(f"/rejeitar: Erro ao notificar user {user_id_rejeitar}: {e_notify_rej}")
            await update.message.reply_text(f"🗑️ Pagamento para {user_id_rejeitar} removido, MAS falha ao notificar. Erro: {e_notify_rej}")
    else:
        await update.message.reply_text(f"🤷‍♀️ Nenhum pagamento pendente (comprovante enviado, não aprovado) para User {user_id_rejeitar} para rejeitar.")

async def listar_usuarios_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SEU_USER_ID: await update.message.reply_text("❌ Acesso negado."); return
    conn = sqlite3.connect(DB_NAME, check_same_thread=False); cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, nome, plano_id, data_expiracao FROM usuarios_vip WHERE ativo = 1 ORDER BY datetime(data_expiracao)")
    usuarios = cursor.fetchall(); conn.close()
    if not usuarios: await update.message.reply_text("📋 Nenhum VIP ativo."); return

    texto_partes = ["📋 **ASSINANTES VIP ATIVOS**\n\n"]
    for uid, u_user, u_nome, u_pid, u_dexp_str in usuarios:
        try: u_dexp_obj = datetime.strptime(u_dexp_str, "%Y-%m-%d %H:%M:%S"); dias_rest = (u_dexp_obj - datetime.now()).days
        except ValueError: u_dexp_obj = None; dias_rest = -999
        plano_nome = PLANOS.get(u_pid, {}).get('nome', u_pid or "N/D")
        status = "🟢" if dias_rest > 7 else "🟡" if dias_rest >= 0 else "🔴"
        dexp_fmt = u_dexp_obj.strftime('%d/%m/%y %H:%M') if u_dexp_obj else "Inválida"
        dias_txt = f"{dias_rest} dias" if dias_rest >=0 else 'Expirado!'
        linha = f"{status} **{u_nome or 'N/D'}** (@{u_user or 'N/A'})\n  ID: `{uid}`\n  💎 Plano: {plano_nome}\n  📅 Exp: {dexp_fmt} ({dias_txt})\n\n"
        if len(texto_partes[-1] + linha) > 4000: texto_partes.append(linha)
        else: texto_partes[-1] += linha
    for parte in texto_partes: await update.message.reply_text(parte, parse_mode=ParseMode.MARKDOWN)

async def pendentes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SEU_USER_ID: await update.message.reply_text("❌ Acesso negado."); return
    conn = sqlite3.connect(DB_NAME, check_same_thread=False); cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, nome, plano_id, valor, data_solicitacao, comprovante_enviado FROM pagamentos_pendentes WHERE aprovado = 0 ORDER BY datetime(data_solicitacao) DESC")
    pendentes = cursor.fetchall(); conn.close()
    if not pendentes: await update.message.reply_text("👍 Nenhum pagamento pendente."); return

    texto_partes = ["💳 **PAGAMENTOS PENDENTES**\n\n"]
    for p_uid, p_user, p_nome, p_pid, p_val, p_dsol_str, p_comp in pendentes:
        stat_comp = "✅ Enviado" if p_comp else "⏳ Aguardando"
        plano_nome = PLANOS.get(p_pid, {}).get('nome', p_pid or "N/D")
        try: dsol_fmt = datetime.strptime(p_dsol_str, '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%y %H:%M')
        except ValueError: dsol_fmt = "Inválida"
        linha = f"👤 **{p_nome or 'N/D'}** (@{p_user or 'N/A'})\n  ID: `{p_uid}`\n  💎 Plano: {plano_nome} ({p_val})\n  📅 Sol: {dsol_fmt}\n  📎 Compr: {stat_comp}\n"
        if p_comp: linha += f"  👉 Use: `/aprovar {p_uid} {p_pid}` ou `/rejeitar {p_uid}`\n"
        linha += "\n"
        if len(texto_partes[-1] + linha) > 4000: texto_partes.append(linha)
        else: texto_partes[-1] += linha
    for parte in texto_partes: await update.message.reply_text(parte, parse_mode=ParseMode.MARKDOWN)

async def verificar_expirados_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("JOB: Verificando expirados...")
    conn = sqlite3.connect(DB_NAME, check_same_thread=False) # check_same_thread para JobQueue
    cursor = conn.cursor(); agora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("SELECT user_id, nome, plano_id, username FROM usuarios_vip WHERE ativo = 1 AND datetime(data_expiracao) < datetime(?)", (agora_str,))
    expirados = cursor.fetchall()
    if not expirados: logger.info("JOB: Nenhum expirado."); conn.close(); return

    ids_exp = [str(ue[0]) for ue in expirados]
    placeholders = ','.join('?' for _ in ids_exp)
    try:
        cursor.execute(f"UPDATE usuarios_vip SET ativo = 0 WHERE user_id IN ({placeholders})", ids_exp)
        conn.commit(); logger.info(f"JOB: {len(ids_exp)} users marcados inativos.")
    except sqlite3.Error as e_sql: conn.rollback(); logger.error(f"JOB: Erro SQL ao inativar: {e_sql}"); conn.close(); return
    conn.close() # Fechar antes de IO demorado

    rem_ok = 0; admin_linhas = ["🔄 **Expirados Removidos do VIP:**\n"]
    for uid, nome, pid, user_n in expirados:
        plano_n = PLANOS.get(pid, {}).get('nome', pid or "N/D")
        try:
            await context.bot.ban_chat_member(CANAL_VIP_ID, uid)
            rem_ok += 1; admin_linhas.append(f"  ✅ Removido: {nome or 'User'} (@{user_n or 'N/A'}), ID `{uid}` (Plano: {plano_n})")
            try: await context.bot.send_message(uid, f"⏰ **Seu acesso VIP expirou.**\n\nOi {nome or 'flor'}! 😊\nSeu plano **{plano_n}** acabou.\n\nQuer renovar? Me chame com /start! 😉\nObrigada! 💕")
            except Exception as e_notify: logger.warning(f"JOB: Falha ao notificar user {uid} expiração: {e_notify}")
        except Exception as e_ban: logger.error(f"JOB: Falha ao banir user {uid}: {e_ban}"); admin_linhas.append(f"  ⚠️ Falha remover: {nome or 'User'} (@{user_n or 'N/A'}), ID `{uid}`.")
    if len(admin_linhas) > 1:
        try: await context.bot.send_message(SEU_USER_ID, "\n".join(admin_linhas), parse_mode=ParseMode.MARKDOWN)
        except Exception as e_admin_notify: logger.error(f"JOB: Falha ao notificar admin expiração: {e_admin_notify}")
    logger.info(f"JOB: Verificação concluída. {rem_ok} removidos.")

async def comando_verificar_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SEU_USER_ID: await update.message.reply_text("❌ Acesso negado."); return
    await update.message.reply_text("⏳ Verificando expirados..."); await verificar_expirados_job(context)
    await update.message.reply_text("✅ Verificação concluída.")

def main():
    inicializar_banco()
    application = Application.builder().token(TOKEN).build()
    # ... (handlers como antes)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("usuarios", listar_usuarios_command))
    application.add_handler(CommandHandler("pendentes", pendentes_command))
    application.add_handler(CommandHandler("aprovar", aprovar_pagamento))
    application.add_handler(CommandHandler("rejeitar", rejeitar_pagamento))
    application.add_handler(CommandHandler("verificarvip", comando_verificar_manual))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler((filters.PHOTO | filters.Document.IMAGE) & (~filters.COMMAND), handle_comprovante))

    if application.job_queue:
        application.job_queue.run_repeating(verificar_expirados_job, interval=3600, first=60) # 1h
        logger.info("Job de verificação agendado.")
    else: logger.warning("JobQueue não disponível. Verificação automática desabilitada.")

    logger.info("Bot iniciado! Pronta para atender... ✨ (PID: %s)", os.getpid() if 'os' in globals() else 'N/A') # Log PID
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Conflict:
        logger.critical("CONFLITO DETECTADO: Outra instância do bot está rodando. Encerrando esta instância.")
        # Idealmente, você não deveria chegar aqui se o Render gerencia bem.
        # Mas se chegar, esta instância para.
    except Exception as e:
        logger.critical(f"Erro crítico não tratado no run_polling: {e}", exc_info=True)


if __name__ == '__main__':
    import os # Para loggar PID
    main()
