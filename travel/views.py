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
from django.db import connections

from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.utils import timezone
from django.db import IntegrityError

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
    parse_user_text_request,
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
    # 힐링/데이트 키워드로 보너스 → 상위 10개는 건너뛰고 그 다음 60개
    healing_keywords = (
        "힐링","휴식","온천","공원","산책","뷰","조용","분위기",
        "감성","야경","카페","데이트","로맨틱","분위기좋은",
        "드라이브","한적","산책코스"
    )
    boosted_sorted = _boost_and_sort(items, healing_keywords)
    return boosted_sorted[10:70] or boosted_sorted[:60]

def _strategy_plan_C(items):
    # 액티브/핫플 보너스 → 상위 20개 건너뛰고 그 다음 60개
    active_keywords = (
        "핫플","핫플레이스","SNS","인스타","액티비티","체험",
        "독특","이색","야경","맛집투어","트렌디","핫스팟"
    )
    boosted_sorted = _boost_and_sort(items, active_keywords)
    return boosted_sorted[20:80] or boosted_sorted[:60]

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
    
    search_yn = request.POST.get("search_yn", "").strip()
    raw_text = request.POST.get("text", "").strip()

    if search_yn == "True" and raw_text:
        user_query = parse_user_text_request(request, raw_text)
        if user_query is False:
            messages.info(request, f"로그인 후 이용해 주세요.")
            return redirect('/')
    else:
        user_query = parse_user_request(request)

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

from datetime import datetime, timedelta

@login_required
def create_diary_from_plan(request, plan_id):
    user_plan = get_object_or_404(UserSelectedPlan, id=plan_id, user=request.user)
    travel_plan = user_plan.plan

    # Check if a diary already exists for this plan
    existing_diary = Travel.objects.filter(plan=travel_plan, author_id=request.user.id).first()
    if existing_diary:
        messages.info(request, "이 플랜에 대한 다이어리가 이미 존재합니다.")
        return redirect('travel:travel_diary_detail', pk=existing_diary.pk)

    # Create a new Travel diary
    new_diary = Travel.objects.create(
        plan=travel_plan,
        name=travel_plan.title,
        start_date=user_plan.start_date,
        end_date=user_plan.end_date,
        author_id=request.user.id
    )

    # Create DiaryEntry for each place in the plan
    if 'day_plans' in travel_plan.data:
        for day_index, day_plan in enumerate(travel_plan.data['day_plans']):
            current_date = user_plan.start_date + timedelta(days=day_index)
            for place_data in day_plan:
                DiaryEntry.objects.create(
                    diary=new_diary,
                    author_id=request.user.id,
                    location=place_data.get('name'),
                    timestamp=datetime.combine(current_date, datetime.min.time()).replace(hour=12), # Noon
                    latitude=place_data.get('lat'),
                    longitude=place_data.get('lng'),
                )

    messages.success(request, "여행 플랜에서 다이어리를 성공적으로 생성했습니다.")
    return redirect('travel:travel_diary_detail', pk=new_diary.pk)


def ensure_plan_available(plan_pk):
    """
    diary_db에 TravelPlan 레코드가 존재하도록 보장한다.
    기본 DB(default)에만 존재하는 경우 복제하여 반환한다.
    """
    if not plan_pk:
        return None

    try:
        plan_id = int(plan_pk)
    except (TypeError, ValueError):
        return None

    existing_plan = TravelPlan.objects.using('diary_db').filter(pk=plan_id).first()
    if existing_plan:
        return existing_plan

    try:
        source_plan = TravelPlan.objects.using('default').get(pk=plan_id)
    except TravelPlan.DoesNotExist:
        return None

    plan_clone = TravelPlan(
        id=source_plan.pk,
        title=source_plan.title,
        user_query=source_plan.user_query,
        data=source_plan.data,
        created_at=source_plan.created_at,
    )
    # auth_user 테이블이 diary_db에 없으므로 FK 충돌을 피하기 위해 owner 정보는 비워 둔다.
    plan_clone.owner_id = None

    diary_conn = connections['diary_db']
    try:
        with diary_conn.cursor() as cursor:
            cursor.execute('PRAGMA foreign_keys=OFF')
        plan_clone.save(using='diary_db', force_insert=True)
    finally:
        with diary_conn.cursor() as cursor:
            cursor.execute('PRAGMA foreign_keys=ON')

    return plan_clone


