# views.py (정상화된 버전)

import json
import re
import time
from itertools import groupby
from operator import attrgetter

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django.urls import reverse

from .models import (
    Place,
    PlaceAnalysis,
    UserProfile,
    TravelPlan,
    UserSelectedPlan,
)

from .services.LLM_analyzer import analyze_place_with_LLM
from .services.analysis_loader import create_or_update_analysis_from_json
from .services.recommender import (
    parse_user_request,
    get_ranked_places,
    split_into_days,
    build_map_paths,  # (경로 polyline용 기존 유틸 - 일부는 안 써도 무방)
)
from .services.itinerary_llm_gemini import generate_itinerary_guide


# -------------------------------------------------------------------
# 내부 유틸
# -------------------------------------------------------------------

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
    """
    기본 플랜: 상위 랭킹 위주
    """
    CHUNK_START = 0
    CHUNK_SIZE = 10
    return _pick_chunk(items, CHUNK_START, CHUNK_SIZE)


def _strategy_plan_B(items):
    """
    힐링 / 데이트 / 잔잔한 분위기 위주
    """
    healing_keywords = (
        "힐링", "휴식", "온천", "공원", "산책", "뷰", "조용", "분위기",
        "감성", "야경", "카페", "데이트", "로맨틱", "분위기좋은",
        "드라이브", "한적", "산책코스"
    )
    boosted_sorted = _boost_and_sort(items, healing_keywords)

    CHUNK_START = 3
    CHUNK_SIZE = 10
    chunk = _pick_chunk(boosted_sorted, CHUNK_START, CHUNK_SIZE)

    if not chunk:
        chunk = _pick_chunk(boosted_sorted, 0, 10)

    return chunk


def _strategy_plan_C(items):
    """
    핫플 / 이색 / 액티비티 위주
    """
    active_keywords = (
        "핫플", "핫플레이스", "SNS", "인스타", "액티비티", "체험",
        "독특", "이색", "야경", "맛집투어", "트렌디", "핫스팟"
    )
    boosted_sorted = _boost_and_sort(items, active_keywords)

    CHUNK_START = 6
    CHUNK_SIZE = 10
    chunk = _pick_chunk(boosted_sorted, CHUNK_START, CHUNK_SIZE)

    if not chunk:
        chunk = _pick_chunk(boosted_sorted, 0, 10)

    return chunk


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


def _build_plan_variant(user_query, ranked_places, variant_name, filter_strategy):
    """
    주어진 전략(filter_strategy)으로 하나의 플랜 변형을 만든다.
    """
    custom_ranked = filter_strategy(ranked_places)

    total_days = user_query["total_days"]
    day_plans = split_into_days(custom_ranked, total_days)

    # Mapbox Directions용 waypoints만 추출
    day_waypoints = _extract_day_waypoints(day_plans)

    guide_text = generate_itinerary_guide(user_query, day_plans)

    return {
        "name": variant_name,
        "day_plans": day_plans,
        "day_waypoints": day_waypoints,
        "guide_text": guide_text,
    }


# -------------------------------------------------------------------
# 실제 화면 뷰
# -------------------------------------------------------------------

def travel_list(request):
    """
    1) 유저 요청 파싱
    2) 후보 장소 점수화
    3) 추천 플랜 A/B/C 생성
    4) TravelPlan 모델에도 저장 (id 부여)
    5) 템플릿 + JS용 context 내려주기
    """

    # 1. 유저 요청 해석 (ex. 도시, 취향, 동행, 일정일수 등)
    user_query = parse_user_request(request)

    # 2. 전체 후보 장소 스코어링
    ranked_all = get_ranked_places(user_query)

    # 3. A/B/C 플랜 구성
    plan_A = _build_plan_variant(user_query, ranked_all, "추천 플랜 A", _strategy_plan_A)
    plan_B = _build_plan_variant(user_query, ranked_all, "추천 플랜 B", _strategy_plan_B)
    plan_C = _build_plan_variant(user_query, ranked_all, "추천 플랜 C", _strategy_plan_C)
    plan_dicts = [plan_A, plan_B, plan_C]

    # 4. TravelPlan 모델로 저장(or 재사용)
    saved_models = []
    for p in plan_dicts:
        tp_obj, _created = TravelPlan.objects.get_or_create(
            title=p["name"],
            defaults={
                "data": {
                    "guide_text": p["guide_text"],
                    "day_waypoints": p["day_waypoints"],
                    "day_plans": _serialize_day_plans_for_js(p["day_plans"]),
                }
            }
        )
        # 이미 있는 title이라면 최신 data로 덮고 싶으면 여길 수정:
        # tp_obj.data = {...}; tp_obj.save()

        saved_models.append(tp_obj)

    # 5. 프론트 JS가 쓸 가벼운 PLANS 배열 구성
    plans_light = []
    for tp_obj, p_dict in zip(saved_models, plan_dicts):
        plans_light.append({
            "id": tp_obj.id,
            "name": p_dict["name"],
            "guide_text": p_dict["guide_text"],
            "day_waypoints": p_dict["day_waypoints"],
            "day_plans": _serialize_day_plans_for_js(p_dict["day_plans"]),
        })

    plans_json = json.dumps(plans_light, ensure_ascii=False)

    # 첫 노출은 플랜 A 기준
    initial_plan_idx = 0

    context = {
        # JS 전역으로 내려줄 것들
        "plans_json": plans_json,
        "initial_plan_idx": initial_plan_idx,
        "MAPBOX_ACCESS_TOKEN": settings.MAPBOX_ACCESS_TOKEN,

        # 템플릿 서버 렌더에 바로 쓸 것들
        "plans": plans_light,
        "day_plans": plan_A["day_plans"],
        "guide_text": plan_A["guide_text"],
    }

    return render(request, "travel/travel_list.html", context)


