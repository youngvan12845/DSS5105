from django.shortcuts import redirect, render

from a_blog.models import ArticlePage


def home_view(request):
    return redirect('a_home:homes')


def help_view(request):
    return render(request, 'help.html')


def about_view(request):
    return redirect('a_order:create_subscription_order')


def find_view(request):
    return redirect('/blog/')


def homes_view(request):
    articles = ArticlePage.objects.live().order_by('-first_published_at')[:6]
    return render(request, 'homes.html', {'articles': articles})
