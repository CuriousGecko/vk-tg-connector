import os
from enum import Enum
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

load_dotenv()

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')


class DbConstant(Enum):
    USE_POSTGRES = os.getenv('USE_POSTGRES', 'True').lower() == 'true'

    if USE_POSTGRES:
        POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'db_postgres')
        POSTGRES_PORT = os.getenv('POSTGRES_PORT', 5432)
        POSTGRES_USER = os.getenv('POSTGRES_USER')
        POSTGRES_PSW = os.getenv('POSTGRES_PASSWORD')
        POSTGRES_DB = os.getenv('POSTGRES_DB', 'chats')
        ECHO = os.getenv('ECHO', 'False').lower() == 'true'
        DB_URL = (
            f'postgresql://{POSTGRES_USER}:{POSTGRES_PSW}'
            f'@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}'
        )
        DB_ENGINE = 'PostgreSQL'
    else:
        DB_URL = 'sqlite:///chats.sqlite3'
        DB_ENGINE = 'SQLite'

    MAX_MESSAGES_PER_USER = 200


class ConnectorConstant(Enum):
    VK_ID = int(os.getenv('VK_ID'))
    LONG_POLL_INTERVAL = 25
    CONN_ER_INTERVAL = 30
    API_ER_TRY_INTERVAL = 30
    EXCEPTION_TRY_INTERVAL = 60
    OUTGOING_MSG_CODE = (51, 35, 19, 2097203, 2097187)
    NEW_MSG_CODE = 4


class TgConstant(Enum):
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = int(os.getenv('TELEGRAM_CHAT_ID'))
    READ_NOTIFICATION_MODE = int(os.getenv('READ_NOTIFICATION_MODE'))
    SEND_MSG_CONN_TIMEOUT = 120
    DEL_NOTIFICATION_OF_SEND = 2


def get_vk_token():
    token = os.getenv('VK_ACCESS_TOKEN')

    if 'https' in token:
        parsed_url = urlparse(token)
        fragment = parsed_url.fragment
        token_params = parse_qs(fragment)
        token = token_params.get('access_token')[0]

    return token


class VkConstant(Enum):
    ACCESS_TOKEN = get_vk_token()
    NEED_PTS = 0
    LP_VERSION = 3
    API_VERSION = 5.199
    LONG_POLL_MODE = 2
    LONG_POLL_VERSION = 2

    ENDPOINTS = {
        'get_lp_server': (
            'https://api.vk.com/method/messages.getLongPollServer'
        ),
        'get_users': 'https://api.vk.com/method/users.get',
        'get_group': 'https://api.vk.com/method/groups.getById',
        'get_video': 'https://api.vk.com/method/video.get',
        'send_message': 'https://api.vk.com/method/messages.send',
        'get_message_by_id': 'https://api.vk.com/method/messages.getById',
        'get_friends': 'https://api.vk.com/method/friends.get',
        'get_short_link': 'https://api.vk.com/method/utils.getShortLink',
        'message_mark_as_read': (
            'https://api.vk.com/method/messages.markAsRead'
        ),
        'get_photo_upload_server': (
            'https://api.vk.com/method/photos.getMessagesUploadServer'
        ),
        'save_messages_photo': (
            'https://api.vk.com/method/photos.saveMessagesPhoto'
        ),
    }
