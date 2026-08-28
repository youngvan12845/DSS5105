from django.db import models
from django.contrib.auth.models import User
from django.utils.timezone import now, timedelta
from django.core.mail import send_mail

import logging
logger = logging.getLogger(__name__)


class SubscriptionConfig(models.Model):
    """订阅积分配置"""
    monthly_points = models.PositiveIntegerField(default=100)  # 月度订阅所需积分
    quarterly_points = models.PositiveIntegerField(default=250)  # 季度订阅所需积分
    yearly_points = models.PositiveIntegerField(default=900)  # 年度订阅所需积分

    def __str__(self):
        return "Subscription Configuration"

    def save(self, *args, **kwargs):
        # 确保表中只有一条记录
        if not self.pk and SubscriptionConfig.objects.exists():
            raise ValueError("只能有一个 SubscriptionConfig 实例")
        return super().save(*args, **kwargs)

    @staticmethod
    def get_config():
        """获取唯一的订阅配置实例"""
        config, created = SubscriptionConfig.objects.get_or_create(
            defaults={
                'monthly_points': 100,
                'quarterly_points': 250,
                'yearly_points': 900,
            }
        )
        return config

class RechargeOrder(models.Model):
    """积分充值订单"""
    PAYMENT_METHODS = [
        ('wechat', 'WeChat Pay'),
        ('alipay', 'Alipay'),
        ('unionpay', 'UnionPay'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recharge_orders')
    amount = models.DecimalField(max_digits=10, decimal_places=2)  # 支付金额
    points = models.PositiveIntegerField()  # 充值的积分数量
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    transaction_id = models.CharField(max_length=100, unique=True, null=True, blank=True)  # 支付平台返回的交易流水号

    def __str__(self):
        return f"RechargeOrder {self.id} - {self.user.username} - {self.status}"

    def process_recharge(self):
        """处理积分充值订单"""
        if self.status == 'paid':
            profile = self.user.profile
            logger.info(f"Points before recharge: {profile.points}")
            profile.add_points(self.points, description="积分充值")
            logger.info(f"Points after recharge: {profile.points}")
            return True
        logger.warning(f"Order {self.id} is not in 'paid' status, cannot process recharge.")
        return False


class SubscriptionOrder(models.Model):
    """会员订阅订单"""
    SUBSCRIPTION_PERIODS = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscription_orders')
    points = models.PositiveIntegerField()  # 扣除的积分数量
    subscription_period = models.CharField(max_length=20, choices=SUBSCRIPTION_PERIODS)  # 订阅周期
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"SubscriptionOrder {self.id} - {self.user.username} - {self.status}"

    def process_subscription(self):
        """处理会员订阅订单"""
        if self.status == 'paid':
            profile = self.user.profile
            profile.deduct_points(self.points, description="会员订阅")
            profile.activate_subscription(self.subscription_period)

            # 发送订阅成功通知
            send_mail(
                '订阅成功通知',
                f'尊敬的 {self.user.username}，您的会员订阅已成功激活！',
                'noreply@example.com',
                [self.user.email],
                fail_silently=True,
            )

            return True
        return False