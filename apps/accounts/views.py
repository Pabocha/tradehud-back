from rest_framework import viewsets, status, views
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import *
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from .models import UserSettings, DeletionRequest, UserProfile, SellerAccount
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from .utils import anonymize_user, hard_delete_user
from .serializers import UserSerializer
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from apps.notifications.models import Notifications
from apps.chat.models import ChatMessage


# Create your views here.

NOTIFICATION_PREFERENCE_KEYS = (
    "order",
    "promo",
    "message",
    "delivery",
    "product",
    "support",
    "account",
)


def _default_notification_preferences():
    return {
        "all": True,
        "order": True,
        "promo": True,
        "message": True,
        "delivery": True,
        "product": True,
        "support": True,
        "account": True,
    }


def _normalize_notification_preferences(raw):
    prefs = _default_notification_preferences()
    if not isinstance(raw, dict):
        return prefs

    for key in ("all", *NOTIFICATION_PREFERENCE_KEYS):
        value = raw.get(key)
        if isinstance(value, bool):
            prefs[key] = value

    if prefs["all"]:
        for key in NOTIFICATION_PREFERENCE_KEYS:
            prefs[key] = True
    else:
        prefs["all"] = all(prefs[key] for key in NOTIFICATION_PREFERENCE_KEYS)
    return prefs


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    # permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Exclure l'utilisateur connecté
        return User.objects.exclude(id=self.request.user.id)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        
        # On n'oublie pas d'enlever le raise_exception=True pour passer dans le else
        if serializer.is_valid(): 
            password = serializer.validated_data.pop('password')
            user = serializer.save()
            user.set_password(password)
            user.save()
            refresh = RefreshToken.for_user(user)
            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': UserSerializer(user, context={'request': request}).data,
            }, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def get_info(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=['get', 'patch'], permission_classes=[IsAuthenticated], url_path='me')
    def me(self, request):
        if request.method == 'GET':
            serializer = self.get_serializer(request.user)
            return Response(serializer.data)

        serializer = self.get_serializer(
            request.user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated], url_path='me/photo')
    def upload_photo(self, request):
        photo = request.FILES.get('photo')
        if photo is None:
            return Response({'detail': 'photo requis'}, status=status.HTTP_400_BAD_REQUEST)
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        profile.photo = photo
        profile.save(update_fields=['photo'])
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)


    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def change_password(self, request):
        """
        POST /auth/users/change_password/
        
        Modifie le mot de passe de l'utilisateur connecté.
        
        Request Body:
            {
                "old_password": "currentPassword123",
                "new_password": "newPassword123!",
                "new_password_confirm": "newPassword123!"
            }
        
        Response:
            {
                "detail": "Mot de passe changé avec succès."
            }
        """
        serializer = ChangePasswordSerializer(data=request.data)
        user = request.user

        if serializer.is_valid():
            old_password = serializer.validated_data['old_password']
            new_password = serializer.validated_data['new_password']

            # Vérifier que l'ancien mot de passe est correct
            if not user.check_password(old_password):
                return Response(
                    {"old_password": "Le mot de passe actuel est incorrect."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Définir le nouveau mot de passe
            user.set_password(new_password)
            user.save()
            
            return Response(
                {"detail": "Mot de passe changé avec succès."},
                status=status.HTTP_200_OK
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class AddressViewSet(viewsets.ModelViewSet):
    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Address.objects.filter(customer=self.request.user)

    def perform_create(self, serializer):
        serializer.save(customer=self.request.user)

        
class SellerAccountViewSet(viewsets.ModelViewSet):
    queryset = SellerAccount.objects.all()
    serializer_class = SellerAccountSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        try:
            serializer.save(user=self.request.user)
        except IntegrityError:
            raise ValidationError({'detail': 'Un compte vendeur existe deja pour cet utilisateur.'})

    @action(detail=False, methods=['post'])
    def create_seller_account(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            try:
                serializer.save(user=request.user)
                return Response(serializer.data, status=201)
            except IntegrityError:
                return Response(
                    {'detail': 'Un compte vendeur existe deja pour cet utilisateur.'},
                    status=status.HTTP_409_CONFLICT
                )
        return Response(serializer.errors, status=400)

    @action(detail=False, methods=['get'], url_path='me')
    def me(self, request):
        try:
            seller = request.user.seller_account
            serializer = self.get_serializer(seller)
            return Response(serializer.data)
        except SellerAccount.DoesNotExist:
            return Response({'detail': 'Aucun compte vendeur.'}, status=status.HTTP_404_NOT_FOUND)
    
    
class ShopFollowViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    # 🔹 GET /shops/followed/
    @action(detail=False, methods=['get'])
    def followed(self, request):
        follows = ShopFollow.objects.filter(user=request.user)
        serializer = ShopFollowSerializer(follows, many=True, context={'request': request})
        return Response(serializer.data)

   
    # 🔄 TOGGLE: POST /shops/{pk}/toggle-follow/
    @action(detail=True, methods=['post'], url_path='toggle-follow')
    def toggle_follow(self, request, pk=None):
        shop = Shops.objects.filter(id=pk).first()
        if not shop:
            return Response({"detail": "Boutique introuvable."}, status=status.HTTP_404_NOT_FOUND)

        follow = ShopFollow.objects.filter(user=request.user, shop=shop).first()
        if follow:
            # 🔹 Désabonnement
            follow.delete()
            if shop.total_follow > 0:
                shop.total_follow -= 1
                shop.save(update_fields=['total_follow'])
            return Response({"detail": "Désabonné", "followed": False}, status=status.HTTP_200_OK)
        else:
            # 🔹 Abonnement
            ShopFollow.objects.create(user=request.user, shop=shop)
            shop.total_follow += 1
            shop.save(update_fields=['total_follow'])
            return Response({"detail": "Abonné", "followed": True}, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_settings(request):
    try:
        settings = UserSettings.objects.get(user=request.user)
        notification_preferences = _normalize_notification_preferences(
            settings.notification_preferences
        )
        return Response({
            'language': settings.language,
            'currency': settings.currency,
            'country': settings.country.code if settings.country else None,
            'notifications_enabled': settings.notifications_enabled,
            'notification_preferences': notification_preferences,
        })
    except UserSettings.DoesNotExist:
        return Response({
            'language': 'fr',
            'currency': 'XOF',
            'country': None,
            'notifications_enabled': True,
            'notification_preferences': _default_notification_preferences(),
        })
    

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def _update_user_settings_legacy(request):
    try:
        settings, created = UserSettings.objects.get_or_create(user=request.user)
        settings.language = request.data.get('language', settings.language)
        settings.currency = request.data.get('currency', settings.currency)

        # Mettre à jour le pays
        country_code = request.data.get('country')
        if country_code:
            settings.country = country_code  # CountryField accepte directement le code du pays

        settings.save()

        # 🔥 Retourner une réponse JSON sérialisable
        return Response({
            'status': 'success',
            'language': settings.language,
            'currency': settings.currency,
            'country': settings.country.code if settings.country else None,  # code ISO (ex: 'FR')
            'country_name': settings.country.name if settings.country else None  # Nom complet (ex: 'France')
        })
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=400)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_user_settings(request):
    try:
        settings, created = UserSettings.objects.get_or_create(user=request.user)
        settings.language = request.data.get('language', settings.language)
        settings.currency = request.data.get('currency', settings.currency)

        if 'notifications_enabled' in request.data:
            notifications_enabled = request.data.get('notifications_enabled')
            if not isinstance(notifications_enabled, bool):
                return Response(
                    {'status': 'error', 'message': 'notifications_enabled doit etre un booleen.'},
                    status=400
                )
            settings.notifications_enabled = notifications_enabled

        if 'notification_preferences' in request.data:
            raw_preferences = request.data.get('notification_preferences')
            if not isinstance(raw_preferences, dict):
                return Response(
                    {'status': 'error', 'message': 'notification_preferences doit etre un objet JSON.'},
                    status=400
                )

            allowed_keys = {"all", "update_delivery", *NOTIFICATION_PREFERENCE_KEYS}
            invalid_keys = [key for key in raw_preferences.keys() if key not in allowed_keys]
            if invalid_keys:
                return Response(
                    {'status': 'error', 'message': f'Cles invalides: {", ".join(invalid_keys)}'},
                    status=400
                )

            if "update_delivery" in raw_preferences:
                raw_preferences["delivery"] = raw_preferences.pop("update_delivery")

            invalid_types = [key for key, value in raw_preferences.items() if not isinstance(value, bool)]
            if invalid_types:
                return Response(
                    {'status': 'error', 'message': f'Les valeurs doivent etre booleennes: {", ".join(invalid_types)}'},
                    status=400
                )

            current = _normalize_notification_preferences(settings.notification_preferences)
            current.update(raw_preferences)

            if 'all' in raw_preferences:
                if current['all']:
                    for key in NOTIFICATION_PREFERENCE_KEYS:
                        current[key] = True
                else:
                    for key in NOTIFICATION_PREFERENCE_KEYS:
                        current[key] = False
            else:
                current['all'] = all(current[key] for key in NOTIFICATION_PREFERENCE_KEYS)

            settings.notification_preferences = current

        country_code = request.data.get('country')
        if country_code:
            settings.country = country_code

        settings.save()

        return Response({
            'status': 'success',
            'language': settings.language,
            'currency': settings.currency,
            'country': settings.country.code if settings.country else None,
            'country_name': settings.country.name if settings.country else None,
            'notifications_enabled': settings.notifications_enabled,
            'notification_preferences': _normalize_notification_preferences(settings.notification_preferences),
        })
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=400)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def notification_settings(request):
    settings, _ = UserSettings.objects.get_or_create(user=request.user)

    if request.method == 'GET':
        prefs = _normalize_notification_preferences(settings.notification_preferences)
        if settings.notification_preferences != prefs:
            settings.notification_preferences = prefs
            settings.save(update_fields=['notification_preferences'])

        return Response({
            'notifications_enabled': settings.notifications_enabled,
            'notification_preferences': prefs,
        })

    payload = request.data if isinstance(request.data, dict) else {}

    if 'notifications_enabled' in payload:
        if not isinstance(payload['notifications_enabled'], bool):
            return Response(
                {'detail': 'notifications_enabled doit etre un booleen.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        settings.notifications_enabled = payload['notifications_enabled']

    raw_preferences = payload.get('notification_preferences')
    if raw_preferences is not None:
        if not isinstance(raw_preferences, dict):
            return Response(
                {'detail': 'notification_preferences doit etre un objet JSON.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        allowed_keys = {"all", "update_delivery", *NOTIFICATION_PREFERENCE_KEYS}
        invalid_keys = [k for k in raw_preferences.keys() if k not in allowed_keys]
        if invalid_keys:
            return Response(
                {'detail': f'Cles invalides: {", ".join(invalid_keys)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if "update_delivery" in raw_preferences:
            raw_preferences["delivery"] = raw_preferences.pop("update_delivery")

        invalid_types = [k for k, v in raw_preferences.items() if not isinstance(v, bool)]
        if invalid_types:
            return Response(
                {'detail': f'Les valeurs doivent etre booleennes: {", ".join(invalid_types)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        prefs = _normalize_notification_preferences(settings.notification_preferences)
        prefs.update(raw_preferences)

        if 'all' in raw_preferences:
            if prefs['all']:
                for key in NOTIFICATION_PREFERENCE_KEYS:
                    prefs[key] = True
            else:
                for key in NOTIFICATION_PREFERENCE_KEYS:
                    prefs[key] = False
        else:
            prefs['all'] = all(prefs[key] for key in NOTIFICATION_PREFERENCE_KEYS)

        settings.notification_preferences = prefs

    settings.save()

    return Response({
        'detail': 'Preferences de notification mises a jour.',
        'notifications_enabled': settings.notifications_enabled,
        'notification_preferences': _normalize_notification_preferences(settings.notification_preferences),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def unread_counters(request):

    notifications_count = Notifications.objects.filter(
        user=request.user,
        is_read=False
    ).count()

    messages_count = ChatMessage.objects.filter(
        chat__member=request.user,
        is_read=False
    ).exclude(user=request.user).distinct().count()

    return Response({
        'notifications_count': notifications_count,
        'messages_count': messages_count,
    })


DELETE_CONFIRMATION_DELAY_DAYS = getattr(settings, "DELETE_CONFIRMATION_DELAY_DAYS", 7)  # ex: 7 jours

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def deactivate_account(request):
    user = request.user
    try:
        user.is_active = False
        user.deleted_at = timezone.now()
        user.save()
        return Response({"status": "success", "message": "Compte désactivé."}, status=200)
    except Exception as e:
        return Response({"status": "error", "message": str(e)}, status=400)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def request_delete_account(request):
    """
    L'utilisateur demande la suppression RGPD.
    - créer une DeletionRequest (pending)
    - envoyer email avec lien de confirmation (token)
    """
    user = request.user
    try:
        # si une requête pendante existe, retourner info
        existing = DeletionRequest.objects.filter(user=user, status="pending").first()
        if existing:
            return Response({"status": "pending", "message": "Une demande est déjà en cours."})

        dr = DeletionRequest.objects.create(
            user=user,
            scheduled_for=timezone.now() + timezone.timedelta(days=DELETE_CONFIRMATION_DELAY_DAYS)
        )

        # envoyer email avec lien de confirmation
        confirm_url = f"{settings.FRONTEND_BASE_URL}/confirm-delete/{dr.token}"  # frontend page
        # ou API endpoint direct :
        api_confirm_url = f"{settings.BACKEND_BASE_URL}/api/account/confirm-delete/{dr.token}/"

        send_mail(
            subject="Confirmez votre demande de suppression de compte",
            message=f"Pour confirmer votre demande de suppression de compte, cliquez sur : {confirm_url}\n" \
                    f"Le lien expirera dans {DELETE_CONFIRMATION_DELAY_DAYS} jours.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

        return Response({"status": "success", "message": "Email de confirmation envoyé."})
    except Exception as e:
        return Response({"status": "error", "message": str(e)}, status=400)


@api_view(['GET', 'POST'])
def confirm_delete_account(request, token):
    """
    Confirme la requête (utilisateur clique le lien dans l'email).
    On marque la request comme 'confirmed' et on effectue la suppression
    soit immédiatement, soit après un délai, selon ta politique.
    """
    try:
        dr = DeletionRequest.objects.get(token=token, status="pending")
    except DeletionRequest.DoesNotExist:
        return Response({"status": "error", "message": "Token invalide ou expiré."}, status=400)

    # marque confirmée
    dr.status = "confirmed"
    dr.confirmed_at = timezone.now()
    # planifier la processing immédiate ou différée
    # ici : on process tout de suite — si tu veux délai, laisse processed_at vide et un job fera la purge après scheduled_for
    dr.processed_at = timezone.now()
    dr.status = "processed"
    dr.save()

    # Exécuter l'anonymisation / suppression définitive
    user = dr.user
    # tu peux choisir anonymize_user(user) ou hard_delete_user(user)
    anonymize_user(user)  # recommandé : anonymisation + disable compte
    # hard_delete_user(user)  # si tu veux supprimer tout de suite (attention aux FK)

    return Response({"status": "success", "message": "Votre compte a été supprimé/anonymisé."})


# ============================================
# 🔐 OTP Password Reset Views
# ============================================

from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny
from .otp_utils import (
    create_otp_for_email,
    send_otp_email,
    verify_otp,
    mark_otp_as_used,
    reset_user_password
)


from .throttles import OTPRateThrottle


class ForgotPasswordView(GenericAPIView):
    """
    POST /auth/password/forgot/
    
    Demande un code OTP pour réinitialiser le mot de passe.
    
    Request Body:
        {
            "email": "user@example.com"
        }
    
    Response:
        {
            "detail": "OTP sent to your email"
        }
    """
    serializer_class = ForgotPasswordSerializer
    permission_classes = [AllowAny]
    throttle_classes = [OTPRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        
        # Créer un nouvel OTP
        otp_obj = create_otp_for_email(email)
        
        # Envoyer l'email
        email_sent = send_otp_email(email, otp_obj.otp)
        
        if not email_sent:
            return Response(
                {"detail": "Erreur lors de l'envoi de l'email. Veuillez réessayer."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        return Response(
            {"detail": "Code OTP envoyé à votre adresse email. Valide pour 10 minutes."},
            status=status.HTTP_200_OK
        )


class VerifyOTPView(GenericAPIView):
    """
    POST /auth/password/verify-otp/
    
    Vérifie le code OTP fourni par l'utilisateur.
    
    Request Body:
        {
            "email": "user@example.com",
            "otp": "123456"
        }
    
    Response:
        {
            "detail": "OTP verified successfully"
        }
    """
    serializer_class = VerifyOTPSerializer
    permission_classes = [AllowAny]
    throttle_classes = [OTPRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        otp_code = serializer.validated_data['otp']
        
        # Vérifier l'OTP
        result = verify_otp(email, otp_code)
        
        if not result['valid']:
            return Response(
                {"detail": result['message']},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(
            {"detail": "Code OTP valide. Vous pouvez maintenant réinitialiser votre mot de passe."},
            status=status.HTTP_200_OK
        )


class ResetPasswordView(GenericAPIView):
    """
    POST /auth/password/reset/
    
    Réinitialise le mot de passe de l'utilisateur avec l'OTP.
    
    Request Body:
        {
            "email": "user@example.com",
            "otp": "123456",
            "new_password": "newPassword123!",
            "new_password_confirm": "newPassword123!"
        }
    
    Response:
        {
            "detail": "Password updated successfully"
        }
    """
    serializer_class = ResetPasswordSerializer
    permission_classes = [AllowAny]
    throttle_classes = [OTPRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        otp_code = serializer.validated_data['otp']
        new_password = serializer.validated_data['new_password']
        
        # Vérifier l'OTP
        result = verify_otp(email, otp_code)
        
        if not result['valid']:
            return Response(
                {"detail": result['message']},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Récupérer l'objet OTP pour le marquer comme utilisé
        otp_obj = result['otp_obj']
        
        # Réinitialiser le mot de passe
        reset_result = reset_user_password(email, new_password)
        
        if not reset_result['success']:
            return Response(
                {"detail": reset_result['message']},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Marquer l'OTP comme utilisé
        mark_otp_as_used(otp_obj)
        
        return Response(
            {"detail": "Mot de passe réinitialisé avec succès. Vous pouvez maintenant vous connecter."},
            status=status.HTTP_200_OK
        )

