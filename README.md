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
  персональных данных»;
- демо-режим (`DEMO_MODE=True`): введённые в формы имена и контакты подменяются
  случайными значениями, на сайте показывается предупреждение - чтобы на
  демонстрационном экземпляре не накапливались реальные персональные данные.
  Подмена работает только в формах сайта, а текст сообщения, логин, email и
  аватар сохраняются как введены.

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

Локальный запуск для разработки.
Про запуск через Docker Compose (для сервера) - в разделе
[Развёртывание (Docker Compose + CI/CD)](#развёртывание-docker-compose--cicd).

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
  `postgres` (+ `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `DB_HOST`, `DB_PORT`);
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

## Развёртывание (Docker Compose + CI/CD)

Три контейнера: `db` (PostgreSQL), `backend` (gunicorn) и `nginx` (отдаёт
`/static/`, `/media/`, проксирует остальное на `backend`).

Порты на хост не публикуются: на сервере 80/443 держит Caddy (в контейнере, выдаёт и
обновляет сертификаты), он ходит к `psycharm-nginx` по имени контейнера через
общую внешнюю docker-сеть `proxy`.

`docker-compose.yml` в корне репозитория использует готовые образы с Docker Hub - их собирает и пушит
GitHub Actions при пуше в `master`, после чего по ssh обновляет контейнеры на сервере.

Миграции, `createcachetable` и `collectstatic` выполняются автоматически при каждом старте `backend`
(`backend/entrypoint.sh`).

### Локальная проверка сборки

`docker-compose.override.yml` подключается автоматически: собирает образы на
месте (`build:`) вместо pull с Docker Hub и публикует nginx на
`http://localhost:8080` (без Caddy). На сервере этого файла быть не
должно (только `docker-compose.yml` - его копирует `main.yml`).

Внешняя сеть `proxy` должна существовать и локально:

```
docker network create proxy
```

```
cp .env.example .env
```

Для локальной проверки в `.env` достаточно `DEBUG=True`.

```
docker compose up --build -d
```

```
docker compose exec backend python manage.py createsuperuser
```

### Деплой на сервере (GitHub Actions)

1. На сервере необходим файл `.env` в корне приложения (рядом с `docker-compose.yml`). Обязательно:
   - `DB_ENGINE=postgres`, `DB_HOST=db` (имя сервиса, не `localhost`);
   - `POSTGRES_DB`/`POSTGRES_USER`/`POSTGRES_PASSWORD` - их читает и образ
     `postgres` (создаёт пользователя и базу при первой инициализации тома),
     и Django; после первого запуска менять их в `.env` бесполезно;
   - `DEBUG=False`, `SECRET_KEY`;
   - `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` - реальный домен (в
     `CSRF_TRUSTED_ORIGINS` - со схемой, например `https://example.com`);
   - `DEMO_MODE=True` - для демонстрационного экземпляра (подмена имён и
     контактов и предупреждение на сайте). Без этой строки режим выключен.
2. В Caddyfile на сервере - блок для домена (DNS-запись домена должна вести на
   сервер, иначе Caddy не выдаст сертификат):

   ```
   <ваш_сервер.домен> {
       reverse_proxy psycharm-nginx:80
   }
   ```

   Заголовки `X-Forwarded-Proto`/`X-Forwarded-For` Caddy выставляет сам, без
   дополнительной настройки - см. «Про HTTPS и IP клиента» ниже.
3. В репозитории на GitHub: Settings → Secrets and variables → Actions,
   добавить `DOCKER_USERNAME`, `DOCKER_PASSWORD`, `HOST`, `USER`, `SSH_KEY`
   и (если нужны уведомления о деплое) `TELEGRAM_TO`, `TELEGRAM_TOKEN`.
4. Пуш в `master` прогоняет тесты и flake8, собирает и пушит образы на Docker
   Hub, копирует `docker-compose.yml` на сервер по ssh и перезапускает стек.

### Про HTTPS и IP клиента

По `X-Forwarded-For` (`common/request.py`) считаются лимиты на заявки, вход и
комментарии: `REMOTE_ADDR` за прокси - адрес контейнера nginx, один на всех
посетителей.

`X-Forwarded-For` - условный список, куда каждый прокси дописывает адрес предыдущего
звена. Доверять можно только хвосту справа, который дописала наша собственная
инфраструктура. `TRUSTED_PROXY_HOPS` в `.env` (по умолчанию 1) - явное число таких узлов, Caddy
без `trusted_proxies` себя не дописывает, а полностью заменяет заголовок на
настоящий IP клиента. При ожидаемой длине цепочки берём то, что перед нашим
хвостом; при любом расхождении - откатываемся на `REMOTE_ADDR` и пишем
предупреждение в лог, а не угадываем позицию.

**Если добавите ещё один прокси перед Caddy (CDN и т.п.) - поднимите
`TRUSTED_PROXY_HOPS` соответственно.** Учтите: если тогда же включите Caddy
`trusted_proxies`, это меняет и поведение самого Caddy - без `trusted_proxies`
он заменяет `X-Forwarded-For` целиком, с ним - дополняет существующую
цепочку, так что пересчитывать число нужно по факту, а не просто прибавлять
единицу за каждый физический узел.

Это и общая для nginx/Caddy предпосылка - что nginx не доступен снаружи в
обход Caddy - держатся на том, что порт nginx не публикуется на хост. Не
публикуйте его.

## Автор

* Github: [@kereot](https://github.com/kereot)
