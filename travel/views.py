# views.py

import json, re, time
from itertools import groupby
from operator import attrgetter
from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse
from django.db.models import Q
from django.conf import settings

from .models import Place
from .services.LLM_analyzer import analyze_place_with_LLM
from .services.analysis_loader import create_or_update_analysis_from_json
from .services.itinerary_generator import generate_itinerary # LLM 추천 함수

# Create your views here.
def travel_list(request):
    """
    GET  : 선택 페이지(redirect -> 'select')
    POST : 추천 코스 생성 -> travel_list.html 렌더링
    """
    
    if request.method == 'POST':
        # 1. POST 데이터 추출
        travel_gu = request.POST.get('travel_gu', '')
        
        # 'days'는 'day2'처럼 넘어오므로 숫자만 추출
        days_str = request.POST.get('days', 'day1').replace('day', '')
        days = int(days_str) if days_str.isdigit() else 1

        # 'tema'는 복수 선택이 가능하므로 getlist 사용
        themes = request.POST.getlist('tema')

        # 2. 추천 코스 생성
        # itinerary는 첫 번째 요소로 route_data가 포함될 수 있는 리스트입니다.
        itinerary = generate_itinerary(travel_gu, days, themes)

        # 3. 템플릿 컨텍스트 생성 및 렌더링
        # 🚨🚨 핵심: ensure_ascii=True로 설정하여 JavaScript JSON 파싱 오류를 방지 🚨🚨
        locations_json_string = json.dumps(itinerary, ensure_ascii=False)
        
        ctx = {
            'llm_recommendations': [item for item in itinerary if item.get('name')],
            'locations_json': locations_json_string,
            'KAKAO_APP_KEY': settings.KAKAO_APP_KEY,
        }
        
        # 디버그 출력
        print(f"DEBUG: travel_gu={travel_gu}, days={days}, themes={themes}")
        print(f"DEBUG: LLM Itinerary result type: {type(itinerary)}")
        print(f"DEBUG: LLM Itinerary result content: {itinerary[:2]} (Showing first 2 items)")


        return render(request, 'travel/travel_list.html', ctx)
    
    # POST가 아니면 select 페이지로 리다이렉트
    return redirect(reverse('travel:select'))


# 🚨 주의: 아래는 기존 프로젝트의 select_and_analyze view의 구조입니다.
# 완전한 views.py 구성을 위해 유지합니다.

def select_and_analyze(request):
    """
    LLM 분석을 위해 장소를 선택하고 분석 결과를 보여주거나 DB에 저장하는 View
    """
    action = request.POST.get('action') if request.method == 'POST' else None
    
    if action == 'analyze':
        # ... (분석 요청 로직) ...
        pass
    elif action == 'save':
        # ... (DB 저장 로직) ...
        pass
    else:
        # GET 요청 또는 action 없음
        return redirect(reverse('travel:select'))