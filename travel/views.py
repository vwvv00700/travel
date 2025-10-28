import json
import re
import time
from itertools import groupby
from operator import attrgetter

from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings  # Mapbox token 전달용

from .models import (
    Place,
    ChatRoom,
    ChatMessage,
    ChatReport,
    TravelPlan
)
from .services.LLM_analyzer import analyze_place_with_LLM
from .services.analysis_loader import create_or_update_analysis_from_json
from .services.recommender import (
    parse_user_request,
    get_ranked_places,
    split_into_days,
    build_map_paths,
)
from .services.itinerary_llm_gemini import generate_itinerary_guide
from .services.matching import create_chatroom_for_plan


# ------------------------
# 회원가입 뷰
# ------------------------
def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('travel:login')
    else:
        form = UserCreationForm()
    return render(request, 'chat/signup.html', {'form': form})


# ------------------------
# 여행 리스트 뷰
# ------------------------
def travel_list(request):
    print(f"request =======> {request.POST}")
    return render(request, "travel/travel_list.html")


# ------------------------
# 실제 매칭용 채팅방 뷰
# ------------------------
@login_required
def chat_view(request, room_name):
    room = get_object_or_404(ChatRoom, room_name=room_name)
    participants = room.participants.exclude(id=request.user.id)
    partner = participants.first() if participants.exists() else None
    partner_profile = getattr(partner, 'userprofile', None) if partner else None

    return render(request, 'chat/match_chat.html', {
        'room_name': room.room_name,
        'partner': partner,
        'partner_profile': partner_profile
    })


# ------------------------
# 채팅 메시지 신고 기능 (AJAX)
# ------------------------
@csrf_exempt
@login_required
def report_message(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "허용되지 않은 요청입니다."}, status=405)

    try:
        data = json.loads(request.body)
        message_id = data.get("message_id")
        reason = data.get("reason", "")
        message = ChatMessage.objects.get(id=message_id)
        reporter = request.user

        if ChatReport.objects.filter(reporter=reporter, message=message).exists():
            return JsonResponse({"success": False, "message": "이미 신고한 메시지입니다."}, status=400)

        ChatReport.objects.create(reporter=reporter, message=message, reason=reason)
        return JsonResponse({"success": True, "message": "✅ 신고가 접수되었습니다."})

    except ChatMessage.DoesNotExist:
        return JsonResponse({"success": False, "message": "❌ 메시지를 찾을 수 없습니다."}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "message": f"에러 발생: {str(e)}"}, status=400)


# ------------------------
# 여행 계획 생성
# ------------------------
@login_required
def create_travel_plan(request):
    if request.method == "POST":
        city = request.POST.get("location_city")
        start_date = request.POST.get("start_date")
        end_date = request.POST.get("end_date")

        plan = TravelPlan.objects.create(
            user=request.user,
            location_city=city,
            start_date=start_date,
            end_date=end_date,
            is_seeking_partner=True
        )

        new_rooms = create_chatroom_for_plan(plan)
        message = f"{len(new_rooms)}개의 채팅방이 생성되었습니다!" if new_rooms else "매칭 가능한 사용자가 아직 없습니다."

        return render(request, "travel/travel_plan_created.html", {"plan": plan, "message": message})

    return render(request, "travel/create_travel_plan.html")


# ------------------------
# LLM 기반 장소 분석 뷰
# ------------------------
def _render_select_page(request):
    all_places = Place.objects.filter(analyses__isnull=True).order_by("category", "name").distinct()
    grouped_places = {cat: list(items) for cat, items in groupby(all_places, key=attrgetter("category"))}
    ctx = {
        "title": "장소 LLM 분석 도구",
        "grouped_places": grouped_places,
        "post_url": request.path,
        "save_url": request.path,
        "hidden_count": Place.objects.exclude(analyses__isnull=True).count(),
    }
    return render(request, "travel/select_and_analyze.html", ctx)


def analyze_selected_places_view(request):
    if request.method == "GET":
        return _render_select_page(request)

    action = request.POST.get("action", "analyze")

    if action == "analyze":
        selected_ids = {int(x) for x in request.POST.getlist("place_ids") if str(x).isdigit()}
        available_qs = Place.objects.filter(id__in=selected_ids, analyses__isnull=True).distinct()
        skipped = selected_ids - set(available_qs.values_list("id", flat=True))
        if skipped:
            messages.warning(request, f"이미 분석된 {len(skipped)}개 장소는 제외했어.")
        if not available_qs.exists():
            messages.warning(request, "분석할 수 있는 새로운 장소가 없어.")
            return redirect(request.path)

        results = []
        start_time = time.time()
        for place in available_qs:
            place_raw_data = f"장소 이름: {place.name}\n"
            result_dict = analyze_place_with_LLM(place_raw_data)
            results.append({
                "place_pk": place.pk,
                "place_id": getattr(place, "place_id", None),
                "place_name": place.name,
                "analysis_dict": result_dict,
                "analysis_json_pretty": json.dumps(result_dict, ensure_ascii=False, indent=2),
                "analysis_json_compact": json.dumps(result_dict, ensure_ascii=False, separators=(",", ":")),
            })
        end_time = time.time()
        print(f"LLM 분석 시간 총 : {len(available_qs)} 개 ============> {round(end_time - start_time, 2)}")

        return render(request, "travel/select_and_analyze.html", {
            "title": "분석 결과",
            "analysis_results": results,
            "post_url": request.path,
            "save_url": request.path,
        })

    elif action == "save":
        key_pat = re.compile(r"^payload_(\d+)$")
        saved = errors = 0
        for key, val in request.POST.items():
            m = key_pat.match(key)
            if not m:
                continue
            try:
                place_pk = int(m.group(1))
                data = json.loads(val)
                if not isinstance(data.get("seasonality_analysis") or [], list):
                    data["seasonality_analysis"] = []
                place = Place.objects.get(pk=place_pk)
                create_or_update_analysis_from_json(place, data)
                saved += 1
            except Exception as e:
                errors += 1
                messages.error(request, f"[{key}] 저장 실패: {e}")

        if saved:
            messages.success(request, f"DB 저장 완료: {saved}건")
        if errors:
            messages.error(request, f"저장 실패: {errors}건")
        return redirect(request.path)

    return redirect(request.path)