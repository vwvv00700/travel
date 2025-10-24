from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .models import ChatRoom, ChatMessage, ChatReport
# from django.contrib.auth.models import User # User 모델은 필요한 경우에만 import합니다.

# ------------------------
# 여행 리스트 뷰
# ------------------------
def travel_list(request):
    print(f"request =======> {request.POST}")
    return render(request, "travel/travel_list.html")

# ------------------------
# 회원가입 뷰
# ------------------------
def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            # 'travel:login'으로 리다이렉트 (travel.urls에서 login 이름 확인)
            return redirect('travel:login')
    else:
        form = UserCreationForm()
    return render(request, 'chat/signup.html', {'form': form})

# ------------------------
# 실제 매칭용 채팅방 뷰
# ------------------------
@login_required
def chat_view(request, room_name):
    # ChatRoom 모델에서 room_name을 찾아 가져옵니다. 없으면 404 에러를 반환합니다.
    room = get_object_or_404(ChatRoom, room_name=room_name)
    
    # 참가자 중 현재 사용자가 아닌 상대방을 찾습니다.
    participants = room.participants.exclude(id=request.user.id)
    partner = participants.first() if participants.exists() else None
    
    partner_profile = None
    if partner:
        # 상대방의 UserProfile을 가져옵니다. (UserProfile 모델이 User 모델에 연결되어 있다고 가정)
        partner_profile = getattr(partner, 'userprofile', None)

    return render(request, 'chat/match_chat.html', {
        'room_name': room.room_name,
        'partner': partner,
        'partner_profile': partner_profile
    })


# ------------------------
# 채팅 메시지 신고 기능 (AJAX 요청용)
# ------------------------
@csrf_exempt
@login_required
def report_message(request):
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