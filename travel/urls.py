from django.urls import path, register_converter
from travel import views


app_name = "travel"
urlpatterns = [
    path("list/", views.travel_list, name="travel_list"),
    path('llm-analysis/', views.analyze_selected_places_view, name='llm_analysis'),
    
]