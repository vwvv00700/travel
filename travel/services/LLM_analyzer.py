import os, json, re
from openai import OpenAI
from dotenv import load_dotenv
from json import JSONDecodeError

# .env 로드
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise EnvironmentError("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
client = OpenAI(api_key=API_KEY)

# ----- JSON 파싱 가드 -----

def _strip_code_fences(text: str) -> str:
    """```json ... ``` 같은 코드블록 제거"""
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.S)

def _extract_first_json(text: str) -> str | None:
    """텍스트에서 첫 '{' ~ 마지막 '}'까지 추출"""
    s, e = text.find("{"), text.rfind("}")
    if s != -1 and e != -1 and e > s:
        return text[s:e+1]
    return None

def _safe_json_loads(text: str) -> dict:
    """
    LLM 응답이 코드블록, 따옴표 깨짐, 여분 텍스트 등으로 JSONDecodeError 날 때 자동 복구.
    + 디버그용: 깨진 위치와 근처 내용 콘솔에 출력.
    """
    try:
        return json.loads(text)

    except JSONDecodeError as e:
        print("\n🚨 JSONDecodeError 발생!")
        print(f"→ 위치: {e.pos}")
        print(f"→ 메시지: {e.msg}")
        print("→ 주변 문자열 ↓↓↓")
        print(text[max(0, e.pos - 80): e.pos + 80])
        print("=======================\n")

    except Exception:
        pass

    # 1️⃣ 코드블록 제거
    t = _strip_code_fences(text)
    # 2️⃣ 첫 JSON 영역 추출
    inner = _extract_first_json(t)
    if inner:
        try:
            return json.loads(inner)
        except JSONDecodeError as e:
            print("\n⚠️ inner JSONDecodeError")
            print(f"→ 위치: {e.pos}")
            print(f"→ 메시지: {e.msg}")
            print("→ 주변 문자열 ↓↓↓")
            print(inner[max(0, e.pos - 80): e.pos + 80])
            print("=======================\n")
        except Exception:
            pass

    # 3️⃣ 따옴표 교정 후 재시도
    t2 = (inner or t).replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    return json.loads(t2)

# ----- 메인 함수 -----
def analyze_place_with_LLM(place_raw_data: str) -> dict:
    system_instruction = (
        "당신은 장소 데이터 전문가 AI입니다. 제공된 장소의 데이터를 분석하여 "
        "다음 항목을 JSON 형식으로 추출해 주세요. 답변은 JSON 코드 블록만 포함해야 하며, "
        "다른 설명은 절대 포함하지 마세요."
    )

    # JSON 스키마 (기존 그대로)
    json_schema = {
        "type": "object",
        "properties": {
            "seasonality_analysis": {
                "type": "array",
                "minItems": 4, "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "season": {"type": "string", "enum": ["봄", "여름", "가을", "겨울"]},
                        "relevance_score": {"type": "integer", "minimum": 0, "maximum": 100}
                    },
                    "required": ["season", "relevance_score"],
                    "additionalProperties": False
                }
            },
            "keyword_analysis": {
                "type": "array",
                "minItems": 5, "maxItems": 5,
                "items": {
                    "type": "object",
                    "properties": {
                        "keyword": {"type": "string"},
                        "importance_score": {"type": "integer", "minimum": 0, "maximum": 100}
                    },
                    "required": ["keyword", "importance_score"],
                    "additionalProperties": False
                }
            },
            "theme_analysis": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "theme_name": {"type": "string", "enum": ["힐링/휴식", "익스트림/액티비티", "역사/문화탐방", "SNS/핫플레이스", "미식/맛집투어"]},
                        "relevance_score": {"type": "integer", "minimum": 0, "maximum": 100}
                    },
                    "required": ["theme_name", "relevance_score"],
                    "additionalProperties": False
                }
            },
            "mbti_profile": {
                "type": "object",
                "properties": {"EI":{"type":"string"},"SN":{"type":"string"},"TF":{"type":"string"},"JP":{"type":"string"}},
                "required": ["EI","SN","TF","JP"],
                "additionalProperties": False
            },
            "visitor_analysis": {
                "type": "object",
                "properties": {
                    "groups": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "category": {"type": "string", "enum": ["커플", "친구", "가족", "혼자"]},
                                "preference_rate": {"type": "integer", "minimum": 0, "maximum": 100},
                            },
                            "required": ["category","preference_rate","keywords"],
                            "additionalProperties": False
                        }
                    },
                    "age_group": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "age": {"type": "string", "enum": ["10대","20대","30대","40대","50대","60대+","기타"]},
                                "preference_rate": {"type": "integer", "minimum": 0, "maximum": 100},
                            },
                            "required": ["age","preference_rate","keywords"],
                            "additionalProperties": False
                        }
                    },
                    "gender": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "gender": {"type": "string", "enum": ["여성","남성"]},
                                "preference_rate": {"type": "integer", "minimum": 0, "maximum": 100},
                            },
                            "required": ["gender","preference_rate","keywords"],
                            "additionalProperties": False
                        }
                    }
                },
                "required": ["groups","age_group","gender"],
                "additionalProperties": False
            }
        },
        "required": ["seasonality_analysis","keyword_analysis","theme_analysis","mbti_profile","visitor_analysis"],
        "additionalProperties": False
    }

    try:
        # Responses API + json_schema 강제 출력
        resp = client.responses.create(
            model="gpt-4.1-nano-2025-04-14",
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
            temperature=0,
        )

        text = getattr(resp, "output_text", "")
        return _safe_json_loads(text)

    except TypeError as te:
        # Responses API가 안 먹을 때 → tools(function calling)로 폴백
        if "response_format" not in str(te):
            return {"error": str(te)}

        comp = client.chat.completions.create(
            model="gpt-4.1-nano-2025-04-14",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": "JSON만 반환하라. 설명/코드블록/텍스트 금지.",
                },
                {"role": "user", "content": place_raw_data},
            ],
            tools=[{
                "type": "function",
                "function": {
                    "name": "emit_place_analysis",
                    "description": "스키마에 맞춘 JSON 결과 반환",
                    "parameters": json_schema,
                },
            }],
            tool_choice={"type": "function", "function": {"name": "emit_place_analysis"}},
        )

        msg = comp.choices[0].message
        if getattr(msg, "tool_calls", None):
            return _safe_json_loads(msg.tool_calls[0].function.arguments)
        return _safe_json_loads(msg.content or "")

    except Exception as e:
        return {"error": str(e)}
