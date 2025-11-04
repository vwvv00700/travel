import json, re, time, uuid, random, string
from collections import defaultdict
from itertools import groupby
from operator import attrgetter
from openai import OpenAI # New import
# ======================================
# 2. 서드파티 라이브러리 (Third-Party)
# ======================================
import requests
from openai import OpenAI
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.db.models import Q # New import
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect ,get_object_or_404
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from django.db import transaction # 트랜잭션을 사용해 안전하게 처리
from django.utils.safestring import mark_safe

from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.utils import timezone

# ======================================
# 3. 로컬 앱 임포트 (Local Application)
# ======================================
from .forms import DiaryEntryForm, TravelForm
from .models import (
    Place,
    ChatRoom,
    ChatMessage,
    ChatReport,
    TravelPlan,
    UserSelectedPlan,
    DiaryEntry,
    Travel,
    PlaceAnalysis,
    UserProfile,
)

from .services.diary_summarizer import summarize_diary_with_ai, generate_tags_with_ai 
from .services.LLM_analyzer import analyze_place_with_LLM
from .services.analysis_loader import create_or_update_analysis_from_json
from .services.itinerary_llm_gemini import generate_itinerary_guide
from travel.services.matching import auto_match_and_create_room
from .services.recommender import (
    parse_user_request,
    get_ranked_places,
    split_into_days,
    build_map_paths,
)

import logging
logger = logging.getLogger('travelAgent')

# -------------------------------------------------------------------
# 여행 Plane 뷰 -------- START
# -------------------------------------------------------------------

@csrf_exempt
@require_GET
def proxy_mapbox_route(request):
    """Mapbox Directions API CORS 우회"""
    url = request.GET.get("url")
    if not url:
        return JsonResponse({"error": "missing url"}, status=400)
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        return JsonResponse(res.json(), safe=False)
    except requests.RequestException as e:
        return JsonResponse({"error": str(e)}, status=500)


def _serialize_day_plans_for_js(day_plans):
    """
    day_plans 형태:
      [
        [ { "place": <Place>, "analysis": <PlaceAnalysis>, "score": ... }, ... ],  # Day1
        [ { ... }, ... ],  # Day2
        ...
      ]

    JS로 내려보낼 때 안전한 값만 추리는 함수.
    """
    safe_days = []
    for stops in day_plans:
        safe_stops = []
        for stop in stops:
            p = stop["place"]
            a = stop["analysis"]
            safe_stops.append({
                "name": p.name,
                "category": p.category,
                "address": p.address,
                "lat": p.lat,
                "lng": p.lon,
                "themes_csv": a.themes_csv if a else "",
                "group_couple": a.group_couple if a else None,
                "season_autumn": a.season_autumn if a else None,
            })
        safe_days.append(safe_stops)
    return safe_days


def _pick_chunk(items, start_idx, size):
    """
    추천 장소들 중 start_idx부터 size개 잘라서 반환.
    """
    end_idx = start_idx + size
    return items[start_idx:end_idx]


def _boost_and_sort(items, keywords):
    """
    keywords 안의 단어가 많이 매칭될수록 score에 보너스를 줘서 재정렬.
    """
    boosted = []
    for entry in items:
        a = entry["analysis"]

        text_bucket = []
        if a:
            if a.themes_csv:
                text_bucket.append(str(a.themes_csv))
            if a.group_couple:
                text_bucket.append(str(a.group_couple))
            if a.season_autumn:
                text_bucket.append(str(a.season_autumn))

        blob = " ".join(text_bucket)

        bonus = 0.0
        for kw in keywords:
            if kw in blob:
                bonus += 5.0

        boosted.append((entry["score"] + bonus, entry))

    boosted.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in boosted]


def _strategy_plan_A(items):
    # 기본 플랜: 상위 랭킹 위주
    # 그냥 상위 많이 준다. (일단 60개 정도까지 잘라주자)
    return items[:60]

def _strategy_plan_B(items):
    # 힐링/데이트 위주: 키워드로 보너스 준 다음 많이 준다
    healing_keywords = (
        "힐링","휴식","온천","공원","산책","뷰","조용","분위기",
        "감성","야경","카페","데이트","로맨틱","분위기좋은",
        "드라이브","한적","산책코스"
    )
    boosted_sorted = _boost_and_sort(items, healing_keywords)

    return boosted_sorted[:60]

def _strategy_plan_C(items):
    # 핫플/이색/액티비티 위주
    active_keywords = (
        "핫플","핫플레이스","SNS","인스타","액티비티","체험",
        "독특","이색","야경","맛집투어","트렌디","핫스팟"
    )
    boosted_sorted = _boost_and_sort(items, active_keywords)

    return boosted_sorted[:60]


