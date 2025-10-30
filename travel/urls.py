from django.urls import path, register_converter
from travel import views


app_name = "travel"
urlpatterns = [
    path("list/", views.travel_list, name="travel_list"),
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
    path("diary_entry/<int:pk>/generate_tags/", views.generate_tags_view, name="generate_tags"),
    path("generate_tags_from_text/", views.generate_tags_from_text_view, name="generate_tags_from_text"),
    path("tags/<str:tag_name>/", views.diary_entries_by_tag, name="diary_entries_by_tag"),
    path("diary/<int:pk>/summarize/", views.summarize_diary_view, name="summarize_diary"),
    path("agent_viewer/", views.travel_agent_viewer, name="travel_agent_viewer"),
    path("agent_viewer/recommendations/", views.get_ai_recommendations, name="get_ai_recommendations"),

    # ✅ 신규: 인증 관련
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("logout/", views.logout_view, name="logout"),
    path("select_plan/", views.select_plan, name="select_plan"),
]