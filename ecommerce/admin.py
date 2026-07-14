from django.contrib import admin
from django.template.response import TemplateResponse
from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone
from datetime import timedelta


class EcommerceAdminSite(admin.AdminSite):
    site_header = 'Administration E-Commerce'
    site_title = 'Admin E-Commerce'
    index_title = 'Tableau de bord'

    def index(self, request, extra_context=None):
        from apps.orders.models import Orders
        from apps.products.models import Products, ProductVariant
        from apps.accounts.models import CustomUser
        from apps.shops.models import Shops
        from apps.comments.models import Ratings, ShopRatings

        now = timezone.now()
        today = now.date()
        thirty_days_ago = now - timedelta(days=30)
        seven_days_ago = now - timedelta(days=7)

        # --- KPIs ---
        total_revenue = Orders.objects.filter(
            payment_status='paid'
        ).aggregate(total=Sum('total_amount'))['total'] or 0

        revenue_today = Orders.objects.filter(
            payment_status='paid',
            order_date__date=today
        ).aggregate(total=Sum('total_amount'))['total'] or 0

        revenue_30d = Orders.objects.filter(
            payment_status='paid',
            order_date__gte=thirty_days_ago
        ).aggregate(total=Sum('total_amount'))['total'] or 0

        total_orders = Orders.objects.count()
        orders_pending = Orders.objects.filter(status='pending').count()
        orders_processing = Orders.objects.filter(status='processing').count()
        orders_delivered = Orders.objects.filter(status='delivered').count()

        total_users = CustomUser.objects.count()
        users_30d = CustomUser.objects.filter(date_joined__gte=thirty_days_ago).count()

        total_products = Products.objects.filter(is_active=True).count()
        total_shops = Shops.objects.filter(status='active').count()

        low_stock_products = ProductVariant.objects.filter(
            stock_quantity__lte=5, product__is_active=True
        ).count()

        # --- Commandes par jour (7 derniers jours) ---
        orders_by_day = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            count = Orders.objects.filter(order_date__date=day).count()
            orders_by_day.append({'day': day.strftime('%d/%m'), 'count': count})

        # --- Top boutiques par revenu (30j) ---
        top_shops = (
            Orders.objects
            .filter(payment_status='paid', order_date__gte=thirty_days_ago)
            .values('order_lines__shop__name')
            .annotate(revenue=Sum('total_amount'), order_count=Count('id'))
            .order_by('-revenue')[:5]
        )

        # --- Répartition statuts commandes ---
        status_distribution = (
            Orders.objects
            .values('status')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # --- Avis non lus (rating bas) ---
        pending_reviews = Ratings.objects.filter(rating__lte=2).count()

        extra_context = extra_context or {}
        extra_context.update({
            'total_revenue': total_revenue,
            'revenue_today': revenue_today,
            'revenue_30d': revenue_30d,
            'total_orders': total_orders,
            'orders_pending': orders_pending,
            'orders_processing': orders_processing,
            'orders_delivered': orders_delivered,
            'total_users': total_users,
            'users_30d': users_30d,
            'total_products': total_products,
            'total_shops': total_shops,
            'low_stock_products': low_stock_products,
            'orders_by_day': orders_by_day,
            'top_shops': list(top_shops),
            'status_distribution': list(status_distribution),
            'pending_reviews': pending_reviews,
        })

        return super().index(request, extra_context=extra_context)


admin_site = EcommerceAdminSite(name='ecommerce_admin')