def _extract_day_waypoints(day_plans):
    """
    day_plans -> [ [ {place,...}, {place,...} ], [ ... ], ... ]

    Leaflet + Mapbox Directions API 에서 사용할 경유지 좌표만 뽑아서
    day_waypoints 형태로 만든다.

    결과 예:
    [
      [ {"lat": "...", "lng": "..."} , ... ],  # Day1
      [ {"lat": "...", "lng": "..."} , ... ],  # Day2
      ...
    ]
    """
    all_days = []
    for stops in day_plans:
        coords = []
        for stop in stops:
            p = stop["place"]
            coords.append({
                "lat": p.lat,
                "lng": p.lon,
            })
        all_days.append(coords)
    return all_days


# def _build_plan_variant(user_query, ranked_places, variant_name, filter_strategy):
#     """
#     주어진 전략(filter_strategy)으로 하나의 플랜 변형을 만든다.
#     """
#     custom_ranked = filter_strategy(ranked_places)

#     total_days = user_query["total_days"]
#     day_plans = split_into_days(custom_ranked, total_days)

#     # Mapbox Directions용 waypoints만 추출
#     day_waypoints = _extract_day_waypoints(day_plans)

#     guide_text = generate_itinerary_guide(user_query, day_plans)

#     return {
#         "name": variant_name,
#         "day_plans": day_plans,
#         "day_waypoints": day_waypoints,
#         "guide_text": guide_text,
#     }

def _extract_day_waypoints(day_plans):
    all_days = []
    for stops in day_plans:
        coords = []
        for stop in stops:
            p = stop["place"]
            coords.append({
                "lat": p.lat,
                "lng": p.lon,
            })
        all_days.append(coords)
    return all_days


def _build_plan_variant_no_guide(user_query, ranked_places, variant_name, filter_strategy):
    custom_ranked = filter_strategy(ranked_places)
    total_days = user_query["total_days"]
    day_plans = split_into_days(custom_ranked, total_days)
    day_waypoints = _extract_day_waypoints(day_plans)
    return {
        "name": variant_name,
        "day_plans": day_plans,
        "day_waypoints": day_waypoints,
    }


def _build_plan_variant_with_guide(user_query, ranked_places, filter_strategy):
    custom_ranked = filter_strategy(ranked_places)
    total_days = user_query["total_days"]
    day_plans = split_into_days(custom_ranked, total_days)
    guide_text = generate_itinerary_guide(user_query, day_plans)
    return {
        "day_plans": day_plans,
        "guide_text": guide_text,
    }


def travel_list(request):
    """
    추천 코스 결과 페이지
    - 여기서는 LLM 가이드를 즉시 안 만들고
      비동기(fetch)로 따로 받도록 함.
    - 대신 TravelPlan을 유저마다 새로 create해서 저장.
    """

    # 1) 유저 조건 파싱
    user_query = parse_user_request(request)
    print(f"DEBUG: user_query = {user_query}")

    # 2) 후보 장소 스코어링
    ranked_all = get_ranked_places(user_query)

    # 3) A/B/C 플랜 (가이드 없이)
    plan_A = _build_plan_variant_no_guide(user_query, ranked_all, "추천 플랜 A", _strategy_plan_A)
    plan_B = _build_plan_variant_no_guide(user_query, ranked_all, "추천 플랜 B", _strategy_plan_B)
    plan_C = _build_plan_variant_no_guide(user_query, ranked_all, "추천 플랜 C", _strategy_plan_C)
    plan_dicts = [plan_A, plan_B, plan_C]

    # 4) DB에 각 플랜을 "새로" 저장 (get_or_create 금지!)
    saved_models = []
    for p in plan_dicts:
        tp_obj = TravelPlan.objects.create(
            owner=request.user if request.user.is_authenticated else None,
            title=p["name"],
            user_query=user_query,
            data={
                "guide_text": "",
                "day_waypoints": p["day_waypoints"],
                "day_plans": _serialize_day_plans_for_js(p["day_plans"]),
            }
        )
        saved_models.append(tp_obj)

    # 5) 프론트에서 쓸 가벼운 배열
    plans_light = []
    for tp_obj, p_dict in zip(saved_models, plan_dicts):
        serialized_days = _serialize_day_plans_for_js(p_dict["day_plans"])
        map_paths = p_dict["day_waypoints"]

        plans_light.append({
            # 기존 필드 (절대 삭제 금지)
            "id": tp_obj.id,
            "name": p_dict["name"],
            "guide_text": "",
            "day_waypoints": map_paths,
            "day_plans": serialized_days,

            # 신규 필드 (프론트 요구사항)
            "days": serialized_days,        # alias for clarity
            "map_paths": map_paths,         # alias for clarity
        })

    plans_json = json.dumps(plans_light, ensure_ascii=False)
    # 첫 노출은 플랜 A 기준
    initial_plan_idx = 0

    context = {
        # JS 전역
        "plans_json": plans_json,
        "initial_plan_idx": initial_plan_idx,
        "MAPBOX_ACCESS_TOKEN": settings.MAPBOX_ACCESS_TOKEN,

        # SSR로 바로 표시할 값
        "plans": plans_light,
        "day_plans": plan_A["day_plans"],
        "guide_text": "생성 중...",
        "user_query_json": json.dumps(user_query, ensure_ascii=False),
    }

    return render(request, "travel/travel_list.html", context)

