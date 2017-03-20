import math
import random


def expfn(minx, halflife, x):
    if x < minx:
        return 0.0
    return 1.0 - 0.5**((x-minx)/halflife)


def linfn(minx, maxx, x):
    if x <= minx:
        return 0.0
    if x >= maxx:
        return 1.0
    return (x-minx)/(maxx-minx)


class ChatStates:
    def __init__(self, database):
        self.min_sticker_interval = \
            database.bound_parameter('min_sticker_interval', 6, int)
        self.max_sticker_interval = \
            database.bound_parameter('max_sticker_interval', 10, int)
        self.min_chain_length = \
            database.bound_parameter('min_chain_length', 0, int)
        self.max_chain_length = \
            database.bound_parameter('max_chain_length', 2, int)
        self.max_reply_chance = \
            database.bound_parameter('max_reply_chance', 1.0, float)
        self.database = database
        self._states = {}

    def __getitem__(self, chat_id):
        try:
            state = self._states[chat_id]
        except KeyError:
            row = self.database.get_chat_state(chat_id)
            if row:
                state = ChatState(self, chat_id,
                                  messages_since_reply=row[0],
                                  stickers_since_reply=row[1],
                                  chain_length=row[2])
            else:
                state = ChatState(self, chat_id, 0, 0, 0)
            self._states[chat_id] = state
        return state

    def on_reply(self, chat_id):
        self[chat_id].on_reply()
        self._save_state(self[chat_id])

    def on_message(self, chat_id):
        self[chat_id].on_message()
        self._save_state(self[chat_id])

    def on_sticker(self, chat_id):
        self[chat_id].on_sticker()
        self._save_state(self[chat_id])

    def _save_state(self, chat_state):
        self.database.set_chat_state(
            chat_state.chat_id,
            chat_state.messages_since_reply,
            chat_state.stickers_since_reply,
            chat_state.chain_length
        )

    def _reply_probability(self, chat_state):
        stkr = linfn(self.min_sticker_interval.get(),
                     self.max_sticker_interval.get(),
                     chat_state.stickers_since_reply)
        chain = linfn(self.min_chain_length.get(),
                      self.max_chain_length.get(),
                      chat_state.chain_length)
        return stkr * chain * self.max_reply_chance.get()

    def should_reply(self, chat_id):
        return self[chat_id].should_reply()


class ChatState:
    def __init__(self, parent, chat_id,
                 messages_since_reply,
                 stickers_since_reply,
                 chain_length):
        self.parent = parent
        self.chat_id = chat_id
        self.messages_since_reply = messages_since_reply
        self.stickers_since_reply = stickers_since_reply
        self.chain_length = chain_length

    def on_reply(self):
        self.messages_since_reply = 0
        self.stickers_since_reply = 0

    def on_message(self):
        self.messages_since_reply += 1
        self.chain_length = 0

    def on_sticker(self):
        self.stickers_since_reply += 1
        self.chain_length += 1

    def save(self):
        self.parent._save_state(self)

    def reply_probability(self):
        return self.parent._reply_probability(self)

    def should_reply(self):
        return random.random() < self.parent._reply_probability(self)
