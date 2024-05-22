## VK-TG connector - это Telegram-бот, позволяющий обмениваться сообщениями с пользователями социальной сети ВКонтакте.

![head.jpg](images%2Fgithub%2Fhead.jpg)
![Alchemy](images%2Fgithub%2Falchemy_badge.png)
![Python](https://img.shields.io/badge/Python-14354C?style=for-the-badge&logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)
![Vk](https://img.shields.io/badge/вконтакте-%232E87FB.svg?&style=for-the-badge&logo=vk&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)
![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)

### Возможности приложения:

- Получение и отправка сообщений.
- Создание ответов.
- Перенаправление сообщений пользователей Vk в отдельные чаты.
- Уведомления о прочитанных сообщениях.

### Запуск приложения с помощью Docker:

1. Установите Docker и Docker-compose. Запустите сервис Docker.

2. Создайте бота в Telegram с помощью @BotFather (подробную инструкцию можно найти в интернете).

3. Склонируйте репозиторий в удобную для вас директорию на компьютере:

    ```bash
    git clone git@github.com:CuriousGecko/vk-tg-connector.git
    ```

    ```bash
    cd vk-tg-connector/infra
    ```

4. Наполните файл env.docker своими данными.

   _**ВАЖНО: держите ваши токены и пароли в секрете, нигде не публикуйте их и никому не пересылайте!**_

   **VK_ID** # ваш id в Vk.

   **VK_ACCESS_TOKEN** # укажите токен приложения Vk, которому вы разрешили доступ к личным сообщениям, списку друзей и прочим данным. Можно воспользоваться [готовым приложением](https://oauth.vk.com/authorize?client_id=2685278&scope=1073737727&redirect_uri=https://api.vk.com/blank.html&display=page&response_type=token&revoke=1). Подтвердите предоставление доступа, в открывшейся вкладке скопируйте из адресной строки ссылку целиком, либо значение параметра access_token.
   
   **TELEGRAM_CHAT_ID** # ваш id в Telegram. Можно узнать у @userinfobot.

   **TELEGRAM_BOT_TOKEN** # токен вашего бота, выданный @BotFather.

   **LOG_LEVEL** # установите уровень логирования (DEBUG, INFO, WARNING, ERROR или CRITICAL)
   
   **READ_NOTIFICATION_MODE** # в каком виде придет уведомление, когда пользователь Vk прочитает ваше сообщение:

   ```
   2 # в виде сообщения в чате.

   1 # на вашем сообщении в Telegram будет установлена реакция 👀.

   0 # уведомления отключены.
   ```
   
   **POSTGRES_USER** # укажите желаемое имя пользователя в БД PostgreSQL.

   **POSTGRES_PASSWORD** # придумайте надежный пароль.

   **POSTGRES_DB** # название БД.

   **POSTGRES_PORT** # измените порт, если потребуется. Также необходимо будет внести изменения в docker-compose.yml

5. Запустите приложение:

    ```bash
    sudo docker compose -f docker-compose.yml up
    ```

### Запуск приложения без Docker (для разработки):

1. Создайте бота в Telegram с помощью @BotFather (подробную инструкцию можно найти в интернете).
   
2. Склонируйте репозиторий в удобную для вас директорию на компьютере:

    ```bash
    git clone git@github.com:CuriousGecko/vk-tg-connector.git
    ```

    ```bash
    cd vk-tg-connector
    ```

3. Скопируйте env.dev в корневую директорию проекта и переименуйте в .env:
   
   ```bash
   cp dev/env.dev .env
   ```

4. Наполните файл .env своими данными (описание ключевых параметров смотрите в предыдущем разделе). Дополнительные параметры:

   **USE_POSTGRES** # выбор базы данных:

   ```
   True: использовать PostgreSQL.

   False: использоваться SQLite (все остальные параметры POSTGRES будут игнорироваться).
   ```

   **POSTGRES_HOST** # хост (укажите localhost или ip, где развернута БД. По умолчанию сервис db_postgres для Docker).

   **POSTGRES_PORT** # порт (по умолчанию 5432).

   **POSTGRES_DB** # название БД (по умолчанию chats).

   **ECHO** # вывод SQL-запросов в терминал (True|False, по умолчанию False).

5. Создайте виртуальное окружение:

   ```bash
   python -m venv venv
   ```
   
6. Активируйте виртуальное окружение.

   Если у вас Windows:

   ```bash
   source venv/scripts/activate
   ```

   Linux/macOS:

   ```bash
   source venv/bin/activate
   ```

7. Установите зависимости:

   ```bash
   pip install -r requirements.txt
   ```

8. Запустите приложение:

   ```bash
   python connector.py
   ```
   
### Взаимодействие с ботом.

Для вызова бота отправьте ему команду /start

![screen_start.png](images%2Fgithub%2Fscreen_start.png)

Важно отметить, что взаимодействовать с ботом может только его владелец.

![screen_access_denied.png](images%2Fgithub%2Fscreen_access_denied.png)

Для отображения команд бота введите **/** или нажмите соответсвующую кнопку.

![screen_commands.png](images%2Fgithub%2Fscreen_commands.jpg)

### Отказ от ответственности.

Это приложение предоставляется "как есть", без каких-либо гарантий, явных или подразумеваемых. Автор не несет ответственности за любой ущерб, возникший в результате использования этого приложения.

Пользователь самостоятельно несет ответственность за любые действия, совершенные с использованием этого приложения. Используя это приложение, вы соглашаетесь с этим отказом от ответственности.

Автор оставляет за собой право вносить изменения в приложение без предварительного уведомления.

### Технология
В проекте используются библиотеки python-telegram-bot и SQLAlchemy.
Полный список зависимостей находится в requirements.txt.

Автор проекта: Леонид Цыбульский
