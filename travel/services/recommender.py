from typing import Dict, List, Any
from datetime import datetime
from django.db.models import Prefetch, Q
from travel.models import Place, PlaceAnalysis, UserProfile


def parse_user_request(request) -> Dict[str, Any]:
    """
    select.html 폼에서 넘어온 사용자 입력을 파싱해서
    이후 전체 로직(travel_list, 가이드 생성, 저장 등)에서 공통으로 쓰는 user_query dict 생성.
    """

    # 기본값 (GET 등 안전 가드)
    default = {
        "areas": [],
        "themes": [],
        "nights": 1,
        "total_days": 2,
        "group": "friends",
        "mbti_guess": "ENFP",
        "season": "autumn",
        "raw_text": "",
        # 👇 새 필드
        "start_date": "",
        "end_date": "",
        "user_id": "",
    }

    if request.method != "POST":
        # 로그인한 유저 id만 보강해주면 프론트에서 user_id도 쓸 수 있음
        if request.user.is_authenticated:
            default["user_id"] = request.user.username
        return default


    raw_text = request.POST.get("searchBox", "").strip()

    # 지역들
    areas = request.POST.getlist("travel_gu")

    # 테마들
    themes = request.POST.getlist("tema")

    # 새 날짜 필드
    start_date = request.POST.get("start_date", "").strip()
    end_date   = request.POST.get("end_date", "").strip()

    # 여행 일수 계산
    # start_date, end_date가 YYYY-MM-DD 들어온다고 가정
    # 둘 다 있으면 실제 날짜 차이로 total_days / nights 계산
    nights = 1
    total_days = 2
    if start_date and end_date:
        try:
            from datetime import datetime
            fmt = "%Y-%m-%d"
            d0 = datetime.strptime(start_date, fmt)
            d1 = datetime.strptime(end_date, fmt)
            delta_days = (d1 - d0).days + 1  # 예: 10/01~10/03 -> 3일
            if delta_days < 1:
                delta_days = 1
            total_days = delta_days
            nights = max(0, delta_days - 1)
        except Exception:
            pass  # 파싱 실패하면 기본값 유지
    

    # 동행 유형
    partner = request.POST.get("partner", "").strip().lower()
    if partner in ["solo", "혼자"]:
        group = "solo"
    elif partner in ["family", "가족"]:
        group = "family"
    elif partner in ["couple", "연인"]:
        group = "couple"
    elif partner in ["friends", "친구"]:
        group = "friends"
    
    # group = "couple" if ("커플" in raw_text or "데이트" in raw_text) else "friends"


    # MBTI -> (로그인한 유저 프로필에서 가져오기)
    mbti = request.user.userprofile.mbti
    if mbti :
        mbti_guess = mbti
    else:
        mbti_guess = "ENFP"


    # 사작일 과 끝일로 계절 구분하기
    datetime_start = datetime.strptime(start_date, "%Y-%m-%d").date()
    datatime_end = datetime.strptime(end_date, "%Y-%m-%d").date()

    mid_date = datetime_start + (datatime_end - datetime_start) / 2
    if 3 <= mid_date.month <= 5:
        season = "spring"
    elif 6 <= mid_date.month <= 8:
        season = "summer"
    elif 9 <= mid_date.month <= 11:
        season = "autumn"
    else:
        season = "winter"

    # season = "autumn"
    
 # ✅ 영문 구 코드 → 한글 구 이름 변환
    DISTRICT_MAP = {
        "gangnam": "강남구",
        "seocho": "서초구",
        "songpa": "송파구",
        "gangdong": "강동구",
        "yongsan": "용산구",
        "mapo": "마포구",
        "jongno": "종로구",
        "jung": "중구",
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
        "yangcheon": "양천구",
        "gangseo": "강서구",
        "guro": "구로구",
        "geumcheon": "금천구",
        "yeongdeungpo": "영등포구",
        "dongjak": "동작구",
        "gwanak": "관악구",
    }

    # 프론트에서 영어 코드로 넘어오는 경우 한글로 변환
    areas = [DISTRICT_MAP.get(a.lower(), a) for a in areas]

    user_id_val = request.user.username if request.user.is_authenticated else ""

    return {
        "areas": areas,
        "themes": themes,
        "nights": nights,
        "total_days": total_days,
        "group": group,
        "mbti_guess": mbti_guess,
        "season": season,
        "raw_text": raw_text,
        "start_date": start_date,   # 👈 추가
        "end_date": end_date,       # 👈 추가
        "user_id": user_id_val,     # 👈 JS가 저장 클릭할 때 같이 보냄
    }


