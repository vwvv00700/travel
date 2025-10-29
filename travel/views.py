# views.py (정상화된 버전)
import json, re, time
from itertools import groupby
from operator import attrgetter
from openai import OpenAI # New import

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q # New import
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST, require_GET
from django.urls import reverse
from django.shortcuts import get_object_or_404

from .models import (
    Place,
    PlaceAnalysis,
    UserProfile,
    TravelPlan,
    UserSelectedPlan,
    DiaryEntry,
    Travel,
)

from .services.LLM_analyzer import analyze_place_with_LLM
from .services.analysis_loader import create_or_update_analysis_from_json
from .services.itinerary_llm_gemini import generate_itinerary_guide
from .services.recommender import (
    parse_user_request,
    get_ranked_places,
    split_into_days,
    build_map_paths,
)

from .forms import DiaryEntryForm, TravelForm # Import TravelForm
from collections import defaultdict # Import defaultdict



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

@login_required
def create_travel_diary(request):
    if request.method == 'POST':
        form = TravelForm(request.POST)
        if form.is_valid():
            travel_diary = form.save(commit=False)
            travel_diary.author = request.user
            travel_diary.save()  # 라우터가 diary_db로 자동 라우팅
            return redirect('travel:diary_home')
    else:
        form = TravelForm()
    return render(request, 'travel/create_travel_diary.html', {'form': form})

@login_required
def travel_diary_detail(request, pk):
    travel_diary = get_object_or_404(Travel, pk=pk, author=request.user)
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
            'photo_url': entry.photo.url if entry.photo else '',
            'comment': entry.comment
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
    travel_diaries = Travel.objects.filter(author=request.user).distinct().order_by('-created_at')
    return render(request, 'travel/diary_list.html', {'travel_diaries': travel_diaries})

@login_required
def diary_home(request):
    return redirect('travel:diary_list')

@login_required
def upload_diary_entry(request, travel_id=None):
    travel_diary = None
    if travel_id:
        travel_diary = get_object_or_404(Travel, pk=travel_id, author=request.user)

    if request.method == 'POST':
        form = DiaryEntryForm(request.POST, request.FILES, user=request.user, travel_diary=travel_diary)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.author = request.user
            if travel_diary:
                entry.travel = travel_diary
            entry.save()
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
    travel_diary = get_object_or_404(Travel, pk=pk, author=request.user)
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
    diary_entry = get_object_or_404(DiaryEntry, pk=pk, author=request.user)
    travel_diary = diary_entry.travel

    if request.method == 'POST':
        form = DiaryEntryForm(request.POST, request.FILES, instance=diary_entry, user=request.user, travel_diary=travel_diary)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.author = request.user
            entry.save()
            return redirect('travel:travel_diary_detail', pk=travel_diary.pk)
        else:
            print(f"DiaryEntryForm errors during edit: {form.errors}")  # Changed to print for debugging
    else:
        form = DiaryEntryForm(instance=diary_entry, user=request.user, travel_diary=travel_diary)
    return render(request, 'travel/edit_diary_entry.html', {'form': form, 'diary_entry': diary_entry, 'travel_diary': travel_diary})

@login_required
def delete_diary_entry(request, pk):
    diary_entry = get_object_or_404(DiaryEntry, pk=pk, author=request.user)
    travel_diary = diary_entry.travel

    if request.method == 'POST':
        diary_entry.delete()
        return redirect('travel:travel_diary_detail', pk=travel_diary.pk)
    return render(request, 'travel/delete_diary_entry.html', {'diary_entry': diary_entry, 'travel_diary': travel_diary})

from django.http import JsonResponse


@login_required
def travel_agent_viewer(request):
    if request.method == 'POST':
        # Store selections in session
        request.session['selected_districts'] = request.POST.getlist('travel_gu')
        request.session['travel_days'] = request.POST.get('days')
        request.session['selected_themes'] = request.POST.getlist('tema')

        context = {
            'selected_districts': request.session['selected_districts'],
            'travel_days': request.session['travel_days'],
            'selected_themes': request.session['selected_themes'],
        }
        return render(request, 'travel/travel_agent_viewer.html', context)
    
    # If accessed via GET or other methods, redirect to the start
    return redirect('travel:travel_list')

import logging

# ... (other imports)

logger = logging.getLogger(__name__)

# ... (other views)

