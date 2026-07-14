# CAHIER DES CHARGES — E-Commerce Multi-Vendeurs

> Document généré automatiquement depuis le code source le 14/07/2026

---

## 1. VUE D'ENSEMBLE

### 1.1 Objectif

Application web multi-vendeurs (marketplace) permettant à des utilisateurs d'acheter et vendre des produits, gérer des restaurants, communiquer en temps réel via chat, et suivre les commandes avec un système de devis (quote) et de coupons promotionnels.

### 1.2 Stack technique

| Composant | Technologie |
|-----------|-------------|
| Backend | Django 5.2.7, Django REST Framework, SimpleJWT |
| Base de données | PostgreSQL |
| Temps réel | Django Channels (WebSockets), Redis (channel layer) |
| Tâches async | Celery + Redis (beat schedule) |
| Recherche | Elasticsearch 8.x (elasticsearch-dsl) |
| Notifications push | FCM-Django + Firebase |
| Auth | JWT (access + refresh tokens, cookie HttpOnly) |

**Autres librairies** : django-mptt (arbres), django-money (MoneyField), django-taggit, django-countries, Pillow, shortuuid

### 1.3 Architecture des routes

Toutes les API passent par `/api/v1/` :

```
/api/v1/auth/                  (JWT login, refresh, verify, logout, check)
/api/v1/accounts/              (Users, sellers, addresses, follows, settings)
/api/v1/notifications/         (Notifications)
/api/v1/cart/                  (Panier)
/api/v1/comments/              (Avis produits et boutiques)
/api/v1/products/              (Produits, variantes, promotions, recherche)
/api/v1/shop/                  (Boutiques, statistiques)
/api/v1/categories/            (Categories MPTT)
/api/v1/restaurant/            (Restaurants, menus, commandes)
/api/v1/orders/                (Commandes, devis/quotes)
/api/v1/messaging/             (Chat temps réel)
```

### 1.4 Apps non routées dans api_v1.py

| App | État |
|-----|------|
| **favorites** | Models + views + urls existent, PAS inclus dans api_v1.py |
| **payments** | Model + list view existent, PAS inclus dans api_v1.py |
| **marketing** | Models + vues existent, PAS inclus dans api_v1.py |
| **contacts** | Commentée dans api_v1.py, aucun view/serializer/URL |

---

## 2. DESCRIPTION DES APPS

---

### 2.1 ACCOUNTS — Gestion des utilisateurs

**Modèles**

#### CustomUser (table : `utilisateur`)

| Champ | Type | Détails |
|-------|------|---------|
| email | EmailField, unique | USERNAME_FIELD |
| first_name, last_name | CharField(255) | |
| phone_number | CharField(30), unique | |
| type_user | CharField | `acheteur`, `vendeur`, `deux` |
| country | CountryField | |
| gender | CharField(1) | `M`, `F` |
| date_of_birth | DateField, nullable | |
| full_address, city | CharField(255), nullable | |
| has_seller_account | BooleanField | |
| is_active, is_staff, is_superuser | BooleanField | |
| date_joined | DateTimeField(auto_now_add) | |
| deleted_at | DateTimeField, nullable | Soft delete timestamp |

#### Address

| Champ | Type | Détails |
|-------|------|---------|
| customer | FK → CustomUser | related_name=`addresses` |
| address_type | CharField | `shipping`, `billing`, `both` |
| first_name, last_name, phone_number | CharField | |
| street_address, city, state_region, postal_code | CharField/TextField | |
| country | CountryField | |
| is_default | BooleanField | |

#### SellerAccount

| Champ | Type | Détails |
|-------|------|---------|
| user | OneToOne → CustomUser | related_name=`seller_account` |
| company_name, phone_number, email_contact | CharField/EmailField | |
| address | CharField(255), nullable | |
| license_number | CharField(100), nullable | |
| id_document, proof_of_address_document | ImageField, nullable | |
| bank_account, tax_id, vat_number | CharField(100), nullable | |
| status | CharField | `pending`, `active`, `suspended` |
| date_created | DateTimeField(auto_now_add) | |