def score_place(pa: PlaceAnalysis, user: Dict[str, Any]) -> float:
    season_field = {
        "spring": "season_spring",
        "summer": "season_summer",
        "autumn": "season_autumn",
        "winter": "season_winter",
    }.get(user["season"], "season_autumn")

    group_field = {
        "couple": "group_couple",
        "friends": "group_friends",
        "family": "group_family",
        "solo": "group_solo",
    }.get(user["group"], "group_friends")

    mbti_weight = max(
        pa.mbti_E, pa.mbti_I,
        pa.mbti_S, pa.mbti_N,
        pa.mbti_T, pa.mbti_F,
        pa.mbti_J, pa.mbti_P,
    )

    base = 0
    base += getattr(pa, season_field, 0) * 1.2
    base += getattr(pa, group_field, 0) * 1.3
    base += mbti_weight * 0.5
    return base


def _base_queryset():
    return (
        Place.objects.all()
        .prefetch_related(
            Prefetch("analyses", queryset=PlaceAnalysis.objects.all())
        )
    )


def _filter_queryset_for_user(qs, user: Dict[str, Any]):
    """
    사용자 조건(지역/테마)에 맞게 필터링해서 queryset을 반환.
    절대 None을 반환하지 않도록 보장.
    """

    # 지역 필터
    areas = user.get("areas", [])
    if areas:
        area_q = Q()
        for area in areas:
            # city_gu 또는 주소에 해당 구 이름이 들어가면 허용
            area_q |= Q(city_gu__icontains=area) | Q(address__icontains=area)
        qs = qs.filter(area_q)

    # 테마 필터
    themes = user.get("themes", [])
    if themes:
        theme_q = Q()
        for t in themes:
            if not t:
                continue
            # category / name / address 안에 테마 키워드 들어가면 허용
            theme_q |= (
                Q(category__icontains=t)
                | Q(name__icontains=t)
                | Q(address__icontains=t)
            )
        qs = qs.filter(theme_q)

    return qs



