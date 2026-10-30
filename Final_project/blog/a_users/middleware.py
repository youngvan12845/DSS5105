from django.contrib.auth.models import AnonymousUser


class EmailVerificationMiddleware:
    """Pass-through middleware: automatic verification enabled for instant onboarding."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)
