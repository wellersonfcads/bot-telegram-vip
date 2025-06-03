import logging
import sqlite3
import asyncio
# import threading # Removido pois não estávamos usando a thread separada do jeito antigo
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest # Importar BadRequest para tratamento específico

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configurações - ALTERE AQUI
TOKEN = "7963030995:AAE8K5RIFJpaOhxLnDxJ4k614wnq4n549AQ" # SEU TOKEN DO BOTFATHER
SEU_USER_ID = 6150001511  # Seu user ID para receber notificações e administrar
CANAL_VIP_ID = "-1002280243232"  # ID do seu canal VIP (numérico, com -100...)

# Dados dos planos
PLANOS = {
    "1mes": {"nome": "Plano VIP 1 mês", "valor": "R$ 39,90", "duracao": 30, "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540539.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA6207050363044086"},
    "3meses": {"nome": "Plano VIP 3 meses", "valor": "R$ 99,90", "duracao": 90, "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540599.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA6207050363041E24"},
    "6meses": {"nome": "Plano VIP 6 meses", "valor": "R$ 179,90", "duracao": 180, "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406179.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA6207050363043084"},
    "12meses": {"nome": "Plano VIP 12 meses", "valor": "R$ 289,90", "duracao": 365, "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406289.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA620705036304CD13"}
}

VIDEO_URL = "" # COLOQUE O FILE_ID DO SEU VÍDEO AQUI QUANDO TIVER
# Exemplo: VIDEO_URL = "BAACAgIAAxkBAAIBlGZ3_NdJb0y4p4Q38GNBq9B5jWOkAAJJSQAC7vJZSDKr1KzCQuvQNAQ"

estados_usuarios = {}
DB_NAME = 'usuarios_vip.db'

def inicializar_banco():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Tabela usuarios_vip (assinantes ativos/expirados)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS usuarios_vip (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        nome TEXT,
        plano_id TEXT,
        data_entrada TEXT,
        data_expiracao TEXT,
        ativo INTEGER DEFAULT 1,
        idade_verificada INTEGER DEFAULT 0
    )
    ''')
    # Tabela pagamentos_pendentes (controle de quem solicitou e aguarda aprovação)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pagamentos_pendentes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        nome TEXT,
        plano_id TEXT,
        valor TEXT,
        data_solicitacao TEXT,
        comprovante_enviado INTEGER DEFAULT 0,
        aprovado INTEGER DEFAULT 0,
        mensagem_pix_id_principal INTEGER -- ID da mensagem que mostra o PIX e botões de pagamento
    )
    ''')
    conn.commit()
    conn.close()

