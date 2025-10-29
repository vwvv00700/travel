from typing import Dict, List, Any
from django.db.models import Prefetch, Q
from travel.models import Place, PlaceAnalysis


def parse_user_request(request) -> Dict[str, Any]:
    """select.html에서 넘어온 사용자 입력을 파싱"""
    if request.method == "POST":
        raw_text = request.POST.get("searchBox", "").strip()
        areas = request.POST.getlist("travel_gu")
        themes = request.POST.getlist("tema")
        days_tag = request.POST.get("days", "")

        nights_map = {
            "day1": 0,
            "day2": 1,
            "day3": 2,
            "day4": 3,
            "day5": 4,
        }
        nights = nights_map.get(
            days_tag,
            1 if "1박" in raw_text else 2 if "2박" in raw_text else 1
        )
        total_days = nights + 1

        group = "couple" if ("커플" in raw_text or "데이트" in raw_text) else "friends"
        mbti_guess = "ENFP"
        season = "autumn"

        return {
            "areas": areas,
            "themes": themes,
            "nights": nights,
            "total_days": total_days,
            "group": group,
            "mbti_guess": mbti_guess,
            "season": season,
            "raw_text": raw_text,
        }

    # GET fallback
    return {
        "areas": [],
        "themes": [],
        "nights": 1,
        "total_days": 2,
        "group": "friends",
        "mbti_guess": "ENFP",
        "season": "autumn",
        "raw_text": "",
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
    """사용자 조건(지역/테마)에 맞게 필터링"""
    # ✅ 지역 필터 (정확한 필드: city_gu)
    if user["areas"]:
        area_q = Q()
        for area in user["areas"]:
            area_q |= Q(city_gu__icontains=area) | Q(address__icontains=area)
        qs = qs.filter(area_q)

    # ✅ 테마 필터 (카테고리에 부분 매칭)
    if user["themes"]:
        theme_q = Q()
        for t in user["themes"]:
            theme_q |= Q(category__icontains=t)
        qs = qs.filter(theme_q)

    return qs


def _rank_places_from_queryset(qs, user: Dict[str, Any]) -> List[Dict[str, Any]]:
    ranked = []
    for place in qs:
        pa = place.analyses.first()
        if not pa:
            continue
        s = score_place(pa, user)
        ranked.append({
            "place": place,
            "analysis": pa,
            "score": s,
        })
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked


def get_ranked_places(user: Dict[str, Any], limit_total: int = 10) -> List[Dict[str, Any]]:
    """
    1) 유저 조건으로 필터해본다
    2) 결과가 너무 적으면 전체 pool에서 인기순 fallback 추가
    """
    qs_user = _filter_queryset_for_user(_base_queryset(), user)
    ranked_user = _rank_places_from_queryset(qs_user, user)

    # ✅ fallback: 필터 결과가 너무 적을 경우 전역 인기 코스 일부 추가
    if len(ranked_user) < 3:
        qs_all = _base_queryset()
        ranked_all = _rank_places_from_queryset(qs_all, user)
        seen_ids = {r["place"].id for r in ranked_user}
        for r in ranked_all:
            if r["place"].id not in seen_ids:
                ranked_user.append(r)
            if len(ranked_user) >= limit_total:
                break

    return ranked_user[:limit_total]


def split_into_days(ranked: List[Dict[str, Any]], total_days: int) -> List[List[Dict[str, Any]]]:
    if total_days <= 0:
        total_days = 1

    per_day = max(1, len(ranked) // total_days)
    days = []
    start = 0
    for _ in range(total_days):
        end = start + per_day
        days.append(ranked[start:end])
        start = end

    if start < len(ranked):
        days[-1].extend(ranked[start:])
    return days


def build_map_paths(day_plans: List[List[Dict[str, Any]]]) -> List[List[Dict[str, float]]]:
    """지도 표시용 경로 데이터"""
    all_days_paths = []
    for day in day_plans:
        coords = []
        for stop in day:
            p = stop["place"]
            if getattr(p, "lat", None) and getattr(p, "lon", None):
                coords.append({"lat": float(p.lat), "lng": float(p.lon)})
        all_days_paths.append(coords)
    return all_days_paths
