from django.urls import path, register_converter
from django.contrib.auth import views as auth_views
from travel import views
from django.shortcuts import render

app_name = "travel"
urlpatterns = [
    path("list/", views.travel_list, name="travel_list"),
    path('chat/<str:room_name>/', views.chat_view, name='chat'),
    path(
        'login/',
        auth_views.LoginView.as_view(
            template_name='chat/login.html',
            redirect_authenticated_user=True  # 이미 로그인 상태면 메인으로
        ),
        name='login'
    ),
    path('chat/test/', views.test_chat_room, name='chat_test'),
]