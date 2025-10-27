from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json, re, time
from .models import ChatRoom, ChatMessage, ChatReport
from .models import Place
from django.conf import settings  # ★ Mapbox token 템플릿에 넘기려고 추가
from django.urls import reverse
from itertools import groupby
from operator import attrgetter
from django.contrib import messages
from .services.LLM_analyzer import analyze_place_with_LLM              # 네 함수 경로에 맞게 조정
from .services.analysis_loader import create_or_update_analysis_from_json  # 앞서 만든 저장 함수
from .services.recommender import (
    parse_user_request,
    get_ranked_places,
    split_into_days,
    build_map_paths,
)
from .services.itinerary_llm_gemini import generate_itinerary_guide

def _serialize_day_plans_for_js(day_plans):
    """
    day_plans: [
      [ { "place": <Place>, "analysis": <PlaceAnalysis>, "score": ... }, ... ],  # Day1
      [ { ... }, ... ],  # Day2
      ...
    ]

    -> JS에서 바로 쓸 수 있게 안전한 자료형(dict/str/float 등)만 남겨줌
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
        safe_stops.append  # (no-op line kept to mirror original structure / avoid lint error)
        safe_days.append(safe_stops)
    return safe_days


# -----------------------
# 플랜 변형 전략들
# -----------------------

def _pick_chunk(items, start_idx, size):
    """
    items: 추천 후보 리스트
    start_idx부터 size개 만큼 잘라서 반환.
    범위를 넘어가면 있는 만큼만 반환.
    """
    end_idx = start_idx + size
    return items[start_idx:end_idx]


def _boost_and_sort(items, keywords):
    """
    keywords 중 하나라도 들어있는 장소일수록 점수를 크게 올려서
    (원래 score + bonus) 기준으로 다시 정렬한 목록을 만든다.

    반환값: score 반영된 entry들만 (entry 그대로) 리스트로 돌려준다.
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
    기본 플랜:
    전체 랭킹 상위 위주를 그대로 사용.
    """
    CHUNK_START = 0
    CHUNK_SIZE = 10
    return _pick_chunk(items, CHUNK_START, CHUNK_SIZE)


def _strategy_plan_B(items):
    """
    힐링/데이트/잔잔한 분위기 위주 플랜.
    """
    healing_keywords = (
        "힐링", "휴식", "온천", "공원", "산책", "뷰", "조용", "분위기",
        "감성", "데이트", "편안한", "따뜻한", "잔잔"
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
    핫플/이색/액티비티 위주 플랜.
    """
    active_keywords = (
        "핫플", "핫플레이스", "SNS", "인스타", "액티비티", "체험",
        "독특", "이색", "야경", "맛집투어", "트렌디", "핫스팟"
    )

    boosted_sorted = _boost_and_sort(items, active_keywords)

    CHUNK_START = 6
    CHUNK_SIZE  = 10
    chunk = _pick_chunk(boosted_sorted, CHUNK_START, CHUNK_SIZE)

    if not chunk:
        chunk = _pick_chunk(boosted_sorted, 0, 10)

    return chunk


def _extract_day_waypoints(day_plans):
    """
    Leaflet + Mapbox Directions API에서 사용할 waypoints만 추출.
    day_plans: [ [ {place,...}, {place,...} ],  # Day1
                 [ {place,...}, ... ], ... ]

    return:
      [
        [ {"lat":..., "lng":...}, {"lat":..., "lng":...}, ... ],  # Day1 waypoints
        [ {...}, {...}, ... ],                                   # Day2 waypoints
        ...
      ]

    기존 build_map_paths()는 단순 직선 polyline 좌표용.
    Mapbox Directions는 실제 경로를 만들어주므로,
    이제 프론트에서 그릴 때는 단순 polyline 대신
    "이 순서대로 이동해줘" 라는 waypoints만 주면 된다.
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
    플랜 1개(A/B/C) 생성
    """
    custom_ranked = filter_strategy(ranked_places)

    total_days = user_query["total_days"]
    day_plans = split_into_days(custom_ranked, total_days)

    # ★ map_paths 대신 day_waypoints 추출
    day_waypoints = _extract_day_waypoints(day_plans)

    guide_text = generate_itinerary_guide(user_query, day_plans)

    return {
        "name": variant_name,
        "day_plans": day_plans,
        "day_waypoints": day_waypoints,  # ★ 프론트에서 Directions API 호출용
        "guide_text": guide_text,
    }

# ------------------------
# 여행 리스트 뷰
# ------------------------
def travel_list(request):
    """
    사용자 선택(취향/계절/동행 등)을 받아서
    - 추천 플랜 A/B/C 3가지 버전 생성
    - 첫 화면은 A로 렌더
    - JS에 모든 플랜(plans_json)도 내려줘서 프론트에서 버튼 클릭으로 전환
    """

    # 1. 사용자 요청 파싱
    user_query = parse_user_request(request)

    # 2. 전체 후보 장소 점수화
    ranked_all = get_ranked_places(user_query)

    # 3. 세 개의 플랜(A/B/C)
    plan_A = _build_plan_variant(user_query, ranked_all, "추천 플랜 A", _strategy_plan_A)
    plan_B = _build_plan_variant(user_query, ranked_all, "추천 플랜 B", _strategy_plan_B)
    plan_C = _build_plan_variant(user_query, ranked_all, "추천 플랜 C", _strategy_plan_C)

    plans = [plan_A, plan_B, plan_C]

    # 4. 프론트에서 쓰는 경량 버전(JSON 직렬화)
    plans_light = []
    for p in plans:
        plans_light.append({
            "name": p["name"],
            "guide_text": p["guide_text"],
            "day_waypoints": p["day_waypoints"],                 # ★ Directions용
            "day_plans": _serialize_day_plans_for_js(p["day_plans"]),
        })

    plans_json = json.dumps(plans_light, ensure_ascii=False)

    # 5. 초기 렌더는 A 플랜
    initial_plan_idx = 0
    guide_text_initial = plan_A["guide_text"]
    day_plans_initial = plan_A["day_plans"]
    day_waypoints_initial = plan_A["day_waypoints"]  # ★

    day_waypoints_json = json.dumps(day_waypoints_initial, ensure_ascii=False)

    context = {
        "plans_json": plans_json,
        "day_waypoints_json": day_waypoints_json,    # ★ JS에서 첫 로드에 사용
        "initial_plan_idx": initial_plan_idx,

        "plans": plans,
        "day_plans": day_plans_initial,
        "guide_text": guide_text_initial,
        "user_query_summary": user_query.get("raw_text") or "맞춤 여행 플랜",

        # ★ Mapbox public token을 템플릿/JS에 주입
        "MAPBOX_ACCESS_TOKEN": settings.MAPBOX_ACCESS_TOKEN,
    }

    return render(request, "travel/travel_list.html", context)


# ===== 운영툴 / 관리용: 그대로 =====

def _render_select_page(request):
    """
    내부용 LLM 분석 관리 페이지
    """
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
    (운영툴)
    GET:
      - 아직 분석 안 된 Place 나열
    POST:
      - action=analyze → LLM 돌려서 미리보기
      - action=save    → 해당 분석결과 DB 반영
    """
    if request.method == "GET":
        return _render_select_page(request)

    action = request.POST.get("action", "analyze")

    if action == "analyze":
        selected_ids = request.POST.getlist("place_ids")
        if not selected_ids:
            messages.warning(request, "선택된 장소가 없어.")
            return redirect(request.path)

        sel_ids = {int(x) for x in selected_ids if str(x).isdigit()}

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

    return redirect(request.path)


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