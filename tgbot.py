import asyncio
import functools
import io
from typing import Optional

import requests
import telegram
from PIL import Image
from telegram import (BotCommand, InlineKeyboardButton, InlineKeyboardMarkup,
                      Update)
from telegram.error import NetworkError, TelegramError
from telegram.ext import (Application, ApplicationBuilder,
                          CallbackQueryHandler, CommandHandler, ContextTypes,
                          MessageHandler, filters)

import vkapi
from constants import TgConstant
from db import Database
from exceptions import (MissingUserVkIdError, NoDataInResponseError,
                        NoInterlocutorError, NoMessageForReply)
from logger import run_logger

logger = run_logger('tgbot')


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

        except (
                NoMessageForReply,
                MissingUserVkIdError,
                NoInterlocutorError,
        ) as error:
            error_text = f'Не удалось отправить сообщение: {error}'

            logger.error(msg=error_text, )

            await context.bot.send_message(
                chat_id=update.effective_message.chat_id,
                text=error_text,
            )

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

        except (TelegramError, NetworkError, Exception) as error:
            if method == 'start':
                logger.exception(
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
                text_error = (
                    'Во время отправки сообщения в Vk произошла ошибка: '
                    f'{error}'
                )
                logger.exception(text_error)

                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text_error,
                )
            elif method == 'send_msg_vk_tg':
                logger.exception(
                    'Во время отправки сообщения в Telegram произошла '
                    f'ошибка: {error}'
                )
            else:
                logger.exception(f'Что-то пошло не так: {error}')

    return wrapper


class TgBotApp:
    """Сборщик базового приложения бота."""

    def __init__(self, token: str):
        self.app = ApplicationBuilder().token(token).build()


class TgBot:
    """Класс инициализации бота."""

    def __init__(self, app: Application, database: Database):
        self.app = app
        self.db = database
        self.chat_handlers = TgBotAddDeleteChatHandler(database=self.db)

        self.handlers = [
            CommandHandler(
                command='start',
                callback=TgBotCommandStart().start,
            ),
            CommandHandler(
                command='read',
                callback=TgBotCommandReadMark(database=self.db).mark_as_read,
            ),
            CommandHandler(
                command='help',
                callback=TgBotCommandHelp().help,
            ),
            CallbackQueryHandler(
                pattern='Список друзей в Vk',
                callback=TgBotFriendsHandler().friends,
            ),
            CallbackQueryHandler(
                pattern='Указать собеседника',
                callback=self.chat_handlers.add_chat,
            ),
            CallbackQueryHandler(
                pattern='Удалить собеседника',
                callback=self.chat_handlers.delete_chat,
            ),
            CallbackQueryHandler(
                pattern='Подтвердить',
                callback=self.chat_handlers.chat_deletion_is_confirmed,
            ),
            CallbackQueryHandler(
                pattern='Отменить',
                callback=TgBotCancelHandler().cancel,
            ),
            MessageHandler(
                filters=(filters.TEXT | filters.PHOTO),
                callback=TgBotMessageHandler(
                    database=self.db, ).message_from_user,
            ),
        ]

        self.commands = [
            BotCommand(
                command='read',
                description='Пометить сообщения как прочитанные',
            ),
            BotCommand(command='start', description='Вызвать бота', ),
            BotCommand(command='help', description='Помощь', )
        ]

    def add_handlers(self) -> None:
        for handler in self.handlers:
            self.app.add_handler(handler)

        logger.info('Обработчики сообщений и команд бота заданы.')

    async def set_commands(self) -> None:
        await self.app.bot.set_my_commands(self.commands)

        logger.info('Установка команд для управления ботом завершена.')

    def run_polling(self) -> None:
        try:
            logger.info('Запускается Telegram Polling.')

            self.app.run_polling()

        except (TelegramError, NetworkError, Exception) as error:
            logger.error(f'Ошибка при запросе обновлений: {error}')


class TgBotSharedAttributes:
    """Общие данные классов."""

    chats_wait_id = set()
    interfaces = {}


class TgBotKeyboard:
    """Сгенерирует клавиатуру для интерфейса бота."""

    def __init__(self):
        self.button_layout = {
            'start': [
                ['Список друзей в Vk'],
                ['Указать собеседника'],
                ['Удалить собеседника'],
            ],
            'cancel': [['Отменить'], ],
            'delete': [['Подтвердить', 'Отменить'], ],
        }

    def generate_inline_keyboard(
            self,
            button_type: str
    ) -> InlineKeyboardMarkup:
        keyboard = list()
        buttons = self.button_layout.get(button_type)

        for values in buttons:
            button_row = [
                InlineKeyboardButton(value, callback_data=value)
                for value in values
            ]
            keyboard.append(button_row)

        reply_markup = InlineKeyboardMarkup(keyboard)

        return reply_markup


