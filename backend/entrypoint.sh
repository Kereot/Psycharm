#!/bin/sh
set -e

python manage.py migrate --noinput
# Если таблица уже есть, просто сообщает об этом и ничего не делает.
python manage.py createcachetable
python manage.py collectstatic --noinput

exec "$@"
