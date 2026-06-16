from django.db import models
from .models import Coupon
from .serializers import CouponSerializer
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.decorators import action
from rest_framework.response import Response

# Create your views here.

class CouponViewSet(viewsets.ModelViewSet):
    queryset = Coupon.objects.all()
    serializer_class = CouponSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return Coupon.objects.all().order_by('-id')

        return Coupon.objects.filter(
            models.Q(audience='public') |
            models.Q(audience='targeted', users=user) |
            models.Q(audience='single', users=user)
        ).distinct().order_by('-id')

    @action(detail=False, methods=['get'], url_path='my-coupons', permission_classes=[IsAuthenticated])
    def my_coupons(self, request):
        coupons = self.get_queryset()

        valid = []
        invalid = []

        for coupon in coupons:
            is_valid = coupon.is_valid_now()
            serialized = CouponSerializer(coupon, context={'request': request}).data
            serialized["valid"] = is_valid
            if is_valid:
                valid.append(serialized)
            else:
                invalid.append(serialized)

        return Response({
            "valid_coupons": valid,
            "invalid_coupons": invalid,
        })