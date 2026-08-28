from django.contrib import admin
from .models import SubscriptionConfig, RechargeOrder, SubscriptionOrder

@admin.register(SubscriptionConfig)
class SubscriptionConfigAdmin(admin.ModelAdmin):
    list_display = ('id', 'monthly_points', 'quarterly_points', 'yearly_points')  # 修正字段名称
    list_display_links = ('id',)
    list_editable = ('monthly_points', 'quarterly_points', 'yearly_points')  # 修正字段名称

@admin.register(RechargeOrder)
class RechargeOrderAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'payment_method', 'status', 'created_at')
    list_filter = ('payment_method', 'status')
    search_fields = ('user__username', 'transaction_id')

@admin.register(SubscriptionOrder)
class SubscriptionOrderAdmin(admin.ModelAdmin):
    list_display = ('user', 'subscription_period', 'status', 'created_at')
    list_filter = ('subscription_period', 'status')
    search_fields = ('user__username', 'transaction_id')