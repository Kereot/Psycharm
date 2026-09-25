import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """IP клиента для лимитов. REMOTE_ADDR за прокси - адрес контейнера nginx, один на всех посетителей."""

    hops = settings.TRUSTED_PROXY_HOPS
    # X-Forwarded-For - условный список, куда каждый прокси дописывает адрес предыдущего
    # звена. Доверять можно только хвосту справа, который дописала наша
    # собственная инфраструктура. Caddy без trusted_proxies себя не дописывает,
    # а заменяет значение целиком на настоящий IP клиента.
    #
    # При ожидаемой длине цепочки берём то, что перед нашим хвостом. При любом
    # расхождении, отступаем к REMOTE_ADDR и пишем предупреждение.
    if hops:
        chain = [ip.strip() for ip in request.META.get('HTTP_X_FORWARDED_FOR', '').split(',') if ip.strip()]
        if len(chain) == hops + 1:
            return chain[-(hops + 1)]
        logger.warning(
            'X-Forwarded-For неожиданной длины (%d элементов) - лимиты считаются '
            'по одному общему ключу, проверьте цепочку прокси.',
            len(chain),
        )
    return request.META.get('REMOTE_ADDR', '')