# -------------------------------------------------------------------
# 관리/운영 도구: 분석 뷰 (원본에서 가져온 부분)
# -------------------------------------------------------------------

def _render_select_page(request):
    # 분석 안 된 Place만 뽑아서 카테고리별로 그룹핑
    all_places = (
        Place.objects
        .filter(analyses__isnull=True)
        .order_by("category", "name")
        .distinct()
    )

    grouped_places = {
        cat: list(items)
        for cat, items in groupby(all_places, key=attrgetter("category"))
    }

    ctx = {
        "title": "장소 LLM 분석 도구",
        "grouped_places": grouped_places,
        "post_url": request.path,
        "save_url": request.path,
        "hidden_count": Place.objects.exclude(analyses__isnull=True).count(),
    }
    return render(request, "travel/select_and_analyze.html", ctx)


def analyze_selected_places_view(request):
    """
    운영툴:
    GET  -> 아직 분석 안 된 Place 목록
    POST -> action=analyze / action=save
    """
    if request.method == "GET":
        return _render_select_page(request)

    action = request.POST.get("action", "analyze")

    if action == "analyze":
        selected_ids = request.POST.getlist("place_ids")
        if not selected_ids:
            messages.warning(request, "선택된 장소가 없어.")
            return redirect(request.path)

        sel_ids = {
            int(x) for x in selected_ids
            if str(x).isdigit()
        }

        available_qs = (
            Place.objects
            .filter(id__in=sel_ids, analyses__isnull=True)
            .distinct()
        )

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
            place_raw_data = (
                f"장소 이름: {place.name}\n"
                f"카테고리: {place.category}\n"
                f"주소: {place.address}\n"
                f"평점: {place.rating}\n"
            )

            result_dict = analyze_place_with_LLM(place_raw_data)

            pretty_json  = json.dumps(result_dict, ensure_ascii=False, indent=2)
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
        print(
            f"LLM 분석 시간 총 : {len(available_qs)} 개 "
            f"==============> {round(end_time - start_time, 2)}초"
        )

        ctx = {
            "title": "분석 결과",
            "analysis_results": results,
            "post_url": request.path,
            "save_url": request.path,
        }
        return render(request, "travel/select_and_analyze.html", ctx)

    elif action == "save":
        key_pat = re.compile(r"^payload_(\d+)$")
        saved = 0
        errors = 0

        for key, val in request.POST.items():
            m = key_pat.match(key)
            if not m:
                continue

            try:
                place_pk = int(m.group(1))
                data = json.loads(val)

                # 안정성 보정
                seasonality = data.get("seasonality_analysis") or []
                if not isinstance(seasonality, list):
                    data["seasonality_analysis"] = []

                place = Place.objects.get(pk=place_pk)

                _, created = create_or_update_analysis_from_json(place, data)
                saved += 1

            except Exception as e:
                errors += 1
                messages.error(request, f"[{key}] 저장 실패: {e}")

        if saved:
            messages.success(request, f"DB 저장 완료: {saved}건")
        if errors:
            messages.error(request, f"저장 실패: {errors}건")

        return redirect(request.path)

    # fallback
    return redirect(request.path)


# -------------------------------------------------------------------
# 로그인 / 회원가입 / 로그아웃 / 플랜 선택 저장
# -------------------------------------------------------------------

def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)
        if user is None:
            messages.error(request, "아이디 또는 비밀번호가 올바르지 않습니다.")
            return render(request, "travel/login.html")

        login(request, user)
        return redirect("/")

    return render(request, "travel/login.html")


def signup_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        email    = request.POST.get("email")
        password = request.POST.get("password")

        # 아이디 중복 체크
        if User.objects.filter(username=username).exists():
            messages.error(request, "이미 존재하는 아이디입니다.")
            return render(request, "travel/login.html")

        # User 생성
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
        )

        # UserProfile 생성
        UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "nickname": username,
                "preferred_style": "",
                "bio": "",
            }
        )

        messages.success(request, "회원가입이 완료되었습니다! 로그인해주세요 🙌")
        return redirect("/travel/login/")

    # GET이면 그냥 로그인 페이지로
    return render(request, "travel/login.html")


def logout_view(request):
    logout(request)
    return redirect("/")


@require_POST
def select_plan(request):
    # 로그인 안 한 경우
    if not request.user.is_authenticated:
        return JsonResponse({"status": "login_required"})

    plan_id = request.POST.get("plan_id")
    if not plan_id:
        return JsonResponse({"status": "error", "msg": "no plan_id"})

    try:
        plan = TravelPlan.objects.get(id=plan_id)
    except TravelPlan.DoesNotExist:
        return JsonResponse({"status": "error", "msg": "plan_not_found"})

    # 유저-플랜 매핑 (중복 저장 방지)
    UserSelectedPlan.objects.get_or_create(
        user=request.user,
        plan=plan,
    )

    return JsonResponse({"status": "success"})
