from django.urls import path
from . import views

app_name = 'a_order'

urlpatterns = [
    path('create_recharge_order/', views.create_recharge_order, name='create_recharge_order'),
    path('create_subscription_order/', views.create_subscription_order, name='create_subscription_order'),
    # path('payment_callback/', views.payment_callback, name='payment_callback'),
    path('payment_success/', views.payment_success, name='payment_success'),  # 支付成功页面
    path('payment_failed_recharge/', views.payment_failed_recharge, name='payment_failed_recharge'),
    path('callback/alipay', views.alipay_callback, name='alipay_callback'),
]