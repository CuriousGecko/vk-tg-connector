import json
from typing import Any, Union

import requests

from constants import VkConstant
from exceptions import (LongPollConnectionError, LongPollResponseError,
                        NoDataInResponseError, VkApiConnectionError,
                        VkApiError)
from image_render import render


class VkApiBase:
    """Базовый функционал для работы с API Vk."""

    def __init__(self):
        self.timestamp: int = 0
        self.poll_server_url: str = ''
        self.poll_server_key: str = ''

    def check_response(self, response: requests.Response) -> dict:
        """Проверит ответ от API Vk."""
        url = response.url

        if response.status_code != 200:
            error_text = f'Эндпоинт {url} недоступен.'

            if url == self.poll_server_url:
                raise LongPollConnectionError(error_text)
            else:
                raise VkApiConnectionError(error_text)

        result = response.json()

        if 'failed' in result:
            raise LongPollResponseError(
                result.get('error')
            )
        elif 'error' in result:
            error_msg = result.get('error', {}).get('error_msg')
            raise VkApiError(
                f'Ошибка запроса к эндпоинту {url}. '
                f'Ответ Vk API: {error_msg}'
            )
        elif 'response' in result:
            if not result.get('response'):
                print(result)
                raise NoDataInResponseError(
                    f'Ответ эндпоинта {url} не содержит данных.'
                )

        return result

    def make_request_and_check(self, url, data=None, files=None):
        """Отправит запрос к API Vk и проверит ответ."""
        response = requests.post(url=url, data=data, files=files,)
        result = self.check_response(response=response,)

        return result

    def update_params(self, params):
        """Обновит timestamp, URL LongPoll-сервера и его ключ."""
        self.timestamp = params['response']['ts']
        self.poll_server_url = f'https://{params["response"]["server"]}'
        self.poll_server_key = params['response']['key']

    def get_vk_long_pol_server(self):
        """Запросит URL LongPoll сервера."""
        endpoint = VkConstant.ENDPOINTS.value['get_lp_server']
        data = {
            'need_pts': VkConstant.NEED_PTS.value,
            'lp_version': VkConstant.LP_VERSION.value,
            'access_token': VkConstant.ACCESS_TOKEN.value,
            'v': VkConstant.API_VERSION.value,
        }
        response = self.make_request_and_check(url=endpoint, data=data, )

        return response

    def connect_vk_long_poll_server(self, wait):
        """Установит связь с LongPoll-сервером."""
        endpoint = self.poll_server_url
        data = {
            'act': 'a_check',
            'wait': wait,
            'key': self.poll_server_key,
            'ts': self.timestamp,
            'mode': VkConstant.LONG_POLL_MODE.value,
            'version': VkConstant.LONG_POLL_VERSION.value,
            }
        response = self.make_request_and_check(url=endpoint, data=data, )

        return response

    def get_photo_upload_server(self):
        """Вернет URL сервера для загрузки изображения."""
        endpoint = VkConstant.ENDPOINTS.value['get_photo_upload_server']
        data = {
            'access_token': VkConstant.ACCESS_TOKEN.value,
            'v': VkConstant.API_VERSION.value,
        }
        response = self.make_request_and_check(url=endpoint, data=data, )
        upload_server_url = response['response']['upload_url']

        return upload_server_url

    def upload_photo(self, upload_server, photo):
        """Загрузит изображение на сервер."""
        endpoint = upload_server
        response = self.make_request_and_check(url=endpoint, files=photo, )

        return response

    def save_messages_photo(self, server_id, photo, resp_hash):
        """Сохранит изображение на сервере."""
        endpoint = VkConstant.ENDPOINTS.value['save_messages_photo']
        data = {
            'server': server_id,
            'photo': photo,
            'hash': resp_hash,
            'access_token': VkConstant.ACCESS_TOKEN.value,
            'v': VkConstant.API_VERSION.value,
        }
        response = self.make_request_and_check(url=endpoint, data=data, )

        return response

    def send_message_to_vk(
            self,
            user_id,
            message,
            reply_to=None,
            uploaded_photo=None,
    ):
        """Отправит сообщение пользователю Vk."""
        endpoint = VkConstant.ENDPOINTS.value['send_message']
        attachment = None

        if uploaded_photo:
            owner_id = uploaded_photo['response'][0]['owner_id']
            photo_id = uploaded_photo['response'][0]['id']
            attachment = f'photo{owner_id}_{photo_id}'

        data = {
            'user_id': user_id,
            'message': message,
            'attachment': attachment,
            'reply_to': reply_to,
            'random_id': 0,
            'access_token': VkConstant.ACCESS_TOKEN.value,
            'v': VkConstant.API_VERSION.value,
        }
        response = self.make_request_and_check(url=endpoint, data=data, )

        return response

    def get_user(self, user_id, name_case):
        """Вернет информацию о пользователе."""
        endpoint = VkConstant.ENDPOINTS.value['get_users']
        data = {
            'user_ids': user_id,
            'fields': 'photo_200',
            'name_case': name_case,
            'access_token': VkConstant.ACCESS_TOKEN.value,
            'v': VkConstant.API_VERSION.value,
        }
        response = self.make_request_and_check(url=endpoint, data=data, )

        return response

    def get_group(self, group_id):
        """Вернет информацию о группе."""
        endpoint = VkConstant.ENDPOINTS.value['get_group']
        data = {
            'group_id': group_id,
            'access_token': VkConstant.ACCESS_TOKEN.value,
            'v': VkConstant.API_VERSION.value,
        }
        response = self.make_request_and_check(url=endpoint, data=data, )

        return response

    def get_friends(self, order='hints', name_case='nom'):
        """Вернет список друзей пользователя."""
        endpoint = VkConstant.ENDPOINTS.value['get_friends']
        data = {
            'fields': 'nickname',
            'order': order,
            'name_case': name_case,
            'access_token': VkConstant.ACCESS_TOKEN.value,
            'v': VkConstant.API_VERSION.value,
        }
        response = self.make_request_and_check(url=endpoint, data=data, )

        return response

    def get_message_by_id(self, message_id):
        """Вернет данные конкретного сообщения."""
        endpoint = VkConstant.ENDPOINTS.value['get_message_by_id']
        data = {
            'message_ids': message_id,
            'access_token': VkConstant.ACCESS_TOKEN.value,
            'v': VkConstant.API_VERSION.value,
        }
        response = self.make_request_and_check(url=endpoint, data=data, )

        return response

    def short_link(self, url, private=True):
        """Сократит ссылку."""
        endpoint = VkConstant.ENDPOINTS.value['get_short_link']
        data = {
            'url': url,
            'private': 1 if private else 0,
            'access_token': VkConstant.ACCESS_TOKEN.value,
            'v': VkConstant.API_VERSION.value,
        }
        response = self.make_request_and_check(url=endpoint, data=data, )

        return response

    def get_video(self, param_videos):
        """Вернет данные видео."""
        endpoint = VkConstant.ENDPOINTS.value['get_video']
        data = {
            'videos': ','.join(param_videos),
            'access_token': VkConstant.ACCESS_TOKEN.value,
            'v': VkConstant.API_VERSION.value,
        }
        response = self.make_request_and_check(url=endpoint, data=data, )

        return response

    def message_mark_as_read(self, peer_id):
        """Отметит сообщения как прочитанные."""
        endpoint = VkConstant.ENDPOINTS.value['message_mark_as_read']
        data = {
            'peer_id': peer_id,
            'access_token': VkConstant.ACCESS_TOKEN.value,
            'v': VkConstant.API_VERSION.value,
        }
        response = self.make_request_and_check(url=endpoint, data=data, )

        return response


