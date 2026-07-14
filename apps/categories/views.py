from rest_framework.response import Response
from rest_framework.generics import GenericAPIView, ListAPIView
from .serializers import CategoriesSerializer, CategoryHierarchySerializer, CategorySerializer, CategoryAttributeSerializer
from rest_framework import viewsets
from rest_framework.decorators import action
from django.db.models import Count
from .models import Categories, CategoryAttribute

# Create your views here.
class CategoriesView(GenericAPIView):
    def get(self, request, *args, **kwargs):
        categories = Categories.objects.filter(
            is_active=True,
            category_type="product"
        ).annotate(
            has_children=Count('children')
        ).filter(
            has_children=0
        )

        serializer = CategoriesSerializer(categories, many=True, context={'request': request})
        return Response(serializer.data)


class IntermediateCategoryView(ListAPIView):
    serializer_class = CategorySerializer

    def get_queryset(self):
        queryset = Categories.objects.filter(
            parent_category__isnull=False,
            children__isnull=False,
            is_active=True,
            category_type="product"
        ).distinct()

        # Affiche les données dans la console du serveur
        print("Résultat de la requête IntermediateCategoryView:")
        for item in queryset:
            print(f" - {item}")

        return queryset

class CategoryHierarchyView(GenericAPIView):
    def get(self, request):
        category_type = request.query_params.get('type', 'shop')  # 'shop' par défaut
        parents = Categories.objects.filter(
            parent_category__isnull=True,
            is_active=True,
            category_type=category_type
        )
        serializer = CategoryHierarchySerializer(parents, many=True, context={'request': request})
        return Response(serializer.data)
    
# class CategoryViewSet(viewsets.ModelViewSet):
#     queryset = Categories.objects.all()
#     serializer_class = CategorySerializer

#     @action(detail=True, methods=['get'])
#     def fields(self, request, pk=None):
#         category = self.get_object()
#         fields = category.fields.all()
#         serializer = CategoryFieldSerializer(fields, many=True)
#         return Response(serializer.data)

class CategoryAttributeViewSet(viewsets.ModelViewSet):
    queryset = CategoryAttribute.objects.all()
    serializer_class = CategoryAttributeSerializer

    # Filtrage des champs d'une ou des catégories spécifiques
    def get_queryset(self):
        queryset = super().get_queryset()
        category_id = self.request.query_params.get('category')
        if category_id:
            queryset = queryset.filter(category__id=category_id)
        return queryset
    