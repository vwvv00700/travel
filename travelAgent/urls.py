from django.contrib import admin
from django.urls import path, include
from .views import main, select, signup_view
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views


urlpatterns = [
    # 메인 랜딩 페이지
    path("", main, name="main"),

    # AI 추천 조건 선택 페이지
    path("select/", select, name="select"),

    # 편의 리다이렉트
    # path("login/", travel_views.login_view, name="root_login"),

    path('accounts/', include('django.contrib.auth.urls')),

    path("travel/", include("travel.urls")),

    # 1. 메인/홈 페이지
    path('', main, name='main'),

    # 2. 채팅방 목록/매칭 페이지 (이 페이지에서 파트너를 선택)
    # URL 경로 시작에 슬래시(/)를 넣지 않습니다.
    
    
    path("admin/", admin.site.urls),
    
    path('accounts/signup/', signup_view, name='signup'),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
]

# 개발환경에서 정적/미디어 서빙
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