def get_user_db_info(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT idade_verificada FROM usuarios_vip WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return {"idade_verificada": bool(result[0])}
    return {"idade_verificada": False}

def set_user_idade_verificada(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Garante que o usuário exista na tabela antes de tentar atualizar, ou insere com idade_verificada = 0 se não existir
    cursor.execute("INSERT OR IGNORE INTO usuarios_vip (user_id, idade_verificada) VALUES (?, 0)", (user_id,))
    cursor.execute("UPDATE usuarios_vip SET idade_verificada = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    logger.info(f"Usuário {user_id} teve idade verificada e salva no DB.")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_db_info = get_user_db_info(user.id)
    estados_usuarios[user.id] = {} # Limpa estados anteriores para este usuário

    if user_db_info.get("idade_verificada", False):
        logger.info(f"Usuário {user.id} já tem idade verificada. Pulando para boas vindas.")
        await boas_vindas_fluxo(update, context, user, is_callback=False)
    else:
        logger.info(f"Usuário {user.id} precisa verificar a idade.")
        keyboard = [
            [InlineKeyboardButton("✅ Sim, tenho 18 anos ou mais", callback_data="idade_ok")],
            [InlineKeyboardButton("❌ Não tenho 18 anos", callback_data="idade_nok")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🔞 Olá! Antes de continuarmos, preciso confirmar uma coisinha...\n\n"
            "Você tem 18 anos ou mais?",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

async def boas_vindas_fluxo(update: Update, context: ContextTypes.DEFAULT_TYPE, user, is_callback=True):
    mensagem_inicial_texto = ("Bom te ver por aqui... 🥰\n\n"
                              "Que bom que você chegou até mim! ✨")
    if is_callback:
        try:
            await update.callback_query.edit_message_text(mensagem_inicial_texto, reply_markup=None)
        except BadRequest as e: # Se a mensagem original não puder ser editada (ex: muito antiga)
            logger.warning(f"Não foi possível editar mensagem em boas_vindas_fluxo para {user.id}: {e}. Enviando nova mensagem.")
            await context.bot.send_message(chat_id=user.id, text=mensagem_inicial_texto, reply_markup=None)
    else:
        await update.message.reply_text(mensagem_inicial_texto, reply_markup=None)

    await asyncio.sleep(2)

    if VIDEO_URL: # Somente tenta enviar se VIDEO_URL estiver preenchido
        try:
            await context.bot.send_chat_action(chat_id=user.id, action="upload_video")
            await context.bot.send_video(
                chat_id=user.id,
                video=VIDEO_URL,
                caption="📹 Deixei um vídeo especial pra você conhecer um pouquinho do meu trabalho..."
            )
        except Exception as e:
            logger.error(f"Erro ao enviar vídeo ({VIDEO_URL}) para {user.id}: {e}. Enviando texto alternativo.")
            await context.bot.send_message(
                chat_id=user.id,
                text="📹 Deixei um vídeo especial pra você conhecer um pouquinho do meu trabalho... (Se o vídeo não apareceu, me avise!)"
            )
    else: # Se VIDEO_URL estiver vazio
        logger.info(f"VIDEO_URL não configurado. Enviando mensagem de texto em vez de vídeo para {user.id}.")
        await context.bot.send_message(
            chat_id=user.id,
            text="📹 Preparei algo especial pra você conhecer um pouquinho do meu trabalho..." # Mensagem genérica se não houver vídeo
        )

    await asyncio.sleep(3)
    keyboard = [[InlineKeyboardButton("🔥 Quero ver os Planos VIP 🔥", callback_data="ver_planos")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=user.id,
        text="💎 Quer ter acesso a todo meu conteúdo completo no VIP?\n\n"
             "🔥 Conteúdos exclusivos toda semana\n"
             "📱 Fotos e vídeos inéditos que você não vê em nenhum outro lugar\n"
             "💬 Interação e surpresas especiais...\n\n"
             "👇 Clique no botão abaixo e escolha seu plano:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data
    chat_id = user.id

    if chat_id not in estados_usuarios: estados_usuarios[chat_id] = {}
    await query.answer()

    if data == "idade_nok":
        await query.edit_message_text(
            "❌ Que pena! Este cantinho é apenas para maiores de 18 anos.\n\n"
            "Volte quando completar a maioridade! 😊"
        )
        return
    elif data == "idade_ok":
        set_user_idade_verificada(user.id)
        estados_usuarios[chat_id]["idade_verificada"] = True
        await boas_vindas_fluxo(update, context, user)
        return

    # Lógica para limpar a mensagem do PIX se o usuário navegar para outro lugar
    # (Exceto se estiver no fluxo de copiar pix ou confirmar pagamento)
    # Esta lógica foi simplificada pois a deleção específica será tratada no fluxo de `solicitar_comprovante`
    # ou a mensagem será editada.

    if data == "ver_planos":
        # Se uma mensagem de PIX estava ativa (mensagem_pix_id_principal), ela será editada agora.
        # Se o usuário volta para os planos, a mensagem que continha o PIX será substituída pela lista de planos.
        keyboard = []
        for plano_id_key, plano_info in PLANOS.items():
            keyboard.append([InlineKeyboardButton(
                f"💎 {plano_info['nome']} - {plano_info['valor']}",
                callback_data=f"plano_{plano_id_key}"
            )])
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_text(
                "💎 **MEUS PLANOS VIP** 💎\n\n"
                "Escolha o que mais te agrada e vem se divertir comigo:\n\n"
                # ... (lista de planos como antes)
                "🔥 **1 MÊS DE ACESSO** - R$ 39,90\n"
                "🔥 **3 MESES DE ACESSO** - R$ 99,90 *(O mais pedido!)*\n"
                "🔥 **6 MESES DE ACESSO** - R$ 179,90 *(Melhor custo-benefício!)*\n"
                "🔥 **12 MESES DE ACESSO** - R$ 289,90 *(Acesso VIP total por 1 ano!)*\n\n"
                "👇 É só clicar no plano que você quer:",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            if "mensagem_pix_id_principal" in estados_usuarios[chat_id]:
                 del estados_usuarios[chat_id]["mensagem_pix_id_principal"] # Mensagem foi transformada
        except BadRequest as e:
            logger.error(f"Erro ao editar para ver_planos: {e}. Message_id: {query.message.message_id if query.message else 'N/A'}")
            # Pode enviar uma nova mensagem como fallback se a edição falhar
            await context.bot.send_message(chat_id, "Tive um problema ao mostrar os planos, tente novamente com /start por favor.")


    elif data.startswith("plano_"):
        plano_id = data.replace("plano_", "")
        if plano_id in PLANOS:
            plano = PLANOS[plano_id]
            estados_usuarios[chat_id]["plano_escolhido"] = plano_id
            keyboard = [
                [InlineKeyboardButton("💳 Gerar PIX para Pagamento", callback_data=f"gerar_pix_{plano_id}")],
                [InlineKeyboardButton("⬅️ Voltar aos planos", callback_data="ver_planos")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"💎 **Você escolheu: {plano['nome']}**\n\n"
                # ... (descrição do plano como antes)
                f"💰 **Valor:** {plano['valor']}\n"
                f"⏰ **Duração do Acesso:** {plano['duracao']} dias de pura diversão!\n\n"
                f"🔥 **O que te espera no VIP:**\n"
                f"📱 Acesso total ao meu cantinho secreto no Telegram\n"
                f"🎬 Vídeos exclusivos que faço só pra assinantes\n"
                f"📸 Fotos inéditas e picantes todos os dias\n"
                f"💬 Nossa interação mais próxima e surpresas que preparo com carinho!\n\n"
                f"👇 Pronta(o) para garantir seu acesso?",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            if "mensagem_pix_id_principal" in estados_usuarios[chat_id]:
                 del estados_usuarios[chat_id]["mensagem_pix_id_principal"] # Mensagem foi transformada

    elif data.startswith("gerar_pix_"):
        plano_id = data.replace("gerar_pix_", "")
        if plano_id in PLANOS:
            plano = PLANOS[plano_id]
            pix_code = plano['pix']
            estados_usuarios[chat_id]["plano_escolhido"] = plano_id

            keyboard = [
                [InlineKeyboardButton("📋 Copiar Código PIX", callback_data=f"copiar_pix_{plano_id}")],
                [InlineKeyboardButton("✅ Já paguei! Enviar Comprovante", callback_data=f"solicitar_comprovante_{plano_id}")],
                [InlineKeyboardButton("⬅️ Voltar aos planos", callback_data="ver_planos")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"💳 **PIX para Pagamento - {plano['nome']}**\n\n"
                # ... (mensagem do PIX como antes)
                f"💰 **Valor:** {plano['valor']}\n\n"
                f"🔑 **Meu PIX (Copia e Cola):**\n"
                f"`{pix_code}`\n\n"
                f"📱 **Como fazer:**\n"
                f"1️⃣ Clique em 'Copiar Código PIX' (vou te mandar o código separado também!)\n"
                f"2️⃣ Abra o app do seu banco\n"
                f"3️⃣ Escolha a opção PIX Copia e Cola\n"
                f"4️⃣ Cole o código e confirme o pagamento\n"
                f"5️⃣ Volte aqui e clique em 'Já paguei! Enviar Comprovante'\n\n"
                f"Te espero lá no VIP! 😉",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            # Armazena o ID da mensagem que agora mostra o PIX e os botões de pagamento.
            estados_usuarios[chat_id]["mensagem_pix_id_principal"] = query.message.message_id

    elif data.startswith("copiar_pix_"):
        plano_id = data.replace("copiar_pix_", "")
        if plano_id in PLANOS:
            plano = PLANOS[plano_id]
            pix_code = plano['pix']
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Aqui está o código PIX para o {plano['nome']} ({plano['valor']}):\n\n`{pix_code}`\n\nÉ só copiar e colar no seu app do banco! 😉",
                parse_mode=ParseMode.MARKDOWN
            )
            await query.answer("Código PIX enviado no chat para facilitar a cópia! ✅", show_alert=True)

    elif data.startswith("solicitar_comprovante_"):
        plano_id = data.replace("solicitar_comprovante_", "")
        if plano_id in PLANOS:
            plano = PLANOS[plano_id]
            estados_usuarios[chat_id]["plano_escolhido"] = plano_id # Garante que está salvo
            estados_usuarios[chat_id]["estado_atual"] = "aguardando_comprovante"

            # Edita a mensagem ATUAL (onde o botão "Já paguei" foi clicado)
            # para instruir o envio do comprovante.
            try:
                await query.edit_message_text(
                    text=f"OK! Você escolheu o {plano['nome']} ({plano['valor']}).\n\n"
                         f"Agora preciso que você me envie o comprovante do pagamento, por favor 😊.\n"
                         f"Pode ser um print da tela do seu app do banco ou uma foto do comprovante.\n\n"
                         f"É só anexar a imagem e enviar aqui na nossa conversa.\n\n"
                         f"Assim que eu receber e conferir, libero seu acesso VIP rapidinho! 🚀",
                    reply_markup=None, # Remove botões anteriores
                    parse_mode=ParseMode.MARKDOWN
                )
                # A mensagem que mostrava o PIX foi transformada, então removemos a referência.
                if "mensagem_pix_id_principal" in estados_usuarios[chat_id]:
                    del estados_usuarios[chat_id]["mensagem_pix_id_principal"]
            except BadRequest as e:
                logger.error(f"Erro ao editar mensagem para solicitar_comprovante: {e}. Message_id: {query.message.message_id}. Enviando nova mensagem de instrução.")
                # Fallback: se a edição falhar (ex: mensagem muito antiga ou deletada), envia uma nova.
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"OK! Para o {plano['nome']} ({plano['valor']}).\n\n"
                         f"Agora preciso que você me envie o comprovante do pagamento, por favor 😊.\n"
                         f"Pode ser um print da tela do seu app do banco ou uma foto do comprovante.\n\n"
                         f"É só anexar a imagem e enviar aqui na nossa conversa.\n\n"
                         f"Assim que eu receber e conferir, libero seu acesso VIP rapidinho! 🚀",
                    parse_mode=ParseMode.MARKDOWN
                )


            # Registrar no banco de dados que um pagamento está pendente
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO pagamentos_pendentes
            (user_id, username, nome, plano_id, valor, data_solicitacao, comprovante_enviado, aprovado, mensagem_pix_id_principal)
            VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)
            ''', (
                user.id,
                user.username or "N/A",
                user.full_name or "N/A",
                plano_id,
                plano['valor'],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                query.message.message_id # Armazenando o ID da mensagem que foi editada (originalmente mostrava o PIX)
                                         # Isso pode não ser mais necessário aqui se a mensagem é transformada
            ))
            conn.commit()
            conn.close()

async def handle_comprovante(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = user.id

    if chat_id in estados_usuarios and estados_usuarios[chat_id].get("estado_atual") == "aguardando_comprovante":
        plano_id = estados_usuarios[chat_id].get("plano_escolhido")
        if not plano_id or plano_id not in PLANOS:
            await update.message.reply_text("Ops! Parece que houve um problema ao identificar seu plano. Por favor, tente selecionar o plano novamente ou fale comigo.")
            return

        plano = PLANOS[plano_id]

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        # Atualiza o pagamento pendente mais recente para este usuário e plano
        cursor.execute('''
        UPDATE pagamentos_pendentes
        SET comprovante_enviado = 1
        WHERE user_id = ? AND plano_id = ? AND aprovado = 0
        ORDER BY id DESC LIMIT 1
        ''', (user.id, plano_id))
        conn.commit()
        conn.close()

        # Limpa o estado APÓS o processamento bem-sucedido
        # estados_usuarios[chat_id]["estado_atual"] = None # Ou del estados_usuarios[chat_id]["estado_atual"]
        # É melhor limpar o estado específico, ou resetar o dict se o fluxo terminou
        if chat_id in estados_usuarios and "estado_atual" in estados_usuarios[chat_id]:
            del estados_usuarios[chat_id]["estado_atual"]


        admin_message = (
            f"🖼️ 💳 **NOVO COMPROVANTE RECEBIDO!** 🎉\n\n"
            f"👤 **De:** {user.full_name or 'Nome não disponível'}\n"
            f"🆔 **ID:** `{user.id}`\n"
            f"📱 **Username:** @{user.username or 'Não tem'}\n"
            f"💎 **Plano Escolhido:** {plano['nome']}\n"
            f"💰 **Valor:** {plano['valor']}\n\n"
            f"Verifique o comprovante e, se estiver tudo OK, use:\n"
            f"`/aprovar {user.id} {plano_id}`\n\n"
            f"Se precisar rejeitar:\n"
            f"`/rejeitar {user.id}`"
        )

        try:
            if update.message.photo:
                await context.bot.send_photo(
                    chat_id=SEU_USER_ID, photo=update.message.photo[-1].file_id,
                    caption=admin_message, parse_mode=ParseMode.MARKDOWN
                )
            elif update.message.document and update.message.document.mime_type.startswith("image/"):
                 await context.bot.send_document(
                    chat_id=SEU_USER_ID, document=update.message.document.file_id,
                    caption=admin_message, parse_mode=ParseMode.MARKDOWN
                )
            else: # Se não for foto nem documento de imagem
                await context.bot.send_message(
                    SEU_USER_ID,
                    f"⚠️ O usuário {user.full_name} (ID: `{user.id}`) enviou um arquivo que não é uma imagem como comprovante para o plano {plano['nome']}.\n"
                    f"Tipo do arquivo: {update.message.document.mime_type if update.message.document else 'Não é documento'}.\n"
                    f"Por favor, peça para enviarem uma imagem (print ou foto)."
                )
                await update.message.reply_text(
                    "📸 Humm, parece que você não enviou uma imagem. Por favor, envie o print da tela do seu banco ou uma foto do comprovante para eu poder analisar! Se tiver dificuldades, me avise. 😊"
                )
                return # Não continua se o comprovante não for imagem

            await update.message.reply_text(
                "✅ Comprovante recebido com sucesso!\n\n"
                "Obrigada! 😊 Já recebi seu comprovante e vou dar uma olhadinha agora mesmo.\n\n"
                "⚡ Assim que eu confirmar, seu acesso será liberado e te aviso aqui!\n\n"
                "Enquanto isso, que tal dar uma espiadinha no meu Instagram? 😉 (coloque seu @ aqui se quiser)"
            )
        except Exception as e:
            logger.error(f"Erro ao encaminhar comprovante para admin ou responder usuário: {e}")
            await update.message.reply_text("Ocorreu um erro ao processar seu comprovante. Vou verificar e te aviso!")
            await context.bot.send_message(SEU_USER_ID, f"⚠️ Erro ao processar comprovante do usuário {user.id} para o plano {plano_id}: {e}")
    else:
        # Se o usuário enviar uma foto/documento fora do fluxo de comprovante
        # Não responder nada para não ser intrusivo, ou uma mensagem genérica se achar necessário.
        logger.info(f"Usuário {user.id} enviou mídia/documento fora do estado 'aguardando_comprovante'.")


async def aprovar_pagamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_user = update.effective_user
    if admin_user.id != SEU_USER_ID:
        await update.message.reply_text("❌ Acesso negado. Este comando é só para a admin aqui! 😉")
        return

    logger.info(f"Comando /aprovar recebido pelo admin {admin_user.id}. Argumentos: {context.args}")

    try:
        user_id_aprovar = int(context.args[0])
        plano_id_aprovar = context.args[1]
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Formato incorreto! Use: /aprovar <IDdoUsuario> <IDdoPlano>\nExemplo: /aprovar 123456789 1mes")
        logger.warning(f"/aprovar: Formato incorreto dos argumentos: {context.args}")
        return

    if plano_id_aprovar not in PLANOS:
        await update.message.reply_text(f"❌ ID de Plano '{plano_id_aprovar}' não é válido. Planos disponíveis: {', '.join(PLANOS.keys())}")
        logger.warning(f"/aprovar: ID de plano inválido: {plano_id_aprovar}")
        return

    plano = PLANOS[plano_id_aprovar]
    logger.info(f"/aprovar: Tentando aprovar User ID: {user_id_aprovar}, Plano ID: {plano_id_aprovar} ({plano['nome']})")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Busca o pagamento pendente MAIS RECENTE para este usuário e plano que tenha comprovante e não esteja aprovado
    cursor.execute('''
    SELECT id, username, nome FROM pagamentos_pendentes
    WHERE user_id = ? AND plano_id = ? AND comprovante_enviado = 1 AND aprovado = 0
    ORDER BY id DESC LIMIT 1
    ''', (user_id_aprovar, plano_id_aprovar))
    pagamento = cursor.fetchone()

    if not pagamento:
        await update.message.reply_text(f"❌ Nenhum pagamento pendente encontrado para o usuário ID {user_id_aprovar} com o plano {plano['nome']} que tenha enviado comprovante, ou já foi aprovado.\nVerifique o ID do usuário e o ID do plano.")
        logger.warning(f"/aprovar: Pagamento não encontrado ou já processado para User ID: {user_id_aprovar}, Plano ID: {plano_id_aprovar}")
        conn.close()
        return

    pagamento_db_id, user_username, user_nome = pagamento
    logger.info(f"/aprovar: Pagamento pendente encontrado (DB ID: {pagamento_db_id}) para User: {user_nome} (@{user_username})")

    data_entrada = datetime.now()
    data_expiracao = data_entrada + timedelta(days=plano['duracao'])

    try:
        # Adicionar ou atualizar na tabela de usuários VIP
        cursor.execute('''
        INSERT INTO usuarios_vip (user_id, username, nome, plano_id, data_entrada, data_expiracao, ativo, idade_verificada)
        VALUES (?, ?, ?, ?, ?, ?, 1, (SELECT idade_verificada FROM usuarios_vip WHERE user_id = ?))
        ON CONFLICT(user_id) DO UPDATE SET
        username=excluded.username, nome=excluded.nome, plano_id=excluded.plano_id, data_entrada=excluded.data_entrada,
        data_expiracao=excluded.data_expiracao, ativo=1
        ''', (
            user_id_aprovar, user_username, user_nome, plano_id_aprovar,
            data_entrada.strftime("%Y-%m-%d %H:%M:%S"),
            data_expiracao.strftime("%Y-%m-%d %H:%M:%S"),
            user_id_aprovar # para a subquery COALESCE( (SELECT idade_verificada FROM usuarios_vip WHERE user_id = excluded.user_id), 0 )
        ))
        # Marcar como aprovado na tabela de pagamentos_pendentes
        cursor.execute('UPDATE pagamentos_pendentes SET aprovado = 1 WHERE id = ?', (pagamento_db_id,))
        conn.commit()
        logger.info(f"/aprovar: Usuário {user_id_aprovar} atualizado/inserido em usuarios_vip. Pagamento {pagamento_db_id} marcado como aprovado.")
    except sqlite3.Error as e_sql:
        conn.rollback()
        logger.error(f"/aprovar: Erro de SQLite ao atualizar DB para {user_id_aprovar}: {e_sql}")
        await update.message.reply_text(f"❌ Ocorreu um erro interno (DB) ao tentar aprovar o usuário. Tente novamente ou verifique os logs. Erro: {e_sql}")
        conn.close()
        return
    finally:
        conn.close()


    link_convite_canal_principal = f"https://t.me/+9TBR6fK429tiMmRh"
    link_para_usuario = link_convite_canal_principal # Default

    try:
        # Tentar criar um link de convite específico (mais seguro)
        invite_link_obj = await context.bot.create_chat_invite_link(
            chat_id=CANAL_VIP_ID,
            member_limit=1,
            expire_date=int(time.time()) + (60 * 60 * 24 * 2)  # Link válido por 2 dias
        )
        link_para_usuario = invite_link_obj.invite_link
        logger.info(f"/aprovar: Link de convite específico criado para {user_id_aprovar} no canal {CANAL_VIP_ID}: {link_para_usuario}")
    except Exception as e_link:
        logger.error(f"/aprovar: Não foi possível criar link de convite específico para {CANAL_VIP_ID} (User: {user_id_aprovar}): {e_link}. Usando link principal.")
        # A mensagem para o admin informará que o link principal foi usado.

    mensagem_confirmacao_admin = (
        f"✅ **Pagamento aprovado com sucesso!**\n\n"
        f"👤 Usuário: {user_nome or user_username or 'N/A'} (ID: `{user_id_aprovar}`)\n"
        f"💎 Plano: {plano['nome']}\n"
        f"📅 Válido até: {data_expiracao.strftime('%d/%m/%Y às %H:%M')}\n"
    )
    if link_para_usuario == link_convite_canal_principal and invite_link_obj is None: # Checa se fallback ocorreu
         mensagem_confirmacao_admin += f"🔗 Link principal enviado ao usuário (falha ao criar link específico)."
    else:
         mensagem_confirmacao_admin += f"🔗 Link específico enviado: {link_para_usuario}"


    try:
        await context.bot.send_message(
            chat_id=user_id_aprovar,
            text=f"🎉 **UAU! PAGAMENTO APROVADO!** 🎉\n\n"
                 f"Parabéns, meu amor! Seu pagamento foi confirmado e seu acesso ao VIP está liberado! 🔥\n\n"
                 f"💎 **Seu plano:** {plano['nome']}\n"
                 f"📅 **Válido até:** {data_expiracao.strftime('%d/%m/%Y às %H:%M')}\n\n"
                 f"👇 **Clique no link abaixo para entrar no nosso paraíso:**\n"
                 f"{link_para_usuario}\n\n"
                 f"Mal posso esperar para te ver lá dentro! 😘💕\n\n"
                 f"Qualquer dúvida, é só me chamar! 🥰",
            parse_mode=ParseMode.MARKDOWN
        )
        logger.info(f"/aprovar: Mensagem de aprovação enviada para User ID: {user_id_aprovar}")
        await update.message.reply_text(mensagem_confirmacao_admin, parse_mode=ParseMode.MARKDOWN)

    except Exception as e_msg:
        logger.error(f"/aprovar: Erro ao notificar usuário {user_id_aprovar} ou admin sobre aprovação: {e_msg}")
        # Mesmo se a notificação falhar, o usuário foi aprovado no DB.
        # O admin recebe uma mensagem indicando a falha na notificação.
        await update.message.reply_text(
            f"✅ Pagamento aprovado para {user_id_aprovar} no sistema, mas *falhei ao enviar a mensagem de confirmação para ele(a)*.\n"
            f"Erro: {e_msg}\n"
            f"Você pode precisar enviar o link manualmente: {link_para_usuario}"
        )

# ... (restante das funções: rejeitar_pagamento, listar_usuarios_command, pendentes_command, verificar_expirados_job, comando_verificar_manual, main)
# Essas funções podem permanecer como na versão anterior, a menos que necessitem de ajustes baseados nestas mudanças.
# Vou incluir a main e a estrutura dos jobs para completude.

async def rejeitar_pagamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SEU_USER_ID:
        await update.message.reply_text("❌ Acesso negado.")
        return

    logger.info(f"Comando /rejeitar recebido. Argumentos: {context.args}")
    try:
        user_id_rejeitar = int(context.args[0])
        # Opcional: aceitar um motivo para a rejeição
        # motivo = " ".join(context.args[1:]) if len(context.args) > 1 else "Não especificado."
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Uso: /rejeitar <IDdoUsuario>")
        logger.warning(f"/rejeitar: Formato incorreto dos argumentos: {context.args}")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Deleta o pagamento pendente MAIS RECENTE para este usuário que tenha comprovante e não esteja aprovado
    cursor.execute('''
    DELETE FROM pagamentos_pendentes
    WHERE user_id = ? AND comprovante_enviado = 1 AND aprovado = 0
    ORDER BY id DESC LIMIT 1
    ''', (user_id_rejeitar,))
    deleted_rows = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted_rows > 0:
        logger.info(f"/rejeitar: Pagamento pendente para User ID {user_id_rejeitar} removido do DB.")
        try:
            await context.bot.send_message(
                chat_id=user_id_rejeitar,
                text="😔 **Pagamento não aprovado** 😔\n\n"
                     "Oi, meu bem. Verifiquei seu comprovante, mas infelizmente não consegui confirmar seu pagamento desta vez.\n\n"
                     "Pode ter sido algum probleminha com o comprovante ou com os dados.\n\n"
                     "Por favor, verifique tudo direitinho e, se quiser, pode tentar me enviar novamente ou falar comigo para a gente resolver, tá bom?\n\n"
                     "Estou aqui para te ajudar! 😊"
            )
            await update.message.reply_text(f"🗑️ Pagamento pendente para o usuário {user_id_rejeitar} foi marcado como rejeitado/removido e ele(a) foi notificado(a).")
        except Exception as e_notify_rej:
            logger.error(f"/rejeitar: Erro ao notificar usuário {user_id_rejeitar} sobre rejeição: {e_notify_rej}")
            await update.message.reply_text(f"🗑️ Pagamento pendente para {user_id_rejeitar} removido, mas falha ao notificar o usuário. Erro: {e_notify_rej}")
    else:
        await update.message.reply_text(f"🤷‍♀️ Nenhum pagamento pendente (com comprovante enviado e não aprovado) encontrado para o usuário {user_id_rejeitar} para rejeitar.")
        logger.info(f"/rejeitar: Nenhum pagamento pendente elegível encontrado para User ID {user_id_rejeitar}.")


async def listar_usuarios_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SEU_USER_ID:
        await update.message.reply_text("❌ Acesso negado.")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
    SELECT user_id, username, nome, plano_id, data_expiracao
    FROM usuarios_vip
    WHERE ativo = 1
    ORDER BY datetime(data_expiracao) -- Ordenar corretamente por data
    ''')
    usuarios = cursor.fetchall()
    conn.close()

    if not usuarios:
        await update.message.reply_text("📋 Nenhum usuário VIP ativo no momento.")
        return

    texto_partes = ["📋 **MEUS ASSINANTES VIP ATIVOS**\n\n"]
    for usuario_db in usuarios:
        uid, u_username, u_nome, u_plano_id, u_data_exp_str = usuario_db
        try:
            u_data_exp_obj = datetime.strptime(u_data_exp_str, "%Y-%m-%d %H:%M:%S")
            dias_restantes = (u_data_exp_obj - datetime.now()).days
        except ValueError: # Caso a data no DB esteja em formato inesperado
            u_data_exp_obj = None
            dias_restantes = -999 # Indica erro ou expiração
            logger.error(f"Formato de data inválido no DB para user {uid}: {u_data_exp_str}")


        plano_nome_display = PLANOS.get(u_plano_id, {}).get('nome', u_plano_id if u_plano_id else "N/D")

        status_emoji = "🟢" if dias_restantes > 7 else "🟡" if dias_restantes >= 0 else "🔴"
        data_exp_formatada = u_data_exp_obj.strftime('%d/%m/%Y às %H:%M') if u_data_exp_obj else "Data Inválida"
        dias_rest_texto = f"{dias_restantes} dias" if dias_restantes >=0 else 'Expirado!'

        linha = (f"{status_emoji} **{u_nome or 'Nome não disponível'}** (@{u_username or 'N/A'})\n"
                 f"   🆔 ID: `{uid}`\n"
                 f"   💎 Plano: {plano_nome_display}\n"
                 f"   📅 Expira em: {data_exp_formatada}\n"
                 f"   ⏳ Restam: {dias_rest_texto}\n\n")

        if len(texto_partes[-1] + linha) > 4000: # Telegram tem limite de ~4096 chars
            texto_partes.append(linha)
        else:
            texto_partes[-1] += linha

    for parte in texto_partes:
        await update.message.reply_text(parte, parse_mode=ParseMode.MARKDOWN)


async def pendentes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SEU_USER_ID:
        await update.message.reply_text("❌ Acesso negado.")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
    SELECT user_id, username, nome, plano_id, valor, data_solicitacao, comprovante_enviado
    FROM pagamentos_pendentes
    WHERE aprovado = 0
    ORDER BY datetime(data_solicitacao) DESC -- Ordenar por data
    ''')
    pendentes = cursor.fetchall()
    conn.close()

    if not pendentes:
        await update.message.reply_text("👍 Nenhum pagamento pendente no momento. Tudo em dia!")
        return

    texto_partes = ["💳 **PAGAMENTOS PENDENTES DE APROVAÇÃO**\n\n"]
    for pag_pendente in pendentes:
        p_uid, p_username, p_nome, p_plano_id, p_valor, p_data_sol_str, p_comprovante = pag_pendente
        status_comp = "✅ Comprovante Enviado" if p_comprovante else "⏳ Aguardando Comprovante"
        plano_nome_display = PLANOS.get(p_plano_id, {}).get('nome', p_plano_id if p_plano_id else "N/D")
        try:
            data_sol_formatada = datetime.strptime(p_data_sol_str, '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%y %H:%M')
        except ValueError:
            data_sol_formatada = "Data Inválida"
            logger.error(f"Formato de data inválido em pag_pendentes para user {p_uid}: {p_data_sol_str}")


        linha = (f"👤 **{p_nome or 'Nome não disponível'}** (@{p_username or 'N/A'})\n"
                 f"   🆔 ID: `{p_uid}`\n"
                 f"   💎 Plano: {plano_nome_display} ({p_valor})\n"
                 f"   📅 Solicitado em: {data_sol_formatada}\n"
                 f"   📎 Comprovante: {status_comp}\n")

        if p_comprovante:
            linha += f"   👉 Use: `/aprovar {p_uid} {p_plano_id}` ou `/rejeitar {p_uid}`\n"
        linha += "\n"

        if len(texto_partes[-1] + linha) > 4000:
            texto_partes.append(linha)
        else:
            texto_partes[-1] += linha

    for parte in texto_partes:
        await update.message.reply_text(parte, parse_mode=ParseMode.MARKDOWN)


async def verificar_expirados_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("JOB: Iniciando verificação de usuários expirados...")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    agora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute('''
    SELECT user_id, nome, plano_id, username FROM usuarios_vip
    WHERE ativo = 1 AND datetime(data_expiracao) < datetime(?)
    ''', (agora_str,)) # Usar datetime() no SQL para comparação correta
    usuarios_expirados = cursor.fetchall()

    if not usuarios_expirados:
        logger.info("JOB: Nenhum usuário expirado encontrado.")
        conn.close()
        return

    user_ids_expirados_str = [str(ue[0]) for ue in usuarios_expirados]
    placeholders = ','.join('?' for _ in user_ids_expirados_str)
    try:
        cursor.execute(f'''
        UPDATE usuarios_vip SET ativo = 0
        WHERE user_id IN ({placeholders})
        ''', user_ids_expirados_str)
        conn.commit()
        logger.info(f"JOB: {len(user_ids_expirados_str)} usuários marcados como inativos no DB.")
    except sqlite3.Error as e_sql_update:
        conn.rollback()
        logger.error(f"JOB: Erro SQLite ao marcar usuários como inativos: {e_sql_update}")
        conn.close()
        return # Não prosseguir se a atualização do DB falhar

    conn.close() # Fechar conexão antes de chamadas de API demoradas

    removidos_sucesso_count = 0
    admin_msg_linhas = ["🔄 **Assinaturas Expiradas e Usuários Removidos do VIP:**\n"]

    for user_id, nome, plano_id_exp, username_exp in usuarios_expirados:
        plano_nome_exp_display = PLANOS.get(plano_id_exp, {}).get('nome', plano_id_exp if plano_id_exp else "N/D")
        try:
            await context.bot.ban_chat_member(chat_id=CANAL_VIP_ID, user_id=user_id)
            # Se quiser que possam reassinar facilmente e entrar com novo link, descomente o unban:
            # await asyncio.sleep(1) # Pequena pausa antes de unban, se necessário
            # await context.bot.unban_chat_member(chat_id=CANAL_VIP_ID, user_id=user_id, only_if_banned=True)
            logger.info(f"JOB: Usuário {user_id} ({nome}) banido do canal {CANAL_VIP_ID} por expiração.")
            removidos_sucesso_count += 1
            admin_msg_linhas.append(f"  ✅ Removido: {nome or 'Usuário'} (@{username_exp or 'N/A'}), ID `{user_id}` (Plano: {plano_nome_exp_display})")

            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"⏰ **Seu acesso VIP ao meu cantinho expirou**\n\n"
                         f"Oi {nome or 'flor'}! 😊\n\n"
                         f"Seu plano **{plano_nome_exp_display}** chegou ao fim. Que pena que o tempo voou!\n\n"
                         f"Mas não se preocupe! Se quiser continuar se divertindo comigo e ter acesso a todas as novidades, é só renovar!\n"
                         f"Me chame com um /start para ver os planos novamente. Posso até ter uma surpresinha pra você que já é de casa! 😉\n\n"
                         f"Obrigada por ter feito parte do meu VIP! Espero te ver de volta em breve! 💕",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e_notify_user:
                logger.warning(f"JOB: Falha ao notificar usuário {user_id} sobre expiração: {e_notify_user}")

        except Exception as e_ban_user:
            logger.error(f"JOB: Falha ao banir usuário {user_id} do canal {CANAL_VIP_ID}: {e_ban_user}")
            admin_msg_linhas.append(f"  ⚠️ Falha ao remover: {nome or 'Usuário'} (@{username_exp or 'N/A'}), ID `{user_id}`. Verificar manualmente.")

    if len(admin_msg_linhas) > 1 : # Se houve alguma ação
        try:
            # Dividir a mensagem para o admin se for muito longa
            mensagem_completa_admin = "\n".join(admin_msg_linhas)
            partes_admin = [mensagem_completa_admin[i:i + 4000] for i in range(0, len(mensagem_completa_admin), 4000)]
            for parte_adm in partes_admin:
                await context.bot.send_message(chat_id=SEU_USER_ID, text=parte_adm, parse_mode=ParseMode.MARKDOWN)
        except Exception as e_admin_final_notify:
            logger.error(f"JOB: Falha ao enviar notificação de expiração final para admin: {e_admin_final_notify}")

    logger.info(f"JOB: Verificação de expirados concluída. {removidos_sucesso_count} removidos com sucesso.")


async def comando_verificar_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SEU_USER_ID:
        await update.message.reply_text("❌ Acesso negado.")
        return
    await update.message.reply_text("⏳ Iniciando verificação manual de usuários expirados... Aguarde o resultado.")
    await verificar_expirados_job(context)
    await update.message.reply_text("✅ Verificação manual de usuários expirados concluída. Verifique os logs ou notificações para detalhes.")


def main():
    inicializar_banco()
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("usuarios", listar_usuarios_command))
    application.add_handler(CommandHandler("pendentes", pendentes_command))
    application.add_handler(CommandHandler("aprovar", aprovar_pagamento))
    application.add_handler(CommandHandler("rejeitar", rejeitar_pagamento))
    application.add_handler(CommandHandler("verificarvip", comando_verificar_manual))

    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(
        (filters.PHOTO | filters.Document.IMAGE) & (~filters.COMMAND),
        handle_comprovante
    ))

    if application.job_queue:
        application.job_queue.run_repeating(
            verificar_expirados_job,
            interval=3600, # A cada 1 hora
            first=60 # Primeira execução após 60s
        )
        logger.info("Job de verificação de expirações agendado.")
    else:
        logger.warning("JobQueue não está disponível. Verificação automática desabilitada.")

    logger.info("Bot iniciado! Estou pronta para atender... ✨")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
