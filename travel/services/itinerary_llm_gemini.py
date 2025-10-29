import os
import google.generativeai as genai
# from travel.models import Place, PlaceAnalysis

# ✅ 동행 유형/계절/지역 코드 → 한글 라벨 매핑
GROUP_LABELS = {
    "couple": "연인",
    "friends": "친구",
    "family": "가족",
    "solo": "혼자",
}

SEASON_LABELS = {
    "spring": "봄",
    "summer": "여름",
    "autumn": "가을",
    "winter": "겨울",
}

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


# ---------- 헬퍼 ----------
def _label_group(group_code: str) -> str:
    return GROUP_LABELS.get(group_code, group_code)


def _label_season(season_code: str) -> str:
    return SEASON_LABELS.get(season_code, season_code)


def _label_area_list(areas: list[str]) -> str:
    if not areas:
        return "미정"
    labeled = [AREA_LABELS.get(a, a) for a in areas]
    # 중복 제거
    deduped = []
    for x in labeled:
        if x not in deduped:
            deduped.append(x)
    # return ", ".join(deduped)
    return deduped


# ---------- 추천 동선 요약 ----------
def _build_outline_user_friendly(user_query, day_plans):
    outline_lines = []
    for day_idx, stops in enumerate(day_plans, start=1):
        outline_lines.append(f"[Day {day_idx} 추천 동선]")
        for order, stop in enumerate(stops, start=1):
            place = stop["place"]
            analysis = stop["analysis"]

            cat_map = {
                "restaurants": "맛집",
                "accommodations": "숙소",
                "attractions": "관광지",
                "cafe": "카페",
            }
            cat_label = cat_map.get(place.category, place.category)
            theme_preview = ""
            if analysis.themes_csv:
                parts = [p.strip() for p in analysis.themes_csv.split(",")]
                theme_preview = " · ".join(parts[:2])
            addr = place.address or ""
            line_bits = [f"{order}. {place.name} ({cat_label})"]
            if theme_preview:
                line_bits.append(f"- {theme_preview}")
            if addr:
                line_bits.append(f"- {addr}")
            outline_lines.append(" ".join(line_bits))
        outline_lines.append("")
    return "\n".join(outline_lines).strip()


# ---------- LLM Prompt ----------
def _build_prompt_for_llm(user_query, outline_for_user):
    areas_text = _label_area_list(user_query["areas"])
    themes_text = ", ".join(user_query["themes"]) if user_query["themes"] else "미정"
    group_label = _label_group(user_query["group"])
    season_label = _label_season(user_query["season"])
    nights = user_query["nights"]
    total_days = user_query["total_days"]
    mbti_guess = user_query["mbti_guess"]

    prompt = f"""
당신은 여행 코디네이터입니다.
아래 정보를 바탕으로 실제 사용자에게 보여줄 최종 여행 가이드를 작성하세요.

[여행 정보 요약]
- 여행 지역: {areas_text}
- 여행 기간: {nights}박 {total_days}일
- 동행: {group_label}
- 예상 MBTI: {mbti_guess}
- 계절: {season_label}
- 요청사항: {user_query['raw_text'] or '없음'}
- 선호 테마: {themes_text}

[추천 동선]
{outline_for_user}

작성 규칙 (아주 중요):
1. 출력은 한국어만 사용하세요.
2. Day 1, Day 2 순서로 작성하고, 각 Day 안에서는
   "아침", "점심", "오후", "저녁", "하루 요약" 순으로만 작성하세요.
3. 각 시간대 설명은 **최대 2문장**만 작성하세요.
   - 첫 문장은 분위기나 감정을 표현 (예: “가을 햇살 아래에서 친구와 커피 한잔으로 시작해보세요.”)
   - 두 번째 문장은 실용 정보 (이동, 위치, 교통 등)
4. 각 문단은 줄바꿈으로만 구분하고, 들여쓰기나 리스트 기호(*, -, 번호, **)를 사용하지 마세요.
   예) "☕ 아침: 홍대의 작은 카페에서 브런치를 시작하세요. 지하철로 쉽게 이동할 수 있습니다."
5. 마크다운 문법(##, ####, **굵게**, *, -, 번호 목록 등)은 절대 사용하지 마세요.
6. 라인 앞에는 간단한 이모지 하나만 사용하세요. (예: ☕, 🍜, 🌇, 🌉, 👫)
7. 문장은 최대한 짧게, 핵심만 부드럽게 전달하세요. (~15~25자 내외 문장 위주)
8. '하루 요약'은 한 문장으로, 감성적으로 마무리하세요.
9. 규칙이나 메타설명은 출력하지 마세요. 최종 결과만 보여주세요.
이제 위 규칙을 지키면서 최종 여행 가이드를 완성하세요.
""".strip()

    return prompt



# ---------- 메인 함수 ----------
def generate_itinerary_guide(user_query, day_plans) -> str:
    outline_for_user = _build_outline_user_friendly(user_query, day_plans)
    prompt = _build_prompt_for_llm(user_query, outline_for_user)

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        fallback_preview = (
            f"[여행 정보 요약]\n"
            f"여행 지역: {_label_area_list(user_query['areas'])}\n"
            f"여행 기간: {user_query['nights']}박 {user_query['total_days']}일\n"
            f"동행: {_label_group(user_query['group'])}\n"
            f"계절: {_label_season(user_query['season'])}\n\n"
            f"[추천 동선]\n{outline_for_user}\n\n"
            f"(⚠ 현재 LLM API 키가 설정되지 않아 예시 요약만 표시 중입니다.)"
        )
        return fallback_preview

    genai.configure(api_key=api_key)

    # ✅ list_models()에서 generateContent 지원한다고 나온 모델 중 하나 선택
    #    빠르고 가볍게 쓸 거면 flash, 더 품질 원하면 pro.
    #    일단 무료/응답 빠른 쪽 우선: gemini-2.5-flash
    model = genai.GenerativeModel("models/gemini-2.5-flash")

    try:
        response = model.generate_content(prompt)

        # 표준 응답 경로
        text = getattr(response, "text", None)
        if text:
            return text.strip()

        # fallback 경로 (일부 버전에서 candidates 배열로만 내려오는 경우)
        return response.candidates[0].content.parts[0].text.strip()

    except Exception as e:
        print("LLM ERROR >>>", repr(e))
        return f"[LLM 호출 에러 - runtime] {e}"

