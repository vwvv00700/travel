# travel/services/LLM_analyzer.py

import json, os
from google import genai           # 👈 Gemini import 활성화
from google.genai.errors import APIError
from google.genai import types
# from openai import OpenAI         # 👈 주석 처리 (OpenAI 사용 안 함)
from dotenv import load_dotenv

# 프로젝트 시작 시 .env 파일 로드 (가장 상단에 위치)
load_dotenv()

# 1. 환경 변수에서 API 키를 가져옴
# settings.py에서 load_dotenv()가 실행되었으므로 여기서 키를 읽을 수 있어요.
API_KEY = os.getenv("GEMINI_API_KEY") # 👈 GEMINI API 키 사용
client = None

# 2. 클라이언트 초기화 시 키를 명시적으로 전달
if API_KEY:
    # 🚨 수정: Gemini 클라이언트 초기화
    client = genai.Client(api_key=API_KEY)
else:
    # 키가 없을 경우 에러 처리
    raise EnvironmentError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다. .env 파일을 확인하세요.")

# 🚨 analyze_place_with_LLM 함수 전체를 Gemini용으로 수정

def analyze_place_with_LLM(place_raw_data: str) -> dict:
    # (생략: 기존 system_instruction과 json_schema는 그대로 둡니다.)

    # --- 기존 OpenAI 로직 주석 처리 ---
    # if API_KEY:
    #     client = OpenAI(api_key=API_KEY)
    # else:
    #     raise EnvironmentError("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다. .env 파일을 확인하세요.")

    system_instruction = (
        "당신은 장소 데이터 전문가 AI입니다. 제공된 장소의 데이터를 분석하여 "
        "다음 항목을 JSON 형식으로 추출해 주세요. 답변은 JSON 코드 블록만 포함해야 하며, "
        "다른 설명은 절대 포함하지 마세요."
    )
    
    # ... (json_schema 정의 코드는 길어서 생략. 기존 코드를 그대로 사용) ...

    # -----------------------------------------------------
    # 💡 Gemini API 호출 로직으로 교체
    # -----------------------------------------------------
    try:
        # 1. JSON 스키마를 types.Schema 객체로 변환 (Gemini API용)
        # 스키마는 PlaceAnalysis 모델에 맞춰서 기존에 정의된 것을 사용합니다.
        
        # 🚨 스키마 변환 로직이 누락되어 있으므로, 임시로 텍스트 응답을 JSON으로 파싱하도록 설정합니다.
        # 정확한 JSON 스키마 기반 호출을 위해서는 types.Schema 정의가 필요합니다.
        
        # (임시: JSON 모드로 설정하고 텍스트를 파싱)
        response = client.models.generate_content(
            model='gemini-2.5-flash', # 혹은 'gemini-2.5-pro'
            contents=place_raw_data,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json", # JSON 출력 강제
            ),
        )
        
        # 응답 텍스트를 JSON으로 파싱
        # (응답이 JSON 코드 블록으로 래핑되지 않았다고 가정)
        return json.loads(response.text)
        
    except APIError as e:
        print(f"🚨 Gemini API 호출 오류: {e}")
        return {} # 실패 시 빈 dict 반환
    except Exception as e:
        print(f"🚨 LLM 분석 오류: {e}")
        return {}