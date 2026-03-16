"""
Cliente Redis centralizado con connection pool.

Todos los módulos deben importar get_redis_client() desde aquí
en lugar de crear sus propias conexiones.
"""

import redis
from .config import settings

_pool: redis.ConnectionPool | None = None


def _get_pool() -> redis.ConnectionPool:
    global _pool
    if _pool is None:
        _pool = redis.ConnectionPool(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True,
        )
    return _pool


def get_redis_client() -> redis.Redis:
    """Obtiene un cliente Redis que reutiliza conexiones del pool."""
    return redis.Redis(connection_pool=_get_pool())
