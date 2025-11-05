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
    current_rooms = ChatRoom.objects.filter(participants=current_user)
    
    room_data_list = []
    
    for room in current_rooms:
        # 현재 사용자를 제외한 나머지 참가자 QuerySet
        other_participants = room.participants.exclude(id=current_user.id)
        
        # ⚠️ (가정) 1:1 채팅방임을 명시적으로 확인
        # 현재 유저를 제외한 참가자가 정확히 1명인 경우만 처리
        if other_participants.count() != 1:
            continue
            
        partner = other_participants.first()
        
        # ... (이후의 여행 계획 유효성 검사 및 데이터 처리 로직은 동일)
        
        # 🚨 NULL 체크 및 객체 유효성 확인 강화
        # 1. 파트너가 없거나 (1인 방) -> 위에서 count로 처리했으므로 사실상 불필요
        if not partner:
            continue
            
        # 2. room.travel_plan1이 None이거나 TravelPlan 객체가 아니면 건너뜁니다.
        if not room.travel_plan1 or not isinstance(room.travel_plan1, TravelPlan):
            continue
            
        # 3. 객체와 필드가 모두 유효함을 확인했으므로, 안전하게 접근합니다.
        try:
            location_value = room.travel_plan1.destination 
        except AttributeError:
            print(f"ERROR: TravelPlan object {room.travel_plan1.id} has no 'destination' field.")
            location_value = "ERROR: 필드 누락"
            
        room_data_list.append({
            'room': room,
            'partner': partner,
            'partner_name': partner.username, 
            'location': location_value, 
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
