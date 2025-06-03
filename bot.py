import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import time
from datetime import datetime, timedelta

# Configurações (seus dados já incluídos)
TOKEN = '7963030995:AAE8K5RIFJpaOhxLnDxJ4k614wnq4n549AQ'
CHANNEL_VIP_ID = '-1002280243232'
ADMIN_ID = 6150001511

bot = telebot.TeleBot(TOKEN)

PLANOS = {
    '1mes': {'nome': 'Plano VIP 1 mês', 'valor': 39.90, 'dias': 30, 'pix': '000201...4086'},
    '3meses': {'nome': 'Plano VIP 3 meses', 'valor': 99.90, 'dias': 90, 'pix': '000201...1E24'},
    '6meses': {'nome': 'Plano VIP 6 meses', 'valor': 179.90, 'dias': 180, 'pix': '000201...3084'},
    '12meses': {'nome': 'Plano VIP 12 meses', 'valor': 289.90, 'dias': 365, 'pix': '000201...CD13'}
}

usuarios = {}

def criar_menu_principal():
    markup = InlineKeyboardMarkup()
    for key in PLANOS:
        btn = InlineKeyboardButton(
            text=f"{PLANOS[key]['nome']} - R${PLANOS[key]['valor']}",
            callback_data=f"plano_{key}"
        )
        markup.add(btn)
    return markup

def criar_menu_comprovante(plano_key):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("📤 Enviar Comprovante", url=f"https://t.me/oiclarinhaalves"),
        InlineKeyboardButton("↩️ Escolher Outro Plano", callback_data="voltar_planos")
    )
    return markup

@bot.message_handler(commands=['start', 'vip'])
def comando_start(message):
    bot.send_message(
        message.chat.id,
        "🎭 *Escolha seu plano VIP:*",
        reply_markup=criar_menu_principal(),
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('plano_'))
def mostrar_pix(call):
    plano_key = call.data.split('_')[1]
    plano = PLANOS[plano_key]
    
    msg = (
        f"💎 *{plano['nome']}*\n"
        f"💵 Valor: *R${plano['valor']}*\n"
        f"⏳ Duração: *{plano['dias']} dias*\n\n"
        "📲 *Chave PIX:*\n"
        f"`{plano['pix']}`\n\n"
        "⚠️ Após o pagamento, clique em *Enviar Comprovante*"
    )
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=msg,
        reply_markup=criar_menu_comprovante(plano_key),
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data == 'voltar_planos')
def voltar_para_planos(call):
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="🎭 *Escolha seu plano VIP:*",
        reply_markup=criar_menu_principal(),
        parse_mode='Markdown'
    )

# ... (mantenha as funções adicionar_vip, remover_vip e aprovar_pagamento do código anterior)

print("🤖 Bot VIP Ativo!")
bot.infinity_polling()
