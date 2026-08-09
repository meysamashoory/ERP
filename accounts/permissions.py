"""Reusable access-control helpers built on top of :class:`UserProfile`."""

from django.contrib.auth.mixins import AccessMixin

from .models import Role, UserProfile


def get_profile(user) -> UserProfile | None:
    if not user.is_authenticated:
        return None
    profile = getattr(user, "profile", None)
    if profile is None:
        profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


class RoleRequiredMixin(AccessMixin):
    """Restrict a class-based view to a capability flag on the profile.

    Set ``required_capability`` to a boolean property name on ``UserProfile``
    (for example ``"can_enter_data"`` or ``"can_create_plans"``).
    """

    required_capability: str | None = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        profile = get_profile(request.user)
        if self.required_capability:
            if not getattr(profile, self.required_capability, False):
                return self.handle_no_permission()
        self.profile = profile
        return super().dispatch(request, *args, **kwargs)


__all__ = ["Role", "UserProfile", "get_profile", "RoleRequiredMixin"]
