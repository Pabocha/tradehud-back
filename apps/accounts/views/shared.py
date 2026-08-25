from rest_framework import status, views
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.generics import GenericAPIView
from apps.accounts.serializers import (
    UserSerializer, ForgotPasswordSerializer, VerifyOTPSerializer,
    ResetPasswordSerializer,
)
from apps.accounts.models import UserSettings, DeletionRequest
from apps.accounts.utils import anonymize_user
from apps.accounts.otp_utils import (
    create_otp_for_email, send_otp_email, verify_otp,
    mark_otp_as_used, reset_user_password,
)
from apps.accounts.throttles import OTPRateThrottle
from apps.notifications.models import Notifications
from apps.chat.models import ChatMessage
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail


NOTIFICATION_PREFERENCE_KEYS = (
    "order", "promo", "message", "delivery",
    "product", "support", "account",
)


def _default_notification_preferences():
    return {
        "all": True, "order": True, "promo": True, "message": True,
        "delivery": True, "product": True, "support": True, "account": True,
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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_settings(request):
    try:
        s = UserSettings.objects.get(user=request.user)
        return Response({
            'language': s.language,
            'currency': s.currency,
            'country': s.country.code if s.country else None,
            'notifications_enabled': s.notifications_enabled,
            'notification_preferences': _normalize_notification_preferences(s.notification_preferences),
        })
    except UserSettings.DoesNotExist:
        return Response({
            'language': 'fr', 'currency': 'XOF', 'country': None,
            'notifications_enabled': True,
            'notification_preferences': _default_notification_preferences(),
        })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_user_settings(request):
    try:
        s, _ = UserSettings.objects.get_or_create(user=request.user)
        s.language = request.data.get('language', s.language)
        s.currency = request.data.get('currency', s.currency)
        if 'notifications_enabled' in request.data:
            notifications_enabled = request.data.get('notifications_enabled')
            if not isinstance(notifications_enabled, bool):
                return Response({'status': 'error', 'message': 'notifications_enabled doit etre un booleen.'}, status=400)
            s.notifications_enabled = notifications_enabled
        if 'notification_preferences' in request.data:
            raw_preferences = request.data.get('notification_preferences')
            if not isinstance(raw_preferences, dict):
                return Response({'status': 'error', 'message': 'notification_preferences doit etre un objet JSON.'}, status=400)
            allowed_keys = {"all", "update_delivery", *NOTIFICATION_PREFERENCE_KEYS}
            invalid_keys = [key for key in raw_preferences.keys() if key not in allowed_keys]
            if invalid_keys:
                return Response({'status': 'error', 'message': f'Cles invalides: {", ".join(invalid_keys)}'}, status=400)
            if "update_delivery" in raw_preferences:
                raw_preferences["delivery"] = raw_preferences.pop("update_delivery")
            invalid_types = [key for key, value in raw_preferences.items() if not isinstance(value, bool)]
            if invalid_types:
                return Response({'status': 'error', 'message': f'Les valeurs doivent etre booleennes: {", ".join(invalid_types)}'}, status=400)
            current = _normalize_notification_preferences(s.notification_preferences)
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
            s.notification_preferences = current
        country_code = request.data.get('country')
        if country_code:
            s.country = country_code
        s.save()
        return Response({
            'status': 'success',
            'language': s.language,
            'currency': s.currency,
            'country': s.country.code if s.country else None,
            'country_name': s.country.name if s.country else None,
            'notifications_enabled': s.notifications_enabled,
            'notification_preferences': _normalize_notification_preferences(s.notification_preferences),
        })
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=400)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def notification_settings(request):
    s, _ = UserSettings.objects.get_or_create(user=request.user)
    if request.method == 'GET':
        prefs = _normalize_notification_preferences(s.notification_preferences)
        if s.notification_preferences != prefs:
            s.notification_preferences = prefs
            s.save(update_fields=['notification_preferences'])
        return Response({
            'notifications_enabled': s.notifications_enabled,
            'notification_preferences': prefs,
        })
    payload = request.data if isinstance(request.data, dict) else {}
    if 'notifications_enabled' in payload:
        if not isinstance(payload['notifications_enabled'], bool):
            return Response({'detail': 'notifications_enabled doit etre un booleen.'}, status=status.HTTP_400_BAD_REQUEST)
        s.notifications_enabled = payload['notifications_enabled']
    raw_preferences = payload.get('notification_preferences')
    if raw_preferences is not None:
        if not isinstance(raw_preferences, dict):
            return Response({'detail': 'notification_preferences doit etre un objet JSON.'}, status=status.HTTP_400_BAD_REQUEST)
        allowed_keys = {"all", "update_delivery", *NOTIFICATION_PREFERENCE_KEYS}
        invalid_keys = [k for k in raw_preferences.keys() if k not in allowed_keys]
        if invalid_keys:
            return Response({'detail': f'Cles invalides: {", ".join(invalid_keys)}'}, status=status.HTTP_400_BAD_REQUEST)
        if "update_delivery" in raw_preferences:
            raw_preferences["delivery"] = raw_preferences.pop("update_delivery")
        invalid_types = [k for k, v in raw_preferences.items() if not isinstance(v, bool)]
        if invalid_types:
            return Response({'detail': f'Les valeurs doivent etre booleennes: {", ".join(invalid_types)}'}, status=status.HTTP_400_BAD_REQUEST)
        prefs = _normalize_notification_preferences(s.notification_preferences)
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
        s.notification_preferences = prefs
    s.save()
    return Response({
        'detail': 'Preferences de notification mises a jour.',
        'notifications_enabled': s.notifications_enabled,
        'notification_preferences': _normalize_notification_preferences(s.notification_preferences),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def unread_counters(request):
    notifications_count = Notifications.objects.filter(user=request.user, is_read=False).count()
    messages_count = ChatMessage.objects.filter(chat__member=request.user, is_read=False).exclude(user=request.user).distinct().count()
    return Response({'notifications_count': notifications_count, 'messages_count': messages_count})


DELETE_CONFIRMATION_DELAY_DAYS = getattr(settings, "DELETE_CONFIRMATION_DELAY_DAYS", 7)


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
    user = request.user
    try:
        existing = DeletionRequest.objects.filter(user=user, status="pending").first()
        if existing:
            return Response({"status": "pending", "message": "Une demande est déjà en cours."})
        dr = DeletionRequest.objects.create(
            user=user,
            scheduled_for=timezone.now() + timezone.timedelta(days=DELETE_CONFIRMATION_DELAY_DAYS),
        )
        confirm_url = f"{settings.FRONTEND_BASE_URL}/confirm-delete/{dr.token}"
        send_mail(
            subject="Confirmez votre demande de suppression de compte",
            message=f"Pour confirmer votre demande de suppression de compte, cliquez sur : {confirm_url}\nLe lien expirera dans {DELETE_CONFIRMATION_DELAY_DAYS} jours.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return Response({"status": "success", "message": "Email de confirmation envoyé."})
    except Exception as e:
        return Response({"status": "error", "message": str(e)}, status=400)


@api_view(['GET', 'POST'])
def confirm_delete_account(request, token):
    try:
        dr = DeletionRequest.objects.get(token=token, status="pending")
    except DeletionRequest.DoesNotExist:
        return Response({"status": "error", "message": "Token invalide ou expiré."}, status=400)
    dr.status = "confirmed"
    dr.confirmed_at = timezone.now()
    dr.processed_at = timezone.now()
    dr.status = "processed"
    dr.save()
    user = dr.user
    anonymize_user(user)
    return Response({"status": "success", "message": "Votre compte a été supprimé/anonymisé."})


class ForgotPasswordView(GenericAPIView):
    serializer_class = ForgotPasswordSerializer
    permission_classes = [AllowAny]
    throttle_classes = [OTPRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        otp_obj = create_otp_for_email(email)
        email_sent = send_otp_email(email, otp_obj.otp)
        if not email_sent:
            return Response({"detail": "Erreur lors de l'envoi de l'email. Veuillez réessayer."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({"detail": "Code OTP envoyé à votre adresse email. Valide pour 10 minutes."}, status=status.HTTP_200_OK)


class VerifyOTPView(GenericAPIView):
    serializer_class = VerifyOTPSerializer
    permission_classes = [AllowAny]
    throttle_classes = [OTPRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        otp_code = serializer.validated_data['otp']
        result = verify_otp(email, otp_code)
        if not result['valid']:
            return Response({"detail": result['message']}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Code OTP valide. Vous pouvez maintenant réinitialiser votre mot de passe."}, status=status.HTTP_200_OK)


class ResetPasswordView(GenericAPIView):
    serializer_class = ResetPasswordSerializer
    permission_classes = [AllowAny]
    throttle_classes = [OTPRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        otp_code = serializer.validated_data['otp']
        new_password = serializer.validated_data['new_password']
        result = verify_otp(email, otp_code)
        if not result['valid']:
            return Response({"detail": result['message']}, status=status.HTTP_400_BAD_REQUEST)
        otp_obj = result['otp_obj']
        reset_result = reset_user_password(email, new_password)
        if not reset_result['success']:
            return Response({"detail": reset_result['message']}, status=status.HTTP_400_BAD_REQUEST)
        mark_otp_as_used(otp_obj)
        return Response({"detail": "Mot de passe réinitialisé avec succès. Vous pouvez maintenant vous connecter."}, status=status.HTTP_200_OK)
