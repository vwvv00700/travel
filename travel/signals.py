from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile

@receiver(post_save, sender=User)
def create_profile_if_missing(sender, instance, created, **kwargs):
    if created:
        # 새 유저일 때만
        UserProfile.objects.create(
            user=instance,
            nickname=instance.username,
            bio="",
            preferred_style="",
        )
