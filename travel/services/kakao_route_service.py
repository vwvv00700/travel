# travel/services/kakao_route_service.py

import requests
import os
import json
from dotenv import load_dotenv

# .env 파일 경로 설정 (llm_optimizer.py와 동일한 방식으로 설정)
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path=dotenv_path)

# 🚨 .env 파일에 KAKAO_REST_API_KEY=발급받은키 를 추가해야 합니다.
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY") 

KAKAO_DIRECTION_URL = "https://apis-navi.kakaomobility.com/v1/directions"

def _parse_and_build(route_data: dict) -> dict:
    """API 응답을 받아서 필요한 정보(좌표, 거리, 시간)를 추출하여 반환합니다."""
    if route_data.get('routes'):
        route = route_data['routes'][0] 
        
        polyline_coords = []
        total_distance = route['summary']['distance'] # 총 거리 (미터)
        total_duration = route['summary']['duration'] # 총 시간 (초)
        
        # 모든 안내점(guide)의 좌표를 추출
        for section in route['sections']:
            for guide in section['guides']:
                # guide의 좌표는 (경도, 위도) 순이지만, 카카오 Map SDK의 LatLng는 (위도, 경도) 순이므로 변환
                # [guide['y'], guide['x']] = [위도, 경도] 순서로 저장
                polyline_coords.append([guide['y'], guide['x']]) 

        return {
            'polyline_coords': polyline_coords,
            'total_distance_km': round(total_distance / 1000, 2),
            'total_duration_min': round(total_duration / 60)
        }
    return {}

def get_optimized_route_data(optimized_places: list) -> dict:
    """
    LLM이 결정한 순서의 장소들을 기반으로 카카오 길 찾기 API를 호출하고
    실제 경로를 그릴 수 있는 Polyline 좌표와 거리/시간 정보를 반환합니다.
    """
    
    if not KAKAO_REST_API_KEY:
        print("🚨 FATAL: KAKAO_REST_API_KEY가 설정되지 않았습니다. .env 확인 필요")
        return {}

    if len(optimized_places) < 2:
        print("WARNING: 길찾기 API는 장소가 2개 미만이면 호출하지 않습니다.")
        return {}
        
    try:
        # 1. 좌표를 float로 변환하여 안정성 확보
        origin_lon = float(optimized_places[0].lon)
        origin_lat = float(optimized_places[0].lat)
        destination_lon = float(optimized_places[-1].lon)
        destination_lat = float(optimized_places[-1].lat)
    except Exception as e:
        print(f"🚨 좌표 변환 실패: {e}")
        return {}
    
    # 2. 카카오 API 요청을 위한 데이터 포맷팅: 경도,위도 (lon, lat) 순서
    origin = f"{origin_lon},{origin_lat}"
    destination = f"{destination_lon},{destination_lat}"
    
    waypoints = []
    for place in optimized_places[1:-1]:
        waypoints.append(f"{place.lon},{place.lat}")

    # 3. 카카오 API 요청 파라미터 설정 (GET 방식)
    params = {
        'origin': origin,
        'destination': destination,
        'waypoints': ";".join(waypoints), # 경유지들은 세미콜론으로 연결
        'priority': 'RECOMMEND', 
        'car_fuel': 'GASOLINE'
    }
    
    headers = {
        'Authorization': f'KakaoAK {KAKAO_REST_API_KEY}',
        # 🚨 GET 요청이므로 Content-Type 헤더를 명시적으로 제거하거나 추가하지 않습니다. 🚨
    }

    try:
        print("DEBUG: [KAKAO] 길 찾기 API GET 호출 시작 (10초 타임아웃 설정)...")
        # 🚨 requests.get을 사용하고, params를 쿼리 파라미터로 전달
        response = requests.get(KAKAO_DIRECTION_URL, headers=headers, params=params, timeout=10)
        
        # 400 에러 등의 상태 코드를 로그에 명확히 기록
        if response.status_code != 200:
            print(f"🚨 카카오 길 찾기 API 요청 실패 (HTTP 오류): {response.status_code} - {response.text[:100]}")
            response.raise_for_status() # HTTP 오류 발생 시 예외 발생
        
        return _parse_and_build(response.json())

    except requests.exceptions.RequestException as e:
        # 400, 401, 404 등 모든 RequestException 처리
        print(f"🚨 카카오 길 찾기 API 요청 실패: {e}")
        return {}
    except Exception as e:
        print(f"🚨 카카오 길 찾기 데이터 처리 중 오류 발생: {e}")
        return {}