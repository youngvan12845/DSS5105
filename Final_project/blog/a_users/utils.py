import random
import string
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache

def generate_verification_code():
    """生成6位数字验证码"""
    return ''.join(random.choices(string.digits, k=6))

def send_verification_code_email(user):
    """发送包含验证码的邮件用于邮箱验证"""
    code = generate_verification_code()
    
    # 将验证码存储在cache中，设置过期时间为10分钟
    cache_key = f"email_verification_code_{user.id}"
    cache.set(cache_key, code, 60 * 10)  # 10分钟过期
    
    subject = "芝士圈网站邮箱验证码"
    message = f"""
    尊敬的用户 {user.username}，您好！
    
    您正在进行邮箱验证操作，您的验证码是：{code}
    
    该验证码10分钟内有效，请及时验证。
    
    如非本人操作，请忽略此邮件。
    
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
    """发送密码重置验证码"""
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return False, "该邮箱未注册"
        
    code = generate_verification_code()
        
    # 将验证码存储在cache中，设置过期时间为10分钟
    cache_key = f"password_reset_code_{email}"
    cache.set(cache_key, code, 60 * 10)  # 10分钟过期
        
    subject = "芝士圈网站密码重置验证码"
    message = f"""
    尊敬的用户 {user.username}，您好！
    
    您正在进行密码重置操作，您的验证码是：{code}
    
    该验证码10分钟内有效，请及时验证。
    
    如非本人操作，请忽略此邮件。
    
    """
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )
    return True, "验证码已发送"

def verify_password_reset_code(email, code):
    """验证密码重置验证码"""
    cache_key = f"password_reset_code_{email}"
    stored_code = cache.get(cache_key)
        
    if stored_code and stored_code == code:
        return True
    return False

def clear_password_reset_code(email):
    """清除密码重置验证码"""
    cache_key = f"password_reset_code_{email}"
    cache.delete(cache_key)

def send_login_verification_code(user):
    """为新登录用户发送邮箱验证码"""
    from .models import EmailVerificationCode
        
    # 生成验证码
    code = generate_verification_code()
        
    # 保存到数据库
    EmailVerificationCode.objects.create(
        user=user,
        email=user.email,
        code=code
    )
        
    subject = "芝士圈网站 - 邮箱验证"
    message = f"""
尊敬的用户 {user.username}，您好！

欢迎使用芝士圈网站！为了确保您的账户安全，请验证您的邮箱地址。

您的验证码是：{code}

该验证码10分钟内有效，请及时验证。

如非本人操作，请忽略此邮件。

祝您使用愉快！
芝士圈团队
    """
        
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return True, "验证码已发送到您的邮箱"
    except Exception as e:
        return False, f"邮件发送失败：{str(e)}"