@login_required
def create_travel_diary(request):
    user_plan_qs = UserSelectedPlan.objects.filter(user=request.user).order_by('-selected_at')
    
    processed_plans = []
    for p in user_plan_qs:
        english_areas = p.plan.user_query.get('areas', [])
        korean_areas = []
        for area_key in english_areas:
            korean_name = AREA_LABELS.get(area_key, area_key)
            korean_areas.append(korean_name)
        areas_display = ", ".join(korean_areas) if korean_areas else "전체 지역"

        processed_plans.append({
            'plan_id': p.plan.id,
            'name': p.plan.title,
            'start_date': p.start_date.strftime('%Y-%m-%d'),
            'end_date': p.end_date.strftime('%Y-%m-%d'),
            'day_plans_json': json.dumps(p.plan.data.get('day_plans', [])),
            'areas_display': areas_display,
        })

    if request.method == 'POST':
        post_data = request.POST.copy()
        user_title = post_data.get('name', '').strip()
        plan_title = post_data.get('plan_title', '').strip()

        if plan_title:
            full_title = f"{user_title} ({plan_title})" if user_title else f"({plan_title})"
            post_data['name'] = full_title.strip()

        form = TravelForm(post_data)
        if form.is_valid():
            travel_diary = form.save(commit=False)
            travel_diary.author_id = request.user.id

            plan_id_raw = post_data.get('plan_id')
            try:
                plan_id_val = int(plan_id_raw) if plan_id_raw else None
            except (TypeError, ValueError):
                plan_id_val = None

            if plan_id_val:
                synced_plan = ensure_plan_available(plan_id_val)
                if synced_plan:
                    travel_diary.plan_id = synced_plan.pk

            travel_diary.save()
            return redirect('travel:diary_home')
    else:
        form = TravelForm()
    
    return render(request, 'travel/create_travel_diary.html', {'form': form, 'user_plans': processed_plans})