class TgBotPermissionChecker:
    """Проверка прав доступа."""

    def check_user_permission(self, user_id: int) -> bool:
        return user_id == TgConstant.TELEGRAM_CHAT_ID.value

    async def is_bot_admin(
            self,
            update: Update = Update,
            context: ContextTypes.DEFAULT_TYPE = ContextTypes.DEFAULT_TYPE
    ) -> bool:
        bot_info = await context.bot.get_chat_member(
            chat_id=update.effective_chat.id,
            user_id=context.bot.id,
        )

        return bot_info.status == 'administrator'


class TgBotInterface(TgBotSharedAttributes):
    """Работа с интерфейсом бота в чате."""

    @log_method
    async def destroy_prev_interface(
            self,
            chat_id: int,
            context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        self.chats_wait_id.discard(chat_id)

        if chat_id in self.interfaces:
            interface_id = self.interfaces.get(chat_id)

            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=interface_id,
            )

    @staticmethod
    def check_interface_freshness(func):
        @functools.wraps(func)
        async def wrapper(
                self,
                update: Update,
                context: ContextTypes.DEFAULT_TYPE
        ):
            chat_id = update.effective_chat.id
            msg_id = update.effective_message.id
            freshness = msg_id in self.interfaces.values()
            error_text = 'Интерфейс устарел. Необходимо вызвать бота снова.'

            if not freshness:
                logger.debug(error_text)

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=error_text,
                )
            else:
                await func(self, update, context)

        return wrapper


class TgBotCommandReadMark(TgBotPermissionChecker, vkapi.VkApi):
    """Обработчик /read для перевода сообщений в Vk в статус прочитанных."""

    def __init__(self, database: Database):
        super().__init__()
        self.db = database

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
        user_id = update.effective_user.id
        access = self.check_user_permission(user_id=user_id)

        if not access:
            await context.bot.send_message(
                chat_id=tg_chat_id,
                text=text['forbidden'],
            )
            return

        chat = self.db.get_chat(tg_chat_id=tg_chat_id)

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


class TgBotCommandStart(
    TgBotKeyboard,
    TgBotPermissionChecker,
    TgBotInterface,
    TgBotSharedAttributes,
):
    """Обработчик команды /start."""

    def __init__(self,):
        super().__init__()

    @log_method
    async def start(
            self,
            update: Update = Update,
            context: ContextTypes.DEFAULT_TYPE = ContextTypes.DEFAULT_TYPE
    ) -> None:
        user_id = update.effective_user.id
        access = self.check_user_permission(user_id=user_id)
        chat_id = update.effective_chat.id

        if access:
            if update.effective_chat.id == TgConstant.TELEGRAM_CHAT_ID.value:
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
                    '4. Вызовите бота.\n'
                    '5. Добавьте с его помощью собеседника.\n'
                )

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode='HTML',
                )
                return

            bot_is_admin = await self.is_bot_admin(update, context,)

            if not bot_is_admin:
                text = (
                    'Я бот, приветствую вас! В данном чате у меня отсутствуют '
                    'необходимые для работы привилегии. Пожалуйста, назначьте '
                    'меня администратором, чтобы я мог добросовестно '
                    'исполнять свои обязанности.'
                )

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                )
            else:
                await self.destroy_prev_interface(
                    chat_id=chat_id,
                    context=context,
                )

                reply_markup = self.generate_inline_keyboard(
                    button_type='start'
                )
                interface = await context.bot.send_message(
                    chat_id=chat_id,
                    text='Я бот, приветствую вас! Чем могу помочь?',
                    reply_markup=reply_markup,
                )
                interface_id = interface.message_id
                self.interfaces[chat_id] = interface_id

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
            username = update.effective_user.username

            logger.debug(
                f'\n\nПользователю https://t.me/{username} (id={user_id}) '
                f'доступ к функциям бота запрещен.\n\n'
            )

            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
            )


