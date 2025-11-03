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
    return ", ".join(deduped)
    # return deduped


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
아래 정보를 바탕으로 실제 사용자에게 보여줄 최종 여행 일정을 작성하세요.

[여행 정보 요약]
- 여행 지역: {areas_text}
- 여행 기간: {nights}박 {total_days}일
- 동행: {group_label}
- 예상 MBTI: {mbti_guess}
- 계절: {season_label}
- 요청사항: {user_query['raw_text'] or '없음'}
- 선호 테마: {themes_text}

[추천 동선 후보지]
{outline_for_user}

출력 형태 (아주 중요):
각 Day마다 아래 2개 섹션을 이 순서로만 출력하세요.
1) 일일 시간표
2) 상세 가이드

각 Day는 이렇게 생겨야 합니다:

Day 1
일일 시간표
07:30 - 08:00 | 기상 & 준비 (숙소) | 가볍게 씻고 옷 챙기기
08:00 - 09:00 | 아침식사 (카페 A) | 부드러운 브런치로 시작
09:00 - 10:30 | 관광 (명소 B) | 사진 찍기 좋은 포인트
10:30 - 11:00 | 이동 (지하철) | 다음 목적지로 이동
...
22:30 - 23:30 | 숙소 휴식 | 샤워 후 취침 준비

상세 가이드
☀ 아침
⏰ 08:00~09:00 (총 1시간 머무르기)
😊 부드러운 브런치로 하루를 천천히 연다는 느낌
🚶 숙소에서 도보 이동 가능, 사람 적은 시간대라 여유로움

🍜 점심
⏰ 12:00~13:00 (총 1시간 머무르기)
😊 현지식 느낌의 든든한 한 끼로 에너지 충전
🚶 지하철 2정거장 거리라 이동 부담 적음

🌇 오후
⏰ 13:00~15:00 (총 2시간 머무르기)
😊 사진 찍고 산책하며 여유롭게 즐기는 코스
🚶 주변 상점, 카페 가까워 쉬어가기 좋음

🌉 저녁
⏰ 18:30~20:00 (총 1시간 30분 머무르기)
😊 밤 분위기와 조명 덕분에 데이트 무드가 살아남
🚶 저녁 식사 후 바로 숙소 방향으로 이동 가능

🌙 하루 요약: 천천히 걷고 맛있게 먹으면서 서로 대화 많이 할 수 있는 하루.

아주 중요한 제약사항 (지켜야 출력 품질이 인정됨):
1. 일일 시간표에 나온 시간 블록만 사용해서 상세 가이드의 ⏰ 시간을 채워야 합니다.
   - 예: 상세 가이드의 아침(⏰ 08:00~09:00)은 반드시 일일 시간표 안에 같은 시간 구간이 존재해야 합니다.
   - 일일 시간표에 없는 시간대(예: 16:10~17:40)를 상세 가이드에 새로 만들지 마세요.
2. "아침 / 점심 / 오후 / 저녁"은 일일 시간표의 여러 블록을 묶어 요약해도 되지만,
   시작과 끝 시각은 그 묶은 블록들의 첫 시작시간과 마지막 종료시간을 그대로 사용하세요.
   예: 시간표에
       11:30 - 12:00 | 이동
       12:00 - 13:00 | 점심식사
      → 점심 ⏰ 11:30~13:00 (총 1시간 30분 머무르기)
3. Day 안에서는 시간은 겹치지 않고 앞→뒤로 이어지게 하세요.
   - 첫 일정은 보통 07:00~09:00 사이 기상으로 시작
   - 마지막은 22:00~24:00 사이 취침 준비로 마무리
4. 이동 블록(예: "10:30 - 11:00 | 이동")도 시간표에는 꼭 넣으세요. 그래야 전체 시간이 끊기지 않습니다.
5. "일일 시간표"에서 각 줄 형식은 정확히 아래 형태만 사용하세요. 다른 문장이나 불릿 기호(-, *, 번호 등) 쓰지 마세요.
   HH:MM - HH:MM | 활동/장소 | 한 줄 메모
6. "상세 가이드"에서는 아래 순서와 아이콘을 반드시 그대로 사용하세요.
   ☀ 아침
   🍜 점심
   🌇 오후
   🌉 저녁
   🌙 하루 요약
7. 각 블록(아침/점심/오후/저녁) 안에서는 이 3줄만:
   ⏰ 시간: "HH:MM~HH:MM (총 X시간 Y분 머무르기)"
   😊 감성 문장 (15~25자)
   🚶 이동·위치 등 실용 문장 (15~25자)
   줄 수를 더 늘리면 안 됩니다.
8. "🌙 하루 요약"은 딱 한 문장만 쓰세요.
9. 마크다운 문법(##, **굵게**, *, -, 번호목록 등)은 절대 쓰지 마세요.
10. 위 예시는 설명일 뿐, 실제 출력에는 Day 1 / Day 2 ... 결과만 쓰세요. 규칙 설명을 넣지 마세요.

이제 Day 1부터 Day {total_days}까지 위 형식을 그대로 따라 작성하세요.
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