@login_required
def travel_diary_detail(request, pk):
    travel_diary = get_object_or_404(Travel, pk=pk, author_id=request.user.id)
    diary_entries = travel_diary.diary_entries.all().order_by('timestamp')
    media_entries = diary_entries.filter(media_file__isnull=False).exclude(media_file__exact='')

    # Group entries by date for the timeline view
    grouped_entries = defaultdict(list)
    for entry in media_entries:
        if entry.timestamp:
            grouped_entries[entry.timestamp.date()].append(entry)

    # Try to find the associated travel plan
    display_plan = travel_diary.plan
    if not display_plan:
        # Fallback logic to find a plan if not directly linked
        plan_title_hint = None
        if travel_diary.name:
            match = re.search(r'\(([^)]+)\)\s*$', travel_diary.name)
            if match:
                plan_title_hint = match.group(1).strip()

        candidate_qs = UserSelectedPlan.objects.filter(user=request.user).select_related('plan').order_by('-selected_at')
        if travel_diary.start_date:
            candidate_qs = candidate_qs.filter(start_date=travel_diary.start_date)
        if travel_diary.end_date:
            candidate_qs = candidate_qs.filter(end_date=travel_diary.end_date)
        if plan_title_hint:
            candidate_qs = candidate_qs.filter(plan__title=plan_title_hint)

        candidate = candidate_qs.first()
        if candidate:
            display_plan = candidate.plan
            # Optionally link it for future lookups
            travel_diary.plan = ensure_plan_available(candidate.plan_id)
            travel_diary.save(update_fields=['plan'])

    # --- New Combined Data Structure for Timeline ---
    combined_days = []
    unmatched_entries = []
    remaining_entries = grouped_entries.copy()

    if display_plan and travel_diary.start_date and isinstance(display_plan.data, dict):
        plan_day_plans = display_plan.data.get('day_plans', []) or []
        if isinstance(plan_day_plans, list):
            for i, day_plan_stops in enumerate(plan_day_plans):
                current_date = travel_diary.start_date + timedelta(days=i)
                combined_days.append({
                    "day_index": i,
                    "day_number": i + 1,
                    "date": current_date,
                    "plan_stops": day_plan_stops,
                    "diary_entries": grouped_entries.get(current_date, [])
                })
                if current_date in remaining_entries:
                    del remaining_entries[current_date]

    for date, entries in sorted(remaining_entries.items()):
        unmatched_entries.extend(entries)

    # --- New Unified Location Data for Map ---
    map_locations = {}

    # 1. Process plan locations
    if display_plan and isinstance(display_plan.data, dict):
        plan_day_plans = display_plan.data.get('day_plans', []) or []
        for day_plan in plan_day_plans:
            for place in day_plan:
                try:
                    lat, lon = place.get('lat'), place.get('lng')
                    if lat and lon:
                        key = f"{float(lat):.6f},{float(lon):.6f}"
                        if key not in map_locations:
                            map_locations[key] = {
                                'lat': lat,
                                'lon': lon,
                                'name': place.get('name'),
                                'type': 'plan', # Initially marked as plan
                                'plan_details': place,
                                'diary_entries': []
                            }
                except (ValueError, TypeError):
                    continue # Skip if lat/lon are invalid

    # 2. Process diary entries and merge
    diary_entries_data_for_map = []
    for entry in media_entries:
        entry_data = {
            'id': entry.id,
            'location': entry.location,
            'timestamp': entry.timestamp.strftime("%Y년 %m월 %d일 %H시 %M분") if entry.timestamp else '',
            'latitude': entry.latitude,
            'longitude': entry.longitude,
            'media_url': entry.media_file.url if entry.media_file else '',
            'media_type': entry.media_type,
            'comment': entry.comment,
            'tags': [tag.name for tag in entry.tags.all()]
        }
        diary_entries_data_for_map.append(entry_data)

        if entry.latitude is not None and entry.longitude is not None:
            try:
                key = f"{float(entry.latitude):.6f},{float(entry.longitude):.6f}"
                if key in map_locations:
                    # Location exists from plan, update type to 'both'
                    map_locations[key]['type'] = 'both'
                    map_locations[key]['diary_entries'].append(entry_data)
                else:
                    # New location only from diary
                    map_locations[key] = {
                        'lat': entry.latitude,
                        'lon': entry.longitude,
                        'name': entry.location or '위치 정보 없음',
                        'type': 'diary',
                        'plan_details': None,
                        'diary_entries': [entry_data]
                    }
            except (ValueError, TypeError):
                continue # Skip if lat/lon are invalid

    context = {
        'travel_diary': travel_diary,
        'combined_days': combined_days,
        'unmatched_entries': unmatched_entries,
        'travel_plan': display_plan,
        'map_locations_json': json.dumps(list(map_locations.values()), ensure_ascii=False),
        'diary_entries_json': json.dumps(diary_entries_data_for_map, ensure_ascii=False), # Keep for original side panel logic if needed
    }

    return render(request, 'travel/travel_diary_detail.html', context)

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

            messages.info(request, f"회원가입 완료!! {user.username}님 환영합니다 🎉")
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
            'plan_id': plan.id,
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

    try:
        usp = UserSelectedPlan.objects.get(id=plan_id)
    except UserSelectedPlan.DoesNotExist:
        messages.error(request, "해당 여행 계획을 찾을 수 없습니다.")
    
        # 2. 메인 페이지의 URL 이름('main')으로 리다이렉트합니다.
        #    (사용자 HTML 코드에서 {% url 'main' %}을 사용하는 것을 보고 'main'으로 가정했습니다.)
        return redirect('main')

    tp = usp.plan
    data = tp.data or {}

    # travel_list.js가 기대하는 형태로 단일 플랜을 배열로 래핑
    plan_light = [{
        "id": tp.id,
        "name": tp.title or "저장된 플랜",
        "guide_text": data.get("guide_text", ""),
        "day_plans": data.get("day_plans", []),
        "day_waypoints": data.get("day_waypoints", []),  # ★ 경로/마커 핵심
    }]

    # 좌측 리스트 SSR (옵션: template에서 {{ list_html }} 그대로 씀)
    html_parts = []
    for day_idx, stops in enumerate(data.get("day_plans", []), start=1):
        html_parts.append(
            f'<div class="day-block">'
            f'  <div class="day-title" data-day="{day_idx}">Day {day_idx}'
            f'    <span class="day-total-dist"></span>'
            f'  </div>'
        )
        if stops:
            for i, stop in enumerate(stops):
                place = (stop or {}).get("place", {}) or {}
                analysis = (stop or {}).get("analysis", {}) or {}
                name = place.get("name", "")
                cat  = place.get("category", "")
                lat  = place.get("lat", "")
                lon  = place.get("lon", "")
                addr = place.get("address") or ""
                html_parts.append(
                    f'''<div class="spot-item"
                           data-day="{day_idx}"
                           data-order="{i}"
                           data-lat="{lat}"
                           data-lng="{lon}">
                          <div class="spot-order">
                            <div class="spot-order-num">{i+1}</div>
                          </div>
                          <div class="spot-meta">
                            <div class="spot-name">{name} <span class="spot-cat">({cat})</span></div>
                            <p class="spot-desc">{analysis.get("themes_csv","")}</p>
                            {f'<p class="spot-desc spot-addr">{addr}</p>' if addr else ''}
                          </div>
                        </div>'''
                )
        else:
            html_parts.append('<div class="spot-desc">추천 장소가 부족합니다.</div>')
        html_parts.append('</div>')

    context = {
        "plans_json": json.dumps(plan_light, ensure_ascii=False),   # → const PLANS = ...
        "initial_plan_idx": 0,
        "MAPBOX_ACCESS_TOKEN": getattr(settings, "MAPBOX_ACCESS_TOKEN", ""),
        "day_plans": data.get("day_plans", []),                    # Day 탭 생성용
        "list_html": mark_safe("".join(html_parts)),               # 좌측 리스트
        "user": request.user,
        'error_boolean': False,
    }
    return render(request, "travel/travel_plan_detail.html", context)

