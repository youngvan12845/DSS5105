from django.urls import path
from a_users.views import *

# app_name = 'a_users'
urlpatterns = [
    path('', profile_view, name="profile"),
    path('edit/', profile_edit_view, name="profile-edit"),
    path('onboarding/', profile_edit_view, name="profile-onboarding"),
    path('settings/', profile_settings_view, name="profile-settings"),
    path('emailchange/', profile_emailchange, name="profile-emailchange"),
    path('usernamechange/', profile_usernamechange, name="profile-usernamechange"),
    path('emailverify/', profile_emailverify, name="profile-emailverify"),
    path('delete/', profile_delete_view, name="profile-delete"),
    path('verify-email-code/', verify_email_code, name="verify-email-code"),
    
    # 密码重置相关URL
    path('password-reset/', password_reset_request, name="password-reset-request"),
    path('password-reset-verify/', password_reset_verify, name="password-reset-verify"),
    path('password-reset-confirm/', password_reset_confirm, name="password-reset-confirm"),
    path('resend-reset-code/', resend_reset_code, name="resend-reset-code"),

    path('login-email-verification/', login_email_verification, name="login_email_verification"),
    path('resend-login-verification-code/', resend_login_verification_code, name="resend-login-verification-code"),
    path('browsing-history/', browsing_history_view, name="browsing-history"),
    path('clear-browsing-history/', clear_browsing_history, name="clear-browsing-history"),
    path('delete-history-item/<int:history_id>/', delete_history_item, name="delete-history-item"),

    ]