"""
URL configuration for travelAgent project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from .views import main, select
from django.conf import settings
from django.conf.urls.static import static
from travel import views as travel_views

urlpatterns = [
    # 메인 랜딩 페이지
    path("", main, name="main"),

    # AI 추천 조건 선택 페이지
    path("select/", select, name="select"),

    # 편의 리다이렉트
    # path("login/", travel_views.login_view, name="root_login"),

    path('accounts/', include('django.contrib.auth.urls')),

    # TravelMate 주요 화면:
    #   /travel/list/ 안에서 Leaflet 지도 위에
    #   Mapbox Directions API 결과(실제 도로 경로)를 그려줌.
    #   외부 지도 앱 전환 없이, 같은 화면에서 즉시 라우팅.
    path("travel/", include("travel.urls")),

    # Django 관리자
    path("admin/", admin.site.urls),
]

# 개발환경에서 정적/미디어 서빙
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
