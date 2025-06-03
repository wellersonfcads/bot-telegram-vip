import logging
import sqlite3
import asyncio
import threading
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configurações - ALTERE AQUI
TOKEN = "7963030995:AAE8K5RIFJpaOhxLnDxJ4k614wnq4n549AQ"
SEU_USER_ID = 6150001511  # Seu user ID para receber notificações
CANAL_VIP_ID = "-1002280243232"  # ID do seu canal VIP
CANAL_PREVIAS = "@oiclarinhaalves"  # Canal de prévias

# Dados dos planos
PLANOS = {
    "1mes": {"nome": "Plano VIP 1 mês", "valor": "R$ 39,90", "duracao": 30, "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540539.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA6207050363044086"},
    "3meses": {"nome": "Plano VIP 3 meses", "valor": "R$ 99,90", "duracao": 90, "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540599.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA6207050363041E24"},
    "6meses": {"nome": "Plano VIP 6 meses", "valor": "R$ 179,90", "duracao": 180, "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406179.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA6207050363043084"},
    "12meses": {"nome": "Plano VIP 12 meses", "valor": "R$ 289,90", "duracao": 365, "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406289.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA620705036304CD13"}
}

# Link do vídeo de apresentação - SUBSTITUA pelo seu vídeo
VIDEO_URL = "https://t.me/c/2071234567/123"  # COLOQUE SEU VÍDEO AQUI

# Estados dos usuários para controle do fluxo
estados_usuarios = {}

