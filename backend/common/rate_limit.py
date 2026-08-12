from django.core.cache import cache

RATE_LIMIT_CACHE_KEY_PREFIX = 'rate_limit'


def is_rate_limited(scope, identifier, limit, window_seconds):
    """Простой rate limiter для работы в обычных view."""
    cache_key = f'{RATE_LIMIT_CACHE_KEY_PREFIX}:{scope}:{identifier}'
    count = cache.get(cache_key)
    if count is None:
        cache.set(cache_key, 1, timeout=window_seconds)
        return False
    if count >= limit:
        return True
    cache.incr(cache_key)
    return False
