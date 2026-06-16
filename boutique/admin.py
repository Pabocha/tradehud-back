from django.contrib import admin
from .models import Shops, DocumentShop, ShopStatistics
from django.utils.html import format_html


# ============================================================================
# SHOP ADMIN
# ============================================================================
@admin.register(Shops)
class ShopsAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'status', 'date_created', 'total_orders', 'average_rating')
    list_filter = ('status', 'is_deleted', 'is_top_seller', 'date_created')
    search_fields = ('name', 'owner__user__email', 'email_contact')
    readonly_fields = ('date_created',)


# ============================================================================
# DOCUMENT SHOP ADMIN
# ============================================================================
@admin.register(DocumentShop)
class DocumentShopAdmin(admin.ModelAdmin):
    list_display = ('shop', 'type_document', 'date_upload')
    list_filter = ('type_document', 'date_upload')
    search_fields = ('shop__name',)
    readonly_fields = ('date_upload',)


## ============================================================================
# SHOP STATISTICS ADMIN (CUSTOM)
# ============================================================================
@admin.register(ShopStatistics)
class ShopStatisticsAdmin(admin.ModelAdmin):
    """
    Interface admin personnalisée pour les statistiques de boutique.
    Affiche les données sous forme de cartes colorées et interactives.
    """
    
    list_display = (
        'shop_name',
        'date',
        'stats_sales_display',      # ✅ Bon nom
        'stats_engagement_display',  # ✅ Bon nom
        'stats_inventory_display',   # ✅ Bon nom
    )
    
    list_filter = ('date', 'shop', 'shop_average_rating')
    search_fields = ('shop__name', 'date')
    ordering = ('-date', 'shop')
    
    readonly_fields = (
        'shop',
        'date',
        'card_sales',
        'card_engagement',
        'card_inventory',
        'card_traffic',
        'card_products',
    )
    
    fieldsets = (
        ('📊 Informations', {
            'fields': ('shop', 'date'),
        }),
        ('💰 Ventes', {
            'fields': ('card_sales',),
            'classes': ('collapse',),
        }),
        ('👥 Engagement', {
            'fields': ('card_engagement',),
            'classes': ('collapse',),
        }),
        ('📦 Inventaire', {
            'fields': ('card_inventory',),
            'classes': ('collapse',),
        }),
        ('🎯 Trafic', {
            'fields': ('card_traffic',),
            'classes': ('collapse',),
        }),
        ('🛍️ Produits', {
            'fields': ('card_products',),
            'classes': ('collapse',),
        }),
    )
    
    list_per_page = 50
    
    # ===== COLONNES DE LISTE =====
    
    def shop_name(self, obj):
        """Affiche le nom de la boutique avec lien"""
        return format_html(
            obj.shop.name
        )
    shop_name.short_description = '🏪 Boutique'
    
    def stats_sales_display(self, obj):
        """Résumé des ventes"""
        total_revenue = float(obj.total_revenue)
        revenue_str = f"{total_revenue:.0f}"
        return format_html(
            '<span style="background-color: #d4edda; color: #000; padding: 5px 10px; border-radius: 4px;">'
            '💰 {}F | {} cmd</span>',
            revenue_str,
            obj.total_orders
        )
    stats_sales_display.short_description = '💰 Ventes'
    
    def stats_engagement_display(self, obj):
        """Résumé de l'engagement"""
        stars = '⭐' * int(obj.shop_average_rating)
        rating = float(obj.shop_average_rating)
        rating_str = f"{rating:.1f}"
        return format_html(
            '<span style="background-color: #cce5ff; color: #000; padding: 5px 10px; border-radius: 4px;">'
            '{} {}/5 | {} avis</span>',
            stars if stars else '☆☆☆☆☆',
            rating_str,
            obj.shop_number_of_reviews
        )
    stats_engagement_display.short_description = '👥 Engagement'
    
    def stats_inventory_display(self, obj):
        """Résumé de l'inventaire"""
        avg_stock = float(obj.average_product_stock)
        stock_str = f"{avg_stock:.0f}"
        return format_html(
            '<span style="background-color: #fff3cd; color: #000; padding: 5px 10px; border-radius: 4px;">'
            '📦 Stock: {} | Bas: {} | Rupture: {}</span>',
            stock_str,
            obj.products_low_stock,
            obj.products_out_of_stock
        )
    stats_inventory_display.short_description = '📦 Inventaire'
    
    # ===== CARTES DÉTAILLÉES =====
    
    def card_sales(self, obj):
        """Carte complète des ventes"""
        total_revenue = float(obj.total_revenue)
        avg_order = float(obj.average_order_value)
        revenue_str = f"{total_revenue:.2f}"
        avg_order_str = f"{avg_order:.2f}"

        html = (
            '<div style="background-color: #f0f9ff; border: 2px solid #38a169; border-radius: 8px; padding: 15px;">'
            '<h3 style="color: #38a169; margin-top: 0;">💰 Ventes</h3>'
            '<table style="width: 100%; border-collapse: collapse;">'
            '<tr><td style="padding: 8px;"><strong>Commandes:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{}</td></tr>'
            '<tr style="background-color: #f9ffee;"><td style="padding: 8px;"><strong>Revenu total:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{}€</td></tr>'
            '<tr><td style="padding: 8px;"><strong>Produits vendus:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{}</td></tr>'
            '<tr style="background-color: #f9ffee;"><td style="padding: 8px;"><strong>Panier moyen:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{}€</td></tr>'
            '</table></div>'
        )
        return format_html(html, obj.total_orders, revenue_str, obj.products_sold, avg_order_str)
    card_sales.short_description = '💰 Ventes'
    
    def card_engagement(self, obj):
        """Carte complète de l'engagement"""
        stars = '⭐' * int(obj.shop_average_rating)
        rating = float(obj.shop_average_rating)
        rating_str = f"{rating:.1f}"
        
        html = (
            '<div style="background-color: #f0e7ff; border: 2px solid #7c3aed; border-radius: 8px; padding: 15px;">'
            '<h3 style="color: #7c3aed; margin-top: 0;">👥 Engagement</h3>'
            '<table style="width: 100%; border-collapse: collapse;">'
            '<tr><td style="padding: 8px;"><strong>Note:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{} {}/5</td></tr>'
            '<tr style="background-color: #f9f3ff;"><td style="padding: 8px;"><strong>Avis:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{}</td></tr>'
            '<tr><td style="padding: 8px;"><strong>Nouveaux followers:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{}</td></tr>'
            '<tr style="background-color: #f9f3ff;"><td style="padding: 8px;"><strong>Nouveaux clients:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{}</td></tr>'
            '<tr><td style="padding: 8px;"><strong>Clients récurrents:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{}</td></tr>'
            '</table></div>'
        )
        return format_html(
            html,
            stars if stars else '☆☆☆☆☆',
            rating,
            obj.shop_number_of_reviews,
            obj.new_followers,
            obj.new_customers,
            obj.repeat_customers
        )
    card_engagement.short_description = '👥 Engagement'
    
    def card_inventory(self, obj):
        """Carte complète de l'inventaire"""
        avg_stock = float(obj.average_product_stock)
        stock_str = f"{avg_stock:.0f}"
        
        html = (
            '<div style="background-color: #fffbf0; border: 2px solid #f59e0b; border-radius: 8px; padding: 15px;">'
            '<h3 style="color: #f59e0b; margin-top: 0;">📦 Inventaire</h3>'
            '<table style="width: 100%; border-collapse: collapse;">'
            '<tr><td style="padding: 8px;"><strong>Stock moyen:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{}</td></tr>'
            '<tr style="background-color: #fffaf5;"><td style="padding: 8px;"><strong>Produits en rupture:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{}</td></tr>'
            '<tr><td style="padding: 8px;"><strong>Produits en bas stock:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{}</td></tr>'
            '</table></div>'
        )
        return format_html(html, stock_str, obj.products_out_of_stock, obj.products_low_stock)
    card_inventory.short_description = '📦 Inventaire'
    
    def card_traffic(self, obj):
        """Carte complète du trafic"""
        total_views = int(obj.total_product_views)
        avg_views = float(obj.average_views_per_product)
        conversion = float(obj.conversion_rate)
        visits = int(obj.visits)

        html = (
            '<div style="background-color: #f0f4ff; border: 2px solid #3b82f6; border-radius: 8px; padding: 15px;">'
            '<h3 style="color: #3b82f6; margin-top: 0;">🎯 Trafic</h3>'
            '<table style="width: 100%; border-collapse: collapse;">'
            '<tr><td style="padding: 8px;"><strong>Vues totales:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{}</td></tr>'
            '<tr style="background-color: #f3f7ff;"><td style="padding: 8px;"><strong>Vues/produit:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{:.2f}</td></tr>'
            '<tr><td style="padding: 8px;"><strong>Visites:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{}</td></tr>'
            '<tr style="background-color: #f3f7ff;"><td style="padding: 8px;"><strong>Taux de conversion:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{:.2f}%</td></tr>'
            '</table></div>'
        )
        return format_html(html, total_views, avg_views, visits, conversion)
    card_traffic.short_description = '🎯 Trafic'
    
    def card_products(self, obj):
        """Carte des produits vedettes"""
        best_product = obj.best_selling_product.name if obj.best_selling_product else "Aucun"
        top_category = obj.top_category.name if obj.top_category else "Aucune"
        turnover = float(obj.inventory_turnover_ratio)
        sponsored = int(obj.active_sponsored_products)
        cancelled = int(obj.cancelled_orders)
        returned = int(obj.returned_products)

        html = (
            '<div style="background-color: #fff5f7; border: 2px solid #ec4899; border-radius: 8px; padding: 15px;">'
            '<h3 style="color: #ec4899; margin-top: 0;">🛍️ Produits</h3>'
            '<table style="width: 100%; border-collapse: collapse;">'
            '<tr><td style="padding: 8px;"><strong>Best-seller:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{}</td></tr>'
            '<tr style="background-color: #fffbfc;"><td style="padding: 8px;"><strong>Catégorie top:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{}</td></tr>'
            '<tr><td style="padding: 8px;"><strong>Sponsorisés actifs:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{}</td></tr>'
            '<tr style="background-color: #fffbfc;"><td style="padding: 8px;"><strong>Rotation stock:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{:.2f}</td></tr>'
            '<tr><td style="padding: 8px;"><strong>Commandes annulées:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{}</td></tr>'
            '<tr style="background-color: #fffbfc;"><td style="padding: 8px;"><strong>Produits retournés:</strong></td>'
            '<td style="padding: 8px; text-align: right;">{}</td></tr>'
            '</table></div>'
        )
        return format_html(
            html,
            best_product,
            top_category,
            sponsored,
            turnover,
            cancelled,
            returned
        )
    card_products.short_description = '🛍️ Produits'
    
    # ===== PERMISSIONS =====
    
    def has_add_permission(self, request):
        """Les stats ne doivent pas être créées manuellement"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Les stats ne doivent pas être supprimées"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Les stats sont en lecture seule"""
        return True