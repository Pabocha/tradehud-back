from rest_framework.throttling import SimpleRateThrottle


class OTPRateThrottle(SimpleRateThrottle):
    scope = 'otp'

    def get_cache_key(self, request, view):
        """Return a cache key for OTP throttling.

        Prefer user-scoped key when the user is authenticated, otherwise fall back to IP-based ident.
        """
        ident = self.get_ident(request)
        if request.user and getattr(request.user, 'is_authenticated', False):
            ident = f"user-{request.user.pk}"
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class LoginRateThrottle(SimpleRateThrottle):
    scope = 'login'

    def get_cache_key(self, request, view):
        """Return a cache key for login throttling (IP-based by default)."""
        ident = self.get_ident(request)
        # For login attempts, we prefer IP-based throttling to avoid allowing attackers to enumerate users
        return self.cache_format % {'scope': self.scope, 'ident': ident}