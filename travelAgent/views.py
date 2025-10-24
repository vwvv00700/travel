from django.shortcuts import render
import json
import logging
import re
from travel.models import Place
from ai_planner.services import generate_travel_plan, _generate_llm_prompt
from ai_planner.forms import SelectPlanForm

logger = logging.getLogger(__name__)

def main(request):
    return render(request, "main.html")

def select(request):
    # ✨ 수정된 부분: 템플릿으로 전달할 딕셔너리를 뷰에서 생성합니다.
    duration_options = {
        "당일치기": "day1",
        "1박 2일": "day2",
        "2박 3일": "day3",
        "3박 4일": "day4",
        "4박 5일": "day5",
    }
    
    theme_options = {
        "cafe": "카페",
        "restaurant": "맛집",
        "festival": "축제",
        "자연 경관": "자연/산책",
        "culture": "문화/전시",
        "park": "테마파크",
        "healing": "힐링/스파",
        "shopping": "쇼핑",
    }
    
    form = SelectPlanForm()
    parsed_plan = None
    plan_result = None
    error_message = None
    enriched_plan = None

    selected_region = None
    selected_duration = None
    selected_theme = None
    prompt = None
    raw_plan_result = None

    existing_places = Place.objects.all()
    place_names = [place.name for place in existing_places]
    places_info = "현재 데이터베이스에 있는 장소 목록: " + ", ".join(place_names) + ". 이 장소들을 우선적으로 추천해줘."

    if request.method == 'POST':
        form = SelectPlanForm(request.POST)
        if form.is_valid():
            selected_regions_list_str = form.cleaned_data.get('selected_regions_list')
            if selected_regions_list_str:
                selected_region = [r.strip() for r in selected_regions_list_str.split(',') if r.strip()]
            else:
                selected_region = []

            selected_duration = form.cleaned_data.get('duration')
            selected_theme = form.cleaned_data.get('theme')
            logger.debug(f"Form data - Region: {selected_region}, Duration: {selected_duration}, Theme: {selected_theme}")

            prompt = _generate_llm_prompt(region=selected_region, duration=selected_duration, theme=selected_theme, places_info=places_info)
            logger.debug(f"AI Prompt: {prompt}")
            raw_plan_result = generate_travel_plan(prompt)
            logger.debug(f"Raw AI Plan Result: {raw_plan_result}")
            
            try:
                json_match = re.search(r'```json\n(.*)\n```', raw_plan_result, re.DOTALL)
                if json_match:
                    json_string = json_match.group(1)
                    parsed_plan = json.loads(json_string)
                    logger.debug(f"Parsed Plan: {parsed_plan}")
                else:
                    parsed_plan = json.loads(raw_plan_result)
                    logger.debug(f"Parsed Plan (direct): {parsed_plan}")
                
                place_names_in_plan = set()
                if isinstance(parsed_plan, list):
                    for day_plan in parsed_plan:
                        if "activities" in day_plan and isinstance(day_plan["activities"], list):
                            for activity in day_plan["activities"]:
                                if "place" in activity:
                                    place_names_in_plan.add(activity["place"])
                logger.debug(f"Place names in plan: {place_names_in_plan}")
                
                detailed_places = Place.objects.filter(name__in=list(place_names_in_plan))
                place_details_map = {place.name: place for place in detailed_places}
                logger.debug(f"Fetched place details map: {place_details_map}")

                enriched_plan = []
                if isinstance(parsed_plan, list):
                    for day_plan in parsed_plan:
                        enriched_day_plan = day_plan.copy()
                        if "activities" in enriched_day_plan and isinstance(enriched_day_plan["activities"], list):
                            enriched_activities = []
                            for activity in enriched_day_plan["activities"]:
                                enriched_activity = activity.copy()
                                if "place" in enriched_activity and enriched_activity["place"] in place_details_map:
                                    enriched_activity["details"] = place_details_map[enriched_activity["place"]]
                                enriched_activities.append(enriched_activity)
                            enriched_day_plan["activities"] = enriched_activities
                        enriched_plan.append(enriched_day_plan)
                logger.debug(f"Enriched Plan: {enriched_plan}")

            except json.JSONDecodeError as e:
                logger.error(f"JSON 파싱 오류 (선택 기반): {e} - 원본 응답: {raw_plan_result}")
                error_message = "AI 응답을 처리하는 중 오류가 발생했습니다. AI가 유효한 JSON을 반환하지 않았습니다. 다시 시도해 주세요."
                plan_result = raw_plan_result
            except Exception as e:
                logger.error(f"알 수 없는 오류 (선택 기반): {e} - 원본 응답: {raw_plan_result}")
                error_message = "AI 응답을 처리하는 중 알 수 없는 오류가 발생했습니다. 다시 시도해 주세요."
                plan_result = raw_plan_result
        else:
            logger.warning(f"Form is invalid: {form.errors}")
            error_message = "선택 입력이 유효하지 않습니다."

    # ✨ 수정된 부분: 생성한 딕셔너리를 context에 추가하여 템플릿으로 전달합니다.
    context = {
        'form': form,
        'duration_options': duration_options,
        'theme_options': theme_options,
        'parsed_plan': enriched_plan,
        'plan_result': plan_result,
        'error_message': error_message,
        'selected_region': selected_region,
        'selected_duration': selected_duration,
        'selected_theme': selected_theme,
        'generated_prompt': prompt,
        'raw_ai_response': raw_plan_result,
    }

    return render(request, "select.html", context)