class VkApi(VkApiBase):
    """Обработка и дополнение материалов сообщений."""

    def get_user_or_group_info(
            self,
            user_or_group_id: int,
            name_case: str = 'nom',
    ) -> dict:
        """Сформирует данные о пользователе или группе."""
        if user_or_group_id > 0:
            response = self.get_user(
                user_id=user_or_group_id,
                name_case=name_case,
            )
            user_data = response.get('response')[0]

            return {
                'type': 'user',
                'user_id': user_or_group_id,
                'first_name': user_data.get('first_name'),
                'last_name': user_data.get('last_name'),
                'avatar': user_data.get('photo_200'),
            }
        else:
            response = self.get_group(group_id=abs(user_or_group_id),)
            group_data = response.get('response', {}).get('groups', [{}])[0]

            return {
                'type': 'group',
                'group_id': group_data['id'],
                'group_name': group_data.get('name'),
                'avatar': group_data.get('photo_200'),
            }

    def largest_image(self, images: dict) -> str:
        """Выберет изображение с наибольшим разрешением."""
        largest_image_url = ''
        largest_image_size = 0

        for image in images:
            image_size = image['height'] * image['width']
            if image_size > largest_image_size:
                largest_image_size = image_size
                largest_image_url = image['url']

        return largest_image_url

    def get_video_url_and_frame(
            self,
            attachments: list[dict[str, Any]],
            get_video_player_url: bool = True,
    ) -> dict[str, list[Union[str, bytes]]]:
        """Вернет ссылку на видео и случайный кадр."""
        param_videos = list()
        videos = {'video_urls': [], 'video_frames': []}

        for attachment in attachments:
            if attachment['type'] == 'video':
                video_data = attachment['video']
                owner_id = video_data['owner_id']
                video_id = video_data['id']

                frames = video_data['image']
                frame = self.largest_image(frames)
                rendered_frame = render(base_image_url=frame,)
                videos['video_frames'].append(rendered_frame)

                if get_video_player_url:
                    access_key = video_data['access_key']
                    param = f'{owner_id}_{video_id}_{access_key}'
                    param_videos.append(param)
                else:
                    videos['video_urls'].append(
                        f'https://vk.com/video{owner_id}_{video_id}'
                    )

        if param_videos:
            response = self.get_video(param_videos=param_videos,)
            items = response['response']['items']

            for item in items:
                video_url = item['player']
                videos['video_urls'].append(video_url)

        return videos

    def get_images(self, attachments):
        """Вернет ссылки на изображения во вложениях."""
        images = list()

        for attachment in attachments:
            if attachment['type'] == 'photo':
                photo_data = attachment['photo']
                photo_sizes = photo_data.get('sizes')
                photo_url = self.largest_image(photo_sizes)
                images.append(photo_url)

        return images

    def get_sticker(self, short_msg_data):
        """Вернет ссылку на изображение стикера."""
        message = dict()

        attachments = json.loads(short_msg_data['attachments'])
        sticker_data = attachments[0]['sticker']
        sticker_sizes = sticker_data['images_with_background']
        message['sticker_url'] = self.largest_image(sticker_sizes)

        return message

    def get_message(self, message_data, short_msg_data):
        """Сформирует данные сообщения."""
        message = dict()

        message['message_id'] = message_data['response']['items'][0]['id']
        user_or_group_id = message_data['response']['items'][0]['from_id']
        sender_info = self.get_user_or_group_info(
            user_or_group_id=user_or_group_id,
        )

        message.update(sender_info)

        if short_msg_data:
            sticker = self.get_sticker(short_msg_data=short_msg_data,)
            message.update(sticker)
        else:
            message['text'] = message_data['response']['items'][0]['text']

            message_attachments = message_data['response']['items'][0][
                'attachments']
            message['images'] = self.get_images(
                attachments=message_attachments,
            )
            message['videos'] = self.get_video_url_and_frame(
                attachments=message_attachments,
            )

        return message

    def get_wall(self, attachments):
        """Сформирует данные репоста."""
        wall = dict()

        for attachment in attachments:
            if 'wall' in attachment:
                wall['message_type'] = 'wall'
                wall_data = [attachment][0]['wall']
                wall['post_id'] = wall_data['id']
                wall['text'] = wall_data['text']

                owner_id = wall_data['from_id']
                owner_info = self.get_user_or_group_info(
                    user_or_group_id=owner_id,
                )
                wall.update(owner_info)

                wall_attachments = wall_data['attachments']
                wall['images'] = self.get_images(
                    attachments=wall_attachments,
                )
                wall['videos'] = self.get_video_url_and_frame(
                    attachments=wall_attachments,
                    get_video_player_url=False,
                )

        return wall

    def get_reply_orig_msg_id(self, message_data):
        """Вернет id сообщения, на которое отправлен ответ."""
        reply_orig_msg_id = message_data['response']['items'][0][
            'reply_message']['id']

        return reply_orig_msg_id

    def get_reply_original_message(self, message_data):
        """Сформирует данные сообщения, на которое отправлен ответ."""
        reply_message = dict()

        reply_orig_msg_data = message_data['response']['items'][0][
            'reply_message']

        author_id = reply_orig_msg_data.get('from_id')
        author_info = self.get_user_or_group_info(
            user_or_group_id=author_id,
        )

        reply_message.update(author_info)

        reply_message['text'] = reply_orig_msg_data.get('text')
        reply_attachments = reply_orig_msg_data.get('attachments')
        reply_message['images'] = self.get_images(
            attachments=reply_attachments,
        )
        reply_message['videos'] = self.get_video_url_and_frame(
                    attachments=reply_attachments,
                )

        wall_data = self.get_wall(attachments=reply_attachments,)

        if wall_data:
            reply_message['wall'] = self.get_wall(
                attachments=reply_attachments,
            )

        return reply_message
