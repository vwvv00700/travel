import os
import google.generativeai as genai
import logging
import openai
from .models import AISettings # Import AISettings

logger = logging.getLogger(__name__)

def _generate_llm_prompt(region: list, duration: str, theme: list, places_info: str) -> str:
    """
    Generates a detailed prompt for the LLM to create a travel plan.
    """
    region_str = ", ".join(region) if region else "선택된 지역 없음"
    theme_str = ", ".join(theme) if theme else "선택된 테마 없음"

    # Emphasize using ONLY provided places and strict JSON format
    prompt = (
        f"다음은 데이터베이스에 있는 장소 목록입니다: {places_info}\n\n"
        f"이 장소 목록만을 사용하여 {region_str} 지역으로 {duration} 동안 {theme_str} 테마의 여행 계획을 JSON 형식으로 상세한 일정을 포함하여 설계해줘. "
        f"응답은 반드시 JSON 형식이어야 하며, 각 일차별로 장소, 활동, 설명을 포함해야 해. "
        f"절대로 위 장소 목록에 없는 장소를 추천하지 마. "
        f"JSON 응답 외에 다른 어떠한 설명이나 대화도 포함하지 마."
    )
    return prompt

def get_api_key(api_name: str):
    """Retrieves API key from AISettings model."""
    try:
        settings = AISettings.objects.first()
        if not settings:
            logger.error("AISettings model instance not found. Please configure AI settings in Django Admin.")
            return None

        if api_name == "gemini":
            return settings.google_gemini_api_key
        elif api_name == "openai":
            return settings.openai_api_key
    except Exception as e:
        logger.error(f"Error retrieving API key from AISettings: {e}")
    return None

def generate_travel_plan(prompt: str, api_model: str = None) -> str:
    # If api_model is not provided, get the default from AISettings
    if api_model is None:
        try:
            settings = AISettings.objects.first()
            if settings:
                api_model = settings.default_api_model
            else:
                logger.warning("AISettings model instance not found. Defaulting to 'gemini'.")
                api_model = "gemini" # Fallback if no settings are configured
        except Exception as e:
            logger.error(f"Error getting default API model from AISettings: {e}. Defaulting to 'gemini'.")
            api_model = "gemini"

    if api_model == "gemini":
        api_key = get_api_key("gemini")
        if not api_key:
            return "Error: Google Gemini API key not found in settings."

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro')

        try:
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Gemini API 호출 중 오류 발생: {e}")
            return f"Error generating travel plan with Gemini: {e}"

    elif api_model == "openai":
        api_key = get_api_key("openai")
        if not api_key:
            return "Error: OpenAI API key not found in settings."

        client = openai.OpenAI(api_key=api_key)
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful travel planner AI."},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API 호출 중 오류 발생: {e}")
            return f"Error generating travel plan with OpenAI: {e}"
    else:
        return "Error: Invalid AI model selected."