#### UserSettings

| Champ | Type | Détails |
|-------|------|---------|
| user | OneToOne → CustomUser | |
| language | CharField(10), default `fr` | |
| currency | CharField(5) | `XOF`, `XAF`, `USD`, `EUR`, `GNF` |
| country | CountryField | |
| notifications_enabled | BooleanField | |
| notification_preferences | JSONField | `all`, `order`, `promo`, `message`, `delivery`, `product`, `support`, `account` |

#### Endpoints

| Méthode | Path | Action | Permissions |
|---------|------|--------|-------------|
| POST | `/auth/token/` | Login JWT | AllowAny (throttle) |
| POST | `/auth/token/refresh/` | Refresh JWT (cookie) | AllowAny |
| POST | `/auth/token/verify/` | Verify JWT | AllowAny |
| GET | `/auth/check/` | Check auth status | AllowAny |
| POST | `/auth/logout/` | Logout + blacklist | AllowAny |
| GET/POST/PUT/PATCH/DELETE | `/accounts/users/` | CRUD utilisateurs | Auth |
| GET/PATCH | `/accounts/users/me/` | Mon profil | IsAuthenticated |
| POST | `/accounts/users/me/photo/` | Upload photo profil | IsAuthenticated |
| POST | `/accounts/users/change_password/` | Changer mot de passe | IsAuthenticated |
| CRUD | `/accounts/addresses/` | Adresses | IsAuthenticated |
| CRUD | `/accounts/sellers/` | Comptes vendeurs | IsAuthenticated |
| POST | `/accounts/sellers/create_seller_account/` | Créer compte vendeur | IsAuthenticated |
| POST | `/accounts/shops/{pk}/toggle-follow/` | Suivre/ne plus suivre | IsAuthenticated |
| GET | `/accounts/shops/followed/` | Boutiques suivies | IsAuthenticated |
| GET/POST | `/accounts/user-settings/` | Paramètres | IsAuthenticated |
| POST | `/accounts/update-user-settings/` | Modifier paramètres | IsAuthenticated |
| GET | `/accounts/unread-counters/` | Compteurs non-lus | IsAuthenticated |
| POST | `/accounts/account/deactivate/` | Désactiver compte | IsAuthenticated |
| POST | `/accounts/account/request-delete/` | Demande suppression RGPD | IsAuthenticated |
| POST | `/accounts/password/forgot/` | Envoyer OTP reset | AllowAny (throttle) |
| POST | `/accounts/password/verify-otp/` | Vérifier OTP | AllowAny (throttle) |
| POST | `/accounts/password/reset/` | Réinitialiser mot de passe | AllowAny (throttle) |

#### Celery Tasks

- `cleanup_old_otps` : Supprime les OTP expirés
- `cleanup_deleted_accounts` : Supprime les comptes anonymisés après délai

---

### 2.2 PRODUCTS — Catalogue de produits

**Modèles**

#### Products

| Champ | Type | Détails |
|-------|------|---------|
| name | CharField(255) | |
| base_price | MoneyField (XOF) | Prix de base |
| brand | CharField(255), nullable | |
| shop | FK → Shops | related_name=`product` |
| category | FK → Categories, nullable | |
| description | TextField | |
| image | ImageField | Image principale |
| stock_quantity | PositiveIntegerField, nullable | Stock global (sans variantes) |
| status | CharField | `available`, `unavailable`, `pre_order` |
| country_origin | CountryField, nullable | |
| is_active | BooleanField | |
| is_sponsored | BooleanField | |
| sponsored_start, sponsored_end | DateTimeField, nullable | Période de sponsoring |
| views_count | PositiveIntegerField | |
| numbers_reviews, average_rating | | Agrégés par signaux |
| tags | TaggableManager | Tags libres |
| attribute | JSONField | Attributs dynamiques |
| variant_structure | JSONField (list) | Ordre des attributs de variantes |
| min_order_quantity | PositiveIntegerField(1) | |

#### ProductVariant

