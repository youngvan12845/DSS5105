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
        user=user, type='earn', description='Daily check-in', created_at__date=today
    ).exists():
        return JsonResponse({'error': 'You have already checked in today!'}, status=400)

    profile = user.profile
    profile.add_points(10, 'Daily check-in')

    return JsonResponse({'success': True, 'msg': 'Check-in successful! You earned 10 points'})


@login_required
def points_records(request):
    records = PointsRecord.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'a_points/points_records.html', {'records': records})
