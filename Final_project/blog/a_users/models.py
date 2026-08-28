from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.utils.timezone import now
from django.utils import timezone
from a_points.models import PointsRecord
from datetime import timedelta
import logging
import random
import string

logger = logging.getLogger(__name__)

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    image = models.ImageField(upload_to='avatars/', null=True, blank=True)
    displayname = models.CharField(max_length=20, null=True, blank=True)
    info = models.TextField(null=True, blank=True)
    is_subscribed = models.BooleanField(default=False)  # 是否订阅
    subscription_date = models.DateField(null=True, blank=True)  # 订阅日期 
    subscription_end_date = models.DateField(null=True, blank=True)  # 订阅结束日期
    points = models.PositiveIntegerField(default=0, verbose_name="积分")  # 用户积分
    
    def __str__(self):
        return str(self.user)
    
    @property
    def name(self):
        if self.displayname:
            return self.displayname
        return self.user.username 
    
    @property
    def avatar(self):
        if self.image:
            return self.image.url
        return f'{settings.STATIC_URL}images/avatar.svg'
    
    def has_valid_subscription(self):
        """检查用户订阅是否有效"""
        return self.is_subscribed and self.subscription_end_date and self.subscription_end_date > now().date()
    
    # 订阅状态
    def handle_subscription(self, period):
        """处理订阅或续费逻辑"""
        self.is_subscribed = True
        today = now().date()

        # 如果当前已订阅且未过期，则在现有订阅结束日期基础上续费
        if self.subscription_end_date and self.subscription_end_date > today:
            start_date = self.subscription_end_date
        else:
            start_date = today

        # 根据订阅周期计算新的结束日期
        if period == 'monthly':
            self.subscription_end_date = start_date + timedelta(days=30)
        elif period == 'quarterly':
            self.subscription_end_date = start_date + timedelta(days=90)
        elif period == 'yearly':
            self.subscription_end_date = start_date + timedelta(days=365)

        self.subscription_date = today  # 更新订阅日期为当前日期
        self.save()
    
    def add_points(self, amount, description=""):
        """增加积分"""
        logger.info(f"Adding {amount} points to user {self.user.username}")
        self.points += amount
        self.save()
        PointsRecord.objects.create(user=self.user, points=amount, type='earn', description=description)

    def deduct_points(self, amount, description=""):
        """扣除积分"""
        if self.points >= amount:
            self.points -= amount
            self.save()
            PointsRecord.objects.create(user=self.user, points=-amount, type='spend', description=description)
            return True
        return False

    def activate_subscription(self, period):
        """激活会员订阅"""
        self.is_subscribed = True
        self.subscription_date = now()
        if period == 'monthly':
            self.subscription_end_date = now() + timedelta(days=30)
        elif period == 'quarterly':
            self.subscription_end_date = now() + timedelta(days=90)
        elif period == 'yearly':
            self.subscription_end_date = now() + timedelta(days=365)
        self.save()

class EmailVerificationCode(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    email = models.EmailField()
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']
    
    def is_expired(self):
        """检查验证码是否已过期（10分钟）"""
        return timezone.now() > self.created_at + timedelta(minutes=10)
    
    @classmethod
    def generate_code(cls):
        """生成6位数字验证码"""
        return ''.join(random.choices(string.digits, k=6))
    
    def __str__(self):
        return f"{self.user.username} - {self.email} - {self.code}"

class BrowsingHistory(models.Model):
    """用户浏览历史记录"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='browsing_history')
    article_id = models.PositiveIntegerField()
    article_title = models.CharField(max_length=255)
    article_url = models.URLField(max_length=500)
    viewed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'article_id')
        ordering = ['-viewed_at']
        verbose_name = '浏览历史'
        verbose_name_plural = '浏览历史'

    def __str__(self):
        return f"{self.user.username} - {self.article_title}"

    @classmethod
    def add_or_update_history(cls, user, article_id, article_title, article_url):
        if user.is_authenticated:
            obj, _created = cls.objects.update_or_create(
                user=user,
                article_id=article_id,
                defaults={
                    'article_title': article_title,
                    'article_url': article_url,
                },
            )
            return obj
        return None