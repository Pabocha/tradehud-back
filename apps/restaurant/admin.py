from django.contrib import admin
from .models import *
# Register your models here.

admin.site.register(Restaurant)
admin.site.register(RestaurantSchedule)
admin.site.register(RestaurantReview)
admin.site.register(RestaurantOrder)
admin.site.register(RestaurantCategory)
admin.site.register(Meal)
admin.site.register(MenuCategory)
admin.site.register(Payment)
admin.site.register(OrderItem)
admin.site.register(RestaurantSettings)
admin.site.register(MealReview)