@login_required
def get_ai_recommendations(request):
    # --- Start of New Logging ---
    logger.info(f"[AI Recommendations] Session - Districts: {request.session.get('selected_districts')}")
    logger.info(f"[AI Recommendations] Session - Days: {request.session.get('travel_days')}")
    logger.info(f"[AI Recommendations] Session - Themes: {request.session.get('selected_themes')}")
    # --- End of New Logging ---
    try:
        client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

        selected_districts = request.session.get('selected_districts', [])
        travel_days = request.session.get('travel_days', '1')
        selected_themes = request.session.get('selected_themes', [])

        # --- Start of New Fallback Logic ---
        # --- Start of District Name Mapping ---
        district_map = {
            'jongno': '종로구', 'junggu': '중구', 'yongsan': '용산구', 'seongdong': '성동구',
            'gwangjin': '광진구', 'dongdaemun': '동대문구', 'jungnang': '중랑구', 'seongbuk': '성북구',
            'gangbuk': '강북구', 'dobong': '도봉구', 'nowon': '노원구', 'eunpyeong': '은평구',
            'seodaemun': '서대문구', 'mapo': '마포구', 'yangcheon': '양천구', 'gangseo': '강서구',
            'guro': '구로구', 'geumcheon': '금천구', 'yeongdeungpo': '영등포구', 'dongjak': '동작구',
            'gwanak': '관악구', 'seocho': '서초구', 'gangnam': '강남구', 'songpa': '송파구',
            'gangdong': '강동구'
        }
        korean_districts = [district_map.get(d.lower()) for d in selected_districts if district_map.get(d.lower())]
        logger.info(f"Mapped Korean districts for query: {korean_districts}")
        # --- End of District Name Mapping ---

        fallback_activated = False

        def perform_query(filter_by_theme):
            base_query = Place.objects.all()
            if korean_districts:
                district_q = Q()
                for district in korean_districts:
                    district_q |= Q(city_gu__icontains=district)
                base_query = base_query.filter(district_q)

            if filter_by_theme and selected_themes:
                theme_q = Q()
                for theme in selected_themes:
                    theme_q |= Q(analysis__themes_csv__icontains=theme)
                base_query = base_query.filter(theme_q).distinct()
            
            # Query each category separately
            restaurants = base_query.filter(category='restaurants').order_by('-rating')
            attractions = base_query.filter(category='attractions').order_by('-rating')
            accommodations = base_query.filter(category='accommodations').order_by('-rating')
            return attractions, restaurants, accommodations

        # 1. Initial query with theme filter
        attractions_query, restaurants_query, accommodations_query = perform_query(filter_by_theme=True)

        # 2. Fallback query without theme filter if initial result is empty
        if not attractions_query.exists() and not restaurants_query.exists():
            fallback_activated = True
            logger.info("Fallback activated: No results with theme filter, querying by district only.")
            attractions_query, restaurants_query, accommodations_query = perform_query(filter_by_theme=False)

        def get_place_data(place):
            return {
                'id': place.id,
                'name': place.name,
                'address': place.address,
                'rating': place.rating,
                'reviewCnt': place.reviewCnt,
                'themes': place.analysis.themes_csv.split(',') if hasattr(place, 'analysis') and place.analysis.themes_csv else [],
            }

        relevant_attractions = [get_place_data(p) for p in attractions_query.select_related('analysis')[:30]]
        relevant_restaurants = [get_place_data(p) for p in restaurants_query.select_related('analysis')[:40]]
        relevant_accommodations = [get_place_data(p) for p in accommodations_query.select_related('analysis')[:20]]

        logger.info(f"Found {len(relevant_attractions)} attractions, {len(relevant_restaurants)} restaurants, {len(relevant_accommodations)} accommodations.")
        if not relevant_attractions and not relevant_restaurants:
            return JsonResponse({"trip_plan": [], "suggested_accommodation": None})

        # 2. Construct OpenAI Prompt
        system_message = """
        You are an expert travel planner in Korea, tasked with creating a detailed itinerary.
        You will receive user preferences and lists of available attractions, restaurants, and accommodations for the selected area.

        **Your Task:**
        1.  **Create a Day-by-Day Plan:** Generate a travel plan for the number of days the user specified.
        2.  **Structure by District:** Group the recommendations by the districts the user selected. For each day, try to focus on places within one district to minimize travel time.
        3.  **Daily Itinerary Logic:** For each day in the plan:
            a.  Select one primary tourist attraction from the `attractions` list that fits the user's themes.
            b.  Based on the attraction's location, find one nearby, high-rated restaurant from the `restaurants` list for **lunch** and one for **dinner**.
            c.  You do not need to recommend breakfast.
        4.  **Accommodation:** From the `accommodations` list, select **only one** high-rated and centrally located accommodation for the entire trip. It should be reasonably accessible to the recommended attractions.
        5.  **Output Format:** You MUST provide the output in a single JSON object with two top-level keys:
            - `suggested_accommodation`: An object containing the details of the single recommended accommodation.
            - `trip_plan`: An array of objects, where each object represents a day's plan.

        **JSON Structure Example:**
        ```json
        {
          "suggested_accommodation": {
            "name": "Hotel ABC",
            "address": "123 Main St, Gangnam-gu",
            "rating": 4.8,
            "recommendation_reason": "Centrally located with excellent reviews."
          },
          "trip_plan": [
            {
              "day": 1,
              "district": "강남구",
              "attraction": {
                  "name": "COEX Aquarium",
                  "address": "513, Yeongdong-daero, Gangnam-gu",
                  "recommendation_reason": "A great spot for family fun and fits the 'healing' theme."
              },
              "meals": {
                "lunch": {
                    "name": "Gangnam Gyoza",
                    "address": "Nearby COEX",
                    "recommendation_reason": "Famous for its dumplings, a short walk from the aquarium."
                },
                "dinner": {
                    "name": "Tosokchon Samgyetang",
                    "address": "Another part of Gangnam",
                    "recommendation_reason": "A hearty and healthy dinner after a long day."
                }
              }
            }
          ]
        }
        ```
        **Important:** Adhere strictly to this JSON structure. Do not add extra commentary outside of the JSON object.
        """
        
        fallback_info = ""
        if fallback_activated:
            fallback_info = "Note: We could not find places that perfectly matched your selected themes. However, here are some popular places in your chosen districts. Please create the best possible course from this list, keeping the original themes in mind if possible."

        # travel_days is like 'day4', we need the number 4.
        num_days = int(''.join(filter(str.isdigit, travel_days))) if travel_days else 1

        user_message_content = f"""
        {fallback_info}

        **User Preferences:**
        - Travel Duration: {num_days} day(s)
        - Selected Districts: {korean_districts}
        - Selected Themes: {selected_themes}

        **Available Places:**
        - Attractions: {json.dumps(relevant_attractions, ensure_ascii=False, indent=2)}
        - Restaurants: {json.dumps(relevant_restaurants, ensure_ascii=False, indent=2)}
        - Accommodations: {json.dumps(relevant_accommodations, ensure_ascii=False, indent=2)}

        Please generate the trip plan in the specified JSON format.
        """

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message_content}
        ]

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            response_format={"type": "json_object"}
        )
        
        llm_response_content = response.choices[0].message.content
        parsed_response = json.loads(llm_response_content)
        
        return JsonResponse(parsed_response)

    except json.JSONDecodeError as e:
        logger.error(f"LLM JSON parsing failed: {e}. Raw response: {llm_response_content}")
        return JsonResponse({"error": f"AI 응답을 처리하는 중 오류가 발생했습니다." }, status=500)
    except Exception as e:
        logger.error(f"An error occurred in get_ai_recommendations: {e}")
        return JsonResponse({"error": f"AI 추천을 생성하는 중 오류가 발생했습니다: {e}"}, status=500)

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message_content}
        ]

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            response_format={"type": "json_object"}
        )
        
        llm_response_content = response.choices[0].message.content
        parsed_response = json.loads(llm_response_content)
        
        recommendations = parsed_response.get("recommendations", [])
        
        if not recommendations:
            for key, value in parsed_response.items():
                if isinstance(value, list) and all(isinstance(item, dict) and "name" in item for item in value):
                    recommendations = value
                    break

        return JsonResponse({"recommendations": recommendations})

    except json.JSONDecodeError as e:
        logger.error(f"LLM JSON parsing failed: {e}. Raw response: {llm_response_content}")
        return JsonResponse({"error": f"AI 응답을 처리하는 중 오류가 발생했습니다." }, status=500)
    except Exception as e:
        logger.error(f"An error occurred in get_ai_recommendations: {e}")
        return JsonResponse({"error": f"AI 추천을 생성하는 중 오류가 발생했습니다: {e}"}, status=500)

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