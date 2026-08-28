from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import PointsRecord
from django.utils.timezone import now


@login_required
def daily_check_in(request):
    user = request.user
    today = now().date()

    if PointsRecord.objects.filter(
        user=user, type='earn', description='每日签到', created_at__date=today
    ).exists():
        return JsonResponse({'error': '您今天已经签到过了！'}, status=400)

    profile = user.profile
    profile.add_points(10, '每日签到')

    return JsonResponse({'success': True, 'msg': '签到成功，已获得 10 积分'})


@login_required
def points_records(request):
    records = PointsRecord.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'a_points/points_records.html', {'records': records})
