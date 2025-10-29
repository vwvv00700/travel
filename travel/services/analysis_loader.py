import re
from typing import Any, Dict, Optional
from travel.models import PlaceAnalysis

def _score(d: Dict[str, Any], *keys, default: int = 0) -> int:
    """여러 키 후보 중 첫 값을 정수로. 없으면 0."""
    for k in keys:
        if k in d and d[k] is not None:
            try:
                return int(d[k])
            except Exception:
                try:
                    return int(float(d[k]))
                except Exception:
                    pass
    return default

def create_or_update_analysis_from_json(place, data: Dict[str, Any]):
    """
    Place 하나에 대해 분석 결과 업서트.
    비어 있는 수치값은 0으로 저장.
    """
    # ----- 텍스트(키워드/테마) -----
    kw_text = ", ".join(
        (k.get("keyword") or "").strip()
        for k in (data.get("keyword_analysis") or [])
        if k.get("keyword")
    )
    th_text = ", ".join(
        (t.get("theme_name") or "").strip()
        for t in (data.get("theme_analysis") or [])
        if t.get("theme_name")
    )

    # ----- 시즌 점수 (기본 0) -----
    season_map = {"봄": "season_spring", "여름": "season_summer",
                  "가을": "season_autumn", "겨울": "season_winter"}
    season_defaults: Dict[str, int] = {v: 0 for v in season_map.values()}
    for s in (data.get("seasonality_analysis") or []):
        name = str(s.get("season", "")).strip()
        score = _score(s, "relevance_score", "importance_score", default=0)
        if name in season_map:
            season_defaults[season_map[name]] = score

    # ----- MBTI (기본 0) -----
    mbti_defaults: Dict[str, int] = {
        "mbti_E": 0, "mbti_I": 0, "mbti_S": 0, "mbti_N": 0,
        "mbti_T": 0, "mbti_F": 0, "mbti_J": 0, "mbti_P": 0,
    }
    # 예: "E(70%) / I(30%)" 같은 문자열 전체에서 퍼센트 뽑기
    for text in (data.get("mbti_profile") or {}).values():
        for letter, val in re.findall(r"([EIFSTJNP])\((\d+)%\)", str(text)):
            mbti_defaults[f"mbti_{letter}"] = int(val)

    # ----- 방문자 그룹/연령/성별 (기본 0) -----
    visitor = data.get("visitor_analysis") or {}

    group_defaults: Dict[str, int] = {
        "group_couple": 0, "group_friends": 0,
        "group_family": 0, "group_solo": 0,
    }
    for g in (visitor.get("groups") or []):
        cat = (g.get("category") or "").strip()
        val = _score(g, "preference_rate", default=0)
        if cat == "커플":  group_defaults["group_couple"] = val
        elif cat == "친구": group_defaults["group_friends"] = val
        elif cat == "가족": group_defaults["group_family"] = val
        elif cat == "혼자": group_defaults["group_solo"] = val

    age_defaults: Dict[str, int] = {"age_20s": 0, "age_30s": 0, "age_40s": 0, "age_50plus": 0}
    for ag in (visitor.get("age_group") or []):
        age = (ag.get("age") or "").strip()
        val = _score(ag, "preference_rate", default=0)
        if "20" in age:   age_defaults["age_20s"] = val
        elif "30" in age: age_defaults["age_30s"] = val
        elif "40" in age: age_defaults["age_40s"] = val
        elif "50" in age: age_defaults["age_50plus"] = val

    gender_defaults: Dict[str, int] = {"gender_female": 0, "gender_male": 0}
    for gg in (visitor.get("gender") or []):
        gen = (gg.get("gender") or "").strip()
        val = _score(gg, "preference_rate", default=0)
        if gen == "여성": gender_defaults["gender_female"] = val
        elif gen == "남성": gender_defaults["gender_male"] = val

    # ----- defaults 조립 -----
    defaults = {
        "place_code": str(getattr(place, "place_id", place.pk)),  # 외부 ID(없으면 pk 문자열)
        "place_title": place.name,
        "raw_json": data,
        **season_defaults,
        **mbti_defaults,
        **group_defaults,
        **age_defaults,
        **gender_defaults,
    }
    # 텍스트 필드명 양쪽 대응
    
    defaults["keywords_csv"] = kw_text
    defaults["themes_csv"] = th_text

    # ----- 업서트 -----
    obj, created = PlaceAnalysis.objects.update_or_create(
        place=place,   # 같은 Place면 1건 유지
        defaults=defaults,
    )
    return obj, created
