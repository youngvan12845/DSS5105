from django.contrib import admin
from .models import PointsRecord

@admin.register(PointsRecord)
class PointsRecordAdmin(admin.ModelAdmin):
    list_display = ('user', 'points', 'type', 'description', 'created_at')
    list_filter = ('type', 'created_at')
    search_fields = ('user__username', 'description')