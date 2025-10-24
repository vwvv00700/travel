# travel/services/llm_optimizer.py
import json
import random
from travel.models import Place
from google import genai  # Gemini API 클라이언트
from google.genai.errors import APIError
from dotenv import load_dotenv
import os

# 🚨🚨 수정: .env 파일 경로 지정 (travel/services/ -> travel/) 🚨🚨
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path=dotenv_path)

# Gemini API 클라이언트 초기화
# 🚨🚨 수정: os.getenv()에 변수 이름(문자열)을 전달 🚨🚨
API_KEY = os.getenv("GEMINI_API_KEY") 

if API_KEY:
    try:
        client = genai.Client(api_key=API_KEY)
        LLM_ACTIVE = True
        print("INFO: Gemini Client가 성공적으로 초기화되었습니다. LLM 최적화를 시도합니다.")
    except Exception as e:
        print(f"WARNING: Gemini Client 초기화 실패 ({e}). Mock 데이터로 작동합니다.")
        LLM_ACTIVE = False
        client = None
else:
    # 이 로그가 보인다면 .env 파일의 GEMINI_API_KEY 설정을 확인하세요.
    print("WARNING: GEMINI_API_KEY가 설정되지 않아 LLM 최적화는 Mock 데이터로 작동합니다.")
    LLM_ACTIVE = False
    client = None


def optimize_route_with_llm(places: list) -> list:
    """
    선택된 장소 리스트를 LLM에 전달하여 최적의 순서를 받아와 재배열하거나, 
    실패 시 Mock 데이터로 폴백합니다.
    """
    
    place_data = []
    for place in places:
        if isinstance(place, Place):
            place_data.append({
                # JSON 오류 방지를 위해 이름에서 줄 바꿈 및 공백을 명시적으로 제거 
                'name': place.name.replace('\n', ' ').strip(), 
                'lat': place.lat,
                'lon': place.lon
            })
            
    optimized_names = []
    
    if LLM_ACTIVE and client:
        prompt = f"""
        당신은 여행 동선 최적화 전문가입니다. 아래 장소들의 위도(lat)와 경도(lon)를 기반으로 
        가장 효율적인 이동 경로 순서를 결정하고, 결정된 순서대로 **장소 이름(name)** 리스트만을 JSON 배열 형태로 반환해야 합니다.
        [장소 목록]
        {json.dumps(place_data, ensure_ascii=False, indent=2)}
        """
        
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    response_mime_type="application/json", 
                    response_schema={"type": "array", "items": {"type": "string"}}
                )
            )
            
            optimized_names = json.loads(response.text)
            
            valid_names = {p['name'] for p in place_data}
            if not isinstance(optimized_names, list) or not all(name in valid_names for name in optimized_names):
                 raise ValueError("LLM 응답이 유효하지 않습니다.")
            
            print("INFO: LLM을 통해 경로 최적화에 성공했습니다.")
            
        except (APIError, json.JSONDecodeError, ValueError) as e:
            print(f"🚨 LLM API/파싱 오류 (Mock 폴백): {e}")
        except Exception as e:
            print(f"🚨 기타 오류 (Mock 폴백): {e}")


    # LLM 호출이 실패하거나 비활성화된 경우, Mock 데이터 로직으로 폴백
    if not optimized_names:
        print("INFO: Mock 경로 순서를 사용합니다.")
        cleaned_names = [p['name'] for p in place_data]
        optimized_names = cleaned_names
        if len(optimized_names) > 1:
            random.shuffle(optimized_names[1:])
        
    # 최종 리스트 재구성 (이름 클리닝을 통해 매칭)
    name_to_place = {place.name.replace('\n', ' ').strip(): place for place in places}
    optimized_places = []
    
    for name in optimized_names:
        if name in name_to_place:
            optimized_places.append(name_to_place[name])
            
    return optimized_places