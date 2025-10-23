import json, os
# from google import genai
# from google.genai.errors import APIError
# from google.genai import types

from openai import OpenAI
from dotenv import load_dotenv # 👈 임포트

# 프로젝트 시작 시 .env 파일 로드 (가장 상단에 위치)
load_dotenv()

# 1. 환경 변수에서 API 키를 가져옴
# settings.py에서 load_dotenv()가 실행되었으므로 여기서 키를 읽을 수 있어요.
# API_KEY = os.getenv("GEMINI_API_KEY")

# # 2. 클라이언트 초기화 시 키를 명시적으로 전달
# if API_KEY:
#     client = genai.Client(api_key=API_KEY) # 👈 키를 직접 전달
# else:
#     # 키가 없을 경우 에러 처리
#     raise EnvironmentError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다. .env 파일을 확인하세요.")

API_KEY = os.getenv("OPENAI_API_KEY")
if API_KEY:
    client = OpenAI(api_key=API_KEY)
else:
    raise EnvironmentError("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다. .env 파일을 확인하세요.")

def analyze_place_with_LLM(place_raw_data: str) -> dict:
    system_instruction = (
        "당신은 장소 데이터 전문가 AI입니다. 제공된 장소의 데이터를 분석하여 "
        "다음 항목을 JSON 형식으로 추출해 주세요. 답변은 JSON 코드 블록만 포함해야 하며, "
        "다른 설명은 절대 포함하지 마세요."
    )
    
    json_schema = {
        "type": "object",
        "properties": {
            # 1. 장소 특성 분석 (강도 점수)
            
            # 🚨 계절별 적합도 점수
            "seasonality_analysis": {
                "type": "array",
                "description": "4계절 각각에 대한 장소의 적합도 점수 분석",
                "items": {
                    "type": "object",
                    "properties": {
                        "season": {"type": "string", "enum": ["봄", "여름", "가을", "겨울"]},
                        "relevance_score": {"type": "integer", "description": "장소 특성이 해당 계절에 얼마나 적합한지 점수 (100점 만점)"}
                    },
                    "required": ["season", "relevance_score"]
                }
            },
            
            # 🚨 키워드 중요도 점수
            "keyword_analysis": {
                "type": "array",
                "description": "장소를 대표하는 핵심 키워드 5개와 그 중요도 점수",
                "items": {
                    "type": "object",
                    "properties": {
                        "keyword": {"type": "string", "description": "핵심 키워드"},
                        "importance_score": {"type": "integer", "description": "장소를 대표하는 키워드의 중요도 점수 (100점 만점)"}
                    },
                    "required": ["keyword", "importance_score"]
                }
            },
            
            # 🚨 테마 적합도 점수
            "theme_analysis": {
                "type": "array",
                "description": "미리 정의된 주요 테마에 대한 장소의 성격 적합도 분석",
                "items": {
                    "type": "object",
                    "properties": {
                        "theme_name": {"type": "string", "enum": ["힐링/휴식", "익스트림/액티비티", "역사/문화탐방", "SNS/핫플레이스", "미식/맛집투어"]},
                        "relevance_score": {"type": "integer", "description": "해당 테마와의 성격 적합도 점수 (100점 만점)"}
                    },
                    "required": ["theme_name", "relevance_score"]
                }
            },

            # 2. MBTI 프로필 (고객 선호도와 무관한 장소 성격이므로 유지)
            "mbti_profile": {
                "type": "object",
                "description": "장소의 분위기를 MBTI 4쌍의 지표(E/I, S/N, T/F, J/P)별로 분석",
                "properties": {
                    "EI": {"type": "string", "description": "E/I 비율과 근거 키워드 (예: E(70%) / I(30%), 핫플, SNS에서 유명)"},
                    "SN": {"type": "string", "description": "S/N 비율과 근거 키워드 (예: S(40%) / N(60%), 분위기, 이국적)"},
                    "TF": {"type": "string", "description": "T/F 비율과 근거 키워드 (예: T(20%) / F(80%), 너무 좋은 장소, 분위기 있다)"},
                    "JP": {"type": "string", "description": "J/P 비율과 근거 키워드 (예: J(20%) / P(80%), 예약 없이 방문, 자유로운 촬영)"}
                },
                "required": ["EI", "SN", "TF", "JP"]
            },

            # 3. 방문객 분석 (고객 선호도)
            "visitor_analysis": {
                "type": "object",
                "description": "장소의 주요 방문객 그룹, 연령대, 성별 분석",
                "properties": {
                    "groups": {
                        "type": "array",
                        "description": "방문객 그룹별 선호도와 근거 키워드",
                        "items": {
                            "type": "object",
                            "properties": {
                                "category": {"type": "string", "enum": ["커플", "친구", "가족", "혼자"]},
                                "preference_rate": {"type": "integer", "description": "선호도 점수 (%)"},
                                "keywords": {"type": "string", "description": "주요 근거 키워드 (쉼표로 구분)"}
                            },
                            "required": ["category", "preference_rate", "keywords"]
                        }
                    },
                    "age_group": {
                        "type": "array",
                        "description": "주요 연령대별 선호도와 근거 키워드",
                        "items": {
                            "type": "object",
                            "properties": {
                                "age": {"type": "string", "description": "연령대 (예: 20대, 30대, 40대, 기타)"},
                                "preference_rate": {"type": "integer", "description": "선호도 점수 (%)"},
                                "keywords": {"type": "string", "description": "주요 근거 키워드 (쉼표로 구분)"}
                            },
                            "required": ["age", "preference_rate", "keywords"]
                        }
                    },
                    "gender": {
                        "type": "array",
                        "description": "성별 선호도와 근거 키워드",
                        "items": {
                            "type": "object",
                            "properties": {
                                "gender": {"type": "string", "enum": ["여성", "남성"]},
                                "preference_rate": {"type": "integer", "description": "선호도 점수 (%)"},
                                "keywords": {"type": "string", "description": "주요 근거 키워드 (쉼표로 구분)"}
                            },
                            "required": ["gender", "preference_rate", "keywords"]
                        }
                    }
                },
                "required": ["groups", "age_group", "gender"]
            }
        },
        
        # 🚨 최상위 필수 항목 업데이트 (점수화된 새 필드 포함)
        "required": [
            "seasonality_analysis", # 👈 변경
            "keyword_analysis",     # 👈 변경
            "theme_analysis",       # 👈 변경
            "mbti_profile", 
            "visitor_analysis"
        ]
    }

    try:
        # 1) 최신 SDK 경로: Responses API + structured outputs
        resp = client.responses.create(
            model="gpt-4o-mini-2024-07-18",
            input=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": place_raw_data},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "PlaceAnalysis",
                    "schema": json_schema,
                    "strict": True,
                },
            },
        )
        text = resp.output_text
        return json.loads(text)

    except TypeError as te:
        # 2) 구버전/호환 이슈: response_format을 인식 못하면 Chat Completions + tools로 폴백
        if "response_format" not in str(te):
            return {"error": str(te)}

        # 🔁 폴백 경로: tools(function calling)로 JSON 스키마 유사 강제
        #  - toolChoice로 특정 함수 호출을 고정 → arguments가 JSON 문자열로 떨어짐
        comp = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "너는 장소 데이터를 주어진 JSON 스키마에 맞춰 '정확한 JSON만' 생성한다. "
                        "설명/코드블록/텍스트 금지. 문자열 안에 줄바꿈/백틱/불필요한 공백 넣지 말 것."
                    ),
                },
                {
                    "role": "user",
                    "content": place_raw_data,
                },
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "emit_place_analysis",
                        "description": "스키마에 맞춘 장소 분석 결과를 JSON으로 반환",
                        "parameters": json_schema,  # ← 네가 정의한 스키마 그대로 사용
                    },
                }
            ],
            tool_choice={"type": "function", "function": {"name": "emit_place_analysis"}},  # 함수 호출 강제
        )

        choice = comp.choices[0].message
        # tool_calls가 비어있지 않다면 함수 인자(arguments)가 JSON 문자열로 들어있음
        if getattr(choice, "tool_calls", None):
            args = choice.tool_calls[0].function.arguments
            return json.loads(args)

        # 혹시 tool_calls가 비어 있으면 메시지 본문을 최후의 보루로 파싱 시도
        return json.loads(choice.content)

    except Exception as e:
        return {"error": str(e)}
    