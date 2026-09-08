import random
import string
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache

def generate_verification_code():
    """Generate a 6-digit verification code."""
    return ''.join(random.choices(string.digits, k=6))

def send_verification_code_email(user):
    """Send a verification code email for email verification."""
    code = generate_verification_code()
    
    cache_key = f"email_verification_code_{user.id}"
    cache.set(cache_key, code, 60 * 10)
    
    subject = "CheeseO — Email Verification Code"
    message = f"""
Hello {user.username},

You are verifying your email address. Your verification code is: {code}

This code expires in 10 minutes. Please verify promptly.

If you did not request this, please ignore this email.

"""
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
    return code

def send_password_reset_code(email):
    """Send a password reset verification code."""
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return False, "This email is not registered"
        
    code = generate_verification_code()
        
    cache_key = f"password_reset_code_{email}"
    cache.set(cache_key, code, 60 * 10)
        
    subject = "CheeseO — Password Reset Code"
    message = f"""
Hello {user.username},

You requested a password reset. Your verification code is: {code}

This code expires in 10 minutes. Please verify promptly.

If you did not request this, please ignore this email.

"""
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )
    return True, "Verification code sent"

def verify_password_reset_code(email, code):
    """Verify a password reset code."""
    cache_key = f"password_reset_code_{email}"
    stored_code = cache.get(cache_key)
        
    if stored_code and stored_code == code:
        return True
    return False

def clear_password_reset_code(email):
    """Clear a stored password reset code."""
    cache_key = f"password_reset_code_{email}"
    cache.delete(cache_key)

def send_login_verification_code(user):
    """Send an email verification code after login."""
    from .models import EmailVerificationCode
        
    code = generate_verification_code()
        
    EmailVerificationCode.objects.create(
        user=user,
        email=user.email,
        code=code
    )
        
    subject = "CheeseO — Email Verification"
    message = f"""
Hello {user.username},

Welcome to CheeseO! To keep your account secure, please verify your email address.

Your verification code is: {code}

This code expires in 10 minutes. Please verify promptly.

If you did not request this, please ignore this email.

Best regards,
The CheeseO Team
    """
        
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return True, "Verification code sent to your email"
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"
