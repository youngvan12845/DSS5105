from django.shortcuts import redirect
from django.urls import reverse
from allauth.account.models import EmailAddress
from django.contrib.auth.models import AnonymousUser

class EmailVerificationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.exempt_paths = [
            '/accounts/login/',
            '/accounts/logout/',
            '/accounts/signup/',
            '/profile/login-email-verification/',
            '/profile/resend-login-verification-code/',
            '/profile/browsing-history/',
            '/admin/',
            '/static/',
            '/media/',
        ]
    
    def __call__(self, request):
        if isinstance(request.user, AnonymousUser):
            response = self.get_response(request)
            return response
        current_path = request.path
        if any(current_path.startswith(path) for path in self.exempt_paths):
            response = self.get_response(request)
            return response
        try:
            email_address = EmailAddress.objects.get(
                user=request.user,
                email=request.user.email
            )
            if not email_address.verified:
                return redirect('login_email_verification')
        except EmailAddress.DoesNotExist:
            return redirect('login_email_verification')
        response = self.get_response(request)
        return response