| Champ | Type | Détails |
|-------|------|---------|
| product | FK → Products | related_name=`variants` |
| sku | CharField(100), unique, nullable | Auto-généré si vide |
| weight | DecimalField, nullable | |
| price_override | MoneyField, nullable | Prix spécifique variante |
| stock_quantity | PositiveIntegerField(1) | |
| custom_attributes | JSONField | Attributs personnalisés |
| attributes | M2M → AttributeValue | Attributs officiels |

#### Attribute / AttributeValue

| Champ | Type | Détails |
|-------|------|---------|
| name / code | CharField(50) / SlugField, unique | ex: Couleur / color |
| is_variant | BooleanField | Utilisé pour les variantes |
| value / code | CharField / SlugField | ex: Rouge / red |
| hex_color | CharField(7), nullable | Pour les couleurs |

#### ProductPriceTier

| Champ | Type | Détails |
|-------|------|---------|
| product | FK → Products | related_name=`price_tiers` |
| min_quantity, max_quantity | PositiveIntegerField | |
| price | MoneyField | |

#### ProductPromotion

| Champ | Type | Détails |
|-------|------|---------|
| product | FK → Products | related_name=`promotions` |
| promo_price | MoneyField | |
| start_at, end_at | DateTimeField | |
| is_active | BooleanField | |

#### Endpoints

| Méthode | Path | Action | Permissions |
|---------|------|--------|-------------|
| CRUD | `/products/` | CRUD produits | AuthOrReadOnly |
| GET | `/products/{pk}/` | Détail produit | AllowAny |
| POST/PUT | `/products/{pk}/variants/` | Créer/Remplacer variantes | AuthOrReadOnly |
| GET | `/products/{pk}/variants-list/` | Arbre de variantes | AllowAny |
| POST | `/products/{pk}/sponsor/` | Sponsoriser | AuthOrReadOnly |
| GET/POST/PATCH/DELETE | `/products/{pk}/price-tiers/` | Paliers de prix | AuthOrReadOnly |
| GET/POST/PATCH/DELETE | `/products/{pk}/promotions/` | Promotions produit | AuthOrReadOnly |
| POST | `/products/{pk}/view/` | Incrémenter vues | AllowAny |
| GET | `/products/search/` | Recherche Elasticsearch | AllowAny |
| GET | `/products/search/autocomplete/` | Autocomplete | AllowAny |
| GET | `/products/recommendations/` | Recommandations | AllowAny |
| GET | `/products/promotions/` | Produits en promo active | AllowAny |
| GET | `/products/categories/{category_id}/` | Par catégorie (+ descendants) | AllowAny |
| CRUD | `/products/{pk}/gallery/` | Galerie images | AuthOrReadOnly |
| CRUD | `/products/recently-viewed/` | Récemment vus | AllowAny |
| GET | `/products/recently-viewed/most_viewed/` | Top 10 vus | AllowAny |

**Filtres disponibles** : `tab` (new/promo/sponsored/favorite/cart/available), `search`, `country`, `category`, `min_price`, `max_price`, `ordering`, `page`

---

### 2.3 SHOPS — Boutiques vendeurs

**Modèles**

#### Shops

| Champ | Type | Détails |
|-------|------|---------|
| name | CharField(255) | |
| owner | FK → SellerAccount | related_name=`shops` |
| email_contact | EmailField, unique | |
| description | TextField, nullable | |
| latitude, longitude | FloatField, nullable | |
| phone_number, address | CharField/TextField | |
| logo | ImageField, nullable | |
| categories | M2M → Categories | |
| status | CharField | `active`, `suspended`, `inactive` |
| is_deleted | BooleanField | Soft delete |
| payment_method | M2M → PaymentMethod | |
| total_products, total_orders | IntegerField | |
| total_follow, number_sale | PositiveSmallIntegerField | |
| average_rating, number_of_reviews | FloatField/PositiveIntegerField | |
| is_top_seller, is_verified | BooleanField | |
| delivery_conditions, delivery_time_estimate | TextField/CharField | |
| free_shipping | BooleanField | |
| return_policy | TextField, nullable | |

#### ShopStatistics (stats journalières)

