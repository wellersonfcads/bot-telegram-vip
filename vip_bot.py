import logging
import sqlite3
import asyncio
import threading
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

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
# CANAL_PREVIAS = "@oiclarinhaalves" # Se precisar usar o @ do canal de prévias em algum momento

# Dados dos planos
PLANOS = {
    "1mes": {"nome": "Plano VIP 1 mês", "valor": "R$ 39,90", "duracao": 30, "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540539.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA6207050363044086"},
    "3meses": {"nome": "Plano VIP 3 meses", "valor": "R$ 99,90", "duracao": 90, "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540599.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA6207050363041E24"},
    "6meses": {"nome": "Plano VIP 6 meses", "valor": "R$ 179,90", "duracao": 180, "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406179.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA6207050363043084"},
    "12meses": {"nome": "Plano VIP 12 meses", "valor": "R$ 289,90", "duracao": 365, "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406289.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA620705036304CD13"}
}

# Link do vídeo de apresentação - SUBSTITUA pelo seu vídeo (link direto para o arquivo ou ID do arquivo no Telegram)
VIDEO_URL = "BAACAgIAAxkBAAIBlGZ3_NdJb0y4p4Q38GNBq9B5jWOkAAJJSQAC7vJZSDKr1KzCQuvQNAQ" # EXEMPLO de File ID, substitua pelo seu
# Se for um link para um post em canal, o bot precisaria ter acesso ao canal.
# Um file_id é mais confiável se o vídeo já estiver no Telegram.
# Para obter o file_id, envie o vídeo para o @RawDataBot e ele te mostrará o file_id.

# Estados dos usuários para controle do fluxo e armazenamento temporário de message_id
# estados_usuarios[user_id] = {"estado_atual": "...", "plano_escolhido": "...", "mensagem_pix_id": ... , "idade_verificada": True/False}
estados_usuarios = {}
DB_NAME = 'usuarios_vip.db'