class TgBotCommandHelp:
    """Обработчик команды /help."""

    @log_method
    async def help(
            self,
            update: Update = Update,
            context: ContextTypes.DEFAULT_TYPE = ContextTypes.DEFAULT_TYPE
    ) -> None:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='Подробная инструкция к боту:\n'
                 'https://github.com/CuriousGecko/vk-tg-connector'
        )


class TgBotCancelHandler(TgBotKeyboard, TgBotSharedAttributes):
    """Обработчик кнопки отмены."""

    def __init__(self):
        super().__init__()

    @log_method
    @TgBotInterface.check_interface_freshness
    async def cancel(
            self,
            update: Update,
            context: ContextTypes.DEFAULT_TYPE,
    ):
        chat_id = update.effective_message.chat_id

        self.chats_wait_id.discard(chat_id)

        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=update.effective_message.id,
            text='Операция отменена.\n\nМогу ли я помочь вам чем-нибудь еще?',
            reply_markup=self.generate_inline_keyboard(
                button_type='start',
            ),
        )


class TgBotMessageImage(vkapi.VkApi):
    """Загрузит изображение из сообщения на сервер Vk."""

    @log_method
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

        logger.debug('Фото успешно загружено на сервер Vk.')

        return saved_photo


class TgBotUserLink(TgBotKeyboard, vkapi.VkApi, TgBotSharedAttributes,):
    """Добавление пользователя Vk в чат."""

    def __init__(self, database: Database):
        super().__init__()
        self.db = database

    @staticmethod
    def check_vk_id(message: str) -> Optional[str]:
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
            chat_id: int,
            update: Update = Update,
            context: ContextTypes.DEFAULT_TYPE = ContextTypes.DEFAULT_TYPE,
    ) -> None:
        message = update.message.text
        text = self.check_vk_id(message)

        if text:
            await context.bot.send_message(
                chat_id=chat_id,
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

        self.db.add_or_update_chat(
            vk_user_id=vk_user_id,
            vk_user=vk_user,
            tg_chat_id=chat_id,
        )
        self.db.delete_messages(vk_user_id=vk_user_id)

        self.chats_wait_id.discard(chat_id)

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

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode='HTML',
            disable_web_page_preview=True,
        )

        interface_id = self.interfaces.get(chat_id)
        text = (
            'Аккаунт собеседника успешно связан с данным чатом.\n\n'
            'Могу ли я помочь вам чем-нибудь еще?'
        )
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=interface_id,
            text=text,
            reply_markup=self.generate_inline_keyboard(
                button_type='start',
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
            avatar_url: str,
            update: Update,
            context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
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


class TgBotMessageHandler(
    TgBotUserLink,
    TgBotKeyboard,
    TgBotMessageImage,
    TgBotSharedAttributes,
):
    """Обработка сообщений пользователя."""

    def __init__(self, database: Database):
        super().__init__(database)

    @log_method
    async def message_from_user(
            self,
            update: Update = Update,
            context: ContextTypes.DEFAULT_TYPE = ContextTypes.DEFAULT_TYPE
    ):
        chat_id = update.effective_message.chat_id

        if chat_id not in self.chats_wait_id:
            await self.send_msg_tg_vk(update=update, context=context)
        else:
            await self.link_user_to_chat(
                chat_id=chat_id,
                update=update,
                context=context,
            )

    def get_vk_user_id_for_msg(self, tg_chat_id: int):
        if tg_chat_id == TgConstant.TELEGRAM_CHAT_ID.value:
            raise NoInterlocutorError(
                'используйте кнопку "Ответить" на входящих сообщениях.'
            )

        chat_in_table = self.db.get_chat(tg_chat_id=tg_chat_id)

        if chat_in_table:
            return chat_in_table.vk_user_id

        raise MissingUserVkIdError('для данного сообщения нет адресата.')

    def get_data_for_reply(self, tg_chat_id: int, update):
        tg_msg_id = update.effective_message.reply_to_message.message_id
        message_in_db = self.db.get_message(
            tg_message_id=tg_msg_id,
            tg_chat_id=tg_chat_id,
        )

        if message_in_db:
            vk_user_id = message_in_db.vk_user_id
            vk_message_id = message_in_db.vk_message_id
        elif tg_chat_id == TgConstant.TELEGRAM_CHAT_ID.value:
            raise MissingUserVkIdError(
                'не могу определить получателя. Возможно, для него '
                'создан отдельный чат или сообщение слишком старое.'
            )
        else:
            raise NoMessageForReply(
                'не могу определить id сообщения в Vk, на которое '
                'отправляется ответ.'
            )

        return vk_user_id, vk_message_id

    @log_method
    async def send_msg_tg_vk(
            self,
            update: Update = Update,
            context: ContextTypes.DEFAULT_TYPE = ContextTypes.DEFAULT_TYPE,
    ):
        if update.effective_message.edit_date:
            logger.warning('Данное сообщение уже было отправлено ранее.')
            return

        logger.info('Подготавливается отправка сообщения в Vk.')

        tg_chat_id = update.effective_chat.id
        vk_msg_id_for_reply = None

        if update.effective_message.reply_to_message:
            vk_user_id, vk_message_id = self.get_data_for_reply(
                tg_chat_id=tg_chat_id, update=update,
            )

            if tg_chat_id != TgConstant.TELEGRAM_CHAT_ID.value:
                vk_msg_id_for_reply = vk_message_id
        else:
            vk_user_id = self.get_vk_user_id_for_msg(tg_chat_id=tg_chat_id)

        photo_data = update.effective_message.photo

        if photo_data:
            photo = await self.get_photo(photo_data=photo_data)
            saved_photo = self.save_photo_in_vk(photo=photo)

            response = self.send_message_to_vk(
                user_id=vk_user_id,
                message=update.effective_message.caption,
                uploaded_photo=saved_photo,
                reply_to=vk_msg_id_for_reply,
            )
        else:
            response = self.send_message_to_vk(
                user_id=vk_user_id,
                message=update.effective_message.text,
                reply_to=vk_msg_id_for_reply,
            )

        logger.info('Сообщение успешно отправлено в Vk.')

        vk_message_id = response.get('response')
        tg_message_id = update.effective_message.id
        chat_id = update.effective_chat.id

        self.db.add_message(
            vk_user_id=vk_user_id,
            vk_message_id=vk_message_id,
            tg_message_id=tg_message_id,
            tg_chat_id=tg_chat_id,
        )

        logger.debug(
            'Исходящее сообщение добавлено в БД.\n'
            f'user: {vk_user_id}, '
            f'vk_message_id: {vk_message_id}, '
            f'tg_message_id: {tg_message_id}.'
            f'tg_chat_id: {chat_id}'
        )

        notification = await context.bot.send_message(
            chat_id=chat_id,
            text='Сообщение отправлено.',
        )

        await asyncio.sleep(TgConstant.DEL_NOTIFICATION_OF_SEND.value)

        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=notification.message_id,
        )


