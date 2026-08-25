<h1 align="center">Добро пожаловать в PsyHelper</h1>
<p align="center">
  <img alt="Version" src="https://img.shields.io/badge/version-0.1--dev-blue.svg?cacheSeconds=2592000" />
  <img alt="Status" src="https://img.shields.io/badge/status-в%20разработке-orange.svg" />
</p>

> PsyHelper - сайт частного психотерапевта: блог со статьями, комментариями и
> оценками читателей, и форма заявки на консультацию (можно отправить
> анонимно) с уведомлением администратора на почту и в Telegram. Отдельно -
> служебная панель для персонала, где заявки обрабатываются через REST API.

### [Страница проекта](https://github.com/Kereot/Psycharm)

## Описание проекта

Проект реализован на Django: основной сайт - серверный рендеринг шаблонов
(Bootstrap), поверх него - REST API (Django REST Framework) для служебной
панели заявок, Swagger/Redoc-документации и в перспективе - стороннего
клиента.

### Стек технологий:
[![Stack](https://skillicons.dev/icons?i=py,django,html,postgres,github)](https://skillicons.dev)

- Django 5.2 + Django REST Framework, Djoser + SimpleJWT (авторизация по
  JWT для API, по сессии - для сайта и служебной панели);
- drf-spectacular (Swagger/Redoc), drf-nested-routers (вложенные роуты
  комментариев/оценок);
- SQLite для локальной разработки, готовность к PostgreSQL через переменные
  окружения;
- pytest-django - автотесты, flake8 - проверка стиля.

### Основные возможности:
- просмотр статей, комментарии и оценки к ним (только для зарегистрированных
  пользователей), список статей с пагинацией;
- регистрация, вход, восстановление пароля по email, профиль пользователя,
  включая загрузку аватара;
- заявка на консультацию - можно отправить анонимно или из-под аккаунта;
  анонимная заявка автоматически привязывается к аккаунту, если
  зарегистрироваться/войти в том же браузере в течение лимитированного времени;
- список своих заявок и правка контакта/текста незакрытой заявки - доступны и
  на сайте, и через API; об изменении отдельно уведомляется администратор;
- уведомление администратора о новой заявке (и о её последующей правке) на
  почту и в Telegram, фоново - не блокирует ответ пользователю;
- служебная панель для персонала: список заявок с группировкой по контакту,
  смена статуса, индикатор недоставленных уведомлений;
- анти-спам: honeypot-поле, лимит на создание/правку заявок и комментариев -
  привязан к отправителю (IP или пользователю), а не к содержимому формы, в
  том числе на страницах, где DRF не участвует;
- статичные страницы «Обо мне», «Контакты», «Цены», «Политика обработки
  персональных данных».

### Разделы сайта:
- / - главная;
- /articles/ - список статей;
- /articles/&lt;slug&gt;/ - статья, комментарии и оценка;
- /consultation/ - заявка на консультацию;
- /consultation/my/ - список своих заявок;
- /consultation/my/&lt;id&gt;/edit/ - правка контакта/текста своей незакрытой заявки;
- /consultation/staff/ - панель заявок (только персонал);
- /accounts/register/, /accounts/login/, /accounts/profile/ - регистрация,
  вход, профиль;
- /accounts/password_reset/ - восстановление пароля по email;
- /about/ - обо мне;
- /contacts/ - контакты;
- /prices/ - цены;
- /privacy/ - политика обработки персональных данных;
- /admin/ - панель администратора Django.

### Основные API эндпоинты:
- /api/v1/users/ - $${\color{green}GET}$$, $${\color{blue}POST}$$ -
  пользователи, регистрация;
- /api/v1/users/me/avatar/ - $${\color{orange}PUT}$$, $${\color{red}DELETE}$$
  - аватар текущего пользователя;
- /api/v1/jwt/create/ | /api/v1/jwt/refresh/ - $${\color{blue}POST}$$ -
  JWT-токены;
- /api/v1/articles/ - $${\color{green}GET}$$, $${\color{blue}POST}$$ -
  статьи;
- /api/v1/articles/&lt;slug&gt;/comments/ - $${\color{green}GET}$$,
  $${\color{blue}POST}$$ - комментарии к статье;
- /api/v1/articles/&lt;slug&gt;/ratings/ - $${\color{green}GET}$$,
  $${\color{blue}POST}$$ - оценки статьи;
- /api/v1/consultations/ - $${\color{green}GET}$$ (персонал),
  $${\color{blue}POST}$$ (все) - заявки на консультацию;
- /api/v1/consultations/my/ - $${\color{green}GET}$$ - свои заявки
  (авторизованный пользователь);
- /api/v1/consultations/&lt;id&gt;/ - $${\color{orange}PATCH}$$ - персоналу
  меняет статус, владельцу незакрытой заявки - контакт и текст;
- /api/v1/prices/ - $${\color{green}GET}$$ - прайс-лист.

### Документация локально:

После запуска backend-приложения:
- /api/v1/schema/swagger-ui/ - Swagger UI;
- /api/v1/schema/redoc/ - Redoc.

## Установка и запуск (локально)

Проект пока не развёрнут на удалённом сервере - ниже только локальный запуск
для разработки.

### 1. Клонировать репозиторий

```
git clone https://github.com/Kereot/Psycharm.git
```

```
cd Psycharm/backend
```

### 2. Создать и активировать виртуальное окружение

```
python -m venv .venv
```

* Linux/macOS

    ```
    source .venv/bin/activate
    ```

* Windows

    ```
    .venv\Scripts\activate
    ```

### 3. Установить зависимости

```
python -m pip install --upgrade pip
```

```
pip install -r requirements.txt
```

Для разработки (тесты) - вместо этого:

```
pip install -r requirements-dev.txt
```

### 4. Настроить переменные окружения

Скопировать `.env.example` в `.env` и заполнить:

```
cp .env.example .env
```

- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`;
- `DB_ENGINE` - `sqlite3` (по умолчанию, проще для локальной разработки) или
  `postgres` (+ `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`) -
  в `.env.example` активен `sqlite3`, для PostgreSQL замените строку на
  `DB_ENGINE=postgres`;
- `EMAIL_*` - SMTP для уведомлений администратору (по умолчанию письма
  просто печатаются в консоль);
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID` - уведомления в Telegram
  (необязательно).

### 5. Применить миграции, создать таблицу кэша и суперпользователя

```
python manage.py migrate
```

Таблица для `CACHES` (общий для всех воркеров бэкенд — на нём держится защита
от флуда заявок/комментариев) создаётся отдельно, не через `migrate`:

```
python manage.py createcachetable
```

```
python manage.py createsuperuser
```

### 6. Запустить проект

```
python manage.py runserver
```

Стандартный адрес приложения: http://127.0.0.1:8000

### Тесты

Нужны зависимости из `requirements-dev.txt` (см. шаг 3).

```
pytest
```

или

```
python manage.py test
```

### Проверка стиля кода

```
flake8 .
```

## Автор

Это учебный проект **Kereot**

* Github: [@kereot](https://github.com/kereot)
