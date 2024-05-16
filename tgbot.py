import asyncio
import io
import re
import textwrap

import requests
import telegram
from PIL import Image
from telegram import (BotCommand, InlineKeyboardButton, InlineKeyboardMarkup,
                      Update)
from telegram.ext import (ApplicationBuilder, CallbackQueryHandler,
                          CommandHandler, ContextTypes, MessageHandler,
                          filters)

import db
import vkapi
from constants import TgConstants
from exceptions import (MissingMessageIdError, MissingUserVkIdIdError,
                        NoDataInResponseError)
from logger import run_logger

logger = run_logger('tgbot')


class TgBot(vkapi.VkApi):
    """Организует работу Telegram-бота."""

    def __init__(self, db_table):
        super().__init__()
        self.last_update_id = None
        self.unread_out_messages = dict()
        self.read_notifications = dict()
        self.table_chat = db_table
        self.app = ApplicationBuilder().token(
            TgConstants.TELEGRAM_BOT_TOKEN.value
        ).build()

        self.buttons = {
            'start': [
                ['Список друзей в Vk'],
                ['Указать собеседника'],
                ['Удалить собеседника'],
            ],
            'cancel': [['Отменить'], ],
            'delete': [['Подтвердить', 'Отменить'], ],
        }

    @staticmethod
    def log_method(func):
        async def wrapper(*args, **kwargs):
            method = func.__name__

            logger.debug(
                f'Вызов метода {method}. \nArgs: {args}, \nKwargs {kwargs}'
            )

            context = kwargs.get('context')
            update = kwargs.get('update')

            try:
                result = await func(*args, **kwargs)
                logger.debug(f'Метод {method} вернул {result}')
                return result

            except (MissingMessageIdError, MissingUserVkIdIdError) as error:
                error_text = f'Не удалось отправить сообщение: {error}'

                logger.error(msg=error_text,)

                await context.bot.send_message(
                    chat_id=update.effective_message.chat_id,
                    text=error_text,
                )
                return

            except NoDataInResponseError as error:
                vk_user_id = update.message.text

                logger.error(
                    'Ошибка создания связи чата с пользователем '
                    f'vk_id({vk_user_id}).\n'
                    f'NoDataInResponseError: {error}',
                )

                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text='Пользователь с таким vk_id не найден.',
                )

            except Exception as error:
                if method == 'start':
                    logger.error(
                        f'Во время вызова бота произошла ошибка: {error}'
                    )
                elif method == 'friends':
                    logger.error(
                        'Во время отправки списка друзей произошла ошибка: '
                        f'{error}'
                    )

                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=str(error),
                    )
                elif method == 'send_msg_tg_vk':
                    logger.error(
                        'Во время отправки сообщения в Vk произошла ошибка: '
                        f'{error}'
                    )
                elif method == 'send_msg_vk_tg':
                    logger.error(
                        'Во время отправки сообщения в Telegram произошла '
                        f'ошибка: {error}'
                    )
                else:
                    logger.exception(f'Что-то пошло не так: {error}')

        return wrapper

    def add_handlers(self):
        handlers = [
            CommandHandler(command='start', callback=self.start, ),
            CommandHandler(command='read', callback=self.mark_as_read, ),
            CommandHandler(command='help', callback=self.help, ),
            CallbackQueryHandler(
                pattern='Список друзей в Vk',
                callback=self.friends,
            ),
            CallbackQueryHandler(
                pattern='Указать собеседника',
                callback=self.add_chat,
            ),
            CallbackQueryHandler(
                pattern='Удалить собеседника',
                callback=self.delete_chat,
            ),
            CallbackQueryHandler(
                pattern='Подтвердить',
                callback=self.chat_deletion_is_confirmed,
            ),
            CallbackQueryHandler(pattern='Отменить', callback=self.cancel, ),
            MessageHandler(
                filters=(filters.TEXT | filters.PHOTO),
                callback=self.message_from_user,
            ),
        ]

        for handler in handlers:
            self.app.add_handler(handler)

    def polling(self):
        try:
            logger.info('Запуск Telegram Polling.')
            self.app.run_polling()

        except Exception as error:
            logger.error(f'Ошибка при запросе обновлений: {error}')

    @log_method
    async def set_commands(self):
        commands = [
            BotCommand(
                command='read',
                description='Пометить сообщения как прочитанные',
            ),
            BotCommand(command='start', description='Запустить бота', ),
            BotCommand(command='help', description='Помощь', )
        ]

        await self.app.bot.set_my_commands(commands)

    @log_method
    async def help(
            self,
            update: Update,
            context: ContextTypes.DEFAULT_TYPE
    ):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='Подробная инструкция к боту:\n'
                 'https://github.com/CuriousGecko/vk-tg-connector'
        )

    @log_method
    async def mark_as_read(
            self,
            update: Update,
            context: ContextTypes.DEFAULT_TYPE
    ):
        text = {
            'success': 'Все сообщения собеседника помечены как прочитанные.',
            'forbidden': 'Операция не позволена.',
            'no_interlocutor': 'Операция не выполнена: в чате отсутствует '
                               'собеседник. Вызовите бота и укажите '
                               'собеседника.',
        }
        tg_chat_id = update.effective_chat.id
        access = self.check_permission(update=update)

        if not access:
            await context.bot.send_message(
                chat_id=tg_chat_id,
                text=text['forbidden'],
            )
            return

        chat = self.table_chat.get_chat(tg_chat_id=tg_chat_id)

        if not chat:
            await context.bot.send_message(
                chat_id=tg_chat_id,
                text=text['no_interlocutor'],
            )
            return

        vk_peer_id = chat.vk_user_id
        self.message_mark_as_read(peer_id=vk_peer_id)

        await context.bot.send_message(
            chat_id=tg_chat_id,
            text=text['success'],
        )

    def check_permission(self, update: Update,):
        access = update.effective_user.id == TgConstants.TELEGRAM_CHAT_ID.value

        return access

    def create_keyboard(self, buttons):
        keyboard = []

        for values in buttons:
            button_row = [
                InlineKeyboardButton(value, callback_data=value)
                for value in values
            ]
            keyboard.append(button_row)

        reply_markup = InlineKeyboardMarkup(keyboard)

        return reply_markup

    async def is_bot_admin(
            self,
            update: Update,
            context: ContextTypes.DEFAULT_TYPE,
    ):
        bot_info = await context.bot.get_chat_member(
            chat_id=update.effective_chat.id,
            user_id=context.bot.id,
        )

        return bot_info.status == 'administrator'

    @log_method
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        access = self.check_permission(update=update)

        if access:
            await self.set_commands()

            if update.effective_chat.id == TgConstants.TELEGRAM_CHAT_ID.value:
                bot_info = await context.bot.get_me()
                bot_link = f'@{bot_info.username}'
                text = (
                    '<b>Я бот, приветствую вас! В данный чат будут поступать '
                    'все адресованные вам сообщения из Vk. Для общения '
                    'используйте кнопку "Ответить". '
                    'Также вы можете перенаправить сообщения конкретного '
                    'пользователя в отдельный чат, для этого нужно '
                    'выполнить следующие действия:</b>\n\n'
                    '1. Создайте для собеседника группу.\n'
                    f'2. Добавьте в неё бота {bot_link}.\n'
                    '3. Назначьте бота администратором.\n'
                    '4. Запустите бота.\n'
                    '5. Добавьте с его помощью собеседника.\n'
                )

                return await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text,
                    parse_mode='HTML',
                )

            bot_is_admin = await self.is_bot_admin(update, context)

            if not bot_is_admin:
                text = (
                    'Я бот, приветствую вас! В данном чате у меня отсутствуют '
                    'необходимые для работы привилегии. Пожалуйста, назначьте '
                    'меня администратором, чтобы я мог добросовестно '
                    'исполнять свои обязанности, а после вызовите меня снова.'
                )

                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text,
                )
            else:
                reply_markup = self.create_keyboard(
                    buttons=self.buttons['start'],
                )

                if 'waiting_for_id' in context.user_data:
                    del context.user_data['waiting_for_id']

                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text='Я бот, приветствую вас! Чем могу помочь?',
                    reply_markup=reply_markup,
                )
        else:
            text = (
                'Приветствую! Я бот, с помощью которого вы можете '
                'отправлять и получать сообщения из социальной сети '
                'Вконтакте. '
                'К сожалению, мои настройки приватности не позволяют '
                'продолжить текущий диалог, но вы можете создать '
                'собственного бота, следуя инструкции: '
                'https://github.com/CuriousGecko/vk-tg-connector'
            )

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
            )

    @log_method
    async def cancel(
            self,
            update: Update,
            context: ContextTypes.DEFAULT_TYPE,
    ):
        if 'waiting_for_id' in context.user_data:
            del context.user_data['waiting_for_id']

        await context.bot.editMessageText(
            chat_id=update.effective_chat.id,
            message_id=update.effective_message.id,
            text='Операция отменена.\n\nМогу ли я помочь вам чем-нибудь еще?',
            reply_markup=self.create_keyboard(
                buttons=self.buttons['start'],
            ),
        )

    def text_to_parts_by_limit(self, text, msg_with_media=False):
        message_limit = 4096 if not msg_with_media else 1024
        message_parts = list()

        if len(text) <= message_limit:
            message_parts.append(text)
        else:
            message_parts = textwrap.wrap(
                text,
                width=message_limit,
                replace_whitespace=False,
            )

        return message_parts

    @log_method
    async def friends(
            self,
            update: Update = Update,
            context: ContextTypes.DEFAULT_TYPE = ContextTypes.DEFAULT_TYPE
    ):
        response = self.get_friends()
        friends = response.get('response').get('items')

        text = str()
        text_parts = list()

        for friend in friends:
            user_id = friend.get('id')
            first_name = friend.get('first_name')
            last_name = friend.get('last_name')
            line = (
                f'<a href="https://vk.com/id{user_id}">'
                f'{first_name} {last_name}</a> '
                f'<b>vk_id: {user_id}</b>\n'
            )

            if len(text + line) >= 4096:
                text_parts.append(text)
                text = line
            else:
                text += line

        text_parts.append(text)

        for part in text_parts:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=part,
                parse_mode='HTML',
                disable_web_page_preview=True,
            )

            await asyncio.sleep(1)

        text = (
            'Выслал список ваших друзей. Вы можете использовать '
            'содержащиеся в нем данные для добавления собеседника.'
        )

        if update.effective_message.text != text:
            await context.bot.editMessageText(
                chat_id=update.effective_chat.id,
                message_id=update.effective_message.id,
                text=text,
                reply_markup=self.create_keyboard(
                    buttons=self.buttons['start'],
                ),
            )

    @log_method
    async def add_chat(
            self,
            update: Update,
            context: ContextTypes.DEFAULT_TYPE,
    ):
        context.user_data['waiting_for_id'] = True
        context.user_data['effective_msg_id'] = update.effective_message.id
        reply_markup = self.create_keyboard(buttons=self.buttons['cancel'])
        text = (
            'Хорошо. Отправьте Vk id пользователя, '
            'которого нужно связать с этим чатом. '
            'Сюда будут перенаправляться все его сообщения, '
            'а у вас появится возможность отвечать ему.'
        )

        await context.bot.editMessageText(
            chat_id=update.effective_chat.id,
            message_id=update.effective_message.id,
            text=text,
            reply_markup=reply_markup,
        )

    @log_method
    async def delete_chat(
            self,
            update: Update,
            context: ContextTypes.DEFAULT_TYPE,
    ):
        chat = self.table_chat.get_chat(tg_chat_id=update.effective_chat.id)

        if chat:
            text = f'Удалить связь данного чата с {chat.vk_user}?'
            reply_markup = self.create_keyboard(
                buttons=self.buttons['delete'],
            )
        else:
            text = (
                'На данный момент ни один пользователь '
                'Vk не связан с данным чатом.'
            )

            if update.effective_message.text == text:
                return

            reply_markup = self.create_keyboard(
                buttons=self.buttons['start'],
            )

        await context.bot.editMessageText(
            chat_id=update.effective_chat.id,
            message_id=update.effective_message.id,
            text=text,
            reply_markup=reply_markup,
        )

    @log_method
    async def chat_deletion_is_confirmed(
            self,
            update: Update,
            context: ContextTypes.DEFAULT_TYPE,
    ):
        self.table_chat.delete_chat(tg_chat_id=update.effective_chat.id)

        text = (
            'Связь успешно удалена.\n\n'
            'Могу ли я помочь вам чем-нибудь еще?'
        )

        await context.bot.editMessageText(
            chat_id=update.effective_chat.id,
            message_id=update.effective_message.id,
            text=text,
            reply_markup=self.create_keyboard(
                buttons=self.buttons['start'],
            ),
        )

    @log_method
    async def message_from_user(
            self,
            update: Update,
            context: ContextTypes.DEFAULT_TYPE,
    ):
        if context.user_data.get('waiting_for_id'):
            await self.link_user_to_chat(update=update, context=context)
        else:
            await self.send_msg_tg_vk(update=update, context=context)

    @staticmethod
    def check_vk_id(message):
        if not message.isdigit():
            logger.error(
                'Ошибка создания связи чата с пользователем '
                f'vk_id({message}).\n'
                'Идентификатор должен состоять только из цифр.'
            )

            text = (
                'Неверный vk_id пользователя. '
                'Он должен состоять только из цифр.'
            )

            return text

        return None

    @log_method
    async def link_user_to_chat(
            self,
            update: Update,
            context: ContextTypes.DEFAULT_TYPE,
    ):
        message = update.message.text

        text = self.check_vk_id(message)
        if text:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
            )
            return

        vk_user_id = int(message)
        vk_user_info = self.get_user_or_group_info(
            user_or_group_id=vk_user_id,
            name_case='ins',
        )

        if vk_user_info.get('type') == 'user':
            vk_user = (
                f'{vk_user_info.get("first_name")} '
                f'{vk_user_info.get("last_name")}'
            )
        else:
            vk_user = vk_user_info.get('group_name')

        chat = self.table_chat.get_chat(vk_user_id=vk_user_id)

        if chat:
            self.table_chat.update_chat(
                vk_user_id=vk_user_id,
                new_vk_user=vk_user,
                tg_chat_id=update.effective_chat.id,
            )
        else:
            self.table_chat.add_chat(
                vk_user_id=vk_user_id,
                vk_user=vk_user,
                tg_chat_id=update.effective_chat.id,
            )

        if vk_user_info.get('type') == 'user':
            text = (
                f'Отлично. Теперь вы можете общаться с '
                f'<a href="https://vk.com/id{vk_user_id}">'
                f'{vk_user}</a> в этом чате.'
            )
        else:
            text = (
                f'Отлично. Теперь вы можете общаться с '
                f'<a href="https://vk.com/public{abs(vk_user_id)}">'
                f'{vk_user}</a> в этом чате.'
            )

        del context.user_data['waiting_for_id']

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode='HTML',
            disable_web_page_preview=True,
        )

        text = (
            'Аккаунт собеседника успешно связан с данным чатом.\n\n'
            'Могу ли я помочь вам чем-нибудь еще?'
        )
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data['effective_msg_id'],
            text=text,
            reply_markup=self.create_keyboard(
                buttons=self.buttons['start'],
            ),
        )

        avatar_url = vk_user_info.get('avatar')
        await self.set_chat_photo(
            avatar_url=avatar_url,
            update=update,
            context=context,
        )

    @log_method
    async def set_chat_photo(
            self,
            avatar_url,
            update: Update,
            context: ContextTypes.DEFAULT_TYPE,
    ):
        avatar = Image.open(requests.get(avatar_url, stream=True).raw)
        avatar = avatar.resize((400, 400))
        avatar_bytes = io.BytesIO()

        avatar.save(avatar_bytes, format='JPEG')
        avatar_bytes.seek(0)

        avatar = telegram.InputFile(avatar_bytes)

        await context.bot.set_chat_photo(
            chat_id=update.effective_chat.id,
            photo=avatar,
        )

    @log_method
    async def send_read_notification(self, vk_user_id, ):
        chat_in_table = self.table_chat.get_chat(vk_user_id=vk_user_id)
        notification_text = {
            'text': 'Ваши сообщения прочитаны.',
            'ext_text': 'Ваши сообщения были прочитаны пользователем '
                        f'vk_id({vk_user_id}).',
        }

        logger.info(notification_text['ext_text'])

        if chat_in_table:
            chat_id = chat_in_table.tg_chat_id
            unread_out_message = self.unread_out_messages.get(chat_id)

            if (
                TgConstants.READ_NOTIFICATION_MODE.value == 1
                and unread_out_message
            ):
                await self.app.bot.set_message_reaction(
                    chat_id=chat_id,
                    message_id=unread_out_message,
                    reaction='👀',
                )
            elif TgConstants.READ_NOTIFICATION_MODE.value == 2:
                read_notification = await self.app.bot.send_message(
                    chat_id=chat_id,
                    text=notification_text['text'],
                    disable_notification=True,
                )

                new_notification_msg_id = read_notification.message_id
                previous_notification = self.read_notifications.get(vk_user_id)

                if previous_notification:
                    await self.app.bot.delete_message(
                        chat_id=chat_id,
                        message_id=previous_notification,
                    )

                self.read_notifications[vk_user_id] = new_notification_msg_id
        else:
            await self.app.bot.send_message(
                chat_id=TgConstants.TELEGRAM_CHAT_ID.value,
                text=notification_text['ext_text'],
            )

    def find_id_in_url(self, url):
        pattern = r'\d+'
        id_in_url = (re.search(pattern, url)).group()

        return id_in_url

    async def get_photo(self, photo_data):
        largest_photo = photo_data[-1]
        photo_file_info = await largest_photo.get_file()
        photo_url = photo_file_info.file_path
        response = requests.get(photo_url)

        photo_bytes = Image.open(io.BytesIO(response.content))
        image_buffer = io.BytesIO()
        photo_bytes.save(image_buffer, format='JPEG')
        image_buffer.seek(0)

        photo = {
            'photo': ('image.jpg', image_buffer, 'image/jpeg')
        }

        return photo

    @log_method
    def save_photo_in_vk(self, photo):
        vk_upload_url = self.get_photo_upload_server()
        uploaded_photo = self.upload_photo(
            upload_server=vk_upload_url,
            photo=photo,
        )
        saved_photo = self.save_messages_photo(
            server_id=uploaded_photo['server'],
            photo=uploaded_photo['photo'],
            resp_hash=uploaded_photo['hash'],
        )

        return saved_photo

    def get_vk_msg_id_for_reply(
            self,
            update: Update,
            vk_user_id,
    ):
        message = self.table_chat.get_message(
            vk_user_id=vk_user_id,
            tg_message_id=(
                update.effective_message.reply_to_message.message_id
            )
        )

        if message:
            return message.vk_message_id
        else:
            raise MissingMessageIdError(
                'в выбранном сообщении отсутствуют данные, необходимые для '
                'определения отправителя, или оно слишком старое.'
            )

    def get_vk_user_id_from_msg(
            self,
            update: Update,
    ):
        vk_user_id = None
        entities = (
            update.message.reply_to_message.caption_entities
            or update.message.reply_to_message.entities
        )

        if entities:
            url_in_name = entities[0].url

            if (
                url_in_name
                and 'https://vk.com/im?sel=' in url_in_name
                and update.message.reply_to_message.from_user.is_bot
            ):
                vk_user_id = self.find_id_in_url(url=url_in_name)
                return vk_user_id

        if not vk_user_id:
            raise MissingUserVkIdIdError(
                'в выбранном сообщении не найден vk_id адресата.'
            )

    @log_method
    async def send_msg_tg_vk(
            self,
            update: Update = Update,
            context: ContextTypes.DEFAULT_TYPE = ContextTypes.DEFAULT_TYPE
    ):
        logger.info('Подготавливается отправка сообщения в Vk.')

        tg_chat_id = update.effective_chat.id
        chat_in_table = self.table_chat.get_chat(tg_chat_id=tg_chat_id)
        vk_msg_id_for_reply = None
        vk_user_id = None

        if update.effective_message.edit_date:
            logger.warning('Данное сообщение уже было отправлено ранее.')
            return
        elif update.effective_message.reply_to_message and chat_in_table:
            logger.info('Получаем vk id сообщения для создания ответа.')
            vk_user_id = chat_in_table.vk_user_id
            vk_msg_id_for_reply = self.get_vk_msg_id_for_reply(
                update=update,
                vk_user_id=vk_user_id,
            )
        elif update.effective_message.reply_to_message:
            logger.info('Получаем vk_id адресата из текста сообщения.')

            vk_user_id = self.get_vk_user_id_from_msg(
                update=update,
            )
        elif (
                update.effective_message.chat_id
                == TgConstants.TELEGRAM_CHAT_ID.value
                or not chat_in_table
        ):
            await context.bot.send_message(
                chat_id=update.effective_message.chat_id,
                text='Для данного сообщения нет адресата.',
            )
            return

        photo_data = update.effective_message.photo
        vk_user_id = (
            chat_in_table.vk_user_id if not vk_user_id else vk_user_id
        )

        if photo_data:
            photo = await self.get_photo(photo_data=photo_data)
            saved_photo = self.save_photo_in_vk(photo=photo)

            vk_message_id = self.send_message_to_vk(
                user_id=vk_user_id,
                message=update.effective_message.caption,
                uploaded_photo=saved_photo,
                reply_to=vk_msg_id_for_reply,
            )
        else:
            vk_message_id = self.send_message_to_vk(
                user_id=vk_user_id,
                message=update.effective_message.text,
                reply_to=vk_msg_id_for_reply,
            )

        logger.info('Сообщение успешно отправлено в Vk.')

        self.unread_out_messages[tg_chat_id] = update.effective_message.id

        self.table_chat.add_message(
            vk_user_id=vk_user_id,
            vk_message_id=vk_message_id.get('response'),
            tg_message_id=update.effective_message.id,
        )

        await asyncio.sleep(TgConstants.SEND_MSG_TG_VK_INTERVAL.value)

    @log_method
    async def send_msg_vk_tg(
            self,
            vk_sender_id,
            message=None,
            reply_to_message_id=None,
    ):
        logger.info(f'Отправка сообщения в Telegram.')

        chat = self.table_chat.get_chat(vk_user_id=vk_sender_id)
        chat_id = (
            chat.tg_chat_id if chat is not None
            else TgConstants.TELEGRAM_CHAT_ID.value
        )

        if 'sticker_url' in message:
            response = requests.get(message.get('sticker_url'))
            sticker_img = response.content

            await self.app.bot.send_sticker(chat_id, sticker_img, )

            await self.app.bot.send_message(
                chat_id=chat_id,
                text=message.get('text'),
                parse_mode='HTML',
                reply_to_message_id=reply_to_message_id,
                connect_timeout=TgConstants.SEND_MSG_CONN_TIMEOUT.value,
            )
            return

        media_group = list()
        images = (
                message.get('images', [])
                + message.get('videos', {}).get('video_frames', [])
        )

        if images:
            for image in images:
                media_group.append(telegram.InputMediaPhoto(image))

            orig_message = await self.app.bot.send_media_group(
                chat_id=chat_id,
                caption=message.get('text'),
                caption_entities=message.get('text'),
                parse_mode='HTML',
                media=media_group,
                reply_to_message_id=reply_to_message_id,
                connect_timeout=TgConstants.SEND_MSG_CONN_TIMEOUT.value,
            )
            orig_message_id = orig_message[0].message_id
        else:
            orig_message = await self.app.bot.send_message(
                chat_id=chat_id,
                text=message.get('text'),
                parse_mode='HTML',
                reply_to_message_id=reply_to_message_id,
                connect_timeout=TgConstants.SEND_MSG_CONN_TIMEOUT.value,
            )
            orig_message_id = orig_message.message_id

        logger.info('Сообщение успешно отправлено в Telegram.')

        if chat:
            message_id = message['message_id']

            self.table_chat.add_message(
                vk_user_id=vk_sender_id,
                vk_message_id=message_id,
                tg_message_id=orig_message_id,
            )

            logger.debug(
                f'Входящее сообщение добавлено в БД.\n'
                f'user: {vk_sender_id}, '
                f'vk_message_id: {message_id}, '
                f'tg_message_id: {orig_message_id}.'
            )

        return orig_message_id


if __name__ == "__main__":
    bot = TgBot(db_table=db.Database())

    bot.add_handlers()
    bot.app.run_polling()