class TgBotAddDeleteChatHandler(TgBotKeyboard, TgBotSharedAttributes):
    """Обработчик запуска создания/удаления связи чата с пользователем Vk."""

    def __init__(self, database: Database):
        super().__init__()
        self.db = database

    @log_method
    @TgBotInterface.check_interface_freshness
    async def add_chat(
            self,
            update: Update = Update,
            context: ContextTypes.DEFAULT_TYPE = ContextTypes.DEFAULT_TYPE
    ):
        chat_id = update.effective_message.chat_id
        text = (
            'Хорошо. Отправьте vk_id пользователя, '
            'которого нужно связать с этим чатом. '
            'Сюда будут перенаправляться все его сообщения.'
        )

        self.chats_wait_id.add(chat_id)

        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=update.effective_message.id,
            text=text,
            reply_markup=self.generate_inline_keyboard(button_type='cancel'),
        )

    @log_method
    @TgBotInterface.check_interface_freshness
    async def delete_chat(
            self,
            update: Update = Update,
            context: ContextTypes.DEFAULT_TYPE = ContextTypes.DEFAULT_TYPE
    ):
        chat_id = update.effective_chat.id
        chat = self.db.get_chat(tg_chat_id=chat_id)

        if chat:
            text = f'Удалить связь данного чата с {chat.vk_user}?'
            reply_markup = self.generate_inline_keyboard(
                button_type='delete',
            )
        else:
            text = (
                'На данный момент ни один пользователь '
                'Vk не связан с данным чатом.'
            )

            if update.effective_message.text == text:
                return

            reply_markup = self.generate_inline_keyboard(
                button_type='start',
            )

        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=update.effective_message.id,
            text=text,
            reply_markup=reply_markup,
        )

    @log_method
    @TgBotInterface.check_interface_freshness
    async def chat_deletion_is_confirmed(
            self,
            update: Update = Update,
            context: ContextTypes.DEFAULT_TYPE = ContextTypes.DEFAULT_TYPE
    ):
        chat_id = update.effective_chat.id
        text = (
            'Связь успешно удалена.\n\n'
            'Могу ли я помочь вам чем-нибудь еще?'
        )

        self.db.delete_chat(tg_chat_id=chat_id)

        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=update.effective_message.id,
            text=text,
            reply_markup=self.generate_inline_keyboard(button_type='start'),
        )


