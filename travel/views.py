from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json, re, time
from .models import ChatRoom, ChatMessage, ChatReport
from .models import Place
from django.urls import reverse
from django.contrib import messages
from .services.LLM_analyzer import analyze_place_with_LLM              # 네 함수 경로에 맞게 조정
from .services.analysis_loader import create_or_update_analysis_from_json  # 앞서 만든 저장 함수

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

def _render_select_page(request):
    """분석 대상 선택 화면(GET)"""
    # ✅ 아직 분석이 없는 Place만 노출
    all_places = (
        Place.objects
        .filter(analyses__isnull=True)       # ← 포인트
        .order_by("category", "name")
        .distinct()
    )

    grouped_places = {cat: list(items)
                      for cat, items in groupby(all_places, key=attrgetter("category"))}

    ctx = {
        "title": "장소 LLM 분석 도구",
        "grouped_places": grouped_places,
        "post_url": request.path,
        "save_url": request.path,
        # (선택) 얼마나 숨겨졌는지 보여주고 싶다면:
        "hidden_count": Place.objects.exclude(analyses__isnull=True).count(),
    }
    return render(request, "travel/select_and_analyze.html", ctx)


def analyze_selected_places_view(request):
    """
    GET  : 선택 화면
    POST : action=analyze -> LLM 분석 실행 후 화면에 결과 표시
           action=save    -> 화면에 있는 결과들을 DB 저장
    """
    if request.method == "GET":
        return _render_select_page(request)

    action = request.POST.get("action", "analyze")

    # 1) 분석 실행
    if action == "analyze":
        selected_ids = request.POST.getlist("place_ids")
        if not selected_ids:
            messages.warning(request, "선택된 장소가 없어.")
            return redirect(request.path)

        # 숫자만 취하고 중복 제거
        sel_ids = {int(x) for x in selected_ids if str(x).isdigit()}

        # 이미 분석된 장소(PlaceAnalysis 존재)는 제외
        available_qs = (
            Place.objects
            .filter(id__in=sel_ids, analyses__isnull=True)  # related_name="analyses"
            .distinct()
        )

        # 제외된 항목 안내 (선택)
        kept_ids = set(available_qs.values_list("id", flat=True))
        skipped = sel_ids - kept_ids
        if skipped:
            messages.warning(request, f"이미 분석된 {len(skipped)}개 장소는 제외했어.")

        if not available_qs.exists():
            messages.warning(request, "분석할 수 있는 새로운 장소가 없어.")
            return redirect(request.path)

        results = []
        start_time = time.time() # 시작 시간 기록

        for place in available_qs:
            place_raw_data = f"장소 이름: {place.name}\n"

            result_dict = analyze_place_with_LLM(place_raw_data)

            # 보기용 / 전송용 분리
            pretty_json  = json.dumps(result_dict, ensure_ascii=False, indent=2)
            compact_json = json.dumps(result_dict, ensure_ascii=False, separators=(",", ":"))

            results.append({
                "place_pk": place.pk,                               # 폼 키용 (정수 PK)
                "place_id": getattr(place, "place_id", None),       # 외부 ID (있으면 저장에 활용)
                "place_name": place.name,
                "analysis_dict": result_dict,
                "analysis_json_pretty": pretty_json,                # 화면 표시용
                "analysis_json_compact": compact_json,              # 폼 hidden 전송용
            })

        end_time = time.time() # 종료 시간 기록
        print(f"LLM 분석 시간 총 : {len(available_qs)} 개 ============> {round(end_time - start_time, 2)}")

        ctx = {
            "title": "분석 결과",
            "analysis_results": results,
            "post_url": request.path,
            "save_url": request.path,   # action=save로 넘어감
        }
        return render(request, "travel/select_and_analyze.html", ctx)

    # 2) DB 저장
    elif action == "save":
        key_pat = re.compile(r"^payload_(\d+)$")

        saved = errors = 0
        for key, val in request.POST.items():
            m = key_pat.match(key)
            if not m:
                continue

            try:
                place_pk = int(m.group(1))

                # textarea(hidden)로 보냈으니 한 번만 디코드
                data = json.loads(val)

                # ✅ seasonality 비어 있어도 통과 (저장 함수가 0으로 처리)
                sea = data.get("seasonality_analysis") or []
                if not isinstance(sea, list):
                    data["seasonality_analysis"] = []  # 안전한 기본값

                place = Place.objects.get(pk=place_pk)

                # 업서트 저장 (빈값은 0으로 처리하는 함수)
                obj, created = create_or_update_analysis_from_json(place, data)
                saved += 1

            except Exception as e:
                errors += 1
                messages.error(request, f"[{key}] 저장 실패: {e}")

        if saved:
            messages.success(request, f"DB 저장 완료: {saved}건")
        if errors:
            messages.error(request, f"저장 실패: {errors}건")
        return redirect(request.path)

    # 알 수 없는 action → 선택화면
    return redirect(request.path)