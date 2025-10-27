
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "travelAgent.settings")
django.setup()

from travel.models import Place
from collections import Counter

def inspect_categories():
    print("--- Category Inspection Start ---")

    # Get all unique categories and their counts
    category_counts = Counter(Place.objects.values_list('category', flat=True))

    print(f"\nFound {len(category_counts)} unique categories:")
    for category, count in category_counts.most_common():
        if category:
            print(f"  - {category}: {count} times")

    print("\n--- Category Inspection End ---")

inspect_categories()
