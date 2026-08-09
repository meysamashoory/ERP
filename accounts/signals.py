from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Role, UserProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile(sender, instance, created, **kwargs):
    """Every user has a profile. Superusers default to planning manager."""
    if created:
        role = Role.PLANNING_MANAGER if instance.is_superuser else Role.VIEWER
        UserProfile.objects.create(user=instance, role=role)
    elif not hasattr(instance, "profile"):
        UserProfile.objects.create(user=instance)