@login_required
def matching(request):
    if not request.user.is_authenticated:
        return redirect('login')
    
    travel_plans = UserSelectedPlan.objects.filter(user=request.user)

    for travel in travel_plans:
        startDate = travel.start_date
        endDate = travel.end_date

        user_areas = travel.plan.user_query.get("areas")
        # user_plan = travel.plan
        plan_user_1 = travel.user

        areas_str = ",".join(user_areas)    
        list = UserSelectedPlan.objects.filter(start_date=startDate, end_date=endDate)
        for item in list:
            user_list = []
            other_area = item.plan.user_query.get("areas")
            # other_plan = item.plan
            plan_user_2 = item.user

            if travel.id == item.id:
                continue
            
            user_list.append(plan_user_1.username)
            user_list.append(plan_user_2.username)
            users = sorted(user_list)

            room_name = f"Chat_{users[0]}_vs_{users[1]}_{areas_str}_{startDate.strftime('%Y%m%d')}-{endDate.strftime('%Y%m%d')}"

            if sorted(user_areas) == sorted(other_area):
                
                if not ChatRoom.objects.filter(room_name=room_name).exists():
                    try:
                        room, created = ChatRoom.objects.get_or_create(
                            room_name=room_name,
                            defaults={
                                "plan_user_1": str(plan_user_1),
                                "travel_plan1_pk": travel.id,
                                "plan_user_2": str(plan_user_2),
                                "travel_plan2_pk": item.id,
                            }
                        )
                        if created:
                            print("ChatRoom created:", room.pk)
                        else:
                            print("ChatRoom already existed (race avoided).")
                    except IntegrityError as e:
                        print("IntegrityError during ChatRoom create:", e)
                        # 추가 로그: 각각 PK 다시 확인
                        print("user_plan.pk (retry):", getattr(travel, "pk", None))
                        print("other_plan.pk (retry):", getattr(item, "pk", None))

    return redirect('chat')