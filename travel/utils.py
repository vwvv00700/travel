# travel/utils.py

import requests
from travel.models import Place
import os

# 네이버 API 인증 정보 (test.py에서 확인된 값)
NAVER_CLIENT_ID = "8UzzcjeXr92mWfAtqo6v"
NAVER_CLIENT_SECRET = "HR8S6o1XFo"
NAVER_MAPS_API_KEY = "oeRWLrI1dXKndxfzThyctuKG56mhe4FOXY889et9"

def geocode_naver(address):
    """주소를 받아 네이버 클라우드 Geocoding API를 통해 좌표를 반환합니다."""
    url = "https://naveropenapi.apigw.ntruss.com/map-geocode/v2/geocode"
    
    headers = {
        "X-NCP-APIGW-API-KEY-ID": NAVER_CLIENT_ID,
        "X-NCP-APIGW-API-KEY": NAVER_MAPS_API_KEY
    }
    
    params = {
        "query": address
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data.get('addresses') and data['addresses'][0].get('x') and data['addresses'][0].get('y'):
            longitude = data['addresses'][0]['x']  # x는 경도 (Longitude)
            latitude = data['addresses'][0]['y']   # y는 위도 (Latitude)
            return latitude, longitude
        
    except requests.exceptions.RequestException as e:
        print(f"🚨 네이버 Geocoding API 요청 오류: {e}")
    except Exception as e:
        print(f"🚨 네이버 Geocoding 응답 파싱 오류: {e}")
    
    return None, None

def update_missing_coordinates():
    """DB에서 좌표가 없는 모든 장소를 찾아 좌표를 갱신합니다."""
    places_to_update = Place.objects.filter(
        latitude__isnull=True,
        address__isnull=False
    ).exclude(address="")
    
    updated_count = 0
    total_count = places_to_update.count()
    
    print(f"🚨 좌표가 없는 장소 {total_count}개 발견. 업데이트를 시작합니다...")
    
    for i, place in enumerate(places_to_update):
        if place.address:
            lat, lon = geocode_naver(place.address)
            
            if lat and lon:
                place.latitude = lat
                place.longitude = lon
                place.save(update_fields=['latitude', 'longitude'])
                updated_count += 1
                print(f"[{i+1}/{total_count}] ✅ 갱신 성공: {place.name} -> ({lat}, {lon})")
            else:
                print(f"[{i+1}/{total_count}] ❌ 갱신 실패: {place.name} (주소: {place.address})")
    
    print(f"\n--- 좌표 갱신 완료: 총 {updated_count}개 갱신됨 ---")
    return updated_count