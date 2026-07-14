from rest_framework import status, views
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from .serializers import MyTokenObtainPairSerializer, UserSerializer
from .throttles import LoginRateThrottle


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
    throttle_classes = [LoginRateThrottle]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            access = response.data.get('access')
            refresh = response.data.get('refresh')

            if access:
                User = get_user_model()
                try:
                    token_obj = AccessToken(access)
                    user_id = token_obj['user_id']
                    user = User.objects.get(id=user_id)

                    user.last_login = timezone.now()
                    user.save(update_fields=['last_login'])

                    response.data['user'] = UserSerializer(user).data
                except Exception:
                    pass

            if refresh:
                response.set_cookie(
                    key=settings.REFRESH_TOKEN_COOKIE_NAME,
                    value=refresh,
                    max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
                    path=settings.REFRESH_TOKEN_COOKIE_PATH,
                    secure=settings.REFRESH_TOKEN_COOKIE_SECURE,
                    httponly=settings.REFRESH_TOKEN_COOKIE_HTTPONLY,
                    samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,
                )
                del response.data['refresh']

        return response


class CookieTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get(settings.REFRESH_TOKEN_COOKIE_NAME)

        if not refresh_token:
            return Response(
                {"error": "Refresh token manquant ou expiré"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        request.data['refresh'] = refresh_token
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            new_refresh = response.data.get('refresh')
            if new_refresh:
                response.set_cookie(
                    key=settings.REFRESH_TOKEN_COOKIE_NAME,
                    value=new_refresh,
                    max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
                    path=settings.REFRESH_TOKEN_COOKIE_PATH,
                    secure=settings.REFRESH_TOKEN_COOKIE_SECURE,
                    httponly=settings.REFRESH_TOKEN_COOKIE_HTTPONLY,
                    samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,
                )
                del response.data['refresh']
        else:
            response.delete_cookie(settings.REFRESH_TOKEN_COOKIE_NAME)

        return response


class LogoutView(views.APIView):
    def post(self, request):
        refresh_token = request.data.get("refresh_token") or request.COOKIES.get(settings.REFRESH_TOKEN_COOKIE_NAME)

        if not refresh_token:
            response = Response({"message": "Déconnexion réussie"}, status=status.HTTP_205_RESET_CONTENT)
            response.delete_cookie(settings.REFRESH_TOKEN_COOKIE_NAME)
            return response

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            pass

        response = Response({"message": "Déconnexion réussie"}, status=status.HTTP_205_RESET_CONTENT)
        response.delete_cookie(settings.REFRESH_TOKEN_COOKIE_NAME)
        return response


class CheckAuthView(views.APIView):
    permission_classes = []

    def get(self, request):
        refresh_token = request.COOKIES.get(settings.REFRESH_TOKEN_COOKIE_NAME)

        if not refresh_token:
            return Response({"authenticated": False}, status=status.HTTP_200_OK)

        try:
            token = RefreshToken(refresh_token)
            user_id = token['user_id']
            User = get_user_model()
            user = User.objects.get(id=user_id, is_active=True)

            return Response({
                "authenticated": True,
                "user": UserSerializer(user).data,
            }, status=status.HTTP_200_OK)
        except Exception:
            return Response({"authenticated": False}, status=status.HTTP_200_OK)
