from django.contrib import admin
from django.urls import path, include
from .views import main, select, signup_view, chat
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from travel import views as travel_views

from django.contrib import admin
from django.urls import path, include
from .views import main, select, signup_view, chat
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from travel import views as travel_views
from django.conf.urls.i18n import i18n_patterns # <-- i18n_patterns 임포트

# 다국어 미적용 URL 패턴 (언어 코드를 붙이지 않을 URL)
# admin과 i18n/ set_language는 i18n_patterns 밖에 두는 것이 일반적입니다.
urlpatterns = [
    # Django의 기본 언어 설정 뷰입니다. (언어 전환 폼의 action URL로 사용됨)
    path('i18n/', include('django.conf.urls.i18n')),

    # 어드민 페이지 (admin은 일반적으로 언어 접두사를 붙이지 않습니다.)
    path("admin/", admin.site.urls),
]

# 🌐 다국어 적용 URL 패턴 (언어 접두사 /ko/, /en/, /es/ 가 붙습니다)
urlpatterns += i18n_patterns(
    # 메인 랜딩 페이지
    path("", travel_views.user_travel_plans, name="main"),

    # AI 추천 조건 선택 페이지
    path("select/", select, name="select"),

    # Django 기본 인증 URL (login, logout, password_reset 등)
    # accounts/login/ -> /ko/accounts/login/, /en/accounts/login/
    path('accounts/', include('django.contrib.auth.urls')),

    # travel 앱의 URL들을 포함합니다.
    path("travel/", include("travel.urls")),
    
    # 유저 관련 직접 정의한 URL
    path('accounts/signup/', signup_view, name='signup'),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    
    # 채팅 및 매칭
    path('chat/', chat, name='chat_list'),
    path('chat/', chat, name='chat'),
    path('chat/report/', travel_views.report_message, name='chat_report'),
    
    path('chat/matching/', travel_views.matching, name='matching'),

    prefix_default_language=False # <-- 기본 언어(ko)에는 접두사(/ko/)를 붙이지 않음 (선택 사항)
) 

# 개발환경에서 정적/미디어 서빙 (i18n_patterns 밖에 둡니다.)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
