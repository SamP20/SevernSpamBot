import random
from enum import IntEnum
import logging

logger = logging.getLogger(__name__)

MESSAGE_TABLE = "messages2"


class FileType(IntEnum):
    Audio = 1
    Document = 2
    Photo = 3
    Sticker = 4
    Video = 5
    Voice = 6


class BoundParameter:
    def __init__(self, database, name, default=None, cast_fn=None):
        self.database = database
        self.name = name
        self.default = default
        self.cast_fn = cast_fn
        # Prefetch parameter
        database.get_parameter(name, default)

    def get(self):
        param = self.database.get_parameter(self.name, self.default)
        if self.cast_fn:
            param = self.cast_fn(param)
        return param

    def set(self, value):
        self.database.set_parameter(self.name, value)

    def __repr__(self):
        return repr(self.__get__(None))

    def __str__(self):
        return str(self.__get__(None))


class Database:
    def __init__(self, conn):
        self.conn = conn
        self._param_cache = {}

    def initialize(self):
        query = ("CREATE TABLE IF NOT EXISTS chains "
                 "(source text, response text, count int)")
        self.conn.execute(query)
        query = ("CREATE UNIQUE INDEX IF NOT EXISTS i_chains ON chains "
                 "(source, response)")
        self.conn.execute(query)

        query = """
            CREATE TABLE IF NOT EXISTS {} (
                "chat_id" INTEGER NOT NULL,
                "message_id" INTEGER NOT NULL,
                "user_id" INTEGER,
                "message" TEXT,
                "file_id" TEXT,
                "filetype" INTEGER,
                "reply_to" INTEGER,
                "sent" DATETIME,
                PRIMARY KEY (chat_id, message_id)
            )
        """.format(MESSAGE_TABLE)
        self.conn.execute(query)

        query = """
            CREATE TABLE IF NOT EXISTS params (
                key text NOT NULL,
                value
            )
        """
        self.conn.execute(query)
        query = ("CREATE UNIQUE INDEX IF NOT EXISTS i_params ON params "
                 "(key)")
        self.conn.execute(query)

        query = """
            CREATE TABLE IF NOT EXISTS chat_aliases (
                name text NOT NULL,
                chat_id NOT NULL
            )
        """
        self.conn.execute(query)
        query = ("CREATE UNIQUE INDEX IF NOT EXISTS i_name "
                 "ON chat_aliases (name)")
        self.conn.execute(query)
        query = ("CREATE UNIQUE INDEX IF NOT EXISTS i_chat_id "
                 "ON chat_aliases (chat_id)")

        self.conn.execute(query)
        query = """
            CREATE TABLE IF NOT EXISTS chat_states (
                chat_id int NOT NULL,
                messages_since_reply int NOT NULL,
                stickers_since_reply int NOT NULL,
                chain_length int NOT NULL
            )
        """
        self.conn.execute(query)
        query = ("CREATE UNIQUE INDEX IF NOT EXISTS i_chat_states "
                 "ON chat_states (chat_id)")
        self.conn.execute(query)

    def commit(self):
        return self.conn.commit()

    def set_parameter(self, key, value):
        self._param_cache[key] = value
        logger.debug('setting {} = {}'.format(key, value))
        query = "INSERT OR REPLACE INTO params VALUES (?, ?)"
        self.conn.execute(query, (key, value))

    def get_parameter(self, key, default=None):
        try:
            return self._param_cache[key]
        except KeyError:
            query = "SELECT value FROM params WHERE key = ?"
            row = self.conn.execute(query, (key,)).fetchone()
            if row:
                self._param_cache[key] = row[0]
                return row[0]
            else:
                self.set_parameter(key, default)
                return default

    def get_parameters(self):
        query = "SELECT key, value FROM params"
        return self.conn.execute(query)

    def bound_parameter(self, key, default=None, cast_fn=None):
        return BoundParameter(self, key, default, cast_fn)

    def set_chat_alias(self, name, value):
        query = "INSERT OR REPLACE INTO chat_aliases VALUES (?, ?)"
        self.conn.execute(query, (name, value))

    def delete_chat_alias(self, name):
        query = "DELETE FROM chat_aliases WHERE name = ?"
        self.conn.execute(query, (name,))

    def get_chat_alias(self, name):
        query = "SELECT chat_id FROM chat_aliases WHERE name = ?"
        row = self.conn.execute(query, (name,)).fetchone()
        if row:
            return row[0]
        return None

    def get_all_chat_aliases(self):
        query = "SELECT name, chat_id FROM chat_aliases"
        return self.conn.execute(query).fetchall()

    def get_chat_state(self, chat_id):
        query = """
            SELECT
                messages_since_reply,
                stickers_since_reply,
                chain_length
            FROM chat_states WHERE
                chat_id = ?
        """
        return self.conn.execute(query, (chat_id, )).fetchone()

    def set_chat_state(self, chat_id,
                       messages_since_reply,
                       stickers_since_reply,
                       chain_length):
        query = """
            INSERT OR REPLACE INTO chat_states
                (chat_id,
                messages_since_reply,
                stickers_since_reply,
                chain_length)
            VALUES (?,?,?,?)
        """
        values = (chat_id,
                  messages_since_reply,
                  stickers_since_reply,
                  chain_length)
        self.conn.execute(query, values)

    def add_message(self, message):
        kwargs = {
            'chat_id': message.chat.id,
            'message_id': message.message_id,
            'sent': message.date.timestamp()
        }
        if message.from_user:
            kwargs['user_id'] = message.from_user.id
        if message.sticker:
            kwargs['file_id'] = message.sticker.file_id
            kwargs['filetype'] = FileType.Sticker
        if message.reply_to_message:
            kwargs['reply_to'] = message.reply_to_message.message_id
        if message.text:
            kwargs['message'] = message.text

        keys = kwargs.keys()
        query = "INSERT INTO {} ({}) VALUES ({})".format(
            MESSAGE_TABLE,
            ', '.join(keys),
            ', '.join([':'+key for key in keys]))
        self.conn.execute(query, kwargs)

    def add_link(self, source, response):
        query = """
            INSERT OR REPLACE INTO chains
            VALUES (:source, :response,
              COALESCE(
                (SELECT count FROM chains
                   WHERE source=:source AND response=:response),
                0) + 1);
        """
        self.conn.execute(query, {'source': source, 'response': response})

    def get_response_rows(self, source):
        query = "SELECT response, count FROM chains WHERE source=?"
        return self.conn.execute(query, (source, ))