def _rank_places_from_queryset(qs, user: Dict[str, Any]) -> List[Dict[str, Any]]:
    ranked = []

    # ✅ None 들어오면 그냥 빈 리스트 반환하고 끝
    if qs is None:
        return ranked

    for place in qs:
        pa = place.analyses.first()
        if not pa:
            continue

        # 기본 점수
        s = score_place(pa, user)

        # 테마 가산점
        themes = user.get("themes", [])
        for t in themes:
            t = (t or "").strip()
            if t and (
                t in (place.category or "")
                or t in (place.name or "")
                or t in (place.address or "")
            ):
                s += 5

        ranked.append({
            "place": place,
            "analysis": pa,
            "score": s,
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked




def get_ranked_places(user: Dict[str, Any], limit_total: int = 120) -> List[Dict[str, Any]]:
    """
    최종 추천 후보 생성.
    - 지역/테마 조건(_filter_queryset_for_user) 반영한 qs_user 우선
    - 부족하면 전체(qs_all)도 보긴 하지만 allowed_areas(사용자 선택 구) 밖이면 버림
    - 숙소/음식/관광 최소 갯수 채움
    - 항상 list를 반환하도록 보장
    """

    # 0. 사용자가 허용한 구
    allowed_areas = set(user.get("areas", []))

    def is_allowed_place(place_obj):
        if not allowed_areas:
            return True
        gu = (place_obj.city_gu or "").strip()
        addr = (place_obj.address or "").strip()

        # 완전 일치 OR 주소에 해당 구 이름이 들어가도 허용
        for area in allowed_areas:
            if area in gu or area in addr:
                return True
        return False

    # 1. 유저 조건 반영 버전
    qs_user = _filter_queryset_for_user(_base_queryset(), user)
    ranked_user = _rank_places_from_queryset(qs_user, user)

    # 2. 전역 fallback (부족할 때 보충용)
    qs_all = _base_queryset()
    ranked_all = _rank_places_from_queryset(qs_all, user)

    def split_by_cat(candidates: List[Dict[str, Any]]):
        acc, food, attr = [], [], []
        for r in candidates:
            cat = (r["place"].category or "").lower()
            if "accommod" in cat:
                acc.append(r)
            elif "restaurant" in cat:
                food.append(r)
            elif "attraction" in cat:
                attr.append(r)
        return acc, food, attr

    acc_u, food_u, attr_u = split_by_cat(ranked_user)
    acc_all, food_all, attr_all = split_by_cat(ranked_all)

    # 최소 확보 목표 (일정 길이에 따라 자동 조정)
    nights = user.get("nights", 0)
    total_days = nights + 1  # 0박이면 1일, 1박이면 2일 등

    # 숙소는 1박 이상이면 1개, 그 외엔 없음
    want_acc = 1 if nights >= 1 else 0

    # 일정이 길수록 음식/관광 개수를 늘림 (기본 3개 + 하루당 3개씩)
    want_food = max(3, total_days * 3)
    want_attr = max(3, total_days * 3)

    selected: List[Dict[str, Any]] = []

    # --- 숙소 확보
    if want_acc > 0:
        # 유저 기반에서 먼저
        for r in acc_u:
            already = [x for x in selected if "accommod" in (x["place"].category or "").lower()]
            if len(already) >= want_acc:
                break
            if is_allowed_place(r["place"]):
                selected.append(r)
        # 부족하면 전역에서 보충 (단 허용 구만)
        for r in acc_all:
            already = [x for x in selected if "accommod" in (x["place"].category or "").lower()]
            if len(already) >= want_acc:
                break
            if (r not in selected) and is_allowed_place(r["place"]):
                selected.append(r)

    # --- 음식 확보
    for r in food_u:
        already = [x for x in selected if "restaurant" in (x["place"].category or "").lower()]
        if len(already) >= want_food:
            break
        if (r not in selected) and is_allowed_place(r["place"]):
            selected.append(r)

    for r in food_all:
        already = [x for x in selected if "restaurant" in (x["place"].category or "").lower()]
        if len(already) >= want_food:
            break
        if (r not in selected) and is_allowed_place(r["place"]):
            selected.append(r)

    # --- 관광 확보
    for r in attr_u:
        already = [x for x in selected if "attraction" in (x["place"].category or "").lower()]
        if len(already) >= want_attr:
            break
        if (r not in selected) and is_allowed_place(r["place"]):
            selected.append(r)

    for r in attr_all:
        already = [x for x in selected if "attraction" in (x["place"].category or "").lower()]
        if len(already) >= want_attr:
            break
        if (r not in selected) and is_allowed_place(r["place"]):
            selected.append(r)

    # --- 나머지 상위 점수로 채우기
    seen_ids = {s["place"].id for s in selected}
    for r in ranked_user:
        if len(selected) >= limit_total:
            break
        if (r["place"].id not in seen_ids) and is_allowed_place(r["place"]):
            selected.append(r)
            seen_ids.add(r["place"].id)

    for r in ranked_all:
        if len(selected) >= limit_total:
            break
        if (r["place"].id not in seen_ids) and is_allowed_place(r["place"]):
            selected.append(r)
            seen_ids.add(r["place"].id)

    # ✅ 항상 리스트 반환 (절대 None 안 나가게)
    return list(selected[:limit_total])



def split_into_days(ranked: List[Dict[str, Any]], total_days: int) -> List[List[Dict[str, Any]]]:
    """
    요구사항 기반 일정 생성 로직

    규칙 요약:
    - total_days = nights + 1
    - nights == 0 (당일치기): 숙소 제외. 그냥 상위 장소들을 순서대로 잘라 일수만큼 분배.
    - nights >= 1:
        - Day1 첫 장소 = 숙소 1곳 (category 에 "accommod" 가 포함된 Place)
        - 나머지 장소들은 음식/관광 교차: restaurant -> attraction -> restaurant -> ...
        - Day2 이후도 교차 패턴 계속 이어짐 (숙소는 더 안 나옴)
    - 각 Day에는 가능한 균등하게 분배하되, 최소 1곳은 들어가게.
    """

    # 안정성 가드
    if total_days <= 0:
        total_days = 1

    # 내부 헬퍼: 카테고리 판별 (소문자 비교)
    def is_accommodation(p: Any) -> bool:
        cat = (p.category or "").lower()
        return "accommodation" in cat or "accommodations" in cat

    def is_food(p: Any) -> bool:
        cat = (p.category or "").lower()
        return "restaurant" in cat or "restaurants" in cat

    def is_attraction(p: Any) -> bool:
        cat = (p.category or "").lower()
        return "attraction" in cat or "attractions" in cat

    # ranked = [{ "place": Place, "analysis": PlaceAnalysis, "score": float }, ...]
    accommodations = []
    foods = []
    attractions = []
    etcs = []  # 혹시 위 세 분류에 안 들어간 것들 fallback

    for item in ranked:
        place = item["place"]
        if is_accommodation(place):
            accommodations.append(item)
        elif is_food(place):
            foods.append(item)
            # 유지: 순위는 이미 ranked 정렬이라 현재 순서를 그대로 사용
        elif is_attraction(place):
            attractions.append(item)
        else:
            etcs.append(item)

    # nights 계산을 위해 ranked 안에는 user_query 정보가 없다.
    # nights 정보는 views.py 쪽에서 user_query["nights"]를 들고 와서 total_days를 만들고 split_into_days에 넘겨줬지.
    # 그런데 split_into_days()에서는 nights 자체를 아직 못 받는다.
    # 해결: nights = total_days - 1 (parse_user_request에서 total_days = nights+1로 정의됨) 이 전제 사용.
    nights = max(0, total_days - 1)

    day_plans: List[List[Dict[str, Any]]] = [[] for _ in range(total_days)]

    # --- Step 1. 숙소 배치 (1박 이상일 때만)
    used_accom = None
    if nights >= 1 and accommodations:
        used_accom = accommodations[0]  # 숙소 후보 중 스코어 높은 첫 번째
        day_plans[0].append(used_accom)

    # --- Step 2. 나머지 방문 후보 풀 만들기
    # 교차 순서: 음식 -> 관광 -> 음식 -> 관광 ...
    # (당일치기일 때도 이 교차로 뽑긴 하는데, 숙소를 안 넣는 것만 다름)
    food_idx = 0
    attr_idx = 0

    alternating_list: List[Dict[str, Any]] = []

    # 우선 음식/관광에서 가능한 만큼 번갈아 뽑는다.
    # 최대 길이: 남은 전체 후보 수만큼.
    max_len = len(foods) + len(attractions) + len(etcs)
    turn_food = True  # 시작은 음식

    for _ in range(max_len):
        picked = None
        if turn_food:
            if food_idx < len(foods):
                picked = foods[food_idx]
                food_idx += 1
            elif attr_idx < len(attractions):
                # 음식 고갈되면 관광으로 대체
                picked = attractions[attr_idx]
                attr_idx += 1
            elif etcs:
                picked = etcs.pop(0)
        else:
            if attr_idx < len(attractions):
                picked = attractions[attr_idx]
                attr_idx += 1
            elif food_idx < len(foods):
                # 관광 고갈되면 음식으로 대체
                picked = foods[food_idx]
                food_idx += 1
            elif etcs:
                picked = etcs.pop(0)

        if picked is None:
            # 더 뽑을 게 없음
            break

        alternating_list.append(picked)
        # 다음 턴은 반대로
        turn_food = not turn_food


    # 1) 번갈이 루프에서 다 못 쓴 남은 음식 / 관광 / 기타를 몽땅 뒤에 붙여서 리스트를 최대한 늘린다.
    if food_idx < len(foods):
        alternating_list.extend(foods[food_idx:])

    if attr_idx < len(attractions):
        alternating_list.extend(attractions[attr_idx:])

    if etcs:
        alternating_list.extend(etcs)

    # 2) 숙소로 이미 사용된 accommodations[0]은 이후 리스트에서 제외해야 함
    if used_accom:
        used_accom_place_id = used_accom["place"].id
        alternating_list = [
            item for item in alternating_list
            if item["place"].id != used_accom_place_id
        ]

    # 당일치기(nights == 0)에서는 숙소 자체를 넣지 않아야 하므로
    # nights == 0이면 day_plans[0]이 비어있을 수 있다. 이 경우 그냥 alternating_list부터 채우는 방식으로 보정.
    # nights >=1 인 경우, day_plans[0]은 [숙소]로 시작했고 그 다음부터 alternating_list를 채운다.

    # --- Step 3. 일자별로 나누기
    # 목표: 가능한 균등 분배. 이미 Day1에 숙소가 깔려있을 수 있음.
    # 알고리즘:
    #   1) 전체 remaining 방문지 수 / total_days -> base_cnt
    #   2) 순서대로 잘라 넣되, Day1은 숙소가 있으면 base_cnt-1 만큼만 우선 넣는 식으로 조정.
    # 하루에 최소 6개씩 채우는 로직으로 변경
    remaining = list(alternating_list)
    PER_DAY_TARGET = 5
    MAX_PER_DAY     = 6 

    for day_idx in range(total_days):
        already = len(day_plans[day_idx])
        need_now = PER_DAY_TARGET - already
        if need_now < 0:
            need_now = 0

        for _ in range(need_now):
            if not remaining:
                break
            day_plans[day_idx].append(remaining.pop(0))

    # 남은 장소 순환 분배 (기존과 동일)
    day_cycle = 0
    while remaining:
        idx = day_cycle % total_days

        # 만약 이 날짜가 이미 MAX_PER_DAY를 꽉 채웠으면 건너뛰고 다음 날로 넘어감
        if len(day_plans[idx]) >= MAX_PER_DAY:
            day_cycle += 1
            if day_cycle > 9999:
                break
            continue

        day_plans[idx].append(remaining.pop(0))

        day_cycle += 1
        if day_cycle > 9999:
            break

    return day_plans

def build_map_paths(day_plans):
    """
    day_plans: [
        [ { "place": <Place>, ... }, { "place": <Place>, ... }, ... ],  # Day1
        [ { "place": <Place>, ... }, ... ],                             # Day2
        ...
    ]

    반환 형식:
    [
        [ {"lat": float, "lng": float}, {"lat": float, "lng": float}, ... ],  # Day1 경로
        [ {"lat": float, "lng": float}, ... ],                                # Day2 경로
        ...
    ]

    이 값은 views.py에서 day_waypoints / map_paths 로 넘어가서
    프론트 지도 polyline/marker 경로를 그릴 때 그대로 사용된다.
    (=> 절대 키 이름 바꾸면 안 됨: "lat", "lng")
    """

    map_paths = []

    for day in day_plans:
        coords_for_day = []
        for stop in day:
            place_obj = stop.get("place")

            # place_obj가 Place 모델 인스턴스라고 가정
            # lat/lng 필드는 Decimal 혹은 float일 수 있으므로 float 변환
            if hasattr(place_obj, "lat") and hasattr(place_obj, "lng"):
                try:
                    lat_val = float(place_obj.lat)
                    lng_val = float(place_obj.lng)
                    coords_for_day.append({
                        "lat": lat_val,
                        "lng": lng_val,
                    })
                except (TypeError, ValueError):
                    # lat/lng가 비정상일 경우 무시 (기존 기능 안 깨지도록 fail-safe)
                    pass

        map_paths.append(coords_for_day)

    return map_paths