# def travel_list(request):
#     # 1) 검색창에서 넘어온 자연어 문장 받기
#     if request.method == "POST":
#         raw_text = request.POST.get("text", "").strip()
#         if raw_text:
#             # 유저 검색어를 파싱해서 user_query 딕셔너리로 만든다
#             user_query = parse_user_request(raw_text)
#         else:
#             # 아무 것도 안 썼으면 기본값
#             user_query = {
#                 "areas": ["강남구", "서초구"],
#                 "nights": 1,
#                 "themes": ["힐링", "맛집"],
#             }
#     else:
#         # GET으로 직접 /travel/list/ 들어올 때 기본값
#         user_query = {
#             "areas": ["강남구", "서초구"],
#             "nights": 1,
#             "themes": ["힐링", "맛집"],
#         }

#     # 2) 후보 장소 랭킹 뽑기
#     ranked_all = get_ranked_places(user_query)

#     # 3) 플랜 A/B/C 구성 (너 기존 코드 그대로 유지)
#     plan_A = _build_plan_variant_no_guide(user_query, ranked_all, "추천 플랜 A", _strategy_plan_A)
#     plan_B = _build_plan_variant_no_guide(user_query, ranked_all, "추천 플랜 B", _strategy_plan_B)
#     plan_C = _build_plan_variant_no_guide(user_query, ranked_all, "추천 플랜 C", _strategy_plan_C)

#     # 4) 템플릿 렌더
#     return render(
#         request,
#         "travel_list.html",
#         {
#             "plan_A": plan_A,
#             "plan_B": plan_B,
#             "plan_C": plan_C,
#         },
#     )


@require_GET
def generate_guide_api(request):
    """
    /travel/generate_guide/?plan_idx=0
    plan_idx: 0 -> 플랜 A 스타일
              1 -> 플랜 B 스타일
              2 -> 플랜 C 스타일
    """

    # 어떤 플랜 스타일로 만들지
    try:
        plan_idx = int(request.GET.get("plan_idx", 0))
    except ValueError:
        plan_idx = 0

    user_query = parse_user_request(request)
    ranked_all = get_ranked_places(user_query)

    strategies = [_strategy_plan_A, _strategy_plan_B, _strategy_plan_C]
    if plan_idx < 0 or plan_idx >= len(strategies):
        plan_idx = 0

    plan_info = _build_plan_variant_with_guide(user_query, ranked_all, strategies[plan_idx])

    return JsonResponse({
        "guide_text": plan_info["guide_text"],
    })

# -------------------------------------------------------------------
# 여행 Plane 뷰 -------- END
# -------------------------------------------------------------------


