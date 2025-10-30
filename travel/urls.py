from django.urls import path, register_converter
from django.contrib.auth import views as auth_views
from . import views

app_name = "travel"

urlpatterns = [

    # 여행 목록
    path("list/", views.travel_list, name="travel_list"),

    # 장소 성격 분석 LLM
    path('llm-analysis/', views.analyze_selected_places_view, name='llm_analysis'),
    
    # 다이어리
    path("upload/", views.upload_diary_entry, name="upload_diary_entry"),
    path("upload/<int:travel_id>/", views.upload_diary_entry, name="upload_diary_entry_to_travel"),
    path("diary/", views.diary_list, name="diary_list"),
    path("diary_home/", views.diary_home, name="diary_home"),
    path("create_diary/", views.create_travel_diary, name="create_travel_diary"),
    path("diary/<int:pk>/", views.travel_diary_detail, name="travel_diary_detail"),
    path("diary/<int:pk>/edit/", views.edit_travel_diary, name="edit_travel_diary"),
    path("diary_entry/<int:pk>/edit/", views.edit_diary_entry, name="edit_diary_entry"),
    path("diary_entry/<int:pk>/delete/", views.delete_diary_entry, name="delete_diary_entry"),

    # path("agent_viewer/", views.travel_agent_viewer, name="travel_agent_viewer"),
    # path("agent_viewer/recommendations/", views.get_ai_recommendations, name="get_ai_recommendations"),

    # ✅ 신규: 인증 관련
    # path("login/", views.login_view, name="login"),
    # path("signup/", views.signup_view, name="signup"),
    # path("logout/", views.logout_view, name="logout"),
    path("select_plan/", views.select_plan, name="select_plan"),

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