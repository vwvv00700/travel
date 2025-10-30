import os
from openai import OpenAI # Changed import

def _build_messages(comments: list[str]) -> list[dict]: # Changed to build messages for chat API
    """Builds the messages for the OpenAI chat API to summarize diary comments."""
    
    comments_text = "\n- ".join(comments)
    
    system_message = """
당신은 여행 후기를 작성하는 전문 블로거입니다.
주어진 여행자의 메모들을 바탕으로, 여행 전체를 아우르는 감성적이고 흥미로운 1개의 요약 문단을 작성해주세요."""

    user_message_content = f"""
[여행 기록 메모]
- {comments_text}

[요약 조건]
- 3~4개의 문장으로 구성된 하나의 문단으로 작성하세요.
- 여행자의 경험과 감정이 잘 드러나도록 작성해주세요.
- "이번 여행은...", "전반적으로..." 와 같은 상투적인 시작을 피하고, 가장 인상적인 경험으로 글을 시작하세요.
- 마크다운 문법이나 줄바꿈 없이, 순수 텍스트로만 작성해주세요.

[요약문 예시]
해질녘 해변에서의 산책은 이번 여행의 백미였고, 현지 식당에서 맛본 신선한 해산물 요리는 입을 즐겁게 했습니다. 예상치 못한 골목길에서의 발견과 따뜻한 현지인들과의 만남 덕분에, 이번 여행은 단순한 휴식을 넘어 삶의 새로운 활력을 불어넣는 소중한 경험이 되었습니다.

이제 위의 메모를 바탕으로 요약문을 작성하세요:
"""
    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message_content}
    ]

def summarize_diary_with_ai(comments: list[str]) -> str:
    """
    Summarizes diary comments using the OpenAI AI model.
    """
    if not comments:
        return "요약할 내용이 없습니다."

    messages = _build_messages(comments) # Changed to use messages list
    
    api_key = os.getenv("OPENAI_API_KEY") # Changed env var name
    if not api_key:
        return "(주의: AI 요약 기능을 사용하려면 OPENAI_API_KEY 설정이 필요합니다.)"

    client = OpenAI(api_key=api_key) # Initialize OpenAI client
    model_name = "gpt-4o" # Consistent with get_ai_recommendations

    try:
        response = client.chat.completions.create( # Changed API call
            model=model_name,
            messages=messages,
            response_format={"type": "text"} # Changed response format to text
        )
        
        summary = response.choices[0].message.content 
        if summary:
            return summary.strip()
        
        return "AI에서 유효한 응답을 받지 못했습니다." # Fallback if no summary
    except Exception as e:
        print(f"AI Diary Summarizer ERROR: {e}")
        return f"[AI 요약 중 오류가 발생했습니다: {e}]"

def generate_tags_with_ai(comment: str) -> str:
    """
    Generates tags for a diary entry comment using the OpenAI AI model.
    Returns a comma-separated string of tags.
    """
    if not comment or not comment.strip():
        return ""

    system_message = """
당신은 주어진 텍스트에서 핵심 키워드와 태그를 추출하는 전문가입니다.
텍스트의 내용을 가장 잘 나타내는 5개 이하의 키워드를 쉼표로 구분하여 나열해주세요.
각 키워드는 띄어쓰기 없이 단일 단어 형태여야 합니다. (예: #여행, #맛집, #풍경)
"""
    user_message_content = f"""
다음 여행 기록 코멘트에서 태그를 생성해주세요:

{comment}

생성된 태그 (쉼표로 구분, 5개 이하):"""

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message_content}
    ]

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # Return a distinct error message for missing API key
        return "MISSING_OPENAI_API_KEY"

    client = OpenAI(api_key=api_key)
    model_name = "gpt-4o"

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            response_format={"type": "text"}
        )
        
        tags_string = response.choices[0].message.content
        if tags_string:
            # Clean up tags: remove #, strip spaces, ensure comma separated
            cleaned_tags = [tag.strip().replace('#', '') for tag in tags_string.split(',') if tag.strip()]
            return ', '.join(cleaned_tags)
        
        return ""
    except Exception as e:
        print(f"AI Tag Generator ERROR: {e}")
        # Return the actual exception message
        return f"API_CALL_ERROR: {e}"