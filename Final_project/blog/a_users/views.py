from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from allauth.account.utils import send_email_confirmation
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.contrib.auth.models import User
from django.contrib.auth.views import redirect_to_login
from django.contrib import messages
from .forms import *
from django.utils.timezone import now
from django.core.cache import cache
from .utils import send_verification_code_email, send_password_reset_code, verify_password_reset_code, clear_password_reset_code
from django.contrib import messages
from allauth.account.models import EmailAddress
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from urllib.parse import quote, unquote
import logging
from .forms import LoginEmailVerificationForm
from django.core.paginator import Paginator
from .models import EmailVerificationCode, BrowsingHistory
from .utils import send_login_verification_code

logger = logging.getLogger(__name__)

def profile_view(request, username=None):
    if username:
        profile = get_object_or_404(User, username=username).profile
    else:
        try:
            profile = request.user.profile
        except:
            return redirect_to_login(request.get_full_path())
    return render(request, 'a_users/profile.html', {'profile': profile, 'now': now()})


@login_required
def profile_edit_view(request):
    form = ProfileForm(instance=request.user.profile)  
    
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=request.user.profile)
        if form.is_valid():
            form.save()
            return redirect('profile')
        
    if request.path == reverse('profile-onboarding'):
        onboarding = True
    else:
        onboarding = False
      
    return render(request, 'a_users/profile_edit.html', {'form': form, 'onboarding': onboarding})


@login_required
def profile_settings_view(request):
    return render(request, 'a_users/profile_settings.html')


@login_required
def profile_emailchange(request):
    
    if request.htmx:
        form = EmailForm(instance=request.user)
        return render(request, 'partials/email_form.html', {'form': form})
    
    if request.method == 'POST':
        form = EmailForm(request.POST, instance=request.user)

        if form.is_valid():
            
            # 查看邮箱是否存在
            email = form.cleaned_data['email']
            if User.objects.filter(email=email).exclude(id=request.user.id).exists():
                messages.warning(request, f'{email} is already in use.')
                return redirect('profile-settings')
            
            form.save() 

            # 发送验证邮件
            send_email_confirmation(request, request.user)
            
            return redirect('profile-settings')
        else:
            messages.warning(request, 'Email not valid or already in use')
            return redirect('profile-settings')
        
    return redirect('profile-settings')


@login_required
def profile_usernamechange(request):
    if request.htmx:
        form = UsernameForm(instance=request.user)
        return render(request, 'partials/username_form.html', {'form': form})
    
    if request.method == 'POST':
        form = UsernameForm(request.POST, instance=request.user)
        
        if form.is_valid():
            form.save()
            messages.success(request, 'Username updated successfully.')
            return redirect('profile-settings')
        else:
            messages.warning(request, 'Username not valid or already in use')
            return redirect('profile-settings')
    
    return redirect('profile-settings')    


@login_required
def profile_emailverify(request):
    # 发送验证码邮件代替原来的验证链接邮件
    send_verification_code_email(request.user)
    messages.success(request, "验证码已发送到您的邮箱，请查收。")
    return redirect('profile-settings')

# 添加验证码验证视图
@login_required
def verify_email_code(request):
    if request.method == 'POST':
        code = request.POST.get('verification_code')
        cache_key = f"email_verification_code_{request.user.id}"
        stored_code = cache.get(cache_key)
        
        if stored_code and stored_code == code:
            # 验证成功，将邮箱标记为已验证
            email_address = EmailAddress.objects.get_for_user(request.user, request.user.email)
            email_address.verified = True
            email_address.save()
            
            # 清除缓存中的验证码
            cache.delete(cache_key)
            
            messages.success(request, "邮箱验证成功！")
        else:
            messages.error(request, "验证码不正确或已过期，请重新获取。")
        
        return redirect('profile-settings')
    
    return render(request, 'a_users/verify_email.html')


@login_required
def profile_delete_view(request):
    user = request.user
    if request.method == "POST":
        logout(request)
        user.delete()
        messages.success(request, '账号已删除')
        return redirect('/')
    
    return render(request, 'a_users/profile_delete.html')

def password_reset_request(request):
    """密码重置请求页面 - 修复版本"""
    if request.method == 'POST':
        form = PasswordResetEmailForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            success, message = send_password_reset_code(email)
            
            if success:
                messages.success(request, message)
                # 使用会话存储邮箱，避免URL编码问题
                request.session['password_reset_email'] = email
                return redirect('password-reset-verify')
            else:
                messages.error(request, message)
    else:
        form = PasswordResetEmailForm()
    
    return render(request, 'a_users/password_reset_request.html', {'form': form})


def password_reset_verify(request):
    """验证码验证页面 - 修复版本（不使用URL参数）"""
    # 从会话中获取邮箱
    email = request.session.get('password_reset_email')
    if not email:
        messages.error(request, "会话已过期，请重新开始密码重置流程")
        return redirect('password-reset-request')
    
    if request.method == 'POST':
        form = VerifyCodeForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['verification_code']
            
            if verify_password_reset_code(email, code):
                # 将验证码也存储在会话中
                request.session['password_reset_code'] = code
                return redirect('password-reset-confirm')
            else:
                messages.error(request, "验证码不正确或已过期")
    else:
        form = VerifyCodeForm(initial={'email': email})
    
    return render(request, 'a_users/password_reset_verify.html', {
        'form': form,
        'email': email
    })


