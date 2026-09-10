from .models import SystemSetting


class DynamicSessionExpiryMiddleware:
    """Apply the admin-configured idle session timeout to authenticated users."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(request, 'user', None) and request.user.is_authenticated:
            try:
                timeout = SystemSetting.get_solo().session_timeout_minutes * 60
                request.session.set_expiry(timeout)
            except Exception:
                # Never break authentication because settings are unavailable during migration/startup.
                pass
        return self.get_response(request)
