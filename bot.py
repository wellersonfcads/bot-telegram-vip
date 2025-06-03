import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import time
from datetime import datetime, timedelta

# Configurações do seu bot (já com seus dados)
TOKEN = '7963030995:AAE8K5RIFJpaOhxLnDxJ4k614wnq4n549AQ'
CHANNEL_VIP_ID = '-1002280243232'  # ID numérico do seu canal VIP
ADMIN_ID = 6150001511  # Seu ID pessoal do Telegram

bot = telebot.TeleBot(TOKEN)

# Planos configurados conforme seus dados
PLANOS = {
    '1mes': {
        'nome': 'Plano VIP 1 mês',
        'valor': 39.90,
        'dias': 30,
        'pix': '00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540539.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***63044086'
    },
    '3meses': {
        'nome': 'Plano VIP 3 meses',
        'valor': 99.90,
        'dias': 90,
        'pix': '00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f520400005303986540599.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***63041E24'
    },
    '6meses': {
        'nome': 'Plano VIP 6 meses',
        'valor': 179.90,
        'dias': 180,
        'pix': '00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406179.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***63043084'
    },
    '12meses': {
        'nome': 'Plano VIP 12 meses',
        'valor': 289.90,
        'dias': 365,
        'pix': '00020101021126580014br.gov.bcb.pix01369cf720a7-fa96-4b33-8a37-76a401089d5f5204000053039865406289.905802BR5919AZ FULL ADMINISTRAC6008BRASILIA62070503***6304CD13'
    }
}

# Dicionário para armazenar usuários e expirações (em produção, use um banco de dados)
usuarios = {}

@bot.message_handler(commands=['start', 'vip'])
def send_welcome(message):
    markup = InlineKeyboardMarkup()
    for key, plano in PLANOS.items():
        btn_text = f"{plano['nome']} - R${plano['valor']}"
        markup.add(InlineKeyboardButton(btn_text, callback_data=key))
    
    bot.send_message(
        message.chat.id,
        "🎭 *Bem-vindo ao Conteúdo VIP!* 🎭\n\n"
        "Escolha abaixo por quanto tempo deseja acesso:",
        reply_markup=markup,
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    plano = PLANOS.get(call.data)
    if plano:
        response = (
            f"💎 *{plano['nome']}* 💎\n"
            f"💵 Valor: *R${plano['valor']}*\n"
            f"⏳ Duração: *{plano['dias']} dias*\n\n"
            "📲 *PIX Copia e Cola:*\n"
            f"`{plano['pix']}`\n\n"
            "⚠️ Após o pagamento, envie o comprovante para @oiclarinhaalves"
        )
        
        bot.send_message(
            call.message.chat.id,
            response,
            parse_mode='Markdown'
        )
    else:
        bot.answer_callback_query(call.id, "Opção inválida")

def adicionar_vip(user_id, plano_key):
    plano = PLANOS.get(plano_key)
    if plano:
        try:
            # Tenta remover restrições primeiro (caso o usuário já tenha sido banido)
            bot.unban_chat_member(CHANNEL_VIP_ID, user_id)
            
            # Concede acesso ao canal
            invite_link = 'https://t.me/+9TBR6fK429tiMmRh'
            bot.send_message(
                user_id,
                f"✅ *Pagamento confirmado!*\n\n"
                f"Agora você tem acesso ao conteúdo VIP por {plano['dias']} dias!\n\n"
                f"👉 Acesse aqui: {invite_link}",
                parse_mode='Markdown'
            )
            
            # Calcula data de expiração
            expiracao = datetime.now() + timedelta(days=plano['dias'])
            usuarios[user_id] = expiracao
            
            # Agenda remoção automática
            threading.Timer(plano['dias'] * 86400, remover_vip, args=[user_id]).start()
            
            return True
        except Exception as e:
            print(f"Erro ao adicionar VIP: {e}")
            return False
    return False

def remover_vip(user_id):
    try:
        bot.ban_chat_member(CHANNEL_VIP_ID, user_id)
        if user_id in usuarios:
            del usuarios[user_id]
            
        bot.send_message(
            user_id,
            "⏳ *Seu acesso VIP expirou!*\n\n"
            "Para renovar, use /vip",
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Erro ao remover VIP: {e}")

@bot.message_handler(commands=['aprovar'])
def aprovar_pagamento(message):
    if message.from_user.id == ADMIN_ID:
        try:
            _, user_id, plano_key = message.text.split()
            user_id = int(user_id)
            
            if adicionar_vip(user_id, plano_key):
                bot.reply_to(message, f"✅ Usuário {user_id} adicionado ao VIP!")
            else:
                bot.reply_to(message, "❌ Erro ao adicionar usuário.")
        except ValueError:
            bot.reply_to(message, "Formato incorreto. Use: /aprovar USER_ID PLANO\nEx: /aprovar 123456 1mes")
    else:
        bot.reply_to(message, "🚫 Acesso negado.")

def verificar_expirados():
    while True:
        agora = datetime.now()
        expirados = [uid for uid, exp in usuarios.items() if exp <= agora]
        
        for uid in expirados:
            remover_vip(uid)
            
        time.sleep(3600)  # Verifica a cada hora

# Inicia a verificação em segundo plano
threading.Thread(target=verificar_expirados, daemon=True).start()

print("🤖 Bot em execução...")
bot.infinity_polling()
