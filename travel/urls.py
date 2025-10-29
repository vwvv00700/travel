from django.urls import path
from travel import views

app_name = "travel"

urlpatterns = [
    # 기존 여행 코스 화면
    path("list/", views.travel_list, name="travel_list"),
    path("llm-analysis/", views.analyze_selected_places_view, name="llm_analysis"),

    # ✅ 신규: 인증 관련
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("logout/", views.logout_view, name="logout"),
    path("select_plan/", views.select_plan, name="select_plan"),
]
