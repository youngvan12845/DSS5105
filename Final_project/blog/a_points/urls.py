from django.urls import path
from . import views

app_name = 'a_points'
urlpatterns = [
    path('daily_check_in/', views.daily_check_in, name='daily_check_in'),
    path('records/', views.points_records, name='points_records'),
]