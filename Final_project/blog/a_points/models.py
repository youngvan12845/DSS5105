from django.db import models
from django.contrib.auth.models import User
from django.utils.timezone import now

class PointsRecord(models.Model):
    POINTS_TYPE_CHOICES = [
        ('earn', 'Earn'),  # 获取积分
        ('spend', 'Spend'),  # 消耗积分
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="points_records")
    points = models.IntegerField()  # 积分数量（正数表示获取，负数表示消耗）
    type = models.CharField(max_length=10, choices=POINTS_TYPE_CHOICES)  # 积分类型
    description = models.CharField(max_length=255, blank=True)  # 积分描述
    created_at = models.DateTimeField(default=now)  # 创建时间

    def __str__(self):
        return f"{self.user.username} - {self.type} - {self.points} points"