| Champ | Type |
|-------|------|
| total_orders, total_revenue, products_sold, average_order_value | Ventes |
| new_followers, new_customers, repeat_customers | Engagement |
| visits, conversion_rate | Trafic |
| cancelled_orders, returned_products | Retours |
| best_selling_product, top_category | Top products |
| shop_average_rating, shop_number_of_reviews | Satisfaction |
| products_low_stock, products_out_of_stock | Inventaire |

#### Endpoints

| Méthode | Path | Action | Permissions |
|---------|------|--------|-------------|
| CRUD | `/shop/` | Mes boutiques | AuthOrReadOnly |
| GET | `/shop/shop-list/` | Liste publique | AllowAny |
| GET | `/shop/{pk}/public-detail/` | Détail public | AllowAny |
| PATCH | `/shop/{pk}/update-fields/` | Modifier boutique | IsAuthenticated |
| GET | `/shop/{pk}/is-followed/` | Statut follow | IsAuthenticated |
| GET | `/shop/statistics/` | Stats journalières | AuthOrReadOnly |
| POST | `/shop/statistics/recalculate-today/` | Recalculer aujourd'hui | IsAuthenticated |

---

### 2.4 CATEGORIES — Catégories en arbre

| Champ | Type | Détails |
|-------|------|---------|
| name | CharField(255) | |
| description, image | TextField, ImageField | |
| icon_name, icon_color, bg_icon | CharField, nullable | Icônes Lucide |
| parent_category | TreeForeignKey → self | MPTT |
| fields_config | JSONField | Config dynamique |
| is_active | BooleanField | |
| category_type | CharField | `product`, `shop` |

**Endpoints** : `GET /categories/all/`, `GET /categories/hierarchy/`, `GET /categories/attributes/`

---

### 2.5 ORDERS — Commandes & Devis

**Modèles**

#### Orders

| Champ | Type | Détails |
|-------|------|---------|
| customer | FK → User | |
| order_date | DateTimeField(auto_now_add) | |
| origin_address | FK → Address, nullable | Adresse source (copiée à la création) |
| shipping_first_name/last_name/phone/street/city/state/postal/country | | Snapshot figé |
| shipping_method | CharField | `standard`, `express`, `pickup` |
| carrier_name, tracking_number, tracking_url | | Suivi transporteur |
| total_amount, delivery_cost | MoneyField (XOF) | |
| status | CharField | `pending`, `processing`, `shipped`, `in_transit`, `delivered`, `cancelled` |
| payment_method | M2M → PaymentMethod | |
| payment_status | CharField | `pending`, `paid`, `failed`, `refunded` |
| order_number | CharField, unique | Auto-généré (UUID short) |
| discount, applied_coupon, applied_coupon_code | | Coupons |
| customer_note | TextField, nullable | |
| shipping_date, estimated_delivery_date | DateTimeField, nullable | |

#### OrderLine

| Champ | Type | Détails |
|-------|------|---------|
| order | FK → Orders | related_name=`order_lines` |
| variant | FK → ProductVariant, nullable | |
| product | FK → Products, nullable | |
| shop | FK → Shops, nullable | |
| quantity | PositiveIntegerField | |
| unit_price | DecimalField | Prix figé |

#### Quote (Devis/Négociation)

| Champ | Type | Détails |
|-------|------|---------|
| user | FK → User | Client |
| shop | FK → Shops | Vendeur |
| status | CharField | `draft`, `sent`, `countered`, `accepted`, `rejected`, `expired`, `converted` |
| expires_at | DateTimeField | |
| payment_link_token | CharField(128), unique, nullable | |
| converted_order | FK → Orders, nullable | |

#### Endpoints

