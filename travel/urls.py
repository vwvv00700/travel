from django.urls import path, register_converter
from django.contrib.auth import views as auth_views
from travel import views
from django.shortcuts import render

app_name = "travel"
urlpatterns = [
    path("list/", views.travel_list, name="travel_list"),
    path("test/", views.travel_test, name="travel_test"),
    path('llm-analysis/', views.analyze_selected_places_view, name='llm_analysis'),
    path("upload/", views.upload_diary_entry, name="upload_diary_entry"),
    path("upload/<int:travel_id>/", views.upload_diary_entry, name="upload_diary_entry_to_travel"),
    path("diary/", views.diary_list, name="diary_list"),
    path("diary_home/", views.diary_home, name="diary_home"),
    path("create_diary/", views.create_travel_diary, name="create_travel_diary"),
    path("diary/<int:pk>/", views.travel_diary_detail, name="travel_diary_detail"),
    path("diary/<int:pk>/edit/", views.edit_travel_diary, name="edit_travel_diary"),
    path("diary_entry/<int:pk>/edit/", views.edit_diary_entry, name="edit_diary_entry"),
    path("diary_entry/<int:pk>/delete/", views.delete_diary_entry, name="delete_diary_entry"),
    path("agent_viewer/", views.travel_agent_viewer, name="travel_agent_viewer"),
    path("agent_viewer/recommendations/", views.get_ai_recommendations, name="get_ai_recommendations"),
    path("travel/create/", views.create_travel_plan, name="create_travel_plan"),
    path('chat/<str:room_name>/', views.chat_view, name='chat'),
    path(
        'login/',
        auth_views.LoginView.as_view(
            template_name='registration/login.html',
            redirect_authenticated_user=True  # 이미 로그인 상태면 메인으로
        ),
        name='login'
    ),
]