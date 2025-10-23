from django.shortcuts import render, redirect
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from travel.models import TravelPlan, ChatRoom
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages

def main(request):
    return render(request, "main.html")

def select(request):
    return render(request, "select.html")

@login_required
def chat(request):
    current_user = request.user
    partners_list = []

    try:
        current_plan = TravelPlan.objects.get(user=current_user)
    except TravelPlan.DoesNotExist:
        return render(request, 'chat/match_chat.html', {
            'partners': [],
            'current_user': current_user.username,
            'message': '여행 계획이 없습니다. 여행 계획을 먼저 등록해주세요.',
        })

    matched_plans = TravelPlan.objects.filter(
        Q(location_city=current_plan.location_city) &
        Q(start_date__lte=current_plan.end_date) &
        Q(end_date__gte=current_plan.start_date) &
        Q(is_seeking_partner=True) &
        ~Q(user=current_user)
    ).select_related('user').order_by('-regdate')

    for plan in matched_plans:
        partner_user = plan.user
        user_ids = sorted([current_user.id, partner_user.id])
        room_name = f"chat_{user_ids[0]}_{user_ids[1]}"

        room, created = ChatRoom.objects.get_or_create(
            room_name=room_name,
            defaults={'user1': current_user, 'user2': partner_user}
        )

        partners_list.append({
            'id': room.room_name,
            'name': partner_user.username,
            'trip': f"{plan.location_city} ({plan.start_date.strftime('%m/%d')}~{plan.end_date.strftime('%m/%d')})"
        })

    return render(request, 'chat/match_chat.html', {
        'partners': partners_list,
        'current_user': current_user.username,
        'message': None,
    })


def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, '회원가입이 완료되었습니다. 로그인 해주세요.')
            return redirect('login')  # urls.py에서 name='login' 확인
    else:
        form = UserCreationForm()
    return render(request, 'chat/signup.html', {'form': form})