def inicializar_banco():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS usuarios_vip (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        nome TEXT,
        plano_id TEXT, -- Alterado para plano_id
        data_entrada TEXT,
        data_expiracao TEXT,
        ativo INTEGER DEFAULT 1,
        idade_verificada INTEGER DEFAULT 0 -- Novo campo
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pagamentos_pendentes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        nome TEXT,
        plano_id TEXT, -- Alterado para plano_id
        valor TEXT,
        data_solicitacao TEXT,
        comprovante_enviado INTEGER DEFAULT 0,
        aprovado INTEGER DEFAULT 0,
        mensagem_pix_id INTEGER -- Novo campo para controlar a mensagem do PIX
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
    cursor.execute("INSERT OR IGNORE INTO usuarios_vip (user_id, idade_verificada) VALUES (?, 0)", (user_id,))
    cursor.execute("UPDATE usuarios_vip SET idade_verificada = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    logger.info(f"Usuário {user_id} teve idade verificada e salva no DB.")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_db_info = get_user_db_info(user.id)

    # Limpar estados anteriores para este usuário
    estados_usuarios[user.id] = {}

    if user_db_info.get("idade_verificada", False):
        logger.info(f"Usuário {user.id} já tem idade verificada. Pulando para boas vindas.")
        # Se já verificou a idade, vai direto para a próxima etapa
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
    """Continua o fluxo após a verificação de idade ou para usuários já verificados."""
    if is_callback:
        target_message = update.callback_query.edit_message_text
    else:
        target_message = update.message.reply_text

    await target_message(
        "Bom te ver por aqui... 🥰\n\n"
        "Que bom que você chegou até mim! ✨",
        reply_markup=None # Remove botões da mensagem anterior
    )
    await asyncio.sleep(2)

    try:
        if VIDEO_URL:
            await context.bot.send_chat_action(chat_id=user.id, action="upload_video")
            await context.bot.send_video(
                chat_id=user.id,
                video=VIDEO_URL, # Use o file_id aqui
                caption="📹 Deixei um vídeo especial pra você conhecer um pouquinho do meu trabalho..."
            )
        else:
            await context.bot.send_message(
                chat_id=user.id,
                text="📹 Deixei um vídeo especial pra você conhecer um pouquinho do meu trabalho..."
            )
    except Exception as e:
        logger.error(f"Erro ao enviar vídeo para {user.id}: {e}")
        await context.bot.send_message(
            chat_id=user.id,
            text="📹 Deixei um vídeo especial pra você conhecer um pouquinho do meu trabalho... (vídeo indisponível no momento)"
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

    # Inicializar estado do usuário se não existir
    if chat_id not in estados_usuarios:
        estados_usuarios[chat_id] = {}

    await query.answer() # Responde ao callback para remover o "loading" do botão

    # Verificação de idade
    if data == "idade_nok":
        await query.edit_message_text(
            "❌ Que pena! Este cantinho é apenas para maiores de 18 anos.\n\n"
            "Volte quando completar a maioridade! 😊"
        )
        return
    elif data == "idade_ok":
        set_user_idade_verificada(user.id) # Salva no DB
        estados_usuarios[chat_id]["idade_verificada"] = True
        await boas_vindas_fluxo(update, context, user) # Chama a função de boas vindas
        return

    # Limpar mensagem de PIX se existir e o usuário navegou para outro lugar
    if "mensagem_pix_id" in estados_usuarios[chat_id] and not data.startswith("copiar_pix_") and not data.startswith("paguei_"):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=estados_usuarios[chat_id]["mensagem_pix_id"])
        except Exception as e:
            logger.warning(f"Não foi possível deletar mensagem PIX {estados_usuarios[chat_id]['mensagem_pix_id']}: {e}")
        del estados_usuarios[chat_id]["mensagem_pix_id"]


    if data == "ver_planos":
        keyboard = []
        for plano_id_key, plano_info in PLANOS.items():
            keyboard.append([InlineKeyboardButton(
                f"💎 {plano_info['nome']} - {plano_info['valor']}",
                callback_data=f"plano_{plano_id_key}"
            )])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "💎 **MEUS PLANOS VIP** 💎\n\n"
            "Escolha o que mais te agrada e vem se divertir comigo:\n\n"
            "🔥 **1 MÊS DE ACESSO** - R$ 39,90\n"
            "🔥 **3 MESES DE ACESSO** - R$ 99,90 *(O mais pedido!)*\n"
            "🔥 **6 MESES DE ACESSO** - R$ 179,90 *(Melhor custo-benefício!)*\n"
            "🔥 **12 MESES DE ACESSO** - R$ 289,90 *(Acesso VIP total por 1 ano!)*\n\n"
            "👇 É só clicar no plano que você quer:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

    elif data.startswith("plano_"):
        plano_id = data.replace("plano_", "")
        if plano_id in PLANOS:
            plano = PLANOS[plano_id]
            estados_usuarios[chat_id]["plano_escolhido"] = plano_id # Armazena o ID do plano

            keyboard = [
                [InlineKeyboardButton("💳 Gerar PIX para Pagamento", callback_data=f"gerar_pix_{plano_id}")],
                [InlineKeyboardButton("⬅️ Voltar aos planos", callback_data="ver_planos")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"💎 **Você escolheu: {plano['nome']}**\n\n"
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

    elif data.startswith("gerar_pix_"):
        plano_id = data.replace("gerar_pix_", "")
        if plano_id in PLANOS:
            plano = PLANOS[plano_id]
            pix_code = plano['pix']
            estados_usuarios[chat_id]["plano_escolhido"] = plano_id # Garante que está salvo

            keyboard = [
                [InlineKeyboardButton("📋 Copiar Código PIX", callback_data=f"copiar_pix_{plano_id}")],
                [InlineKeyboardButton("✅ Já paguei! Enviar Comprovante", callback_data=f"solicitar_comprovante_{plano_id}")],
                [InlineKeyboardButton("⬅️ Voltar aos planos", callback_data="ver_planos")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Edita a mensagem anterior para mostrar o PIX
            await query.edit_message_text(
                f"💳 **PIX para Pagamento - {plano['nome']}**\n\n"
                f"💰 **Valor:** {plano['valor']}\n\n"
                f"🔑 **Meu PIX (Copia e Cola):**\n"
                f"`{pix_code}`\n\n" # Código PIX entre crases para cópia fácil
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
            # Guarda o ID da mensagem que contém o PIX para poder editá-la ou deletá-la depois
            estados_usuarios[chat_id]["mensagem_pix_id_principal"] = query.message.message_id


    elif data.startswith("copiar_pix_"):
        plano_id = data.replace("copiar_pix_", "")
        if plano_id in PLANOS:
            plano = PLANOS[plano_id]
            pix_code = plano['pix']
            # Envia o código PIX como mensagem separada para facilitar a cópia
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
            estados_usuarios[chat_id]["plano_escolhido"] = plano_id
            estados_usuarios[chat_id]["estado_atual"] = "aguardando_comprovante"

            # Remover a mensagem do PIX se ainda estiver visível (a principal)
            if "mensagem_pix_id_principal" in estados_usuarios[chat_id]:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=estados_usuarios[chat_id]["mensagem_pix_id_principal"])
                    del estados_usuarios[chat_id]["mensagem_pix_id_principal"]
                except Exception as e:
                    logger.warning(f"Não foi possível deletar mensagem PIX principal: {e}")


            await query.edit_message_text(
                text=f" Combinado! Para o {plano['nome']} ({plano['valor']}).\n\n"
                     f"Agora, por favor, me envie o comprovante do pagamento (print da tela ou foto).\n\n"
                     f"Assim que eu receber e confirmar, libero seu acesso rapidinho! 📸✨\n\n"
                     f"(É só anexar a imagem aqui na nossa conversa)",
                reply_markup=None, # Remove botões anteriores
                parse_mode=ParseMode.MARKDOWN
            )
            # Registrar no banco de dados que um pagamento está pendente
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO pagamentos_pendentes
            (user_id, username, nome, plano_id, valor, data_solicitacao, comprovante_enviado, aprovado)
            VALUES (?, ?, ?, ?, ?, ?, 0, 0)
            ''', (
                user.id,
                user.username or "N/A",
                user.full_name or "N/A",
                plano_id, # Usando plano_id
                plano['valor'],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
        cursor.execute('''
        UPDATE pagamentos_pendentes
        SET comprovante_enviado = 1
        WHERE user_id = ? AND plano_id = ? AND aprovado = 0 ORDER BY id DESC LIMIT 1
        ''', (user.id, plano_id)) # Garantir que atualiza o mais recente se houver múltiplos
        conn.commit()
        conn.close()

        del estados_usuarios[chat_id]["estado_atual"] # Limpa o estado

        admin_message = (
            f"💳 **NOVO COMPROVANTE RECEBIDO!** 🎉\n\n"
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
                    chat_id=SEU_USER_ID,
                    photo=update.message.photo[-1].file_id,
                    caption=admin_message,
                    parse_mode=ParseMode.MARKDOWN
                )
            elif update.message.document:
                await context.bot.send_document(
                    chat_id=SEU_USER_ID,
                    document=update.message.document.file_id,
                    caption=admin_message,
                    parse_mode=ParseMode.MARKDOWN
                )
            else: # Caso seja uma mensagem de texto tentando ser comprovante
                await context.bot.send_message(SEU_USER_ID, f"O usuário {user.full_name} (ID: {user.id}) enviou uma mensagem de texto como comprovante para o plano {plano['nome']}. Por favor, verifique.\nMensagem: {update.message.text}")
                await update.message.reply_text(
                    "📸 Humm, não consegui identificar uma imagem aqui. Por favor, envie o print ou foto do comprovante para eu poder analisar! Se tiver dificuldades, me avise."
                )
                return

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
        await update.message.reply_text("Oi! 😊 Se você está tentando me enviar um comprovante, por favor, selecione um plano e clique em 'Já paguei!' primeiro, ok? Se precisar de ajuda, é só chamar!")


async def aprovar_pagamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SEU_USER_ID:
        await update.message.reply_text("❌ Acesso negado. Este comando é só para a admin aqui! 😉")
        return

    try:
        user_id_aprovar = int(context.args[0])
        plano_id_aprovar = context.args[1] # Pega o plano_id dos argumentos
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Formato incorreto! Use: /aprovar <user_id> <plano_id>\nExemplo: /aprovar 123456789 1mes")
        return

    if plano_id_aprovar not in PLANOS:
        await update.message.reply_text(f"❌ Plano ID '{plano_id_aprovar}' não é válido. Planos disponíveis: {', '.join(PLANOS.keys())}")
        return

    plano = PLANOS[plano_id_aprovar]

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
    SELECT id, username, nome FROM pagamentos_pendentes
    WHERE user_id = ? AND plano_id = ? AND comprovante_enviado = 1 AND aprovado = 0
    ORDER BY id DESC LIMIT 1
    ''', (user_id_aprovar, plano_id_aprovar))
    pagamento = cursor.fetchone()

    if not pagamento:
        await update.message.reply_text(f"❌ Nenhum pagamento pendente encontrado para o usuário ID {user_id_aprovar} com o plano {plano['nome']} que tenha enviado comprovante, ou já foi aprovado.")
        conn.close()
        return

    pagamento_db_id, user_username, user_nome = pagamento
    data_entrada = datetime.now()
    data_expiracao = data_entrada + timedelta(days=plano['duracao'])

    cursor.execute('''
    INSERT OR REPLACE INTO usuarios_vip
    (user_id, username, nome, plano_id, data_entrada, data_expiracao, ativo, idade_verificada)
    VALUES (?, ?, ?, ?, ?, ?, 1, (SELECT idade_verificada FROM usuarios_vip WHERE user_id = ?)) 
    ON CONFLICT(user_id) DO UPDATE SET
    username=excluded.username, nome=excluded.nome, plano_id=excluded.plano_id, data_entrada=excluded.data_entrada,
    data_expiracao=excluded.data_expiracao, ativo=1
    ''', (
        user_id_aprovar,
        user_username,
        user_nome,
        plano_id_aprovar, # Usando plano_id
        data_entrada.strftime("%Y-%m-%d %H:%M:%S"),
        data_expiracao.strftime("%Y-%m-%d %H:%M:%S"),
        user_id_aprovar # Para a subquery de idade_verificada
    ))

    cursor.execute('UPDATE pagamentos_pendentes SET aprovado = 1 WHERE id = ?', (pagamento_db_id,))
    conn.commit()
    conn.close()

    link_convite_canal = f"https://t.me/+9TBR6fK429tiMmRh" # Seu link de convite principal

    try:
        # Tentar criar um link de convite específico para o usuário (mais seguro)
        # O bot precisa ser admin COM PERMISSÃO de "Convidar usuários via link"
        invite_link_obj = await context.bot.create_chat_invite_link(
            chat_id=CANAL_VIP_ID,
            member_limit=1,
            expire_date=int(time.time()) + (60 * 60 * 24)  # Link válido por 1 dia
        )
        link_para_usuario = invite_link_obj.invite_link
        logger.info(f"Link de convite específico criado para {user_id_aprovar}: {link_para_usuario}")
    except Exception as e:
        logger.error(f"Não foi possível criar link de convite específico para {CANAL_VIP_ID}: {e}. Usando link principal.")
        link_para_usuario = link_convite_canal # Fallback para o link principal

    try:
        await context.bot.send_message(
            chat_id=user_id_aprovar,
            text=f"🎉 **UAU! PAGAMENTO APROVADO!** 🎉\n\n"
                 f"Parabéns, meu amor! Seu pagamento foi confirmado e seu acesso ao VIP está liberado! 🔥\n\n"
                 f"💎 **Seu plano:** {plano['nome']}\n"
                 f"📅 **Válido até:** {data_expiracao.strftime('%d/%m/%Y')}\n\n"
                 f"👇 **Clique no link abaixo para entrar no nosso paraíso:**\n"
                 f"{link_para_usuario}\n\n"
                 f"Mal posso esperar para te ver lá dentro! 😘💕\n\n"
                 f"Qualquer dúvida, é só me chamar! 🥰",
            parse_mode=ParseMode.MARKDOWN
        )
        await update.message.reply_text(
            f"✅ **Pagamento aprovado com sucesso!**\n\n"
            f"👤 Usuário: {user_nome or user_username} (ID: {user_id_aprovar})\n"
            f"💎 Plano: {plano['nome']}\n"
            f"📅 Válido até: {data_expiracao.strftime('%d/%m/%Y')}\n"
            f"🔗 Link enviado: {link_para_usuario}"
        )
    except Exception as e:
        logger.error(f"Erro ao notificar usuário {user_id_aprovar} sobre aprovação: {e}")
        await update.message.reply_text(f"✅ Pagamento aprovado para {user_id_aprovar}, mas falhei ao enviar a mensagem de confirmação para ele. Erro: {e}")


async def rejeitar_pagamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SEU_USER_ID:
        await update.message.reply_text("❌ Acesso negado.")
        return

    try:
        user_id_rejeitar = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Uso: /rejeitar <user_id>")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Deleta o pagamento pendente. Você pode optar por marcar como rejeitado em vez de deletar.
    # Aqui, vamos apenas deletar para simplificar, assumindo que se rejeitado, o processo recomeça.
    cursor.execute('''
    DELETE FROM pagamentos_pendentes
    WHERE user_id = ? AND comprovante_enviado = 1 AND aprovado = 0
    ''', (user_id_rejeitar,))
    deleted_rows = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted_rows > 0:
        try:
            await context.bot.send_message(
                chat_id=user_id_rejeitar,
                text="😔 **Pagamento não aprovado** 😔\n\n"
                     "Oi, meu bem. Verifiquei seu comprovante, mas infelizmente não consegui confirmar seu pagamento desta vez.\n\n"
                     "Pode ter sido algum probleminha com o comprovante ou com os dados.\n\n"
                     "Por favor, verifique tudo direitinho e, se quiser, pode tentar me enviar novamente ou falar comigo para a gente resolver, tá bom?\n\n"
                     "Estou aqui para te ajudar! 😊"
            )
        except Exception as e:
            logger.error(f"Erro ao notificar usuário {user_id_rejeitar} sobre rejeição: {e}")

        await update.message.reply_text(f"🗑️ Pagamento pendente para o usuário {user_id_rejeitar} foi marcado como rejeitado/removido e ele foi notificado.")
    else:
        await update.message.reply_text(f"🤷‍♀️ Nenhum pagamento pendente (com comprovante enviado e não aprovado) encontrado para o usuário {user_id_rejeitar} para rejeitar.")


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
    ORDER BY data_expiracao
    ''')
    usuarios = cursor.fetchall()
    conn.close()

    if not usuarios:
        await update.message.reply_text("📋 Nenhum usuário VIP ativo no momento.")
        return

    texto = "📋 **MEUS ASSINANTES VIP ATIVOS**\n\n"
    for usuario_db in usuarios:
        uid, u_username, u_nome, u_plano_id, u_data_exp = usuario_db
        u_data_exp_obj = datetime.strptime(u_data_exp, "%Y-%m-%d %H:%M:%S")
        dias_restantes = (u_data_exp_obj - datetime.now()).days
        plano_nome_display = PLANOS.get(u_plano_id, {}).get('nome', u_plano_id) # Mostra nome do plano ou ID se não encontrar

        status_emoji = "🟢" if dias_restantes > 7 else "🟡" if dias_restantes >= 0 else "🔴"

        texto += f"{status_emoji} **{u_nome or 'Nome não disponível'}** (@{u_username or 'N/A'})\n"
        texto += f"   🆔 ID: `{uid}`\n"
        texto += f"   💎 Plano: {plano_nome_display}\n"
        texto += f"   📅 Expira em: {u_data_exp_obj.strftime('%d/%m/%Y às %H:%M')}\n"
        texto += f"   ⏳ Dias restantes: {dias_restantes if dias_restantes >=0 else 'Expirado!'}\n\n"

    if len(texto) > 4096: # Limite do Telegram
        partes = [texto[i:i + 4000] for i in range(0, len(texto), 4000)]
        for parte in partes:
            await update.message.reply_text(parte, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(texto, parse_mode=ParseMode.MARKDOWN)


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
    ORDER BY data_solicitacao DESC
    ''')
    pendentes = cursor.fetchall()
    conn.close()

    if not pendentes:
        await update.message.reply_text("📋 Nenhum pagamento pendente no momento. Tudo em dia!")
        return

    texto = "💳 **PAGAMENTOS PENDENTES DE APROVAÇÃO**\n\n"
    for pag_pendente in pendentes:
        p_uid, p_username, p_nome, p_plano_id, p_valor, p_data_sol, p_comprovante = pag_pendente
        status_comp = "✅ Comprovante Enviado" if p_comprovante else "⏳ Aguardando Comprovante"
        plano_nome_display = PLANOS.get(p_plano_id, {}).get('nome', p_plano_id)

        texto += f"👤 **{p_nome or 'Nome não disponível'}** (@{p_username or 'N/A'})\n"
        texto += f"   🆔 ID: `{p_uid}`\n"
        texto += f"   💎 Plano: {plano_nome_display} ({p_valor})\n"
        texto += f"   📅 Solicitado em: {datetime.strptime(p_data_sol, '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%y %H:%M')}\n"
        texto += f"   📎 Comprovante: {status_comp}\n"

        if p_comprovante:
            texto += f"   👉 Use: `/aprovar {p_uid} {p_plano_id}` ou `/rejeitar {p_uid}`\n"
        texto += "\n"

    if len(texto) > 4096:
        partes = [texto[i:i + 4000] for i in range(0, len(texto), 4000)]
        for parte in partes:
            await update.message.reply_text(parte, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(texto, parse_mode=ParseMode.MARKDOWN)


async def verificar_expirados_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("JOB: Iniciando verificação de usuários expirados...")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    agora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
    SELECT user_id, nome, plano_id, username FROM usuarios_vip
    WHERE ativo = 1 AND data_expiracao < ?
    ''', (agora_str,))
    usuarios_expirados = cursor.fetchall()

    if not usuarios_expirados:
        logger.info("JOB: Nenhum usuário expirado encontrado.")
        conn.close()
        return

    # Marcar como inativos primeiro
    user_ids_expirados = [ue[0] for ue in usuarios_expirados]
    placeholders = ','.join('?' for _ in user_ids_expirados)
    cursor.execute(f'''
    UPDATE usuarios_vip SET ativo = 0
    WHERE user_id IN ({placeholders})
    ''', user_ids_expirados)
    conn.commit()
    logger.info(f"JOB: {len(user_ids_expirados)} usuários marcados como inativos no DB.")

    conn.close() # Fechar conexão antes de longas operações de IO (API do Telegram)

    removidos_count = 0
    falha_remocao_ids = []
    admin_notification_lines = ["🔄 **Assinaturas Expiradas e Usuários Removidos do VIP:**\n"]

    for user_id, nome, plano_id_exp, username in usuarios_expirados:
        plano_nome_exp = PLANOS.get(plano_id_exp, {}).get('nome', plano_id_exp)
        try:
            await context.bot.ban_chat_member(chat_id=CANAL_VIP_ID, user_id=user_id)
            # É uma boa prática remover o banimento imediatamente se a intenção é apenas remover, não banir permanentemente.
            # No entanto, banir e não remover o banimento garante que não possam reentrar por links antigos.
            # Se quiser que possam re-assinar facilmente, use unban_chat_member.
            # await context.bot.unban_chat_member(chat_id=CANAL_VIP_ID, user_id=user_id)
            logger.info(f"JOB: Usuário {user_id} ({nome}) removido do canal {CANAL_VIP_ID} por expiração.")
            removidos_count += 1
            admin_notification_lines.append(f"  - ✅ {nome or 'Usuário'} (@{username or 'N/A'}), ID `{user_id}`, Plano: {plano_nome_exp}")

            try: # Notificar usuário sobre expiração
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"⏰ **Seu acesso VIP ao meu cantinho expirou**\n\n"
                         f"Oi {nome or 'flor'}! 😊\n\n"
                         f"Seu plano **{plano_nome_exp}** chegou ao fim. Que pena que o tempo voou!\n\n"
                         f"Mas não se preocupe! Se quiser continuar se divertindo comigo e ter acesso a todas as novidades, é só renovar!\n"
                         f"Me chame com um /start para ver os planos novamente. Posso até ter uma surpresinha pra você que já é de casa! 😉\n\n"
                         f"Obrigada por ter feito parte do meu VIP! Espero te ver de volta em breve! 💕",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e_notify:
                logger.warning(f"JOB: Falha ao notificar usuário {user_id} sobre expiração: {e_notify}")

        except Exception as e_ban:
            logger.error(f"JOB: Falha ao remover usuário {user_id} do canal {CANAL_VIP_ID}: {e_ban}")
            falha_remocao_ids.append(user_id)
            admin_notification_lines.append(f"  - ❌ Falha ao remover {nome or 'Usuário'} (@{username or 'N/A'}), ID `{user_id}`. Verificar manualmente.")


    if removidos_count > 0 or falha_remocao_ids:
        if falha_remocao_ids:
             admin_notification_lines.append(f"\n⚠️ **IDs com falha na remoção (verificar no canal):** {', '.join(map(str, falha_remocao_ids))}")
        try:
            await context.bot.send_message(chat_id=SEU_USER_ID, text="\n".join(admin_notification_lines), parse_mode=ParseMode.MARKDOWN)
        except Exception as e_admin_notify:
            logger.error(f"JOB: Falha ao enviar notificação de expiração para admin: {e_admin_notify}")

    logger.info(f"JOB: Verificação de usuários expirados concluída. {removidos_count} removidos. {len(falha_remocao_ids)} falhas.")


async def comando_verificar_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SEU_USER_ID:
        await update.message.reply_text("❌ Acesso negado.")
        return
    await update.message.reply_text("⏳ Iniciando verificação manual de usuários expirados... Aguarde o resultado.")
    await verificar_expirados_job(context) # Chama a mesma lógica do job
    await update.message.reply_text("✅ Verificação manual de usuários expirados concluída. Verifique os logs ou notificações para detalhes.")


def main():
    inicializar_banco()
    application = Application.builder().token(TOKEN).build()

    # Handlers de Comando
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("usuarios", listar_usuarios_command))
    application.add_handler(CommandHandler("pendentes", pendentes_command))
    application.add_handler(CommandHandler("aprovar", aprovar_pagamento))
    application.add_handler(CommandHandler("rejeitar", rejeitar_pagamento))
    application.add_handler(CommandHandler("verificarvip", comando_verificar_manual))


    # Handler de Callback (botões)
    application.add_handler(CallbackQueryHandler(callback_handler))

    # Handler para receber comprovantes (fotos e documentos)
    application.add_handler(MessageHandler(
        (filters.PHOTO | filters.Document.IMAGE) & (~filters.COMMAND), # Apenas fotos ou documentos que são imagens, e não comandos
        handle_comprovante
    ))

    # Job para verificação automática de expirações
    if application.job_queue:
        application.job_queue.run_repeating(
            verificar_expirados_job,
            interval=3600,  # A cada 1 hora (3600 segundos)
            first=60  # Primeira execução após 60 segundos do bot iniciar
        )
        logger.info("Job de verificação de expirações agendado.")
    else:
        logger.warning("JobQueue não está disponível. A verificação automática de expirações não funcionará.")

    logger.info("Bot iniciado! Estou pronta para atender... ✨")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