| Méthode | Path | Action |
|---------|------|--------|
| POST | `/orders/create/` | Créer commande |
| GET | `/orders/my-orders/` | Mes commandes (client) |
| GET | `/orders/shop-orders/` | Commandes boutiques (vendeur) |
| POST | `/orders/{pk}/pay/` | Payer commande |
| PATCH | `/orders/{pk}/payment-status/` | Modifier statut paiement |
| CRUD | `/orders/quotes/client/` | Devis (client) |
| POST | `/orders/quotes/client/{pk}/accept/` | Accepter devis |
| POST | `/orders/quotes/client/{pk}/counter/` | Contre-proposition |
| POST | `/orders/quotes/client/{pk}/checkout/` | Convertir en commande |
| POST | `/orders/quotes/client/pay/{token}/` | Payer par lien |
| GET | `/orders/quotes/seller/list/` | Devis (vendeur) |
| POST | `/orders/quotes/seller/{pk}/send/` | Envoyer devis |
| POST | `/orders/quotes/seller/{pk}/payment-link/` | Générer lien paiement |

---

### 2.6 CARTS — Panier

| Méthode | Path | Action |
|---------|------|--------|
| CRUD | `/cart/` | CRUD panier |
| POST | `/cart/add/` | Ajouter au panier |
| PATCH | `/cart/{pk}/change-quantity/` | Changer quantité |
| DELETE | `/cart/clear/` | Vider panier |
| DELETE | `/cart/remove-product/` | Supprimer produit |
| POST | `/cart/preview-coupon/` | Aperçu coupon |

---

### 2.7 COMMENTS — Avis & Notes

| Méthode | Path | Action |
|---------|------|--------|
| CRUD | `/comments/products/` | Avis produits |
| GET | `/comments/products/my-reviews/` | Mes avis produits |
| CRUD | `/comments/shops/` | Avis boutiques |
| GET | `/comments/shops/my-shops-reviews/` | Avis de mes boutiques (vendeur) |

**Signaux** : Recalcul automatique `average_rating` / `numbers_reviews` sur produit et boutique.

---

### 2.8 CHAT — Messagerie temps réel

**Modèles** : `ChatRoom` (DM, SUPPORT), `ChatMessage` (text, image, product)

**WebSocket** : `ws/users/{userId}/chat/` — actions : `message`, `typing`, `stop_typing`, `onlineUser`

**Endpoints REST** :
- `GET/POST /messaging/user/chats` — Créer/retrouver room DM
- `GET /messaging/user/conversations` — Conversations avec détails
- `GET /messaging/chats/{roomId}/messages` — Messages (pagination)
- `POST /messaging/chats/{roomId}/messages/read` — Marquer comme lu

---

### 2.9 RESTAURANT — Livraison de repas

Système complet indépendant : Restaurant, MenuCategory, Meal, RestaurantOrder, OrderItem, Payment, RestaurantReview, MealReview, RestaurantSchedule, RestaurantSettings

**Endpoints** : CRUD restaurants, menus, plats, commandes restaurant, avis, statistiques avancées (sales_chart, peak_hours, top_meals, etc.)

---

### 2.10 COUPONS — Codes promo

| Champ | Type | Détails |
|-------|------|---------|
| code | CharField(50), unique | Code promo |
| discount_type | CharField | `fixed`, `percent`, `shipping` |
| discount_value | DecimalField | |
| scope | CharField | `cart`, `product`, `category`, `shop`, `shipping` |
| audience | CharField | `public`, `targeted`, `single` |
| max_uses, uses | PositiveIntegerField | |
| start_date, end_date | DateTimeField | |

**Service** : `apply_coupon()` — validation + calcul de réduction

**Note** : PAS d'endpoint REST exposé dans `api_v1.py`. Utilisé via `carts/preview_coupon`.

---

### 2.11 NOTIFICATIONS — Système de notifications

| Méthode | Path | Action |
|---------|------|--------|
| CRUD | `/notifications/` | CRUD notifications |
| PATCH | `/notifications/{pk}/mark-read/` | Marquer comme lu |
| POST | `/notifications/mark-all-read/` | Tout marquer lu |
| POST | `/notifications/bulk-delete/` | Suppression multiple |

**Celery Tasks** : notifs order, delivery, message, payment (18 tâches définies)

---

### 2.12 FAVORITES — Produits favoris

| Méthode | Path | Action |
|---------|------|--------|
| CRUD | `/favorites/` | Mes favoris |
| GET | `/favorites/is_favorite/?product_id=` | Vérifier si favori |
| POST | `/favorites/toggle/` | Toggle favori |