class TgBotFriendsHandler(TgBotKeyboard, TgBotSharedAttributes, vkapi.VkApi):
    """Сгенерирует список друзей в Vk."""

    def __init__(self):
        super().__init__()

    @log_method
    @TgBotInterface.check_interface_freshness
    async def friends(
            self,
            update: Update = Update,
            context: ContextTypes.DEFAULT_TYPE = ContextTypes.DEFAULT_TYPE
    ):
        chat_id = update.effective_chat.id
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
                chat_id=chat_id,
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
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=update.effective_message.id,
                text=text,
                reply_markup=self.generate_inline_keyboard(
                    button_type='start',
                ),
            )


class VkTgMessage:
    """Отправка сообщений из Vk в Telegram."""

    def __init__(self, app, database):
        self.db = database
        self.app = app

    @log_method
    async def send_msg_vk_tg(
            self,
            vk_sender_id: int,
            message: dict = None,
            reply_to_message_id: int = None,
    ) -> Optional[int]:
        logger.info(f'Отправка сообщения в Telegram.')

        chat = self.db.get_chat(vk_user_id=vk_sender_id)
        chat_id = (
            chat.tg_chat_id if chat
            else TgConstant.TELEGRAM_CHAT_ID.value
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
                connect_timeout=TgConstant.SEND_MSG_CONN_TIMEOUT.value,
                read_timeout=TgConstant.READ_TIMEOUT.value,
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
                connect_timeout=TgConstant.SEND_MSG_CONN_TIMEOUT.value,
                read_timeout=TgConstant.READ_TIMEOUT.value,
            )
            orig_message_id = orig_message[0].message_id
        else:
            orig_message = await self.app.bot.send_message(
                chat_id=chat_id,
                text=message.get('text'),
                parse_mode='HTML',
                reply_to_message_id=reply_to_message_id,
                connect_timeout=TgConstant.SEND_MSG_CONN_TIMEOUT.value,
                read_timeout=TgConstant.READ_TIMEOUT.value,
            )
            orig_message_id = orig_message.message_id

        logger.info('Сообщение успешно отправлено в Telegram.')

        message_id = message.get('message_id')

        self.db.add_message(
            vk_user_id=vk_sender_id,
            vk_message_id=message_id,
            tg_message_id=orig_message_id,
            tg_chat_id=chat_id,
        )

        logger.debug(
            f'Входящее сообщение добавлено в БД.\n'
            f'user: {vk_sender_id}, '
            f'vk_message_id: {message_id}, '
            f'tg_message_id: {orig_message_id}.'
            f'tg_chat_id: {chat_id}'
        )

        return orig_message_id


class TgBotNotification(vkapi.VkApi):
    """Отправит уведомление в Telegram о прочитанном сообщении в VK."""

    def __init__(self, app: Application, database: Database):
        super().__init__()
        self.read_notifications = {}
        self.app = app
        self.db = database

    @log_method
    async def send_read_notification(
            self, vk_user_id: int,
            vk_message_id: int
    ):
        chat_in_table = self.db.get_chat(vk_user_id=vk_user_id)
        response = self.get_user(vk_user_id, name_case='nom').get(
            'response')[0]
        username = f"{response.get('first_name')} {response.get('last_name')}"
        notification_text = {
                'text': 'Ваши сообщения были прочитаны.',
                'ext_text': f'{username} прочитал ваши сообщения.',
            }

        logger.info(notification_text['ext_text'])

        if chat_in_table:
            chat_id = chat_in_table.tg_chat_id

            if TgConstant.READ_NOTIFICATION_MODE.value == 1:
                vk_message_in_db = self.db.get_message(
                    vk_message_id=vk_message_id,
                )

                if vk_message_in_db:
                    tg_message_id = vk_message_in_db.tg_message_id

                    await self.app.bot.set_message_reaction(
                        chat_id=chat_id,
                        message_id=tg_message_id,
                        reaction='👀',
                    )
            elif TgConstant.READ_NOTIFICATION_MODE.value == 2:
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
                chat_id=TgConstant.TELEGRAM_CHAT_ID.value,
                text=notification_text['ext_text'],
            )
