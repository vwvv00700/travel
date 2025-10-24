# travel/services/itinerary_generator.py

from travel.models import Place
from django.db.models import Q
import random
# LLM 최적화 로직 import
from .llm_optimizer import optimize_route_with_llm 
# 카카오 길 찾기 서비스 import
from .kakao_route_service import get_optimized_route_data 

def generate_itinerary(travel_gu: str, days: int, themes: list) -> list:
    """
    여행지 (구), 기간, 테마를 기반으로 장소 추천 리스트를 생성합니다.
    - 최종 반환되는 장소는 LLM이 결정한 최적 순서대로 정렬되며, 
      첫 번째 요소로 카카오 길 찾기 경로 데이터가 포함될 수 있습니다.
    """
    
    # 1. 구(Gu) 이름 변환 및 테마 필터링 조건 생성
    gu_map = {'gangnam': '강남구', 'jongno': '종로구', 'jung': '중구'}
    city_gu = gu_map.get(travel_gu.lower(), travel_gu) 
    
    theme_q = Q()
    for theme in themes:
        if theme == 'restaurant':
            theme_q |= Q(category='restaurants')
        elif theme == 'cafe':
            theme_q |= Q(analyses__themes_csv__icontains='카페')
        else:
            theme_q |= Q(analyses__themes_csv__icontains=theme)
        
    # 2. 장소 쿼리 실행
    places = Place.objects.filter(
        city_gu__icontains=city_gu,
        analyses__isnull=False  
    ).filter(theme_q).distinct().order_by('-rating', '?')
    
    # 3. 장소 선택
    max_days = min(days, 5) 
    max_selection = max_days * 4 # 총 추천할 장소의 최대 개수
    
    all_places = list(places[:max_selection])

    if not all_places:
        print(f"WARNING: DB 쿼리 결과가 비어있습니다. (Gu:{city_gu}, Themes:{themes})")
        return []

    num_to_select = min(max_selection, len(all_places))
    selected_places = random.sample(all_places, num_to_select)
    
    
    # 4. 경로 순서 최적화 (LLM 호출)
    print("DEBUG: [ITINERARY] 4. LLM 경로 순서 최적화 시작.")
    optimized_places = optimize_route_with_llm(selected_places)
    print("DEBUG: [ITINERARY] 4. LLM 경로 순서 최적화 완료.")
    
    # 🚨🚨 핵심 수정: 카카오 API 제한을 위해 최대 7개 장소만 전달 🚨🚨
    kakao_places = optimized_places[:7] 
    
    if len(optimized_places) > 7:
        print(f"WARNING: LLM 최적화 결과가 7개를 초과하여 ({len(optimized_places)}개), 카카오 길 찾기 API에는 앞의 7개 장소만 사용합니다.")


    # 5. 카카오 길 찾기 API 호출 (경로 데이터 가져오기)
    print("DEBUG: [ITINERARY] 5. 카카오 길 찾기 API 호출 시작.")
    # 🚨 수정된 장소 리스트(kakao_places) 사용
    route_data = get_optimized_route_data(kakao_places) 
    print("DEBUG: [ITINERARY] 5. 카카오 길 찾기 API 호출 완료.")
    
    
    # 6. 최종 리스트 생성 및 딕셔너리로 변환
    final_itinerary = []
    
    # 경로 데이터가 있다면 맨 앞에 추가 (프론트에서 첫 번째 요소로 처리)
    if route_data:
        final_itinerary.append(route_data) 
    
    for place in optimized_places:
        
        # JSON 파싱 오류 방지를 위한 이름 클리닝
        cleaned_name = place.name.replace('\n', ' ').strip()
        
        # LLM 추천 사유 가져오기
        rationale = "DB 분석 기반 추천 코스"
        try:
            analysis = place.analyses.latest('created_at') 
            rationale = getattr(analysis, 'llm_recommendation_text', 'LLM 분석 기반 추천') 
        except Exception:
            pass 
            
        final_itinerary.append({
            'name': cleaned_name,
            'lat': place.lat,
            'lon': place.lon,
            'category': place.category, 
            'rationale': rationale,
        })

    return final_itinerary