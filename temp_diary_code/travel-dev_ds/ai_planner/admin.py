from django.contrib import admin
from .models import AISettings

@admin.register(AISettings)
class AISettingsAdmin(admin.ModelAdmin):
    list_display = ('default_api_model',)
    fields = ('default_api_model',)

    def has_add_permission(self, request):
        # Allow adding only if no instance exists
        return not AISettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Prevent deletion
        return False