def inicializar_banco():
    """Inicializa o banco de dados"""
    conn = sqlite3.connect('usuarios_vip.db')
    cursor = conn.cursor()
    
    # Tabela de usuários VIP
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS usuarios_vip (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        nome TEXT,
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
        nome TEXT,
        plano TEXT,
        valor TEXT,
        data_solicitacao TEXT,
        comprovante_enviado INTEGER DEFAULT 0,
        aprovado INTEGER DEFAULT 0
    )
    ''')
    
    conn.commit()
    conn.close()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start - Verificação de idade"""
    user = update.effective_user
    
    # Resetar estado do usuário
    estados_usuarios[user.id] = "inicio"
    
    keyboard = [
        [InlineKeyboardButton("✅ Sim, tenho 18 anos ou mais", callback_data="idade_ok")],
        [InlineKeyboardButton("❌ Não tenho 18 anos", callback_data="idade_nok")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔞 **CONTEÚDO ADULTO** 🔞\n\n"
        "Olá! Antes de continuar, preciso confirmar sua idade.\n\n"
        "Você tem 18 anos ou mais?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manipula todos os callbacks dos botões"""
    query = update.callback_query
    user = query.from_user
    data = query.data
    
    await query.answer()
    
    # Verificação de idade
    if data == "idade_nok":
        await query.edit_message_text(
            "❌ Desculpe, este conteúdo é apenas para maiores de 18 anos.\n\n"
            "Volte quando completar 18 anos! 😊"
        )
        return
    
    elif data == "idade_ok":
        estados_usuarios[user.id] = "boas_vindas"
        
        # Primeira mensagem de boas-vindas
        await query.edit_message_text(
            "Bom te ver por aqui... 🥰\n\n"
            "Que bom que você chegou até mim! ✨"
        )
        
        # Aguardar um pouco e enviar o vídeo
        await asyncio.sleep(2)
        
        try:
            # Tentar enviar vídeo (substitua pela URL do seu vídeo)
            await context.bot.send_message(
                chat_id=user.id,
                text="📹 Deixei um vídeo especial pra você conhecer um pouquinho do meu trabalho..."
            )
            
            # Se você tiver um vídeo no Telegram, descomente e ajuste:
            # await context.bot.send_video(
            #     chat_id=user.id,
            #     video=VIDEO_URL,
            #     caption="🔥 Um gostinho do que te espera no VIP..."
            # )
            
        except Exception as e:
            logger.error(f"Erro ao enviar vídeo: {e}")
        
        # Aguardar mais um pouco e mostrar call-to-action
        await asyncio.sleep(3)
        
        keyboard = [[InlineKeyboardButton("🔥 Quero acesso ao VIP", callback_data="ver_planos")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=user.id,
            text="💎 **Quer ter acesso a todo meu conteúdo completo no VIP?**\n\n"
                 "🔥 Conteúdos exclusivos\n"
                 "📱 Fotos e vídeos inéditos\n" 
                 "💬 Interação direta comigo\n"
                 "🎁 Surpresas especiais\n\n"
                 "👇 Clique no botão abaixo e escolha seu plano:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    # Mostrar planos
    elif data == "ver_planos":
        keyboard = []
        for plano_id, plano_info in PLANOS.items():
            keyboard.append([InlineKeyboardButton(
                f"💎 {plano_info['nome']} - {plano_info['valor']}", 
                callback_data=f"plano_{plano_id}"
            )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "💎 **PLANOS VIP DISPONÍVEIS** 💎\n\n"
            "Escolha o plano que mais combina com você:\n\n"
            "🔥 **1 MÊS** - R$ 39,90\n"
            "🔥 **3 MESES** - R$ 99,90 *(Mais popular)*\n"
            "🔥 **6 MESES** - R$ 179,90 *(Melhor custo-benefício)*\n"
            "🔥 **12 MESES** - R$ 289,90 *(Oferta especial)*\n\n"
            "👇 Clique no plano desejado:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    # Detalhes de um plano específico
    elif data.startswith("plano_"):
        plano_id = data.replace("plano_", "")
        plano = PLANOS[plano_id]
        
        # Salvar plano escolhido no estado
        if user.id not in estados_usuarios:
            estados_usuarios[user.id] = {}
        estados_usuarios[user.id] = {"plano_escolhido": plano_id}
        
        keyboard = [
            [InlineKeyboardButton("💳 Gerar PIX", callback_data=f"gerar_pix_{plano_id}")],
            [InlineKeyboardButton("⬅️ Voltar aos planos", callback_data="ver_planos")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"💎 **{plano['nome']}**\n\n"
            f"💰 **Valor:** {plano['valor']}\n"
            f"⏰ **Duração:** {plano['duracao']} dias\n\n"
            f"🔥 **O que você vai receber:**\n"
            f"📱 Acesso total ao grupo VIP\n"
            f"🎬 Todos os vídeos exclusivos\n"
            f"📸 Fotos inéditas diariamente\n"
            f"💬 Interação direta comigo\n"
            f"🎁 Conteúdos especiais e surpresas\n\n"
            f"👇 Clique para gerar o PIX:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    # Gerar PIX
    elif data.startswith("gerar_pix_"):
        plano_id = data.replace("gerar_pix_", "")
        plano = PLANOS[plano_id]
        pix_code = plano['pix']
        
        keyboard = [
            [InlineKeyboardButton("📋 Copiar PIX", callback_data=f"copiar_pix_{plano_id}")],
            [InlineKeyboardButton("✅ Já paguei! Solicitar acesso", callback_data=f"paguei_{plano_id}")],
            [InlineKeyboardButton("⬅️ Voltar aos planos", callback_data="ver_planos")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"💳 **PIX para pagamento - {plano['nome']}**\n\n"
            f"💰 **Valor:** {plano['valor']}\n\n"
            f"📋 **Código PIX (Copia e Cola):**\n"
            f"`{pix_code}`\n\n"
            f"📱 **Como pagar:**\n"
            f"1️⃣ Clique em 'Copiar PIX' abaixo\n"
            f"2️⃣ Abra seu banco/app de pagamento\n"
            f"3️⃣ Cole o código PIX\n"
            f"4️⃣ Confirme o pagamento\n"
            f"5️⃣ Volte aqui e clique em 'Já paguei'\n\n"
            f"⚡ **Acesso liberado em até 5 minutos!**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    # Copiar PIX
    elif data.startswith("copiar_pix_"):
        plano_id = data.replace("copiar_pix_", "")
        plano = PLANOS[plano_id]
        pix_code = plano['pix']
        
        # Enviar o PIX como mensagem separada para facilitar a cópia
        await context.bot.send_message(
            chat_id=user.id,
            text=f"📋 **PIX copiado com sucesso!**\n\n"
                 f"Cole este código no seu app de pagamento:\n\n"
                 f"`{pix_code}`",
            parse_mode='Markdown'
        )
        
        await query.answer("PIX copiado! ✅", show_alert=True)
    
    # Já paguei - solicitar comprovante
    elif data.startswith("paguei_"):
        plano_id = data.replace("paguei_", "")
        plano = PLANOS[plano_id]
        
        # Salvar na tabela de pagamentos pendentes
        conn = sqlite3.connect('usuarios_vip.db')
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT OR REPLACE INTO pagamentos_pendentes 
        (user_id, username, nome, plano, valor, data_solicitacao, comprovante_enviado, aprovado)
        VALUES (?, ?, ?, ?, ?, ?, 0, 0)
        ''', (
            user.id,
            user.username or "N/A",
            user.full_name or "N/A",
            plano['nome'],
            plano['valor'],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        
        conn.commit()
        conn.close()
        
        # Definir estado para aguardar comprovante
        estados_usuarios[user.id] = {"aguardando_comprovante": True, "plano": plano_id}
        
        keyboard = [
            [InlineKeyboardButton("📎 Enviar comprovante", callback_data=f"enviar_comprovante_{plano_id}")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data=f"gerar_pix_{plano_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✅ **Perfeito!**\n\n"
            f"Agora preciso que você envie o comprovante do pagamento para eu liberar seu acesso rapidinho! 😊\n\n"
            f"📱 **Plano:** {plano['nome']}\n"
            f"💰 **Valor:** {plano['valor']}\n\n"
            f"👇 Clique no botão abaixo e envie uma foto ou print do comprovante:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    # Preparar para enviar comprovante
    elif data.startswith("enviar_comprovante_"):
        plano_id = data.replace("enviar_comprovante_", "")
        
        estados_usuarios[user.id] = {"aguardando_comprovante": True, "plano": plano_id}
        
        await query.edit_message_text(
            "📎 **Enviar comprovante**\n\n"
            "Por favor, envie uma foto ou print do comprovante de pagamento.\n\n"
            "📱 Pode ser:\n"
            "• Print da tela do app do banco\n"
            "• Foto do comprovante\n"
            "• Screenshot da transação\n\n"
            "⚡ Assim que eu receber, vou liberar seu acesso em alguns minutos!"
        )

async def handle_comprovante(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe comprovantes de pagamento"""
    user = update.effective_user
    
    # Verificar se o usuário está no estado de enviar comprovante
    if user.id not in estados_usuarios or not estados_usuarios[user.id].get("aguardando_comprovante"):
        return
    
    plano_id = estados_usuarios[user.id].get("plano")
    if not plano_id:
        return
    
    plano = PLANOS[plano_id]
    
    # Atualizar no banco que o comprovante foi enviado
    conn = sqlite3.connect('usuarios_vip.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    UPDATE pagamentos_pendentes 
    SET comprovante_enviado = 1 
    WHERE user_id = ? AND aprovado = 0
    ''', (user.id,))
    
    conn.commit()
    conn.close()
    
    # Resetar estado
    estados_usuarios[user.id] = {}
    
    # Enviar comprovante para você (admin)
    try:
        if update.message.photo:
            # Se for foto
            photo = update.message.photo[-1]
            await context.bot.send_photo(
                chat_id=SEU_USER_ID,
                photo=photo.file_id,
                caption=f"💳 **NOVO COMPROVANTE RECEBIDO**\n\n"
                        f"👤 **Usuário:** {user.full_name}\n"
                        f"🆔 **ID:** {user.id}\n"
                        f"📱 **Username:** @{user.username or 'N/A'}\n"
                        f"💎 **Plano:** {plano['nome']}\n"
                        f"💰 **Valor:** {plano['valor']}\n\n"
                        f"Para aprovar, use: `/aprovar {user.id}`\n"
                        f"Para rejeitar, use: `/rejeitar {user.id}`",
                parse_mode='Markdown'
            )
        elif update.message.document:
            # Se for documento
            document = update.message.document
            await context.bot.send_document(
                chat_id=SEU_USER_ID,
                document=document.file_id,
                caption=f"💳 **NOVO COMPROVANTE RECEBIDO**\n\n"
                        f"👤 **Usuário:** {user.full_name}\n"
                        f"🆔 **ID:** {user.id}\n"
                        f"📱 **Username:** @{user.username or 'N/A'}\n"
                        f"💎 **Plano:** {plano['nome']}\n"
                        f"💰 **Valor:** {plano['valor']}\n\n"
                        f"Para aprovar, use: `/aprovar {user.id}`\n"
                        f"Para rejeitar, use: `/rejeitar {user.id}`",
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Erro ao enviar comprovante para admin: {e}")
    
    # Confirmar recebimento para o usuário
    await update.message.reply_text(
        "✅ **Comprovante recebido com sucesso!**\n\n"
        "Obrigada! 😊 Recebi seu comprovante e vou analisar agora.\n\n"
        "⚡ **Seu acesso será liberado em até 10 minutos!**\n\n"
        "Enquanto isso, já pode me seguir no Instagram e ficar por dentro de tudo! 💕"
    )

async def aprovar_pagamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para aprovar pagamento (apenas admin)"""
    if update.effective_user.id != SEU_USER_ID:
        await update.message.reply_text("❌ Acesso negado.")
        return
    
    try:
        user_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Uso: /aprovar <user_id>")
        return
    
    # Buscar dados do pagamento
    conn = sqlite3.connect('usuarios_vip.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT * FROM pagamentos_pendentes 
    WHERE user_id = ? AND comprovante_enviado = 1 AND aprovado = 0
    ''', (user_id,))
    
    pagamento = cursor.fetchone()
    
    if not pagamento:
        await update.message.reply_text("❌ Pagamento não encontrado ou já processado.")
        conn.close()
        return
    
    # Encontrar plano correspondente
    plano_nome = pagamento[3]  # Nome do plano
    plano_id = None
    for pid, pinfo in PLANOS.items():
        if pinfo['nome'] == plano_nome:
            plano_id = pid
            break
    
    if not plano_id:
        await update.message.reply_text("❌ Plano não encontrado.")
        conn.close()
        return
    
    plano = PLANOS[plano_id]
    
    # Calcular data de expiração
    data_entrada = datetime.now()
    data_expiracao = data_entrada + timedelta(days=plano['duracao'])
    
    # Adicionar à tabela de usuários VIP
    cursor.execute('''
    INSERT OR REPLACE INTO usuarios_vip 
    (user_id, username, nome, plano, data_entrada, data_expiracao, ativo)
    VALUES (?, ?, ?, ?, ?, ?, 1)
    ''', (
        user_id,
        pagamento[1],  # username
        pagamento[2],  # nome
        plano_nome,
        data_entrada.strftime("%Y-%m-%d %H:%M:%S"),
        data_expiracao.strftime("%Y-%m-%d %H:%M:%S")
    ))
    
    # Marcar como aprovado
    cursor.execute('''
    UPDATE pagamentos_pendentes 
    SET aprovado = 1 
    WHERE user_id = ?
    ''', (user_id,))
    
    conn.commit()
    conn.close()
    
    # Adicionar ao canal VIP
    try:
        await context.bot.approve_chat_join_request(CANAL_VIP_ID, user_id)
    except:
        try:
            # Se não funcionar com approve_chat_join_request, tentar criar link de convite
            invite_link = await context.bot.create_chat_invite_link(
                CANAL_VIP_ID,
                member_limit=1,
                expire_date=int(time.time()) + 300  # 5 minutos
            )
            
            # Enviar link para o usuário
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 **PAGAMENTO APROVADO!**\n\n"
                     f"Seu acesso ao VIP foi liberado! 🔥\n\n"
                     f"👇 **Clique no link abaixo para entrar:**\n"
                     f"{invite_link.invite_link}\n\n"
                     f"💎 **Seu plano:** {plano_nome}\n"
                     f"📅 **Válido até:** {data_expiracao.strftime('%d/%m/%Y')}\n\n"
                     f"Bem-vinda ao VIP! 😘💕",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Erro ao adicionar usuário ao canal: {e}")
            await update.message.reply_text(f"❌ Erro ao adicionar usuário ao canal: {e}")
            return
    
    # Notificar usuário sobre aprovação
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🎉 **PAGAMENTO APROVADO!**\n\n"
                 f"Parabéns! Seu pagamento foi confirmado e seu acesso ao VIP foi liberado! 🔥\n\n"
                 f"💎 **Seu plano:** {plano_nome}\n"
                 f"📅 **Válido até:** {data_expiracao.strftime('%d/%m/%Y')}\n\n"
                 f"Você já foi adicionada ao grupo VIP! Aproveite todo o conteúdo exclusivo! 😘💕\n\n"
                 f"Qualquer dúvida, é só me chamar! 🥰",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Erro ao notificar usuário: {e}")
    
    await update.message.reply_text(
        f"✅ **Pagamento aprovado com sucesso!**\n\n"
        f"👤 Usuário: {pagamento[2]} (ID: {user_id})\n"
        f"💎 Plano: {plano_nome}\n"
        f"📅 Válido até: {data_expiracao.strftime('%d/%m/%Y')}"
    )

async def rejeitar_pagamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para rejeitar pagamento (apenas admin)"""
    if update.effective_user.id != SEU_USER_ID:
        await update.message.reply_text("❌ Acesso negado.")
        return
    
    try:
        user_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Uso: /rejeitar <user_id>")
        return
    
    # Marcar como rejeitado
    conn = sqlite3.connect('usuarios_vip.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    DELETE FROM pagamentos_pendentes 
    WHERE user_id = ? AND comprovante_enviado = 1 AND aprovado = 0
    ''', (user_id,))
    
    conn.commit()
    conn.close()
    
    # Notificar usuário
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ **Pagamento não aprovado**\n\n"
                 "Infelizmente não consegui confirmar seu pagamento.\n\n"
                 "Por favor, verifique os dados e tente novamente ou entre em contato comigo.\n\n"
                 "Estou aqui para te ajudar! 😊"
        )
    except Exception as e:
        logger.error(f"Erro ao notificar usuário sobre rejeição: {e}")
    
    await update.message.reply_text(f"❌ Pagamento rejeitado para usuário {user_id}")

async def listar_usuarios_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista usuários VIP ativos (apenas admin)"""
    if update.effective_user.id != SEU_USER_ID:
        await update.message.reply_text("❌ Acesso negado.")
        return
    
    conn = sqlite3.connect('usuarios_vip.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT user_id, username, nome, plano, data_expiracao 
    FROM usuarios_vip 
    WHERE ativo = 1 
    ORDER BY data_expiracao
    ''')
    
    usuarios = cursor.fetchall()
    conn.close()
    
    if not usuarios:
        await update.message.reply_text("📋 Nenhum usuário VIP ativo encontrado.")
        return
    
    texto = "📋 **USUÁRIOS VIP ATIVOS**\n\n"
    
    for usuario in usuarios:
        user_id, username, nome, plano, data_exp = usuario
        data_exp_obj = datetime.strptime(data_exp, "%Y-%m-%d %H:%M:%S")
        dias_restantes = (data_exp_obj - datetime.now()).days
        
        status = "🟢" if dias_restantes > 7 else "🟡" if dias_restantes > 0 else "🔴"
        
        texto += f"{status} **{nome}**\n"
        texto += f"🆔 ID: `{user_id}`\n"
        texto += f"📱 Username: @{username or 'N/A'}\n"
        texto += f"💎 Plano: {plano}\n"
        texto += f"📅 Expira: {data_exp_obj.strftime('%d/%m/%Y')}\n"
        texto += f"⏰ Restam: {dias_restantes} dias\n\n"
    
    await update.message.reply_text(texto, parse_mode='Markdown')

def remover_usuarios_expirados():
    """Remove usuários com acesso expirado"""
    try:
        conn = sqlite3.connect('usuarios_vip.db')
        cursor = conn.cursor()
        
        # Buscar usuários expirados
        cursor.execute('''
        SELECT user_id, nome, plano FROM usuarios_vip 
        WHERE ativo = 1 AND data_expiracao < ?
        ''', (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
        
        usuarios_expirados = cursor.fetchall()
        
        if usuarios_expirados:
            # Marcar como inativos
            cursor.execute('''
            UPDATE usuarios_vip 
            SET ativo = 0 
            WHERE ativo = 1 AND data_expiracao < ?
            ''', (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
            
            conn.commit()
            
            # Tentar remover do canal VIP
            for user_id, nome, plano in usuarios_expirados:
                try:
                    # Aqui você precisa usar a instância do bot
                    # Como esta função roda em thread separada, vamos registrar para remoção manual
                    logger.info(f"Usuário expirado: {nome} (ID: {user_id}) - Plano: {plano}")
                except Exception as e:
                    logger.error(f"Erro ao remover usuário {user_id}: {e}")
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Erro na verificação de usuários expirados: {e}")

async def verificar_expirados_manual(context: ContextTypes.DEFAULT_TYPE):
    """Verifica e remove usuários expirados - versão async"""
    try:
        conn = sqlite3.connect('usuarios_vip.db')
        cursor = conn.cursor()
        
        # Buscar usuários expirados
        cursor.execute('''
        SELECT user_id, nome, plano, username FROM usuarios_vip 
        WHERE ativo = 1 AND data_expiracao < ?
        ''', (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
        
        usuarios_expirados = cursor.fetchall()
        
        if usuarios_expirados:
            # Marcar como inativos
            cursor.execute('''
            UPDATE usuarios_vip 
            SET ativo = 0 
            WHERE ativo = 1 AND data_expiracao < ?
            ''', (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
            
            conn.commit()
            
            # Remover do canal VIP e notificar
            for user_id, nome, plano, username in usuarios_expirados:
                try:
                    # Remover do canal
                    await context.bot.ban_chat_member(CANAL_VIP_ID, user_id)
                    await context.bot.unban_chat_member(CANAL_VIP_ID, user_id)
                    
                    # Notificar usuário sobre expiração
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"⏰ **Seu acesso VIP expirou**\n\n"
                             f"Oi {nome}! 😊\n\n"
                             f"Seu plano **{plano}** chegou ao fim.\n\n"
                             f"🔄 **Quer renovar?** É só me chamar que faço um desconto especial pra você! 😉\n\n"
                             f"Obrigada por ter feito parte do VIP! 💕",
                        parse_mode='Markdown'
                    )
                    
                    logger.info(f"Usuário removido por expiração: {nome} (ID: {user_id})")
                    
                except Exception as e:
                    logger.error(f"Erro ao remover usuário {user_id}: {e}")
            
            # Notificar admin
            if usuarios_expirados:
                nomes = [f"{nome} (@{username or 'N/A'})" for _, nome, _, username in usuarios_expirados]
                await context.bot.send_message(
                    chat_id=SEU_USER_ID,
                    text=f"🔄 **Usuários removidos por expiração:**\n\n" + "\n".join(nomes)
                )
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Erro na verificação de usuários expirados: {e}")

async def comando_verificar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando manual para verificar expirados (apenas admin)"""
    if update.effective_user.id != SEU_USER_ID:
        await update.message.reply_text("❌ Acesso negado.")
        return
    
    await verificar_expirados_manual(context)
    await update.message.reply_text("✅ Verificação de usuários expirados concluída!")

async def pendentes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista pagamentos pendentes (apenas admin)"""
    if update.effective_user.id != SEU_USER_ID:
        await update.message.reply_text("❌ Acesso negado.")
        return
    
    conn = sqlite3.connect('usuarios_vip.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT user_id, username, nome, plano, valor, data_solicitacao, comprovante_enviado 
    FROM pagamentos_pendentes 
    WHERE aprovado = 0 
    ORDER BY data_solicitacao DESC
    ''')
    
    pendentes = cursor.fetchall()
    conn.close()
    
    if not pendentes:
        await update.message.reply_text("📋 Nenhum pagamento pendente.")
        return
    
    texto = "💳 **PAGAMENTOS PENDENTES**\n\n"
    
    for pagamento in pendentes:
        user_id, username, nome, plano, valor, data_sol, comprovante = pagamento
        status_comp = "✅ Enviado" if comprovante else "⏳ Aguardando"
        
        texto += f"👤 **{nome}**\n"
        texto += f"🆔 ID: `{user_id}`\n"
        texto += f"📱 Username: @{username or 'N/A'}\n"
        texto += f"💎 Plano: {plano}\n"
        texto += f"💰 Valor: {valor}\n"
        texto += f"📅 Solicitado: {data_sol}\n"
        texto += f"📎 Comprovante: {status_comp}\n"
        
        if comprovante:
            texto += f"⚡ Use: `/aprovar {user_id}` ou `/rejeitar {user_id}`\n"
        
        texto += "\n"
    
    await update.message.reply_text(texto, parse_mode='Markdown')

def iniciar_verificacao_automatica():
    """Inicia verificação automática em thread separada"""
    def loop_verificacao():
        while True:
            time.sleep(3600)  # Verifica a cada hora
            remover_usuarios_expirados()
    
    thread = threading.Thread(target=loop_verificacao, daemon=True)
    thread.start()

def main():
    """Função principal"""
    # Inicializar banco de dados
    inicializar_banco()
    
    # Criar aplicação
    application = Application.builder().token(TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(CommandHandler("usuarios", listar_usuarios_command))
    application.add_handler(CommandHandler("pendentes", pendentes_command))
    application.add_handler(CommandHandler("aprovar", aprovar_pagamento))
    application.add_handler(CommandHandler("rejeitar", rejeitar_pagamento))
    application.add_handler(CommandHandler("verificar", comando_verificar))
    
    # Handler para receber comprovantes (fotos e documentos)
    application.add_handler(MessageHandler(
        filters.PHOTO | filters.Document.ALL, 
        handle_comprovante
    ))
    
    # Iniciar verificação automática
    iniciar_verificacao_automatica()
    
    # Configurar job para verificação automática (versão async)
    application.job_queue.run_repeating(
        verificar_expirados_manual, 
        interval=3600,  # A cada hora
        first=60  # Primeira execução após 1 minuto
    )
    
    logger.info("Bot iniciado com sucesso!")
    
    # Iniciar bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

# ================================
# COMANDOS DISPONÍVEIS PARA ADMIN:
# ================================
# /usuarios - Lista todos os usuários VIP ativos
# /pendentes - Lista pagamentos aguardando aprovação  
# /aprovar <user_id> - Aprova um pagamento
# /rejeitar <user_id> - Rejeita um pagamento
# /verificar - Verifica manualmente usuários expirados
# 
# ================================
# CONFIGURAÇÕES IMPORTANTES:
# ================================
# 1. SEU_USER_ID = Seu ID do Telegram
# 2. CANAL_VIP_ID = ID do canal VIP (com -100...)
# 3. TOKEN = Token do seu bot
# 4. VIDEO_URL = URL do seu vídeo de apresentação
# 
# ================================ 
# FLUXO COMPLETO:
# ================================
# 1. Usuário inicia (/start)
# 2. Verificação de idade (18+)
# 3. Mensagem de boas-vindas personalizada
# 4. Envio do vídeo de apresentação
# 5. Call-to-action para VIP
# 6. Seleção de planos
# 7. Geração de PIX com botão copiar
# 8. Solicitação de comprovante
# 9. Envio do comprovante para admin
# 10. Aprovação/rejeição manual
# 11. Acesso liberado automaticamente
# 12. Remoção automática na expiração
