
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "travelAgent.settings")
django.setup()

from travel.models import Place, PlaceAnalysis
from collections import Counter
import json

def inspect_db():
    print("--- Database Inspection Start ---")

    # Count total places
    total_places = Place.objects.count()
    print(f"\n[1] Total number of places in DB: {total_places}")

    if total_places == 0:
        print("\nInspection finished: Database is empty.")
        return

    # Get all unique districts
    districts = Place.objects.values_list('city_gu', flat=True).distinct()
    districts_list = [d for d in districts if d]
    print(f"\n[2] Unique districts found ({len(districts_list)}):")
    print(districts_list)

    # Get all themes
    all_themes = []
    place_analyses = PlaceAnalysis.objects.filter(themes_csv__isnull=False)
    for pa in place_analyses:
        themes = [theme.strip() for theme in pa.themes_csv.split(',') if theme.strip()]
        all_themes.extend(themes)
    
    theme_counts = Counter(all_themes)
    print(f"\n[3] Unique themes found ({len(theme_counts)}):")
    # Print top 20 most common themes
    for theme, count in theme_counts.most_common(20):
        print(f"  - {theme}: {count} times")

    # Check places with both district and theme
    places_with_themes = Place.objects.filter(analysis__themes_csv__isnull=False).exclude(analysis__themes_csv__exact='')
    print(f"\n[4] Number of places with associated themes: {places_with_themes.count()}")


    print("\n--- Database Inspection End ---")

inspect_db()
