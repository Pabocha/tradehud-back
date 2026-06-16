from rest_framework import serializers
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.exceptions import AuthenticationFailed
from django.db.models import Value
from django.db.models.functions import Replace
from .models import SellerAccount, ShopFollow, UserSettings
from apps.shops.models import Shops
from apps.products.models import Products
from djmoney.contrib.django_rest_framework.fields import MoneyField
from django.contrib.auth.password_validation import validate_password


User = get_user_model()

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @staticmethod
    def _normalize_phone(value: str) -> str:
        if not value:
            return ""
        normalized = value.strip()
        for token in (" ", "-", "(", ")"):
            normalized = normalized.replace(token, "")
        return normalized
    def _resolve_login_input_to_email(self, login_input: str) -> str:
        login_input = (login_input or "").strip()
        if not login_input:
            raise AuthenticationFailed("Email ou numero de telephone requis.")
        if "@" in login_input:
            return login_input.lower()
        normalized = self._normalize_phone(login_input)
        normalized_no_plus = normalized.lstrip("+")
        candidates = {login_input, normalized, normalized_no_plus, f"+{normalized_no_plus}"}
        queryset = User.objects.annotate(
            phone_normalized=Replace(
                Replace(
                    Replace(
                        Replace("phone_number", Value(" "), Value("")),
                        Value("-"), Value("")
                    ),
                    Value("("), Value("")
                ),
                Value(")"), Value("")
            )
        ).filter(phone_normalized__in=candidates)
        count = queryset.count()
        if count == 0:
            raise AuthenticationFailed("Aucun utilisateur trouve avec cet email/numero.")
        if count > 1:
            raise AuthenticationFailed("Ce numero est associe a plusieurs comptes.")
        return queryset.first().email
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        return token
    def validate(self, attrs):
        login_input = (
            self.initial_data.get("email")
            or self.initial_data.get("phone_number")
            or self.initial_data.get("phone")
            or ""
        )
        attrs[self.username_field] = self._resolve_login_input_to_email(login_input)
        data = super().validate(attrs)
        # Verifier si l'utilisateur est actif
        if not self.user.is_active:
            raise AuthenticationFailed("Ce compte est desactive. Contactez le support.")
        return data

class UserSerializer(serializers.ModelSerializer):
    photo = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=True)
    country = serializers.CharField(allow_blank=True, allow_null=True)

    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'phone_number', 
                  'gender', 'date_of_birth', 'full_address', 'city', 'postal_code', 
                  'country', 'latitude', 'longitude', 'type_user', 'is_active', 
                  'date_joined', 'photo', 'password')

    def get_photo(self, obj):
        request = self.context.get('request')
        profile = getattr(obj, 'userprofile', None)
        if not profile or not getattr(profile, 'photo', None):
            return None
        try:
            url = profile.photo.url
            return request.build_absolute_uri(url) if request else url
        except Exception:
            return None

class SellerAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerAccount
        fields = ('__all__')
        extra_kwargs = {
            'user': {'required': False, 'allow_null': True},
            'id_document': {'required': False, 'allow_null': True},
            'proof_of_address_document': {'required': False, 'allow_null': True},
        }

# class ChangePasswordSerializer(serializers.Serializer):
#     old_password = serializers.CharField(required=True)
#     new_password1 = serializers.CharField(required=True)
#     new_password2 = serializers.CharField(required=True)

#     def validate_new_password(self, value):
#         validate_password(value)
#         return value

# ðŸ”¹ Serializer simplifiÃ© pour afficher les produits
class SimpleProductSerializer(serializers.ModelSerializer):
    price = MoneyField(source='base_price', max_digits=15, decimal_places=2, read_only=True)
    second_price = serializers.SerializerMethodField()
    discount = serializers.SerializerMethodField()
    class Meta:
        model = Products
        fields = ['id', 'name', 'price', 'second_price', 'discount', 'image', 'status'] 

    def get_second_price(self, obj):
        return None

    def get_discount(self, obj):
        return None



# ðŸ”¹ Serializer principal
class ShopFollowSerializer(serializers.ModelSerializer):
    shop_detail = serializers.SerializerMethodField()

    class Meta:
        model = ShopFollow
        fields = ['id', 'shop', 'shop_detail', 'followed_at']

    def get_shop_detail(self, obj):
        request = self.context.get('request')
        products = obj.shop.product.filter(is_active=True)[:10]

        logo_url = obj.shop.logo.url if obj.shop.logo else None
        if logo_url and request:
            logo_url = request.build_absolute_uri(logo_url)

        return {
            'id': obj.shop.id,
            'name': obj.shop.name,
            'logo': logo_url,
            'status': obj.shop.status,
            'total_follow': obj.shop.total_follow,
            'products': SimpleProductSerializer(products, many=True, context={'request': request}).data
        }


# ============================================
# ðŸ” OTP Password Reset Serializers
# ============================================

class ForgotPasswordSerializer(serializers.Serializer):
    """
    SÃ©rializer pour demander un code OTP.
    Input: { "email": "user@example.com" }
    """
    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        """
        VÃ©rifie que l'email existe dans la base de donnÃ©es.
        """
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Aucun utilisateur trouvÃ© avec cet email.")
        return value


class VerifyOTPSerializer(serializers.Serializer):
    """
    SÃ©rializer pour vÃ©rifier le code OTP.
    Input: { "email": "user@example.com", "otp": "123456" }
    """
    email = serializers.EmailField(required=True)
    otp = serializers.CharField(max_length=6, min_length=4, required=True)

    def validate_email(self, value):
        """
        VÃ©rifie que l'email existe.
        """
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Aucun utilisateur trouvÃ© avec cet email.")
        return value


class ResetPasswordSerializer(serializers.Serializer):
    """
    SÃ©rializer pour rÃ©initialiser le mot de passe avec l'OTP.
    Input: { "email": "user@example.com", "otp": "123456", "new_password": "newpass123" }
    """
    email = serializers.EmailField(required=True)
    otp = serializers.CharField(max_length=6, min_length=4, required=True)
    new_password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    new_password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )

    def validate_email(self, value):
        """
        VÃ©rifie que l'email existe.
        """
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Aucun utilisateur trouvÃ© avec cet email.")
        return value

    def validate_new_password(self, value):
        """
        Valide le mot de passe selon les rÃ¨gles Django.
        """
        validate_password(value)
        return value

    def validate(self, attrs):
        """
        VÃ©rifie que les deux mots de passe correspondent.
        """
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({
                'new_password_confirm': "Les mots de passe ne correspondent pas."
            })
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    """
    SÃ©rializer pour modifier le mot de passe (utilisateur authentifiÃ©).
    Input: { "old_password": "oldpass123", "new_password": "newpass123", "new_password_confirm": "newpass123" }
    NÃ©cessite l'authentification.
    """
    old_password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    new_password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    new_password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )

    def validate_new_password(self, value):
        """
        Valide le mot de passe selon les rÃ¨gles Django.
        """
        validate_password(value)
        return value

    def validate(self, attrs):
        """
        VÃ©rifie que les deux nouveaux mots de passe correspondent.
        """
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({
                'new_password_confirm': "Les mots de passe ne correspondent pas."
            })
        return attrs


class NotificationSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSettings
        fields = ('notifications_enabled', 'notification_preferences')

