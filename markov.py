from collections import defaultdict
import random
import logging

logger = logging.getLogger(__name__)

def items_to_key(items):
    return ' '.join(items)


class Markov:
    def __init__(self, database, max_order=2):
        self.db = database
        self.chats = defaultdict(list)
        self.max_order = max_order

    def add_item(self, item, chat_id, add_chain=True):
        chat = self.chats[chat_id]
        chat.append(item)
        if add_chain:
            logger.debug('Adding chain with item {}'.format(item))
            for order in range(1, self.max_order+1):
                if len(chat) <= order:
                    break
                source = items_to_key(chat[-(order+1):-1])
                response = chat[-1]
                self.db.add_link(source, response)

        # Trim excess items
        if len(chat) > self.max_order:
            chat.pop(0)  # This is O(n), but n is small so I don't care

    def break_chain(self, chat_id):
        self.chats.pop(chat_id, None)

    def get_response(self, chat_id):
        chain = self.chats[chat_id]
        response = None
        for i in range(self.max_order, 0, -1):
            if len(chain) < i:
                continue
            response = self.db.get_random_response(items_to_key(chain[-i:]))
            if response:
                break
        return response
