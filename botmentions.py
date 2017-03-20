import re
import random
from datetime import datetime


notices = {}


def on_message(bot, update):
    message = update.message
    username = bot.username
    if message.entities:
        for ent in message.entities:
            if ent.type != 'mention':
                continue
            a, b = ent.offset, ent.offset+ent.length
            text = message.text[a+1:b]  # drop the @
            if text.lower() == username.lower():
                text = (message.text[:a]+message.text[b:]).strip()
                on_bot_mention(bot, update, text)
                return


def re_fn(test):
    regex = re.compile(test)
    return lambda x: regex.search(x) is not None


def on_bot_mention(bot, update, text):
    responses = [
        (re_fn(r'notice\s+me'), on_notice_me)
    ]
    for response in responses:
        if response[0](text):
            response[1](bot, update, text)


def on_notice_me(bot, update, text):
    user_id = update.message.from_user.id
    last_notice = notices.get(user_id)
    now = datetime.now()
    chance = 0.5

    if last_notice:
        delta = now - last_notice
        if delta.total_seconds() < 60*5:
            chance = 0.0

    if random.random() < chance:
        update.message.reply_text('*notices you*')
    else:
        update.message.reply_text('*ignores you*')
    notices[user_id] = now
