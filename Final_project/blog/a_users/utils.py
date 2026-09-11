import hmac
import secrets
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache

RESET_CODE_TTL = 60 * 10
RESET_MAX_ATTEMPTS = 5            # wrong guesses allowed per code before it is invalidated
RESET_SEND_COOLDOWN = 60          # seconds between two reset emails to the same address
RESET_SEND_LIMIT_PER_HOUR = 5
RESET_REQUESTED_MESSAGE = "If this email is registered, a verification code has been sent"

def generate_verification_code():
    """Generate a 6-digit verification code."""
    return f'{secrets.randbelow(10**6):06d}'

def _reset_cache_key(kind, email):
    return f"password_reset_{kind}_{email.strip().lower()}"

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
    """Send a password reset verification code.

    Registered and unregistered addresses get the same response, so the form
    cannot be used to check whether an email has an account.
    """
    cooldown_key = _reset_cache_key('cooldown', email)
    sends_key = _reset_cache_key('sends', email)

    if cache.get(cooldown_key):
        return False, "Please wait a minute before requesting another code"
    cache.add(sends_key, 0, 60 * 60)
    if cache.get(sends_key, 0) >= RESET_SEND_LIMIT_PER_HOUR:
        return False, "Too many requests. Please try again later"
    cache.set(cooldown_key, True, RESET_SEND_COOLDOWN)
    cache.incr(sends_key)

    user = User.objects.filter(email=email).first()
    if user is None:
        return True, RESET_REQUESTED_MESSAGE

    code = generate_verification_code()
    cache.set(_reset_cache_key('code', email), code, RESET_CODE_TTL)
    cache.delete(_reset_cache_key('attempts', email))

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
    return True, RESET_REQUESTED_MESSAGE

def verify_password_reset_code(email, code):
    """Verify a password reset code; too many wrong guesses invalidate it."""
    stored_code = cache.get(_reset_cache_key('code', email))
    if not stored_code:
        return False

    if hmac.compare_digest(stored_code.encode(), str(code or '').encode()):
        return True

    attempts_key = _reset_cache_key('attempts', email)
    attempts = cache.get(attempts_key, 0) + 1
    if attempts >= RESET_MAX_ATTEMPTS:
        clear_password_reset_code(email)
    else:
        cache.set(attempts_key, attempts, RESET_CODE_TTL)
    return False

def clear_password_reset_code(email):
    """Clear a stored password reset code and its failed-attempt counter."""
    cache.delete(_reset_cache_key('code', email))
    cache.delete(_reset_cache_key('attempts', email))

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
