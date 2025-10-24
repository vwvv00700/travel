from django.shortcuts import render, get_object_or_404, redirect
from .models import ChatRoom, ChatMessage
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import render, get_object_or_404, redirect
from .models import ChatRoom, ChatMessage
from django.contrib.auth.decorators import login_required
import json
from .models import ChatMessage, ChatReport
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

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
@login_required
def chat_view(request, room_name):
    room = get_object_or_404(ChatRoom, room_name=room_name)
    
    # 참가자 중 현재 사용자가 아닌 상대방
    participants = room.participants.exclude(id=request.user.id)
    partner = participants.first() if participants.exists() else None
    
    partner_profile = None
    if partner:
        partner_profile = getattr(partner, 'userprofile', None)

    return render(request, 'chat/match_chat.html', {
        'room_name': room.room_name,
        'partner': partner,
        'partner_profile': partner_profile
    })



@login_required
def test_chat_room(request):
    """
    테스트용 채팅방 + 파트너 정보 표시
    """
    # 내 계정 이름 기준 테스트용 방 생성
    room_name = f"test_{request.user.username}"
    room, created = ChatRoom.objects.get_or_create(room_name=room_name)

    #  예제 파트너 정보 (실제 DB에서 UserProfile 가져오기)
    partner_users = User.objects.exclude(id=request.user.id)  # 본인 제외

    partners = []
    for user in partner_users:
        profile = getattr(user, 'userprofile', None)
        partners.append({
            'id': user.id,
            'name': user.username,
            'age': profile.age if profile and hasattr(profile,'age') else '정보 없음',
            'gender': profile.gender if profile and hasattr(profile,'gender') else '정보 없음',
            'intro': profile.intro if profile else '',
            'trip': '테스트 여행'  # 필요 시 TravelPlan에서 가져올 수 있음
        })

    # 테스트용 AI 파트너도 추가
    partners.append({
        'id': 0,
        'name': 'AI 여행 파트너',
        'age': '∞',
        'gender': 'AI',
        'intro': '혼자 테스트 여행',
        'trip': '서울 여행'
    })

    context = {
        'room_name': room_name,
        'partners': partners
    }

    return render(request, 'travel/match_chat.html', context)
# ------------------------
# chat_test 뷰 (urls.py 연결용)
# ------------------------
@login_required
def chat_test(request):
    return test_chat_room(request)



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
@login_required
def chat_view(request, room_name):
    room = get_object_or_404(ChatRoom, room_name=room_name)
    
    # 참가자 중 현재 사용자가 아닌 상대방
    participants = room.participants.exclude(id=request.user.id)
    partner = participants.first() if participants.exists() else None
    
    partner_profile = None
    if partner:
        partner_profile = getattr(partner, 'userprofile', None)

    return render(request, 'chat/match_chat.html', {
        'room_name': room.room_name,
        'partner': partner,
        'partner_profile': partner_profile
    })



@login_required
def test_chat_room(request):
    """
    테스트용 채팅방 + 파트너 정보 표시
    """
    # 내 계정 이름 기준 테스트용 방 생성
    room_name = f"test_{request.user.username}"
    room, created = ChatRoom.objects.get_or_create(room_name=room_name)

    #  예제 파트너 정보 (실제 DB에서 UserProfile 가져오기)
    partner_users = User.objects.exclude(id=request.user.id)  # 본인 제외

    partners = []
    for user in partner_users:
        profile = getattr(user, 'userprofile', None)
        partners.append({
            'id': user.id,
            'name': user.username,
            'age': profile.age if profile and hasattr(profile,'age') else '정보 없음',
            'gender': profile.gender if profile and hasattr(profile,'gender') else '정보 없음',
            'intro': profile.intro if profile else '',
            'trip': '테스트 여행'  # 필요 시 TravelPlan에서 가져올 수 있음
        })

    # 테스트용 AI 파트너도 추가
    partners.append({
        'id': 0,
        'name': 'AI 여행 파트너',
        'age': '∞',
        'gender': 'AI',
        'intro': '혼자 테스트 여행',
        'trip': '서울 여행'
    })

    context = {
        'room_name': room_name,
        'partners': partners
    }

    return render(request, 'travel/match_chat.html', context)
# ------------------------
# chat_test 뷰 (urls.py 연결용)
# ------------------------
@login_required
def chat_test(request):
    return test_chat_room(request)


@csrf_exempt
@login_required
def report_message(request):
    """
    채팅 메시지 신고 기능 (AJAX 요청용)
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            message_id = data.get("message_id")
            reason = data.get("reason", "")

            # 메시지 찾기
            message = ChatMessage.objects.get(id=message_id)
            reporter = request.user

            # 중복 신고 방지
            if ChatReport.objects.filter(reporter=reporter, message=message).exists():
                return JsonResponse({"success": False, "message": "이미 신고한 메시지입니다."}, status=400)

            # 신고 생성
            ChatReport.objects.create(
                reporter=reporter,
                message=message,
                reason=reason
            )

            return JsonResponse({"success": True, "message": "✅ 신고가 접수되었습니다."})

        except ChatMessage.DoesNotExist:
            return JsonResponse({"success": False, "message": "❌ 메시지를 찾을 수 없습니다."}, status=404)
        except Exception as e:
            return JsonResponse({"success": False, "message": f"에러 발생: {str(e)}"}, status=400)

    return JsonResponse({"success": False, "message": "허용되지 않은 요청입니다."}, status=405)