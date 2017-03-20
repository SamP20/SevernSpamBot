from telegram.ext import Updater, MessageHandler, Filters, BaseFilter, Handler
from markov import Markov
from database import Database
from datetime import datetime
from admin import Admin
from chatstates import ChatStates
import botmentions
import config
import sqlite3
import logging
import os


logger = logging.getLogger(__name__)
database = None
markov = None
updater = None
chat_states = None


class AllUpdateHandler(Handler):
    def check_update(self, update):
        return True

    def handle_update(self, update, dispatcher):
        return self.callback(dispatcher.bot, update)


def on_sticker(bot, update):
    logger.debug('Sticker received')
    message = update.message
    chat_id = message.chat.id
    sticker_id = message.sticker.file_id

    markov.add_item(sticker_id, chat_id)
    state = chat_states[chat_id]
    state.on_sticker()

    # Don't reply if bot was slow retreiving message
    if (datetime.now() - message.date).total_seconds() > 3:
        return

    if state.should_reply():
        sticker = markov.get_response(chat_id)
        if sticker:
            state.on_reply()
            bot.send_sticker(chat_id=chat_id, sticker=sticker)
            # This allows replies to the bot to be added to the chains
            markov.add_item(sticker, chat_id, False)
    state.save()


def on_message(bot, update):
    message = update.message
    chat_id = message.chat.id
    markov.break_chain(chat_id)
    chat_states.on_message(chat_id)
    botmentions.on_message(bot, update)


def on_post_message(bot, update):
    database.add_message(update.message)
    on_post_update(bot, update)


def on_post_update(bot, update):
    database.set_parameter('last_update', update.update_id)
    database.commit()


def on_error(bot, update, error):
    logger.warn('Update "{}" caused error "{}"'.format(update, error))


def main():
    global database
    global markov
    global updater
    global chat_states
    # This is safe as long as we only access the db within the dispatcher
    # callbacks. If not then we need locks.
    database = Database(sqlite3.connect(config.DBFILE, check_same_thread=False))
    database.initialize()
    markov = Markov(database)
    chat_states = ChatStates(database)
    updater = Updater(config.TOKEN)

    updater.last_update_id = database.get_parameter('last_update', -1)+1

    admin = Admin(database, markov, updater, chat_states, config.ADMIN_LIST)

    dp = updater.dispatcher

    admin.register_handlers(dp)
    dp.add_handler(MessageHandler(Filters.sticker, on_sticker), 0)
    dp.add_handler(MessageHandler(Filters.all, on_message), 0)

    # Commit updates after being handled. This avoids messages being handled
    # twice or updates being missed
    dp.add_handler(MessageHandler(Filters.all, on_post_message), 1)
    dp.add_handler(AllUpdateHandler(on_post_update), 1)

    dp.add_error_handler(on_error)

    updater.start_polling()
    updater.idle()
    os._exit(0)


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        level=config.LOG_LEVEL)
    main()