**Note** : PAS inclus dans `api_v1.py`.

---

### 2.13 MARKETING — Banners & Annonces

Models : `Announcement`, `Banner` (slider, slidebanner, popup, sidebar)

**Note** : PAS inclus dans `api_v1.py`. Aucun endpoint REST actif.

---

### 2.14 PAYMENTS — Méthodes de paiement

Model : `PaymentMethod` (value, name, image)

**Note** : PAS inclus dans `api_v1.py`. Référencé par `Orders.payment_method` et `Shops.payment_method`.

---

## 3. BUGS IDENTIFIÉS

| # | Fichier | Bug |
|---|---------|-----|
| 1 | `products/models.py` | `get_unit_price()` défini 2 fois — la 1ère (promo+tiers) est écrasée par la 2ème |
| 2 | `shops/signals.py:50` | `lignecommande` n'existe pas → devrait être `order_lines` |
| 3 | `orders/views.py:234,265,270` | `lignes_commande__shop_id` → devrait être `order_lines__shop_id` |
| 4 | `comments/views.py:107` | `order.lignes_commande` → devrait être `order.order_lines` |
| 5 | `notifications/tasks.py` (×5) | `order.lignes_commande` → devrait être `order.order_lines` |
| 6 | `restaurant/views.py:326` | `RestaurantDeliverySettingsSerializer` non importé |
| 7 | `restaurant/models.py:74` | `models.Count` utilisé sans import local |
| 8 | `restaurant/models.py` | Champs `notify_*` dupliqués entre `Restaurant` et `RestaurantSettings` |

---

## 4. LACUNES FONCTIONNELLES

### Priorité Haute

| Manque | Impact |
|--------|--------|
| Pas d'intégration paiement réel (Wave, Orange Money, Stripe...) | Le paiement est simulé (statut forcé à "paid") |
| Favorites, Payments, Coupons, Marketing pas routés dans api_v1.py | Fonctionnalités developpées mais inaccessibles |
| Pas de tests automatisés | Régression non détectée, maintenance difficile |


### Priorité Moyenne

| Manque | Impact |
|--------|--------|
| Pas de gestion des retours/remboursements | Pas de processus return, tâches de notif orphelines |
| Pas de calcul automatique des frais de port | Frais fixes uniquement |
| Pas d'assignation de livreur (restaurant) | Pas de suivi en temps réel de la livraison |
| Pas d'estimation de livraison dynamique | `estimated_delivery_time` est manuel |

### Priorité Basse

| Manque | Impact |
|--------|--------|
| Pas d'inventaire avancé (mouvements de stock, alertes) | Gestion basique via `stock_quantity` brut |
| Pas de promotion globale (vente flash, Black Friday) | Promotions uniquement au niveau produit |
| Pas de système de comparaison de produits | |
| Pas de dashboard admin custom | Admin Django de base uniquement |
| Pas de versioning API au-delà de v1 | |

---

## 5. RELATIONS ENTRE APPS

```
CustomUser ──< SellerAccount ──< Shops ──< Products ──< ProductVariant
    │                            │           │              │
    ├──< Address ──< Orders ──< OrderLine    │              ├──< CartItem
    ├──< UserProfile              │          │              ├──< Favorites
    ├──< UserSettings             │          ├──< ProductPromotion
    ├──< ShopFollow               │          ├──< ProductPriceTier
    ├──< Notifications            │          ├──< GalerieImages
    ├──< ChatRoom (M2M)          │          └──< RecentlyViewedProduct
    ├──< ChatMessage              │
    ├──< Favorites                ├──< Categories (MPTT)
    ├──< DeletionRequest          ├──< ShopStatistics
    └──< PasswordResetOTP         └──< ShopRatings

Orders ──< CouponUsage
       ──< Ratings (via OrderLine)

Quote ──< QuoteLine

Restaurant ──< MenuCategory ──< Meal ──< MealReview
           ──< RestaurantSchedule        ──< RestaurantOrder ──< OrderItem
           ──< RestaurantReview                          ──< Payment
           ──< RestaurantSettings
```
