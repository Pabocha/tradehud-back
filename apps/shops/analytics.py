"""
Utilitaires Redis pour la comptabilisation légère des visites de boutiques et
des vues produits. Les compteurs sont incrémentés de façon atomique en Redis,
puis vidés en base par la tâche Celery `flush_visits_and_views`.

Tous les accès Redis sont protégés : si Redis est indisponible, on ne compte
pas la visite (dégradation douce) au lieu de lever une erreur.
"""
import logging

logger = logging.getLogger(__name__)

try:
    from django_redis import get_redis_connection

    def _conn():
        return get_redis_connection('default')

    REDIS_AVAILABLE = True
except Exception:  # pragma: no cover
    _conn = None
    REDIS_AVAILABLE = False

VISIT_EXPIRE_SECONDS = 7 * 24 * 60 * 60  # 7 jours
VIEW_EXPIRE_SECONDS = 7 * 24 * 60 * 60


def shop_visit_key(shop_id, date):
    return f'th:shop_visits:{shop_id}:{date.isoformat()}'


def product_view_key(product_id):
    return f'th:product_views:{product_id}'


def increment_shop_visit(shop_id, date):
    """Incrémente de 1 le compteur de visites d'une boutique pour une journée."""
    if not REDIS_AVAILABLE:
        return False
    try:
        conn = _conn()
        key = shop_visit_key(shop_id, date)
        conn.incr(key, 1)
        conn.expire(key, VISIT_EXPIRE_SECONDS)
        return True
    except Exception as exc:
        logger.warning("Redis indisponible pour la visite boutique %s: %s", shop_id, exc)
        return False


def increment_product_view(product_id):
    """Incrémente de 1 le compteur de vues d'un produit."""
    if not REDIS_AVAILABLE:
        return False
    try:
        conn = _conn()
        key = product_view_key(product_id)
        conn.incr(key, 1)
        conn.expire(key, VIEW_EXPIRE_SECONDS)
        return True
    except Exception as exc:
        logger.warning("Redis indisponible pour la vue produit %s: %s", product_id, exc)
        return False


def buffered_shop_visits(shop_id, date):
    """Renvoie le nombre de visites en attente de flush pour une (shop, journée)."""
    if not REDIS_AVAILABLE:
        return 0
    try:
        raw = _conn().get(shop_visit_key(shop_id, date))
        return int(raw) if raw else 0
    except Exception as exc:
        logger.warning("Redis indisponible (lecture visites shop %s): %s", shop_id, exc)
        return 0


def buffered_views_product(product_id):
    """Renvoie le nombre de vues en attente de flush pour un produit."""
    if not REDIS_AVAILABLE:
        return 0
    try:
        raw = _conn().get(product_view_key(product_id))
        return int(raw) if raw else 0
    except Exception as exc:
        logger.warning("Redis indisponible (lecture vues produit %s): %s", product_id, exc)
        return 0


def get_shop_total_visits(shop_id, date):
    """Visites totales d'une journée = base + buffer Redis non encore flushé."""
    from .models import ShopStatistics

    base = 0
    try:
        row = ShopStatistics.objects.filter(shop_id=shop_id, date=date).values_list('visits', flat=True).first()
        base = row or 0
    except Exception:
        pass
    return base + buffered_shop_visits(shop_id, date)


def buffered_visits_map(shop_id, dates):
    """Map {date.isoformat(): visites_en_buffer} pour une liste de dates."""
    if not REDIS_AVAILABLE:
        return {}
    out = {}
    try:
        pipe = _conn().pipeline()
        keys = [shop_visit_key(shop_id, d) for d in dates]
        for key in keys:
            pipe.get(key)
        values = pipe.execute()
        for date, raw in zip(dates, values):
            if raw:
                out[date.isoformat()] = int(raw)
    except Exception as exc:
        logger.warning("Redis indisponible (map visites shop %s): %s", shop_id, exc)
    return out


def buffered_views_map(shop_id):
    """Map {product_id: vues_en_buffer} pour tous les produits d'une boutique."""
    if not REDIS_AVAILABLE:
        return {}
    out = {}
    try:
        conn = _conn()
        keys = list(conn.scan_iter(match='th:product_views:*', count=200))
        if not keys:
            return out
        from .models import Shops
        from apps.products.models import Products

        if not Shops.objects.filter(pk=shop_id).exists():
            return out
        valid_ids = set(Products.objects.filter(shop_id=shop_id).values_list('id', flat=True))
        for key in keys:
            parts = key.decode() if isinstance(key, bytes) else key
            parts = parts.split(':')  # ['th', 'product_views', product_id]
            if len(parts) != 3:
                continue
            pid = int(parts[2])
            if pid in valid_ids:
                raw = conn.get(key)
                if raw:
                    out[pid] = int(raw)
    except Exception as exc:
        logger.warning("Redis indisponible (map vues shop %s): %s", shop_id, exc)
    return out