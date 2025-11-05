from django.urls import path, register_converter
from django.contrib.auth import views as auth_views
from travel import views
from django.shortcuts import render

app_name = "travel"

urlpatterns = [

    # 여행 목록
    path("list/", views.travel_list, name="travel_list"),

    # 장소 성격 분석 LLM
    path('llm-analysis/', views.analyze_selected_places_view, name='llm_analysis'),
    
    # 다이어리
    path("create_diary_from_plan/<int:plan_id>/", views.create_diary_from_plan, name="create_diary_from_plan"),
    path("upload/", views.upload_diary_entry, name="upload_diary_entry"),
    path("upload/<int:travel_id>/", views.upload_diary_entry, name="upload_diary_entry_to_travel"),
    path("diary/", views.diary_list, name="diary_list"),
    path("diary_home/", views.diary_home, name="diary_home"),
    path("create_diary/", views.create_travel_diary, name="create_travel_diary"),
    path("diary/<int:pk>/", views.travel_diary_detail, name="travel_diary_detail"),
    path("diary/<int:pk>/edit/", views.edit_travel_diary, name="edit_travel_diary"),
    path("diary_entry/<int:pk>/edit/", views.edit_diary_entry, name="edit_diary_entry"),
    path("diary_entry/<int:pk>/delete/", views.delete_diary_entry, name="delete_diary_entry"),
    path("diary_entry/<int:pk>/generate_tags/", views.generate_tags_view, name="generate_tags"),
    path("generate_tags_from_text/", views.generate_tags_from_text_view, name="generate_tags_from_text"),
    path("diary/<int:pk>/summarize/", views.summarize_diary_view, name="summarize_diary"),
    # path("agent_viewer/", views.travel_agent_viewer, name="travel_agent_viewer"),
    # path("agent_viewer/recommendations/", views.get_ai_recommendations, name="get_ai_recommendations"),

    # ✅ 신규: 인증 관련
    path("select_plan/", views.select_plan, name="select_plan"),

    # ✅ 새로 추가된 비동기 가이드 생성 API
    path("generate_guide/", views.generate_guide_api, name="generate_guide"),

    # ✅ 추가: 플랜/가이드 JSON
    path("get_selected_plan/", views.get_selected_plan_api, name="get_selected_plan"),
    path("proxy_mapbox/", views.proxy_mapbox_route, name="proxy_mapbox"),

    path('chat/<str:room_name>/', views.chat_view, name='chat'),
    path("travel/create/", views.create_travel_plan, name="create_travel_plan"),

    path("my_plans/", views.user_travel_plans, name="user_travel_plans"),
    path("plans_detail/<str:plan_id>/", views.travel_plan_detail, name="travel_plan_detail"),

    # 사용자 인증 관련
    # 로그인
    path(
        'login/',
        auth_views.LoginView.as_view(
            template_name='registration/login.html',
            redirect_authenticated_user=True  # 이미 로그인 상태면 메인으로
        ),
        name='login'
    ),

    # 로그아웃
    path('logout/', views.logout_view, name='logout'),

    # 회원가입
    path('signup/', views.signup_view, name='signup'),

    # 비밀번호 변경
    path('changePass/', views.change_password, name='changePass'),

    # 비밀번호 찾기
    path('changeFindForm/', views.reset_password_form, name='changeFindForm'),
    path('changeReset/', views.reset_password_instant, name='changeReset'),
]