from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.conf.urls.i18n import i18n_patterns

# Import views from the project's views.py (travelAgent/views.py)
from .views import main, select, signup_view, chat

# Import views from the travel app (travel/views.py)
from travel import views as travel_views

# URLs that do NOT get an i18n prefix
urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
    path("admin/", admin.site.urls),
]

# 🌐 다국어 적용 URL 패턴 (언어 접두사 /ko/, /en/, /es/ 가 붙습니다)
urlpatterns += i18n_patterns(
    # Main landing page
    path("", main, name="main"), # Assuming main is the actual main page

    # AI recommendation selection page
    path("select/", select, name="select"),

    # Django built-in auth URLs (login, logout, password_reset etc.)
    path('accounts/', include('django.contrib.auth.urls')),

    # Include URLs from the travel app
    path("travel/", include("travel.urls")),
    
    # User-related custom URLs
    path('accounts/signup/', signup_view, name='signup'),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    
    # Chat and Matching
    path('chat/', chat, name='chat_list_page'), # Assuming 'chat' from .views is the chat list
    path('chat/report/', travel_views.report_message, name='chat_report'),
    path('chat/matching/', travel_views.matching, name='matching'),

    # My Travel Plans page (renamed for clarity)
    path('my-travel-plans/', travel_views.user_travel_plans, name='my_travel_plans_page'),

    prefix_default_language=False
) 

# Static and Media files serving in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)