from django.shortcuts import render, get_object_or_404, redirect
from .models import ChatRoom, ChatMessage
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required

# ------------------------
# 여행 리스트 뷰
# ------------------------
def travel_list(request):
    print(f"request =======> {request.POST}")
    return render(request, "travel/travel_list.html")


# ------------------------
# 회원가입 뷰
# ------------------------
def signup_view(request, room_name=None):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('travel:login')  # travel.urls에서 login 이름 확인
    else:
        form = UserCreationForm()
    return render(request, 'chat/signup.html', {'form': form})


# ------------------------
# 실제 매칭용 채팅방 뷰
# ------------------------
def chat_view(request, room_name):
    room = get_object_or_404(ChatRoom, room_name=room_name)
    return render(request, 'chat/match_chat.html', {
        'room_name': room.room_name
    })


# ------------------------
# 혼자 테스트용 채팅방 뷰
# ------------------------
@login_required
def test_chat_room(request):
    # 내 계정 이름 기준 테스트용 방 생성
    room_name = f"test_{request.user.username}"
    room, created = ChatRoom.objects.get_or_create(room_name=room_name)

    # ✅ 테스트용 더미 파트너
    dummy_partner = {
        'id': 1,
        'name': 'AI 여행 파트너',
        'trip': '혼자 테스트 여행'
    }

    context = {
        'room_name': room_name,
        'partners': [dummy_partner],
        'message': "테스트용 채팅방입니다."
    }
    return render(request, 'travel/match_chat.html', context)


# ------------------------
# chat_test 뷰 (urls.py 연결용)
# ------------------------
@login_required
def chat_test(request):
    return test_chat_room(request)