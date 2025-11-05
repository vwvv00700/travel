import json, logging, re 

from django.shortcuts import render, redirect
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.models import User

from travel.models import TravelPlan, Place, ChatRoom, UserSelectedPlan
from travel.services.matching import matchingRoom

logger = logging.getLogger(__name__)

def main(request):
    return render(request, "index.html")

def select(request):
    return render(request, "select.html")


@login_required
def chat(request):
    current_user = request.user
    # 참여자가 2명인 방만 가져오거나, 나중에 필터링하는 것이 좋습니다.
    # 현재는 일단 모든 방을 가져와서 처리합니다.

    # 같은 여행 플랜을 가진 사용자와 매칭하여 ChatRoom 데이터 생성
    refresh , messages = matchingRoom(request)
    
    or_condition = Q(plan_user_1=current_user) | Q(plan_user_2=current_user)
    current_rooms = ChatRoom.objects.filter(or_condition, user_matched=True)
    room_data_list = []
    
    for room in current_rooms:

        if room.plan_user_1 == current_user.username:
            partner = room.plan_user_2
            plan_pk = room.travel_plan2_pk
        else:
            partner = room.plan_user_1
            plan_pk = room.travel_plan1_pk
        
        plan = UserSelectedPlan.objects.filter(id=plan_pk).first()
        plan_title = plan.plan_title if plan else "알 수 없음"
            
        room_data_list.append({
            'room': room,
            'plan_title': plan_title,
            'partner_name': partner,
            # 'location': location_value, 
        })
            
    return render(request, 'travel/match_chat.html', {
        'room_data_list': room_data_list, 
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
    return render(request, 'registration/signup.html', {'form': form})
