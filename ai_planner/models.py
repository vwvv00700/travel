from django.db import models

class AISettings(models.Model):
    API_CHOICES = [
        ('gemini', 'Google Gemini'),
        ('openai', 'OpenAI GPT'),
    ]

    openai_api_key = models.CharField(max_length=255, blank=True, null=True, verbose_name="OpenAI API Key")
    google_gemini_api_key = models.CharField(max_length=255, blank=True, null=True, verbose_name="Google Gemini API Key")
    default_api_model = models.CharField(
        max_length=10,
        choices=API_CHOICES,
        default='gemini',
        verbose_name="기본 AI 모델"
    )

    class Meta:
        verbose_name = "AI 설정"
        verbose_name_plural = "AI 설정"

    def __str__(self):
        return "AI 설정"

    def save(self, *args, **kwargs):
        # Ensure there's only one instance of this model
        if self.__class__.objects.exists() and not self.pk:
            # If an instance already exists and this is a new object, update the existing one
            existing = self.__class__.objects.first()
            self.pk = existing.pk
            super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)