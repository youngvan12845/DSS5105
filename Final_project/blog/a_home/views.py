from django.shortcuts import render,redirect

def home_view(request):
    # return render(request, 'home.html')
    return redirect('home/')


def help_view(request):
    # 帮助页面视图
    return render(request, 'help.html')

def about_view(request):
    # 关于我们页面视图
    return render(request, 'about.html')

def find_view(request):
    # 主推产品页面视图
    return render(request, 'find.html')

def homes_view(request):
    # 主页视图
    return render(request, 'homes.html')