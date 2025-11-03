from django.contrib import admin
from django.urls import path, include
from .views import main, select, signup_view, chat
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from travel import views as travel_views

urlpatterns = [
    # 메인 랜딩 페이지
    path("", main, name="main"),

    # AI 추천 조건 선택 페이지
    path("select/", select, name="select"),

    # 편의 리다이렉트
    # path("login/", travel_views.login_view, name="root_login"),

    path('accounts/', include('django.contrib.auth.urls')),

    path("travel/", include("travel.urls")),
    
    # 어드민
    path("admin/", admin.site.urls),
    
    # 유저 관련
    path('accounts/signup/', signup_view, name='signup'),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    
    # 채팅 및 매칭
    path('chat/', chat, name='chat_list'),
    path('chat/', chat, name='chat'),
    path('chat/report/', travel_views.report_message, name='chat_report'),
] 

# 개발환경에서 정적/미디어 서빙
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)