from django.urls import path, register_converter
from django.contrib.auth import views as auth_views
from . import views
from .views import travel_plan_new, travel_plan_list, travel_plan_edit


app_name = "travel"

urlpatterns = [
    # 여행 계획
    path('plan/new/', travel_plan_new, name='travel_plan_new'),
    path('plan/list/', travel_plan_list, name='travel_plan_list'),
    path('plan/edit/<int:plan_id>/', travel_plan_edit, name='travel_plan_edit'),

    # 로그아웃
    path('logout/', views.logout_view, name='logout'),

    # 여행 목록
    path("list/", views.travel_list, name="travel_list"),

    # 채팅
    path('chat/<str:room_name>/', views.chat_view, name='chat'),

    # 로그인
    path(
        'login/',
        auth_views.LoginView.as_view(
            template_name='chat/login.html',
            redirect_authenticated_user=True  # 이미 로그인 상태면 메인으로
        ),
        name='login'
    ),

    # 회원가입 추가
    path('signup/', views.signup_view, name='signup'),
]