from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import CategoriesView, CategoryHierarchyView, CategoryAttributeViewSet

app_name = 'categories'

router = DefaultRouter()

# router.register('', CategoryViewSet, basename='category-field')

urlpatterns = [
    path('attributes/', CategoryAttributeViewSet.as_view({'get': 'list'}), name='category-attributes'),
    path('', include(router.urls)),
    path('all/', CategoriesView.as_view(), name='categories'),
    path('hierarchy/', CategoryHierarchyView.as_view(), name='category-hierarchy'),
]