# ------------------------
# 실제 매칭용 채팅방 뷰
# ------------------------
@login_required
def chat_view(request, room_name):
    room = get_object_or_404(ChatRoom, room_name=room_name)
    participants = room.participants.exclude(id=request.user.id)
    partner = participants.first() if participants.exists() else None
    partner_profile = getattr(partner, 'userprofile', None) if partner else None

    return render(request, 'travel/match_chat.html', {
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

        new_rooms = auto_match_and_create_room(plan)
        message = f"{len(new_rooms)}개의 채팅방이 생성되었습니다!" if new_rooms else "매칭 가능한 사용자가 아직 없습니다."

        return render(request, "travel/travel_plan_created.html", {"plan": plan, "message": message})

    return render(request, "travel/create_travel_plan.html")


# ------------------------
# LLM 기반 장소 분석 뷰
# ------------------------
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
        "hidden_count": Place.objects.exclude(analyses__isnull=True).count(),
    }
    return render(request, "travel/select_and_analyze.html", ctx)


def analyze_selected_places_view(request):
    if request.method == "GET":
        return _render_select_page(request)

    action = request.POST.get("action", "analyze")

    if action == "analyze":
        selected_ids = request.POST.getlist("place_ids")
        if not selected_ids:
            messages.warning(request, "선택된 장소가 없어.")
            return redirect(request.path)

        sel_ids = {int(x) for x in selected_ids if str(x).isdigit()}
        available_qs = Place.objects.filter(id__in=sel_ids, analyses__isnull=True).distinct()

        kept_ids = set(available_qs.values_list("id", flat=True))
        skipped = sel_ids - kept_ids
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
            pretty_json = json.dumps(result_dict, ensure_ascii=False, indent=2)
            compact_json = json.dumps(result_dict, ensure_ascii=False, separators=(",", ":"))
            results.append({
                "place_pk": place.pk,
                "place_id": getattr(place, "place_id", None),
                "place_name": place.name,
                "analysis_dict": result_dict,
                "analysis_json_pretty": pretty_json,
                "analysis_json_compact": compact_json,
            })

        end_time = time.time()
        print(f"LLM 분석 시간 총 : {len(available_qs)} 개 ============> {round(end_time - start_time, 2)}")

        ctx = {
            "title": "분석 결과",
            "analysis_results": results,
            "post_url": request.path,
            "save_url": request.path,
        }
        return render(request, "travel/select_and_analyze.html", ctx)

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
                sea = data.get("seasonality_analysis") or []
                if not isinstance(sea, list):
                    data["seasonality_analysis"] = []
                place = Place.objects.get(pk=place_pk)
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

@login_required
def create_travel_diary(request):
    if request.method == 'POST':
        form = TravelForm(request.POST)
        if form.is_valid():
            travel_diary = form.save(commit=False)
            # travel_diary.author = request.user
            travel_diary.author_id = request.user.id
            travel_diary.save()  # 라우터가 diary_db로 자동 라우팅
            return redirect('travel:diary_home')
    else:
        form = TravelForm()
    return render(request, 'travel/create_travel_diary.html', {'form': form})

@login_required
def travel_diary_detail(request, pk):
    # travel_diary = get_object_or_404(Travel, pk=pk, author=request.user)
    travel_diary = get_object_or_404(Travel, pk=pk, author_id=request.user.id)
    diary_entries = travel_diary.diary_entries.all().order_by('timestamp')

    # Group entries by date
    grouped_entries = defaultdict(list)
    for entry in diary_entries:
        if entry.timestamp:
            grouped_entries[entry.timestamp.date()].append(entry)

    # Sort dates for consistent display
    sorted_dates = sorted(grouped_entries.keys())

    # Prepare data for template: list of (date, entries_for_date) tuples
    entries_by_date = [(date, grouped_entries[date]) for date in sorted_dates]
    
    # Prepare data for JavaScript map (ensure photo__url is correctly accessed)
    diary_entries_data = []
    for entry in diary_entries:
        diary_entries_data.append({
            'id': entry.id,
            'location': entry.location,
            'timestamp': entry.timestamp.strftime("%Y년 %m월 %d일 %H시 %i분") if entry.timestamp else '',
            'latitude': entry.latitude,
            'longitude': entry.longitude,
            # 'photo_url': entry.photo.url if entry.photo else '',
            # 'comment': entry.comment
            'media_url': entry.media_file.url if entry.media_file else '',
            'media_type': entry.media_type,
            'comment': entry.comment,
            'tags': [tag.name for tag in entry.tags.all()]
        })
    diary_entries_json = json.dumps(diary_entries_data)

    print("DEBUG: diary_entries_json content:", diary_entries_json) # Debug print

    return render(request, 'travel/travel_diary_detail.html', {
        'travel_diary': travel_diary,
        'entries_by_date': entries_by_date,
        'diary_entries_json': diary_entries_json,
    })

@login_required # Ensure user is logged in to view their diary
def diary_list(request):
    # Fetch all travel diaries for the current user
    # travel_diaries = Travel.objects.filter(author=request.user).distinct().order_by('-created_at')
    travel_diaries = Travel.objects.filter(author_id=request.user.id).distinct().order_by('-created_at')
    return render(request, 'travel/diary_list.html', {'travel_diaries': travel_diaries})

@login_required
def diary_home(request):
    return redirect('travel:diary_list')

@login_required
def upload_diary_entry(request, travel_id=None):
    travel_diary = None
    if travel_id:
        # travel_diary = get_object_or_404(Travel, pk=travel_id, author=request.user)
        travel_diary = get_object_or_404(Travel, pk=travel_id, author_id=request.user.id)

    if request.method == 'POST':
        form = DiaryEntryForm(request.POST, request.FILES, user=request.user, travel_diary=travel_diary)
        if form.is_valid():
            entry = form.save(commit=False)
            # entry.author = request.user
            entry.author_id = request.user.id
            if travel_diary:
                entry.diary = travel_diary
            entry.save()
            form.save_tags()
            if not entry.latitude and not entry.timestamp:
                messages.warning(request, "사진은 업로드되었지만, 위치나 시간 정보를 읽어올 수 없었습니다.")
            if travel_diary:
                return redirect('travel:travel_diary_detail', pk=travel_diary.pk)
            else:
                return redirect('travel:diary_home')
        else:
            print(f"DiaryEntryForm errors: {form.errors}") # Changed to print for debugging
    else:
        form = DiaryEntryForm(user=request.user, travel_diary=travel_diary)
    return render(request, 'upload.html', {'form': form, 'travel_diary': travel_diary})

@login_required
def edit_travel_diary(request, pk):
    # travel_diary = get_object_or_404(Travel, pk=pk, author=request.user)
    travel_diary = get_object_or_404(Travel, pk=pk, author_id=request.user.id)
    if request.method == 'POST':
        form = TravelForm(request.POST, instance=travel_diary)
        if form.is_valid():
            form.save()
            return redirect('travel:travel_diary_detail', pk=travel_diary.pk)
        else:
            print(f"TravelForm errors during edit: {form.errors}")  # Changed to print for debugging
    else:
        form = TravelForm(instance=travel_diary)
    return render(request, 'travel/edit_travel_diary.html', {'form': form, 'travel_diary': travel_diary})

@login_required
def edit_diary_entry(request, pk):
    # diary_entry = get_object_or_404(DiaryEntry, pk=pk, author=request.user)
    diary_entry = get_object_or_404(DiaryEntry, pk=pk, author_id=request.user.id)
    travel_diary = diary_entry.diary

    if request.method == 'POST':
        form = DiaryEntryForm(request.POST, request.FILES, instance=diary_entry, user=request.user, travel_diary=travel_diary)
        if form.is_valid():
            entry = form.save(commit=False)
            # entry.author = request.user
            entry.author_id = request.user.id
            entry.save()
            form.save_tags()
            if not entry.latitude and not entry.timestamp:
                messages.warning(request, "다이어리 항목이 수정되었지만, 사진에서 위치나 시간 정보를 읽어올 수 없었습니다.")
            return redirect('travel:travel_diary_detail', pk=travel_diary.pk)
        else:
            print(f"DiaryEntryForm errors during edit: {form.errors}")  # Changed to print for debugging
    else:
        form = DiaryEntryForm(instance=diary_entry, user=request.user, travel_diary=travel_diary)
    return render(request, 'travel/edit_diary_entry.html', {'form': form, 'diary_entry': diary_entry, 'travel_diary': travel_diary})

@login_required
def delete_diary_entry(request, pk):
    # diary_entry = get_object_or_404(DiaryEntry, pk=pk, author=request.user)
    diary_entry = get_object_or_404(DiaryEntry, pk=pk, author_id=request.user.id)
    travel_diary = diary_entry.diary

    if request.method == 'POST':
        diary_entry.delete()
        return redirect('travel:travel_diary_detail', pk=travel_diary.pk)
    return render(request, 'travel/delete_diary_entry.html', {'diary_entry': diary_entry, 'travel_diary': travel_diary})


@login_required
def summarize_diary_view(request, pk):
    travel_diary = get_object_or_404(Travel, pk=pk, author_id=request.user.id)
    
    comments = [
        entry.comment 
        for entry in travel_diary.diary_entries.all() 
        if entry.comment and entry.comment.strip()
    ]

    if not comments:
        return JsonResponse({'summary': '요약할 코멘트가 없습니다.'})

    # Import the summarizer service
    from .services.diary_summarizer import summarize_diary_with_ai
    try:
        summary = summarize_diary_with_ai(comments)
        return JsonResponse({'summary': summary})
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error generating AI summary for DiaryEntry {pk}: {e}")
        return JsonResponse({'error': f"AI 요약 중 오류가 발생했습니다: {e}"}, status=500)


@login_required
def generate_tags_view(request, pk):
    diary_entry = get_object_or_404(DiaryEntry, pk=pk, author_id=request.user.id)
    
    comment = diary_entry.comment
    if not comment or not comment.strip():
        return JsonResponse({'tags': ''}) # Return empty string if no comment

    # Import the tag generator service
    from .services.diary_summarizer import generate_tags_with_ai
    try:
        generated_tags = generate_tags_with_ai(comment)
        return JsonResponse({'tags': generated_tags})
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error generating AI tags for DiaryEntry {pk}: {e}")
        return JsonResponse({'error': f"AI 태그 생성 중 오류가 발생했습니다: {e}"}, status=500)


@require_POST
@login_required
def generate_tags_from_text_view(request):
    try:
        data = json.loads(request.body)
        comment = data.get('comment', '')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if not comment or not comment.strip():
        return JsonResponse({'tags': ''})

    try:
        generated_tags = generate_tags_with_ai(comment)
        if generated_tags == "MISSING_OPENAI_API_KEY":
            return JsonResponse({'error': "OPENAI_API_KEY 환경 변수가 설정되지 않았습니다."}, status=500)
        elif generated_tags.startswith("API_CALL_ERROR:"):
            return JsonResponse({'error': f"OpenAI API 호출 중 오류가 발생했습니다: {generated_tags[len('API_CALL_ERROR:'):].strip()}"}, status=500)
        return JsonResponse({'tags': generated_tags})
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error in generate_tags_from_text_view: {e}")
        return JsonResponse({'error': f"예상치 못한 오류가 발생했습니다: {e}"}, status=500)

import logging
logger = logging.getLogger(__name__)


@require_POST
def select_plan(request):
    if not request.user.is_authenticated:
        return JsonResponse({"status": "login_required"})

    plan_id = request.POST.get("plan_id")
    if not plan_id:
        return JsonResponse({"status": "error", "msg": "no plan_id"})

    current_time = timezone.now()

    trip_start = request.POST.get("trip_start_date", "").strip()
    trip_end   = request.POST.get("trip_end_date", "").strip()

    plan_title = request.POST.get("plan_title", "").strip()

    try:
        plan = TravelPlan.objects.get(id=plan_id)
    except TravelPlan.DoesNotExist:
        return JsonResponse({"status": "error", "msg": "plan_not_found"})

    obj, created = UserSelectedPlan.objects.get_or_create(
        user=request.user,
        plan=plan,
        start_date = trip_start,
        end_date = trip_end,
        plan_title = plan_title,
    )

    if not created:
        # 이미 있었다는 뜻
        return JsonResponse({"status": "duplicate"})

    return JsonResponse({"status": "success"})

@require_GET
def get_selected_plan_api(request):
    """
    클라이언트가 보여줄 현재 플랜/가이드 정보를 JSON으로 준다.
    /travel/get_selected_plan/?plan_idx=0
    """
    try:
        plan_idx = int(request.GET.get("plan_idx", 0))
    except ValueError:
        plan_idx = 0

    user_query = parse_user_request(request)
    ranked_all = get_ranked_places(user_query)

    strategies = [_strategy_plan_A, _strategy_plan_B, _strategy_plan_C]
    if plan_idx < 0 or plan_idx >= len(strategies):
        plan_idx = 0

    # 플랜/경로/가이드 생성
    plan_info = _build_plan_variant_with_guide(user_query, ranked_all, strategies[plan_idx])

    safe_days = _serialize_day_plans_for_js(plan_info["day_plans"])
    waypoints = _extract_day_waypoints(plan_info["day_plans"])

    return JsonResponse({
        "guide_text": plan_info["guide_text"],
        "day_plans": safe_days,
        "day_waypoints": waypoints,
    })

# ================== 회원가입 ==================
def signup_view(request):
    print("Signup view called")

    if request.method == "POST":
        email = request.POST.get("email")
        userid = request.POST.get("userid")
        password = request.POST.get("password")
        nickname = request.POST.get("nickname")
        gender = request.POST.get("gender")
        age_range = request.POST.get("age_range")
        country = request.POST.get("country")
        languages = request.POST.get("language")  # form 필드 이름과 일치
        travel_style = request.POST.get("travel_style")
        budget = request.POST.get("budget")
        smoking = request.POST.get("smoking")
        drinking = request.POST.get("drinking")
        sns = request.POST.get("sns")
        bio = request.POST.get("bio")
        mbti = request.POST.get("mbti")

        # 1. username 중복 체크
        if User.objects.filter(username=userid).exists():
            return render(request, f"{userid}", {"error": "이미 가입된 아이디입니다.."})

        try:
            # 2. User 객체 생성 (이때 Signal이 UserProfile 객체를 자동 생성함)
            # 트랜잭션을 사용하여 User 생성 실패 시 UserProfile 생성도 롤백
            with transaction.atomic():
                user = User.objects.create_user(username=userid, email=email, password=password)
                print("========== 지점 (User 생성 완료) ===========")
                
                # 3. 자동으로 생성된 UserProfile 객체를 가져와서 업데이트
                # Signal이 작동하지 않는 경우를 대비해 get() 대신 filter().first()를 쓰거나,
                # Signal이 확실하다면 user.userprofile (또는 user.profile)을 바로 사용합니다.
                
                # Note: 'userprofile'은 UserProfile 모델이 User와 연결된 기본 이름입니다.
                profile = user.userprofile 
                
                # 4. 폼에서 받은 데이터로 profile 객체 업데이트
                profile.nickname = nickname
                profile.gender = gender
                profile.age_range = age_range
                profile.country = country
                profile.languages = languages
                profile.travel_style = travel_style
                profile.budget = budget
                profile.smoking = smoking
                profile.drinking = drinking
                profile.sns = sns
                profile.bio = bio
                profile.mbti = mbti
                
                profile.save() # UserProfile 객체 저장

            # 5. 로그인 처리 및 리다이렉트
            login(request, user)
            return redirect("/")

        except Exception as e:
            # 예상치 못한 DB 오류나 다른 오류 발생 시 처리
            print(f"회원가입 중 오류 발생: {e}")
            return render(request, "registration/signup.html", {"error": "회원가입 중 오류가 발생했습니다. 다시 시도해 주세요."})
            
    else:
        return render(request, "registration/signup.html")

# ================== 로그인 ==================
class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse('/')

    def form_valid(self, form):
        user = form.get_user()
        display_name = getattr(user.userprofile, 'nickname', user.username)
        messages.success(self.request, f"{display_name}님 환영합니다! 🎉")
        return super().form_valid(form)



# ================== 로그아웃 ==================
def logout_view(request):
    logout(request)
    messages.info(request, "성공적으로 로그아웃되었습니다.")
    return redirect("/")

# ================== 비밀번호 재설정 ==================
def change_password(request):
    # 로그인 여부 확인
    if not request.user.is_authenticated:
        return redirect('login') 

    if request.method == 'POST':
        # 현재 사용자 객체와 POST 데이터로 폼 생성
        form = PasswordChangeForm(request.user, request.POST)
        
        if form.is_valid():
            # 폼에 있는 set_password와 save()가 자동으로 처리됨
            user = form.save() 
            
            # ❗️ 중요: 비밀번호 변경 후 세션 업데이트 (로그아웃 방지)
            update_session_auth_hash(request, user) 
            
            return redirect('password_change_done') # 성공 페이지로 이동
    else:
        form = PasswordChangeForm(request.user)

    return render(request, 'registration/change_password.html', {'form': form})

# ================== 비밀번호 찾기 ==================
def reset_password_instant(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        try:
            user = User.objects.get(email=email)
            
            # 1. 무작위 임시 비밀번호 생성 (예: 10자리)
            temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            
            # 2. set_password()로 비밀번호를 안전하게 저장
            user.set_password(temp_password)
            user.save()
            
            # 3. 임시 비밀번호를 사용자에게 보여주는 페이지 렌더링
            return render(request, 'password_reset_show.html', {
                'temp_password': temp_password,
                'email': email
            })
            
        except User.DoesNotExist:
            return render(request, 'registration/password_reset_form.html', {'error': '해당 이메일의 사용자가 없습니다.'})

def reset_password_form(request):
    return render(request, 'registration/password_reset_form.html')


# # ================== 내 여행 계획 보기 ==================
AREA_LABELS = {
    "gangnam": "강남구",
    "seocho": "서초구",
    "jongno": "종로구",
    "jung": "중구",
    "yongsan": "용산구",
    "seongdong": "성동구",
    "gwangjin": "광진구",
    "dongdaemun": "동대문구",
    "jungnang": "중랑구",
    "seongbuk": "성북구",
    "gangbuk": "강북구",
    "dobong": "도봉구",
    "nowon": "노원구",
    "eunpyeong": "은평구",
    "seodaemun": "서대문구",
    "mapo": "마포구",
    "yangcheon": "양천구",
    "gangseo": "강서구",
    "guro": "구로구",
    "geumcheon": "금천구",
    "yeongdeungpo": "영등포구",
    "dongjak": "동작구",
    "gwanak": "관악구",
    "songpa": "송파구",
    "gangdong": "강동구",
}

def user_travel_plans(request):

    request_path = request.path
    type = ""

    if "travel" in request_path:
        type = "travel"
    else :
        type = "main"
    
    if type == "travel":
        if not request.user.is_authenticated:
            return redirect('login')
    
        travel_plans = UserSelectedPlan.objects.filter(user=request.user)
    elif type == "main":
        travel_plans = UserSelectedPlan.objects.all()
    

    final_plans = [] # 최종 가공된 플랜들이 담길 리스트

    for plan in travel_plans:
        english_areas = plan.plan.user_query.get('areas', [])
        korean_areas = []
        
        # 영문 지역명을 한글로 치환합니다.
        for area_key in english_areas:
            # 맵에 키가 없으면 기본값으로 영문 이름을 사용하거나 건너뜁니다.
            korean_name = AREA_LABELS.get(area_key, area_key) 
            korean_areas.append(korean_name)
        if korean_areas:    
            areas_display = ", ".join(korean_areas[:-1])
            if len(korean_areas) > 1:
                areas_display += ", "
            areas_display += f"{korean_areas[-1]}"
        else:
            areas_display = "선택된 지역 없음"


        themes = plan.plan.user_query.get('themes', []) 
        mbti_guess = plan.plan.user_query.get('mbti_guess')
        
        combined_tags = []
        if mbti_guess:
            combined_tags.append(mbti_guess) # MBTI를 먼저 추가
        
        combined_tags.extend(themes) # 테마 리스트를 합칩니다.

        season = plan.plan.user_query.get('season')
        group = plan.plan.user_query.get('group')
        total_days = plan.plan.user_query.get('total_days')
        start_date = plan.start_date
        end_date = plan.end_date

        plan_title = plan.plan_title
        plan_id = plan.id

        processed_plan = {
            'areas_display': areas_display,      
            'combined_tags': combined_tags,      
            'season': season,
            'group': group,
            'total_days': total_days,
            'start_date': start_date,
            'end_date': end_date,
            'plan_title': plan_title,
            'plan_id': plan_id,
        }

        final_plans.append(processed_plan)
    
    # HTML 템플릿으로 전달할 Context 딕셔너리를 구성합니다.
    context = {
        'final_plans': final_plans, # ⭐️ 가공된 플랜 리스트를 넘깁니다.
    }

    print("context:", context)  # 디버그 출력

    if type == "travel":
        return render(request, 'travel/my_travel_plan.html', context)
    elif type == "main":
        return render(request, 'index.html', context)

    
def travel_plan_detail(request, plan_id):
    if not request.user.is_authenticated:
        return redirect('login')

    print("Requested plan_id:", plan_id)

    try:
        user_selected_plan = UserSelectedPlan.objects.get(id=plan_id, user=request.user)
    except UserSelectedPlan.DoesNotExist:
        return HttpResponse("해당 여행 계획을 찾을 수 없습니다.", status=404)
    
    travel_plan = user_selected_plan.plan
    user = user_selected_plan.user

    day_plans = travel_plan.data.get("day_plans", [])
    html_parts = []

    # print(travel_plan.data)  # 디버그 출력

    for day_idx, stops in enumerate(day_plans, start=1):
        html_parts.append(
            "<div class='spot-item-list' style='padding: 10px 0;'>"
            f"<h3 style='margin:16px 0; color:#fff; background: #333; padding: 5px 10px; width: 60px; font-size: 14px; border-radius: 4px;'>Day {day_idx}</h3>"
        )

        if not isinstance(stops, list):
            continue
        
        for order_idx, stop in enumerate(stops, start=1):
            name = stop.get("name", "")
            category = stop.get("category", "")
            address = stop.get("address", "")

            # 우리가 serialize_day_plans_for_js 에서 넣어줬던 필드들
            themes_csv = stop.get("themes_csv", "")  # 예: 힐링/휴식, 인스타감성, ...
            group_couple = stop.get("group_couple", "")  # 커플선호 80 같은 수치
            season_autumn = stop.get("season_autumn", "")  # 가을매력 90 같은 수치

            lat = stop.get("lat", 0.0)
            lng = stop.get("lng", 0.0)

            # 카드 스타일 비슷하게
            html_parts.append(
                f'<div class="spot-item" data-day={day_idx} data-order={order_idx - 1} data-lat={lat} data-lng={lng}>'
                '<div class="spot-order">'
                f'<div class="spot-order-num">{order_idx}</div>'
                # <div class="spot-order-dist">4.7 km</div>
                '</div>'

                '<div class="spot-meta">'
                f'<div class="spot-name">{name}'
                f'<span class="spot-cat">({category})</span>'
                '</div>'
                f'<p class="spot-desc">{themes_csv}</p>'
                f'<span>커플선호 : {group_couple}</span>'
                f'<span>가을매력 : {season_autumn}</span>'
                '</p>'
                f'<p class="spot-desc spot-addr">{address}</p>'
                '</div>'
                '</div>'
            )

        html_parts.append("</div>")
    list_html = mark_safe("".join(html_parts))
    # print("Generated list_html for plan detail.")
    # print(list_html)  # 디버그 출력

    context = {
        'list_html': list_html,
        'user': user,
        # 'plans_json': json.dumps(travel_plan.data, ensure_ascii=False),
        'plans_json': json.dumps(travel_plan.data, ensure_ascii=False),
        "initial_plan_idx": 0,
        "MAPBOX_ACCESS_TOKEN": settings.MAPBOX_ACCESS_TOKEN,
    }

    return render(request, 'travel/travel_plan_detail.html', context)

