import os
import logging
import datetime
import asyncio
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import TelegramError
from dotenv import load_dotenv

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configurações do bot a partir de variáveis de ambiente
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CANAL_VIP_ID = int(os.getenv("CANAL_VIP_ID"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# Verificar se as variáveis de ambiente foram carregadas corretamente
if not all([TOKEN, CANAL_VIP_ID, ADMIN_ID]):
    logger.error("Erro: Variáveis de ambiente não configuradas corretamente.")
    logger.error("Certifique-se de criar um arquivo .env com as configurações necessárias.")
    logger.error("Você pode usar o arquivo .env.example como modelo.")
    exit(1)

# Informações dos planos
PLANOS = {
    "1_mes": {
        "nome": "Plano VIP 1 mês",
        "valor": "R$ 39,90",
        "duracao_dias": 30,
        "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540539.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***63044086"
    },
    "3_meses": {
        "nome": "Plano VIP 3 meses",
        "valor": "R$ 99,90",
        "duracao_dias": 90,
        "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540599.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***63041E24"
    },
    "6_meses": {
        "nome": "Plano VIP 6 meses",
        "valor": "R$ 179,90",
        "duracao_dias": 180,
        "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406179.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***63043084"
    },
    "12_meses": {
        "nome": "Plano VIP 12 meses",
        "valor": "R$ 289,90",
        "duracao_dias": 365,
        "pix": "00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406289.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***6304CD13"
    }
}

# Arquivo para armazenar os usuários e suas assinaturas
USUARIOS_DB = "usuarios.json"

# Função para carregar os dados dos usuários
def carregar_usuarios():
    if os.path.exists(USUARIOS_DB):
        with open(USUARIOS_DB, 'r') as file:
            try:
                return json.load(file)
            except json.JSONDecodeError:
                logger.error("Erro ao decodificar o arquivo de usuários")
                return {}
    return {}

# Função para salvar os dados dos usuários
def salvar_usuarios(usuarios):
    with open(USUARIOS_DB, 'w') as file:
        json.dump(usuarios, file, indent=4)

# Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔥 Plano VIP 1 mês - R$ 39,90", callback_data="plano_1_mes")],
        [InlineKeyboardButton("🔥 Plano VIP 3 meses - R$ 99,90", callback_data="plano_3_meses")],
        [InlineKeyboardButton("🔥 Plano VIP 6 meses - R$ 179,90", callback_data="plano_6_meses")],
        [InlineKeyboardButton("🔥 Plano VIP 12 meses - R$ 289,90", callback_data="plano_12_meses")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔞 *BEM-VINDO AO CONTEÚDO VIP* 🔞\n\n"
        "Escolha um plano para ter acesso ao conteúdo exclusivo:\n",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Função para processar a escolha do plano
async def processar_plano(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    plano_id = query.data.replace("plano_", "")
    plano = PLANOS.get(plano_id)
    
    if not plano:
        await query.edit_message_text(text="Plano não encontrado. Por favor, tente novamente.")
        return
    
    # Botão para gerar o PIX
    keyboard = [
        [InlineKeyboardButton("💰 Gerar PIX", callback_data=f"pix_{plano_id}")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="voltar")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"*{plano['nome']}*\n\n"
        f"Valor: *{plano['valor']}*\n\n"
        f"Duração: *{plano['duracao_dias']} dias*\n\n"
        f"Clique em 'Gerar PIX' para realizar o pagamento.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Função para gerar o PIX
async def gerar_pix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    plano_id = query.data.replace("pix_", "")
    plano = PLANOS.get(plano_id)
    
    if not plano:
        await query.edit_message_text(text="Plano não encontrado. Por favor, tente novamente.")
        return
    
    # Botões para confirmar pagamento ou voltar
    keyboard = [
        [InlineKeyboardButton("✅ Confirmar Pagamento", callback_data=f"confirmar_{plano_id}")],
        [InlineKeyboardButton("🔙 Voltar", callback_data=f"plano_{plano_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"*{plano['nome']}*\n\n"
        f"Valor: *{plano['valor']}*\n\n"
        f"*Copie o código PIX abaixo:*\n`{plano['pix']}`\n\n"
        f"Após realizar o pagamento, clique em 'Confirmar Pagamento'.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Função para confirmar o pagamento
async def confirmar_pagamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    plano_id = query.data.replace("confirmar_", "")
    plano = PLANOS.get(plano_id)
    
    if not plano:
        await query.edit_message_text(text="Plano não encontrado. Por favor, tente novamente.")
        return
    
    user_id = query.from_user.id
    username = query.from_user.username or f"user_{user_id}"
    
    # Notificar o administrador sobre o pagamento
    admin_message = (
        f"🔔 *NOVA SOLICITAÇÃO DE ACESSO* 🔔\n\n"
        f"Usuário: @{username} (ID: {user_id})\n"
        f"Plano: {plano['nome']}\n"
        f"Valor: {plano['valor']}\n\n"
        f"Aguardando confirmação de pagamento."
    )
    
    # Botões para o admin aprovar ou rejeitar
    admin_keyboard = [
        [InlineKeyboardButton("✅ Aprovar", callback_data=f"aprovar_{user_id}_{plano_id}")],
        [InlineKeyboardButton("❌ Rejeitar", callback_data=f"rejeitar_{user_id}")]
    ]
    admin_reply_markup = InlineKeyboardMarkup(admin_keyboard)
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_message,
            reply_markup=admin_reply_markup,
            parse_mode='Markdown'
        )
        
        # Informar ao usuário que o pagamento está sendo processado
        await query.edit_message_text(
            "✅ *Solicitação enviada com sucesso!*\n\n"
            "Seu pagamento está sendo verificado pelo administrador.\n"
            "Você receberá o link de acesso assim que o pagamento for confirmado.",
            parse_mode='Markdown'
        )
    except TelegramError as e:
        logger.error(f"Erro ao enviar mensagem para o administrador: {e}")
        await query.edit_message_text(
            "❌ Ocorreu um erro ao processar sua solicitação. Por favor, tente novamente mais tarde."
        )

# Função para o administrador aprovar o pagamento
async def aprovar_pagamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Extrair informações do callback_data
    _, user_id, plano_id = query.data.split("_")
    user_id = int(user_id)
    plano = PLANOS.get(plano_id)
    
    if not plano:
        await query.edit_message_text(text="Plano não encontrado.")
        return
    
    # Gerar link de convite para o canal VIP
    try:
        invite_link = await context.bot.create_chat_invite_link(
            chat_id=CANAL_VIP_ID,
            expire_date=None,  # Link não expira
            member_limit=1  # Limite de 1 uso
        )
        
        # Calcular a data de expiração da assinatura
        data_inicio = datetime.datetime.now()
        data_expiracao = data_inicio + datetime.timedelta(days=plano["duracao_dias"])
        
        # Salvar informações do usuário
        usuarios = carregar_usuarios()
        usuarios[str(user_id)] = {
            "plano": plano_id,
            "data_inicio": data_inicio.isoformat(),
            "data_expiracao": data_expiracao.isoformat(),
            "invite_link": invite_link.invite_link
        }
        salvar_usuarios(usuarios)
        
        # Enviar link de convite para o usuário
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🎉 *Pagamento aprovado!* 🎉\n\n"
                 f"Seu acesso ao *{plano['nome']}* foi liberado.\n\n"
                 f"Clique no link abaixo para acessar o canal VIP:\n"
                 f"{invite_link.invite_link}\n\n"
                 f"Seu acesso expira em: {data_expiracao.strftime('%d/%m/%Y')}\n\n"
                 f"Aproveite o conteúdo exclusivo! 🔞",
            parse_mode='Markdown'
        )
        
        # Atualizar mensagem do admin
        await query.edit_message_text(
            f"✅ Acesso aprovado para o usuário ID: {user_id}\n"
            f"Plano: {plano['nome']}\n"
            f"Expira em: {data_expiracao.strftime('%d/%m/%Y')}"
        )
        
    except TelegramError as e:
        logger.error(f"Erro ao criar link de convite: {e}")
        await query.edit_message_text(f"❌ Erro ao criar link de convite: {e}")

# Função para o administrador rejeitar o pagamento
async def rejeitar_pagamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Extrair ID do usuário do callback_data
    _, user_id = query.data.split("_")
    user_id = int(user_id)
    
    try:
        # Informar ao usuário que o pagamento foi rejeitado
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ *Pagamento não confirmado* ❌\n\n"
                 "Não foi possível confirmar seu pagamento.\n"
                 "Por favor, verifique se o pagamento foi realizado corretamente e tente novamente.",
            parse_mode='Markdown'
        )
        
        # Atualizar mensagem do admin
        await query.edit_message_text(f"❌ Pagamento rejeitado para o usuário ID: {user_id}")
        
    except TelegramError as e:
        logger.error(f"Erro ao enviar mensagem de rejeição: {e}")
        await query.edit_message_text(f"❌ Erro ao enviar mensagem de rejeição: {e}")

# Função para voltar ao menu principal
async def voltar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🔥 Plano VIP 1 mês - R$ 39,90", callback_data="plano_1_mes")],
        [InlineKeyboardButton("🔥 Plano VIP 3 meses - R$ 99,90", callback_data="plano_3_meses")],
        [InlineKeyboardButton("🔥 Plano VIP 6 meses - R$ 179,90", callback_data="plano_6_meses")],
        [InlineKeyboardButton("🔥 Plano VIP 12 meses - R$ 289,90", callback_data="plano_12_meses")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🔞 *BEM-VINDO AO CONTEÚDO VIP* 🔞\n\n"
        "Escolha um plano para ter acesso ao conteúdo exclusivo:\n",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Comando para verificar assinaturas expiradas (apenas para o administrador)
async def verificar_expiracoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Verificar se o comando foi enviado pelo administrador
    if user_id != ADMIN_ID:
        await update.message.reply_text("Você não tem permissão para usar este comando.")
        return
    
    usuarios = carregar_usuarios()
    agora = datetime.datetime.now()
    expirados = []
    
    for user_id, info in usuarios.items():
        data_expiracao = datetime.datetime.fromisoformat(info["data_expiracao"])
        if agora > data_expiracao:
            expirados.append((user_id, info))
    
    if not expirados:
        await update.message.reply_text("Não há assinaturas expiradas no momento.")
        return
    
    # Listar assinaturas expiradas
    mensagem = "📊 *Assinaturas Expiradas* 📊\n\n"
    
    for user_id, info in expirados:
        plano_id = info["plano"]
        plano_nome = PLANOS.get(plano_id, {}).get("nome", "Plano desconhecido")
        data_expiracao = datetime.datetime.fromisoformat(info["data_expiracao"])
        
        mensagem += f"Usuário ID: {user_id}\n"
        mensagem += f"Plano: {plano_nome}\n"
        mensagem += f"Expirou em: {data_expiracao.strftime('%d/%m/%Y')}\n\n"
    
    # Botão para remover todos os expirados
    keyboard = [[InlineKeyboardButton("🗑️ Remover Todos Expirados", callback_data="remover_expirados")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        mensagem,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Função para remover todos os usuários expirados
async def remover_expirados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Verificar se o comando foi enviado pelo administrador
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("Você não tem permissão para usar este comando.")
        return
    
    usuarios = carregar_usuarios()
    agora = datetime.datetime.now()
    expirados = []
    
    # Identificar usuários expirados
    for user_id, info in list(usuarios.items()):
        data_expiracao = datetime.datetime.fromisoformat(info["data_expiracao"])
        if agora > data_expiracao:
            expirados.append(int(user_id))
            del usuarios[user_id]
    
    # Salvar usuários atualizados
    salvar_usuarios(usuarios)
    
    # Remover usuários do canal VIP
    bot = context.bot
    removidos = 0
    falhas = 0
    
    for user_id in expirados:
        try:
            await bot.ban_chat_member(CANAL_VIP_ID, user_id)
            await bot.unban_chat_member(CANAL_VIP_ID, user_id)  # Desbanir para permitir que entre novamente no futuro
            removidos += 1
            
            # Notificar o usuário sobre a expiração
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text="⏰ *Sua assinatura expirou* ⏰\n\n"
                         "Seu acesso ao conteúdo VIP foi encerrado porque sua assinatura expirou.\n\n"
                         "Para renovar seu acesso, inicie uma nova conversa com o bot e escolha um plano.",
                    parse_mode='Markdown'
                )
            except TelegramError:
                # Ignorar erros ao enviar mensagem para o usuário
                pass
            
        except TelegramError as e:
            logger.error(f"Erro ao remover usuário {user_id}: {e}")
            falhas += 1
    
    # Atualizar mensagem com o resultado
    await query.edit_message_text(
        f"🗑️ *Remoção de usuários expirados* 🗑️\n\n"
        f"Total de usuários expirados: {len(expirados)}\n"
        f"Removidos com sucesso: {removidos}\n"
        f"Falhas na remoção: {falhas}",
        parse_mode='Markdown'
    )

# Função para verificar assinaturas automaticamente
async def verificar_assinaturas_automaticamente(bot):
    while True:
        try:
            usuarios = carregar_usuarios()
            agora = datetime.datetime.now()
            expirados = []
            
            # Identificar usuários expirados
            for user_id, info in list(usuarios.items()):
                data_expiracao = datetime.datetime.fromisoformat(info["data_expiracao"])
                if agora > data_expiracao:
                    expirados.append(int(user_id))
                    del usuarios[user_id]
            
            # Salvar usuários atualizados
            if expirados:
                salvar_usuarios(usuarios)
            
                # Remover usuários do canal VIP
                for user_id in expirados:
                    try:
                        await bot.ban_chat_member(CANAL_VIP_ID, user_id)
                        await bot.unban_chat_member(CANAL_VIP_ID, user_id)  # Desbanir para permitir que entre novamente no futuro
                        
                        # Notificar o usuário sobre a expiração
                        try:
                            await bot.send_message(
                                chat_id=user_id,
                                text="⏰ *Sua assinatura expirou* ⏰\n\n"
                                     "Seu acesso ao conteúdo VIP foi encerrado porque sua assinatura expirou.\n\n"
                                     "Para renovar seu acesso, inicie uma nova conversa com o bot e escolha um plano.",
                                parse_mode='Markdown'
                            )
                        except TelegramError:
                            # Ignorar erros ao enviar mensagem para o usuário
                            pass
                        
                    except TelegramError as e:
                        logger.error(f"Erro ao remover usuário {user_id}: {e}")
                
                # Notificar o administrador
                if expirados:
                    try:
                        await bot.send_message(
                            chat_id=ADMIN_ID,
                            text=f"🔔 *Notificação Automática* 🔔\n\n"
                                 f"{len(expirados)} usuários com assinaturas expiradas foram removidos do canal VIP.",
                            parse_mode='Markdown'
                        )
                    except TelegramError as e:
                        logger.error(f"Erro ao notificar administrador: {e}")
            
        except Exception as e:
            logger.error(f"Erro na verificação automática: {e}")
        
        # Verificar a cada 24 horas
        await asyncio.sleep(86400)  # 24 horas em segundos

# Função para iniciar o servidor web para o Render
def start_web_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Bot is running!')
    
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Started web server on port {port}")

# Função principal
async def main():
    # Iniciar servidor web para o Render
    start_web_server()
    
    # Criar a aplicação
    application = Application.builder().token(TOKEN).build()
    
    # Adicionar handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("verificar", verificar_expiracoes))
    
    # Adicionar callback handlers
    application.add_handler(CallbackQueryHandler(processar_plano, pattern=r"^plano_"))
    application.add_handler(CallbackQueryHandler(gerar_pix, pattern=r"^pix_"))
    application.add_handler(CallbackQueryHandler(confirmar_pagamento, pattern=r"^confirmar_"))
    application.add_handler(CallbackQueryHandler(aprovar_pagamento, pattern=r"^aprovar_"))
    application.add_handler(CallbackQueryHandler(rejeitar_pagamento, pattern=r"^rejeitar_"))
    application.add_handler(CallbackQueryHandler(voltar_menu, pattern=r"^voltar$"))
    application.add_handler(CallbackQueryHandler(remover_expirados, pattern=r"^remover_expirados$"))
    
    # Iniciar o bot
    bot = Bot(TOKEN)
    
    # Iniciar a verificação automática de assinaturas em segundo plano
    asyncio.create_task(verificar_assinaturas_automaticamente(bot))
    
    # Iniciar o polling com close_loop=False para evitar o erro "Cannot close a running event loop"
    await application.run_polling(close_loop=False)

if __name__ == "__main__":
    # Configurar o loop de eventos
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Executar a função main assíncrona
        loop.run_until_complete(main())
        # Manter o loop rodando para o servidor web
        loop.run_forever()
    except KeyboardInterrupt:
        # Encerrar graciosamente quando Ctrl+C for pressionado
        print("Bot encerrado pelo usuário")
    finally:
        # Limpar recursos
        loop.close()
