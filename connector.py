import asyncio
import multiprocessing
import os
import sys
from pprint import pformat

from dotenv import load_dotenv
from requests.exceptions import ConnectionError
from urllib3.exceptions import NameResolutionError

import db
import tgbot
import vkapi
from constants import ConnectorConstants as ConnConst
from constants import DbConstant, TgConstants
from exceptions import (LongPollConnectionError, LongPollResponseError,
                        VkApiConnectionError, VkApiError)
from logger import run_logger

logger = run_logger(os.path.basename(sys.argv[0]))


class VkTgConnector(vkapi.VkApi):
    """Обработает обновления от API Vk и передаст их Telegram-боту."""

    def __init__(self):
        super().__init__()

    async def manager(self):
        logger.info(
            '\nЗапуск vk-tg connector v0.1.6a.'
            f'\nБаза данных подключена ({DbConstant.DB_ENGINE.value}).'
        )

        while True:
            try:
                if not self.timestamp:
                    logger.info('Получаем новый Vk LongPoll-сервер.')

                    params = self.get_vk_long_pol_server()
                    self.update_params(params=params)

                    logger.info('Vk LongPoll-сервер получен. Ждем обновлений.')

                response = self.connect_vk_long_poll_server(
                    wait=ConnConst.LONG_POLL_INTERVAL.value
                )
                self.timestamp = response.get('ts')
                updates = response.get('updates')

                if updates:
                    await self.processing_updates(updates=updates)

            except (
                    ConnectionError,
                    NameResolutionError,
                    VkApiConnectionError,
            ) as error:
                logger.error(msg=str(error))

                await asyncio.sleep(ConnConst.CONN_ER_INTERVAL.value)

            except LongPollConnectionError as error:
                logger.warning(f'LongPollConnectionError: {error}')

            except LongPollResponseError as error:
                logger.warning(f'LongPollResponseError: {error}')

                self.timestamp = None

            except VkApiError as error:
                error = str(error)
                logger.error(msg=error)

                await bot.app.bot.send_message(
                    chat_id=TgConstants.TELEGRAM_CHAT_ID.value,
                    text=error,
                )

                await asyncio.sleep(ConnConst.API_ER_TRY_INTERVAL.value)

            except Exception as error:
                logger.exception(f'Что-то пошло не так: {error}')

                await asyncio.sleep(ConnConst.EXCEPTION_TRY_INTERVAL.value)

    async def processing_updates(self, updates):
        logger.debug(pformat(f'Update: {updates}'))

        for element in updates:
            if element[0] == 7:
                vk_user_id = element[1]

                await bot.send_read_notification(vk_user_id=vk_user_id)
            elif (
                element[0] == ConnConst.NEW_MSG_CODE.value
                and element[2] not in ConnConst.OUTGOING_MSG_CODE.value
            ):
                logger.info(
                    'Новое входящее сообщение. Подготавливаем пересылку.'
                )

                await self.handle_incoming_message(update=element)

    async def handle_incoming_message(self, update):
        logger.debug(pformat(update))

        message_id = update[1]
        sender_id = update[3]
        short_msg_data = update[6]

        message_data = self.get_message_by_id(message_id=message_id,)
        message = self.get_message(
            message_data=message_data,
            short_msg_data=(
                short_msg_data if 'sticker' in short_msg_data.values()
                else None
            ),
        )

        if 'reply' in short_msg_data.keys():
            reply_orig_msg_id = self.get_reply_orig_msg_id(
                message_data=message_data,
            )
            msg_in_db = table_chat.get_message(vk_message_id=reply_orig_msg_id)

            if msg_in_db:
                reply_orig_message_tg_id = msg_in_db.tg_message_id

                await self.send_reply(
                    sender_id=sender_id,
                    reply=message,
                    reply_orig_message_tg_id=reply_orig_message_tg_id,
                )
            else:
                reply_orig_message = self.get_reply_original_message(
                    message_data=message_data,
                )
                reply_orig_message['message_id'] = message_id

                await self.send_reply(
                    sender_id=sender_id,
                    reply=message,
                    reply_orig_message=reply_orig_message,
                )

        elif 'wall' in short_msg_data.values():
            attachments = message_data['response']['items'][0]['attachments']
            post = self.get_wall(attachments=attachments)
            post['message_id'] = message_id

            await self.send_wall(
                post_comment=message,
                post=post,
                sender_id=sender_id,
            )
        else:
            message['text'] = self.text_for_tg(**message)

            await bot.send_msg_vk_tg(
                vk_sender_id=sender_id,
                message=message,
            )

    async def send_wall(self, sender_id, post_comment, post):
        ids = {'post_comment_id': None, 'post_id': None}
        post_comment_exists = self.content_exists(message=post_comment,)

        if post_comment_exists:
            post_comment['text'] = self.text_for_tg(**post_comment,)
            ids['post_comment_id'] = await bot.send_msg_vk_tg(
                vk_sender_id=sender_id,
                message=post_comment,
            )

        sender_signature = self.get_signature(**post_comment)
        post['text'] = self.text_for_tg(
            head_signature=(
                sender_signature if not post_comment_exists else None
            ), **post,
        )

        ids['post_id'] = await bot.send_msg_vk_tg(
            vk_sender_id=sender_id,
            message=post,
        )

        return ids

    async def send_reply(
            self,
            sender_id,
            reply,
            reply_orig_message=None,
            reply_orig_message_tg_id=None,
    ):
        reply['text'] = self.text_for_tg(**reply)

        if reply_orig_message_tg_id:
            tg_msg_id_for_reply = reply_orig_message_tg_id
        elif 'wall' in reply_orig_message:
            post = reply_orig_message['wall']
            post_comment = reply_orig_message

            messages_id = await self.send_wall(
                sender_id=sender_id,
                post_comment=post_comment,
                post=post,
            )

            if messages_id.get('post_comment_id'):
                tg_msg_id_for_reply = messages_id.get('post_comment_id')
            else:
                tg_msg_id_for_reply = messages_id.get('post_id')

        else:
            reply_orig_message['text'] = self.text_for_tg(
                **reply_orig_message,
            )
            tg_msg_id_for_reply = await bot.send_msg_vk_tg(
                vk_sender_id=sender_id,
                message=reply_orig_message,
            )

        await bot.send_msg_vk_tg(
            vk_sender_id=sender_id,
            message=reply,
            reply_to_message_id=tg_msg_id_for_reply,
        )

    def content_exists(self, message):
        return (
            message['text'] != ''
            or len(message['images']) > 0
            or len(message['videos']['video_urls']) > 0
        )

    def text_for_tg(self, head_signature=None, **kwargs):
        if kwargs.get('message_type') == 'wall':
            wall_signature = self.get_signature(wall=True, **kwargs)

            if head_signature:
                text = (
                    f'<b>{head_signature}</b>\n\n'
                    f'<b>Переслано от {wall_signature}</b>\n'
                )
            else:
                text = f'<b>Переслано от {wall_signature}</b>\n'
        else:
            signature = self.get_signature(**kwargs)
            text = f'{signature}\n'

        if kwargs.get('text'):
            msg_text = kwargs.get('text')
            text += f'{msg_text}\n'

        videos = kwargs.get('videos', {}).get('video_urls')

        if videos:
            formatted_videos = '\n\n'.join(videos)
            text += f'\n<b>Видео:</b>\n{formatted_videos}'

        return text

    def get_signature(self, wall=False, **kwargs):
        author_type = kwargs.get('type')

        if author_type == 'user':
            user_id = kwargs.get('user_id')
            name = f'{kwargs.get("first_name")} {kwargs.get("last_name")}'

            if wall:
                post_id = kwargs.get('post_id')
                url = f'https://vk.com/wall{user_id}_{post_id}'
            else:
                url = f'https://vk.com/im?sel={user_id}'
        else:
            group_id = kwargs.get('group_id')
            name = kwargs.get('group_name')

            if wall:
                post_id = kwargs.get('post_id')
                url = f'https://vk.com/wall-{group_id}_{post_id}'
            else:
                url = f'https://vk.com/club{group_id}'

        signature = (
            f'<a href="{url}"><b>{name}</b></a>'
        )

        return signature


if __name__ == '__main__':
    table_chat = db.Database()
    bot = tgbot.TgBot(db_table=table_chat)
    shared_unread_messages = multiprocessing.Manager().dict()
    shared_notifications = multiprocessing.Manager().dict()
    bot.unread_out_messages = shared_unread_messages
    bot.read_notifications = shared_notifications

    bot.add_handlers()

    bot_process = multiprocessing.Process(target=bot.polling)
    bot_process.start()

    connector = VkTgConnector()
    asyncio.run(connector.manager())

    try:
        bot_process.join()
    finally:
        bot_process.terminate()