def password_reset_confirm(request):
    """设置新密码页面 - 修复版本"""
    # 从会话中获取邮箱和验证码
    email = request.session.get('password_reset_email')
    code = request.session.get('password_reset_code')
    
    if not email or not code:
        messages.error(request, "会话已过期，请重新开始密码重置流程")
        return redirect('password-reset-request')
    
    # 验证验证码是否仍然有效
    if not verify_password_reset_code(email, code):
        messages.error(request, "验证码已过期，请重新申请密码重置")
        return redirect('password-reset-request')
    
    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            new_password = form.cleaned_data['new_password']
            
            try:
                user = User.objects.get(email=email)
                user.set_password(new_password)
                user.save()
                
                # 清除会话数据和验证码
                clear_password_reset_code(email)
                del request.session['password_reset_email']
                del request.session['password_reset_code']
                
                messages.success(request, "密码重置成功，请使用新密码登录")
                return redirect('account_login')
            except User.DoesNotExist:
                messages.error(request, "用户不存在")
    else:
        form = ResetPasswordForm()
    
    return render(request, 'a_users/password_reset_confirm.html', {
        'form': form,
        'email': email
    })


@require_http_methods(["POST"])
def resend_reset_code(request):
    """重新发送密码重置验证码 - 修复版本"""
    email = request.session.get('password_reset_email')
    if email:
        success, message = send_password_reset_code(email)
        if success:
            return JsonResponse({'success': True, 'message': '验证码已重新发送'})
        else:
            return JsonResponse({'success': False, 'message': message})
    return JsonResponse({'success': False, 'message': '会话已过期'})

def login_email_verification(request):
    """登录后邮箱验证页面"""
    if not request.user.is_authenticated:
        return redirect('account_login')
    
    # 检查邮箱是否已验证
    try:
        email_address = EmailAddress.objects.get(user=request.user, email=request.user.email)
        if email_address.verified:
            return redirect('/')  # 已验证，跳转到首页
    except EmailAddress.DoesNotExist:
        # 如果没有EmailAddress记录，创建一个
        EmailAddress.objects.create(
            user=request.user,
            email=request.user.email,
            verified=False,
            primary=True
        )
    
    if request.method == 'POST':
        form = LoginEmailVerificationForm(user=request.user, data=request.POST)
        if form.is_valid():
            # 如果表单验证通过，说明验证码正确且未过期
            # 在表单的clean_verification_code方法中已经验证过了
            code = form.cleaned_data['verification_code']
            
            try:
                # 获取验证记录并标记为已使用
                verification = EmailVerificationCode.objects.filter(
                    user=request.user,
                    code=code,
                    used=False
                ).latest('created_at')
                
                verification.used = True
                verification.save()
                
                # 更新邮箱验证状态
                email_address = EmailAddress.objects.get(user=request.user, email=request.user.email)
                email_address.verified = True
                email_address.save()
                
                messages.success(request, "邮箱验证成功！欢迎使用芝士圈！")
                return redirect('/')
                
            except EmailVerificationCode.DoesNotExist:
                messages.error(request, "验证过程中出现错误，请重试")
        # 如果表单验证失败，错误信息已经在表单中设置了
    else:
        form = LoginEmailVerificationForm(user=request.user)
        
        # 如果是第一次访问，自动发送验证码
        if 'code_sent' not in request.session:
            success, message = send_login_verification_code(request.user)
            if success:
                messages.info(request, message)
                request.session['code_sent'] = True
            else:
                messages.error(request, message)
    
    return render(request, 'a_users/login_email_verification.html', {
        'form': form,
        'user_email': request.user.email
    })

@require_http_methods(["POST"])
def resend_login_verification_code(request):
    """重新发送登录验证码"""
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'message': '用户未登录'})
    
    success, message = send_login_verification_code(request.user)
    return JsonResponse({'success': success, 'message': message})

@login_required
def browsing_history_view(request):
    """浏览历史页面"""
    history_list = BrowsingHistory.objects.filter(user=request.user).order_by('-viewed_at')

    paginator = Paginator(history_list, 20)
    page_number = request.GET.get('page')
    history_records = paginator.get_page(page_number)

    context = {
        'history_records': history_records,
        'total_articles': history_list.count(),
    }

    return render(request, 'a_users/browsing_history.html', context)


@login_required
@require_http_methods(["POST"])
def clear_browsing_history(request):
    """清空浏览历史"""
    BrowsingHistory.objects.filter(user=request.user).delete()

    if request.headers.get('Content-Type') == 'application/json':
        return JsonResponse({'success': True, 'message': '浏览历史已清空'})
    messages.success(request, '浏览历史已清空')
    return redirect('browsing-history')


@login_required
@require_http_methods(["POST"])
def delete_history_item(request, history_id):
    """删除单条浏览历史"""
    try:
        history_item = BrowsingHistory.objects.get(id=history_id, user=request.user)
        history_item.delete()

        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({'success': True, 'message': '记录已删除'})
        messages.success(request, '记录已删除')
    except BrowsingHistory.DoesNotExist:
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({'success': False, 'message': '记录不存在'})
        messages.error(request, '记录不存在')

    return redirect('browsing-history')