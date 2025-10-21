from django.shortcuts import render
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from travel.models import TravelPlan, ChatRoom

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
        # 회원가입 처리 후 메인으로 리디렉션
        return redirect('main')

    # GET 요청 시 회원가입 페이지 렌더링
    return render(request, 'registration/signup.html', {})

