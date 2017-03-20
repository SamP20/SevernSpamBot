from telegram.ext import CommandHandler, ConversationHandler, MessageHandler
from telegram.ext import Filters
from functools import wraps
import traceback
import logging

STICKER, = range(1)

logger = logging.getLogger(__name__)


def restricted(func):
    @wraps(func)
    def wrapped(self, bot, update, *args, **kwargs):
        # extract user_id from arbitrary update
        message = None
        if update.message:
            message = update.message
        elif update.inline_query:
            message = update.inline_query
        elif update.edited_message:
            message = update.edited_message
        elif update.chosen_inline_result:
            message = update.chosen_inline_result
        elif update.callback_query:
            message = update.callback_query
        if not message:
            logger.debug("No valid field available in update.")
            return
        try:
            user_id = message.from_user.id
        except (NameError, AttributeError):
            logger.debug("No user_id available in update.")
            return
        if user_id not in self.admins:
            logger.info("Unauthorized access denied for {}.".format(user_id))
            return
        return func(self, bot, update, *args, **kwargs)
    return wrapped


class Admin:
    def __init__(self, database, markov, updater, chat_states, admins):
        self.database = database
        self.markov = markov
        self.updater = updater
        self.chat_states = chat_states
        self.admins = admins
        # Conversation targets
        self.targets = {}

    def register_handlers(self, dispatcher):
        dispatcher.add_handler(ConversationHandler(
            entry_points=[CommandHandler('sticker',
                                         self.on_pre_sticker,
                                         pass_args=True)],

            states={
                STICKER: [MessageHandler(Filters.sticker, self.on_sticker)]
            },

            fallbacks=[CommandHandler('cancel', self.on_cancel)]
        ))
        dispatcher.add_handler(CommandHandler(
            'kill', self.on_kill), 0)
        dispatcher.add_handler(CommandHandler(
            'eval', self.on_eval, allow_edited=True), 0)
        dispatcher.add_handler(CommandHandler(
            'setparam', self.on_setparam, pass_args=True), 0)
        dispatcher.add_handler(CommandHandler(
            'setint', self.on_setint, pass_args=True), 0)
        dispatcher.add_handler(CommandHandler(
            'setfloat', self.on_setfloat, pass_args=True), 0)
        dispatcher.add_handler(CommandHandler(
            'getparams', self.on_getparams), 0)
        dispatcher.add_handler(CommandHandler(
            'setalias', self.on_setalias, pass_args=True), 0)
        dispatcher.add_handler(CommandHandler(
            'message', self.on_message), 0)

    @restricted
    def on_kill(self, bot, update):
        update.message.reply_text('*dies*')
        logger.debug('Stop command sent')
        self.updater.is_idle = False
        self.updater.stop()

    @restricted
    def on_setparam(self, bot, update, args):
        if len(args) < 2:
            update.message.reply_text('usage: /setparam <name> <value>')
            return
        name = args[0]
        value = ' '.join(args[1:])
        self.database.set_parameter(name, value)
        update.message.reply_text('Paramater {} set to {}'.format(name, value))

    @restricted
    def on_setint(self, bot, update, args):
        if len(args) < 2:
            update.message.reply_text('usage: /setint <name> <value>')
            return
        name = args[0]
        try:
            value = int(' '.join(args[1:]))
        except ValueError:
            update.message.reply_text('{} is not an integer'.format(args[1]))
        else:
            self.database.set_parameter(name, value)
            update.message.reply_text(
                'Paramater {} set to {}'.format(name, value))

    @restricted
    def on_setfloat(self, bot, update, args):
        if len(args) < 2:
            update.message.reply_text('usage: /setfloat <name> <value>')
            return
        name = args[0]
        try:
            value = float(' '.join(args[1:]))
        except ValueError:
            update.message.reply_text('{} is not a float'.format(args[1]))
        else:
            self.database.set_parameter(name, value)
            update.message.reply_text(
                'Paramater {} set to {}'.format(name, value))

    @restricted
    def on_getparams(self, bot, update):
        lines = []
        for row in self.database.get_parameters():
            lines.append('{} = {}'.format(row[0], row[1]))
        if lines:
            update.message.reply_text('\n'.join(lines))
        else:
            update.message.reply_text('No parameters found')

    @restricted
    def on_eval(self, bot, update):
        if update.message:
            message = update.message
        elif update.edited_message:
            message = update.edited_message
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            message.reply_text('usage: /eval <command>')
            return

        # Bring in some convenience locals
        chat_id = message.chat.id
        chat_state = self.chat_states[chat_id]
        db = self.database
        markov = self.markov

        try:
            message.reply_text(repr(eval(args[1])))
        except SyntaxError:
            exec(args[1])
        except Exception:
            message.reply_text(traceback.format_exc())

    @restricted
    def on_setalias(self, bot, update, args):
        if update.message:
            message = update.message
        elif update.edited_message:
            message = update.edited_message
        if len(args) < 1:
            update.message.reply_text('usage: /setalias <name> ')
            return
        name = args[0]
        self.database.set_chat_alias(name, message.chat.id)
        for admin in self.admins:
            bot.send_message(chat_id=admin, text='New alias: {}'.format(name))

    @restricted
    def on_message(self, bot, update):
        if update.message:
            message = update.message
        elif update.edited_message:
            message = update.edited_message
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            message.reply_text('usage: /message <chat> text')
            return
        alias = args[1]
        message = args[2]
        chat = self.database.get_chat_alias(alias)
        if chat:
            bot.send_message(chat_id=chat, text=message)

    @restricted
    def on_pre_sticker(self, bot, update, args):
        message = update.message
        if len(args) < 1:
            message.reply_text('usage: /sticker <chat>')
            return ConversationHandler.END
        message.reply_text('Please send the sticker you want to send\n'
                                  'or cancel with \cancel')
        alias = args[0]
        chat = self.database.get_chat_alias(alias)
        if not chat:
            message.reply_text('Sorry this chat doesn\'t exist')
            return ConversationHandler.END
        self.targets[(message.from_user.id, message.chat.id)] = chat
        return STICKER

    @restricted
    def on_sticker(self, bot, update):
        message = update.message
        sticker = message.sticker.file_id
        chat_id = self.targets.pop((message.from_user.id, message.chat.id))
        state = self.chat_states[chat_id]
        state.on_reply()
        bot.send_sticker(chat_id=chat_id, sticker=sticker)
        self.markov.add_item(sticker, chat_id, False)
        state.save()
        return ConversationHandler.END

    @restricted
    def on_cancel(self, bot, update):
        update.message.reply_text('Operation cancelled')
        return ConversationHandler.END
