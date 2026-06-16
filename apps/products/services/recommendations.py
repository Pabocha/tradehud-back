import hashlib
import math
from collections import defaultdict
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from apps.orders.models import OrderLine
from apps.comments.models import Ratings
from apps.accounts.models import ShopFollow
from apps.favorites.models import Favorites
from apps.carts.models import CartItem
from apps.products.models import Products, RecentlyViewedProduct


class RecommendationService:
    CACHE_TTL_SECONDS = 600

    def __init__(self, user, params):
        self.user = user
        self.params = params
        self.now = timezone.now()

    def build(self):
        cache_key = self._build_cache_key()
        if not self.params["refresh"]:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

        profile = self._build_user_profile()
        candidates = list(self._fetch_candidates(profile["owned_shop_ids"]))
        seed_product = self._get_seed_product()

        scored_items = []
        for product in candidates:
            score, breakdown, reason = self._score_product(product, profile, seed_product)
            if score <= 0:
                continue
            scored_items.append(
                {
                    "product": product,
                    "score": round(score, 6),
                    "reason": reason,
                    "score_breakdown": breakdown,
                }
            )

        scored_items.sort(key=lambda item: item["score"], reverse=True)
        selected = self._diversify(scored_items, self.params["limit"])
        payload = {
            "count": len(selected),
            "context": self.params["context"],
            "generated_at": self.now.isoformat(),
            "items": selected,
        }
        cache.set(cache_key, payload, timeout=self.CACHE_TTL_SECONDS)
        return payload

    def _build_cache_key(self):
        exclude_string = ",".join(str(i) for i in sorted(self.params["exclude_ids"]))
        exclude_hash = hashlib.md5(exclude_string.encode("utf-8")).hexdigest()
        seed_id = self.params.get("seed_product_id") or 0
        user_id = getattr(self.user, "id", None)
        user_key = user_id if isinstance(user_id, int) else "anon"
        return (
            f"reco:v1:user:{user_key}:ctx:{self.params['context']}:"
            f"seed:{seed_id}:limit:{self.params['limit']}:ex:{exclude_hash}"
        )

    def _daily_rotation_boost(self, product_id):
        """
        Petit bonus/malus deterministe qui change chaque jour.
        - Stable pendant une meme journee (pas de flicker a chaque refresh)
        - Different le lendemain pour faire tourner les produits
        """
        user_id = getattr(self.user, "id", 0) if getattr(self.user, "is_authenticated", False) else 0
        day_key = self.now.date().isoformat()
        raw = f"{day_key}:{user_id}:{product_id}"
        digest = hashlib.md5(raw.encode("utf-8")).hexdigest()
        # [0, 1] -> [-0.06, +0.06]
        normalized = int(digest[:8], 16) / 0xFFFFFFFF
        return (normalized - 0.5) * 0.12

    def _safe_price_amount(self, product):
        base_price = getattr(product, "base_price", None)
        if base_price is None:
            return None
        amount = getattr(base_price, "amount", None)
        if amount is None:
            return None
        try:
            return float(amount)
        except Exception:
            return None

    def _get_seed_product(self):
        seed_id = self.params.get("seed_product_id")
        if not seed_id:
            return None
        try:
            return Products.objects.select_related("category", "shop").prefetch_related("tags").get(id=seed_id)
        except Products.DoesNotExist:
            return None

    def _get_owned_shop_ids(self):
        if not self.user.is_authenticated or not hasattr(self.user, "seller_account"):
            return []
        return list(self.user.seller_account.shops.values_list("id", flat=True))

    def _build_user_profile(self):
        user_id = getattr(self.user, "id", None)
        if not isinstance(user_id, int):
            return {
                "owned_shop_ids": [],
                "recent_bought_product_ids": set(),
                "category_weights": {},
                "shop_weights": {},
                "brand_weights": {},
                "tag_weights": {},
                "avg_price": None,
                "max_category_weight": 0.0,
                "max_shop_weight": 0.0,
                "max_brand_weight": 0.0,
                "max_tag_weight": 0.0,
                "cart_category_ids": set(),
                "cart_brand_values": set(),
            }

        since_90d = self.now - timedelta(days=90)
        since_30d = self.now - timedelta(days=30)

        category_weights = defaultdict(float)
        shop_weights = defaultdict(float)
        brand_weights = defaultdict(float)
        tag_weights = defaultdict(float)
        prices = []

        owned_shop_ids = self._get_owned_shop_ids()
        recent_bought_product_ids = set()

        line_items = (
            OrderLine.objects.filter(order__customer_id=user_id, order__order_date__gte=since_90d)
            .select_related("product", "variant__product", "shop", "product__category", "variant__product__category")
            .prefetch_related("product__tags", "variant__product__tags")
        )
        for line in line_items:
            product = line.variant.product if line.variant else line.product
            if not product:
                continue
            qty = max(int(getattr(line, "quantity", 1) or 1), 1)
            self._accumulate_profile(
                product,
                base_weight=5.0 * qty,
                category_weights=category_weights,
                shop_weights=shop_weights,
                brand_weights=brand_weights,
                tag_weights=tag_weights,
                prices=prices,
            )
            if line.order and line.order.order_date >= since_30d:
                recent_bought_product_ids.add(product.id)

        favorites = (
            Favorites.objects.filter(user_id=user_id)
            .select_related("product", "product__category", "product__shop")
            .prefetch_related("product__tags")
        )
        for favorite in favorites:
            product = favorite.product
            self._accumulate_profile(
                product,
                base_weight=3.0,
                category_weights=category_weights,
                shop_weights=shop_weights,
                brand_weights=brand_weights,
                tag_weights=tag_weights,
                prices=prices,
            )

        recent_views = (
            RecentlyViewedProduct.objects.filter(user_id=user_id, viewed_at__gte=since_90d)
            .select_related("product", "product__category", "product__shop")
            .prefetch_related("product__tags")
        )
        for item in recent_views:
            product = item.product
            weight = 2.0 * min(int(item.view_count or 1), 5)
            self._accumulate_profile(
                product,
                base_weight=weight,
                category_weights=category_weights,
                shop_weights=shop_weights,
                brand_weights=brand_weights,
                tag_weights=tag_weights,
                prices=prices,
            )

        ratings = (
            Ratings.objects.filter(user_id=user_id, date_added__gte=since_90d)
            .select_related("product", "product__category", "product__shop")
            .prefetch_related("product__tags")
        )
        for rating in ratings:
            product = rating.product
            if not product:
                continue
            if rating.rating >= 4:
                weight = 4.0
            elif rating.rating <= 2:
                weight = -2.0
            else:
                weight = 1.0
            self._accumulate_profile(
                product,
                base_weight=weight,
                category_weights=category_weights,
                shop_weights=shop_weights,
                brand_weights=brand_weights,
                tag_weights=tag_weights,
                prices=prices,
            )

        for follow in ShopFollow.objects.filter(user_id=user_id).values_list("shop_id", flat=True):
            shop_weights[int(follow)] += 5.0

        cart_category_ids = set()
        cart_brand_values = set()
        if self.params["context"] == "cart":
            cart_items = (
                CartItem.objects.filter(user_id=user_id)
                .select_related("product", "product__category", "variant__product", "variant__product__category")
            )
            for item in cart_items:
                product = item.variant.product if item.variant else item.product
                if not product:
                    continue
                if product.category_id:
                    cart_category_ids.add(product.category_id)
                if product.brand:
                    cart_brand_values.add(product.brand.strip().lower())

        avg_price = sum(prices) / len(prices) if prices else None
        return {
            "owned_shop_ids": owned_shop_ids,
            "recent_bought_product_ids": recent_bought_product_ids,
            "category_weights": dict(category_weights),
            "shop_weights": dict(shop_weights),
            "brand_weights": dict(brand_weights),
            "tag_weights": dict(tag_weights),
            "avg_price": avg_price,
            "max_category_weight": max(category_weights.values()) if category_weights else 0.0,
            "max_shop_weight": max(shop_weights.values()) if shop_weights else 0.0,
            "max_brand_weight": max(brand_weights.values()) if brand_weights else 0.0,
            "max_tag_weight": max(tag_weights.values()) if tag_weights else 0.0,
            "cart_category_ids": cart_category_ids,
            "cart_brand_values": cart_brand_values,
        }

    def _accumulate_profile(
        self,
        product,
        base_weight,
        category_weights,
        shop_weights,
        brand_weights,
        tag_weights,
        prices,
    ):
        if product.category_id:
            category_weights[product.category_id] += base_weight
        if product.shop_id:
            shop_weights[product.shop_id] += base_weight * 0.8
        if product.brand:
            brand_weights[product.brand.strip().lower()] += base_weight * 0.5
        for tag_name in product.tags.names():
            tag_weights[tag_name.strip().lower()] += base_weight * 0.35

        amount = self._safe_price_amount(product)
        if amount is not None and amount > 0:
            prices.append(amount)

    def _fetch_candidates(self, owned_shop_ids):
        queryset = (
            Products.objects.with_total_stock()
            .select_related("shop", "category")
            .prefetch_related("variants", "tags")
            .filter(is_active=True, status="available")
            .filter(Q(stock_quantity__gt=0) | Q(variants__stock_quantity__gt=0))
            .exclude(id__in=self.params["exclude_ids"])
            .distinct()
        )
        if owned_shop_ids:
            queryset = queryset.exclude(shop_id__in=owned_shop_ids)
        return queryset

    def _score_product(self, product, profile, seed_product):
        category_affinity = 0.0
        shop_affinity = 0.0
        brand_tag_affinity = 0.0
        price_affinity = 0.0
        quality_score = 0.0
        popularity_score = 0.0
        freshness_score = 0.0
        context_boost = 0.0
        rotation_boost = 0.0
        penalties = 0.0

        if profile["max_category_weight"] > 0 and product.category_id:
            category_affinity = max(
                0.0, profile["category_weights"].get(product.category_id, 0.0) / profile["max_category_weight"]
            )
        if profile["max_shop_weight"] > 0 and product.shop_id:
            shop_affinity = max(0.0, profile["shop_weights"].get(product.shop_id, 0.0) / profile["max_shop_weight"])

        brand_score = 0.0
        if profile["max_brand_weight"] > 0 and product.brand:
            brand_score = max(
                0.0,
                profile["brand_weights"].get(product.brand.strip().lower(), 0.0) / profile["max_brand_weight"],
            )
        tag_score = 0.0
        if profile["max_tag_weight"] > 0:
            current_tags = [t.strip().lower() for t in product.tags.names()]
            if current_tags:
                tag_score = max(
                    [
                        max(0.0, profile["tag_weights"].get(name, 0.0) / profile["max_tag_weight"])
                        for name in current_tags
                    ]
                    + [0.0]
                )
        brand_tag_affinity = (brand_score + tag_score) / 2.0

        product_price = self._safe_price_amount(product)
        if profile["avg_price"] and product_price and profile["avg_price"] > 0:
            diff_ratio = abs(product_price - profile["avg_price"]) / profile["avg_price"]
            price_affinity = max(0.0, 1.0 - min(diff_ratio, 1.0))

        avg_rating = float(getattr(product, "average_rating", 0.0) or 0.0)
        reviews = float(getattr(product, "numbers_reviews", 0) or 0)
        quality_score = min(1.0, max(0.0, avg_rating / 5.0)) * 0.7 + min(1.0, reviews / 20.0) * 0.3

        views = float(getattr(product, "views_count", 0) or 0)
        popularity_score = min(1.0, views / 1000.0)

        days_old = max(0, (self.now - product.date_added).days) if product.date_added else 365
        freshness_score = max(0.0, 1.0 - min(days_old / 60.0, 1.0))

        if self.params["context"] == "product_detail" and seed_product:
            # For product detail, push strongly toward related items.
            related_score = 0.0
            if seed_product.category_id and product.category_id == seed_product.category_id:
                related_score += 0.5
            if (
                seed_product.brand
                and product.brand
                and seed_product.brand.strip().lower() == product.brand.strip().lower()
            ):
                related_score += 0.3
            seed_tags = {t.strip().lower() for t in seed_product.tags.names()}
            current_tags = {t.strip().lower() for t in product.tags.names()}
            if seed_tags and current_tags and seed_tags.intersection(current_tags):
                related_score += 0.2
            context_boost += min(0.45, related_score * 0.45)
            # Penalize unrelated items so product_detail differs from home.
            if related_score == 0:
                penalties += 0.25

        if self.params["context"] == "cart":
            # For cart, favor items related to current cart composition.
            cart_match_score = 0.0
            has_cart_context = bool(profile["cart_category_ids"] or profile["cart_brand_values"])
            if product.category_id and product.category_id in profile["cart_category_ids"]:
                cart_match_score += 0.6
            if product.brand and product.brand.strip().lower() in profile["cart_brand_values"]:
                cart_match_score += 0.4
            context_boost += min(0.35, cart_match_score * 0.35)
            if has_cart_context and cart_match_score == 0:
                penalties += 0.20

        if product.id in profile["recent_bought_product_ids"]:
            penalties += 0.20

        stock_value = getattr(product, "stock_quantity", None)
        if stock_value is None:
            stock_value = getattr(product, "total_stock", 0) or 0
        if stock_value <= 3:
            penalties += 0.15

        # Rotation quotidienne legere pour eviter les memes tops en permanence.
        rotation_boost = self._daily_rotation_boost(product.id)

        weighted = (
            0.35 * category_affinity
            + 0.20 * shop_affinity
            + 0.15 * brand_tag_affinity
            + 0.10 * price_affinity
            + 0.10 * quality_score
            + 0.05 * popularity_score
            + 0.05 * freshness_score
            + context_boost
            + rotation_boost
            - penalties
        )

        reason_parts = []
        if category_affinity >= 0.5:
            reason_parts.append("category_match")
        if shop_affinity >= 0.5:
            reason_parts.append("shop_affinity")
        if brand_tag_affinity >= 0.5:
            reason_parts.append("brand_tag_match")
        if context_boost > 0:
            reason_parts.append(f"context_{self.params['context']}")
        if not reason_parts:
            reason_parts.append("quality_popularity")

        breakdown = {
            "category_affinity": round(category_affinity, 4),
            "shop_affinity": round(shop_affinity, 4),
            "brand_tag_affinity": round(brand_tag_affinity, 4),
            "price_affinity": round(price_affinity, 4),
            "quality": round(quality_score, 4),
            "popularity": round(popularity_score, 4),
            "freshness": round(freshness_score, 4),
            "context_boost": round(context_boost, 4),
            "rotation_boost": round(rotation_boost, 4),
            "penalty": round(-penalties, 4),
        }
        return weighted, breakdown, "+".join(reason_parts)

    def _diversify(self, scored_items, limit):
        if not scored_items:
            return []

        primary_target = max(1, int(math.ceil(limit * 0.8)))
        selected = []
        selected_ids = set()
        shop_counts = defaultdict(int)
        category_counts = defaultdict(int)

        for item in scored_items:
            product = item["product"]
            if product.id in selected_ids:
                continue
            if len(selected) < 10 and shop_counts[product.shop_id] >= 2:
                continue
            if len(selected) < 20 and product.category_id and category_counts[product.category_id] >= 4:
                continue
            selected.append(item)
            selected_ids.add(product.id)
            shop_counts[product.shop_id] += 1
            if product.category_id:
                category_counts[product.category_id] += 1
            if len(selected) >= primary_target:
                break

        preferred_category_ids = {
            item["product"].category_id for item in selected if item["product"].category_id is not None
        }
        trending_queryset = (
            Products.objects.with_total_stock()
            .select_related("shop", "category")
            .prefetch_related("tags")
            .filter(is_active=True, status="available")
            .exclude(id__in=list(selected_ids | self.params["exclude_ids"]))
        )
        if preferred_category_ids:
            trending_queryset = trending_queryset.filter(category_id__in=preferred_category_ids)
        trending = list(trending_queryset.order_by("-views_count", "-average_rating", "-date_added")[: max(20, limit * 2)])

        for product in trending:
            if len(selected) >= limit:
                break
            if product.id in selected_ids:
                continue
            selected.append(
                {
                    "product": product,
                    "score": 0.2,
                    "reason": "trending_fallback",
                    "score_breakdown": {
                        "category_affinity": 0.0,
                        "shop_affinity": 0.0,
                        "brand_tag_affinity": 0.0,
                        "price_affinity": 0.0,
                        "quality": 0.0,
                        "popularity": 0.2,
                        "freshness": 0.0,
                        "context_boost": 0.0,
                        "penalty": 0.0,
                    },
                }
            )
            selected_ids.add(product.id)

        if len(selected) < limit:
            for item in scored_items:
                if len(selected) >= limit:
                    break
                product = item["product"]
                if product.id in selected_ids:
                    continue
                selected.append(item)
                selected_ids.add(product.id)

        output = []
        for item in selected[:limit]:
            row = {
                "product_id": item["product"].id,
                "score": item["score"],
                "reason": item["reason"],
            }
            if self.params["debug"]:
                row["score_breakdown"] = item["score_breakdown"]
            output.append(row)
        return output


def parse_recommendation_params(request):
    raw_limit = request.query_params.get("limit", 20)
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 50))

    context = request.query_params.get("context", "home")
    if context not in {"home", "product_detail", "cart"}:
        context = "home"

    exclude_ids = set()
    raw_exclude = request.query_params.get("exclude_ids", "")
    if raw_exclude:
        for token in raw_exclude.split(","):
            token = token.strip()
            if token.isdigit():
                exclude_ids.add(int(token))

    seed_product_id = request.query_params.get("seed_product_id")
    if seed_product_id is not None and str(seed_product_id).isdigit():
        seed_product_id = int(seed_product_id)
    else:
        seed_product_id = None

    refresh = str(request.query_params.get("refresh", "false")).lower() == "true"
    debug = str(request.query_params.get("debug", "false")).lower() == "true"

    return {
        "limit": limit,
        "context": context,
        "exclude_ids": exclude_ids,
        "seed_product_id": seed_product_id,
        "refresh": refresh,
        "debug": debug,
    }
