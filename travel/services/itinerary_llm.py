# travel/services/itinerary_llm.py
# 실제 OpenAI / 기타 LLM 호출부는 너 환경에 맞게 채우면 돼.
# 아래는 형태/프롬프트만 설계해둔 스켈레톤.

def generate_itinerary_guide(user_query, day_plans) -> str:
    """
    user_query: dict (areas, nights, group 등)
    day_plans: [ [ {place, analysis, score}, ... ], ... ]  # Day1, Day2, ...
    return: 자연어 가이드 문자열
    """
    # LLM 프롬프트용 요약 데이터 만들기
    outline_lines = []
    for day_idx, stops in enumerate(day_plans, start=1):
        outline_lines.append(f"[Day {day_idx}]")
        for order, stop in enumerate(stops, start=1):
            p = stop["place"]
            a = stop["analysis"]
            why = f"{a.themes_csv} / 커플선호:{a.group_couple} / 가을점수:{a.season_autumn}"
            outline_lines.append(f"{order}. {p.name} ({p.category}, {p.city_gu}) - {why}")
        outline_lines.append("")

    outline_text = "\n".join(outline_lines)

    prompt = f"""
너는 맞춤 여행 컨시어지다.
아래 조건의 여행자를 위해 상세한 여행 가이드를 작성해라.

[여행자 정보]
- 여행 지역 후보: {', '.join(user_query['areas']) or '미지정'}
- 여행 기간: {user_query['nights']}박 {user_query['total_days']}일
- 동행: {user_query['group']}
- 선호 MBTI 추정: {user_query['mbti_guess']}
- 계절: {user_query['season']}
- 사용자 요청 원문: {user_query['raw_text']}

[추천 동선 개요]
{outline_text}

가이드 작성 규칙:
1. Day별로 아침/점심/저녁 흐름처럼 설명해.
2. 왜 이 장소를 가는지(분위기, 누구랑 가면 좋은지, 계절 매력)를 자연스럽게 넣어.
3. 이동 동선 팁 (걸어 이동? 지하철 2정거장? 택시가 편함?) 을 넣어.
4. 말투는 친절하고 실전 팁 위주. 너무 광고처럼 쓰지 마.

이제 가이드를 작성해.
"""

    # 실제 모델 호출은 환경별이니까 여기선 더미 리턴
    # 나중에 OpenAI 등 붙이면 prompt를 넣고 text를 받아서 반환.
    fake_response = "예시 가이드:\n" + prompt[:800] + "\n..."
    return fake_response
