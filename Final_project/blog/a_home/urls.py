from django.urls import path
from a_home.views import *

app_name = 'a_home'

urlpatterns = [
    path('', home_view, name="home"),
    path('help/', help_view, name="help"),
    path('about/', about_view, name="about"),
    path('find/', find_view, name="find"),
    path('home/', homes_view, name="homes"),
]
