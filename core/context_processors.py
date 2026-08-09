from accounts.permissions import get_profile


def user_profile(request):
    """Expose the current user's profile to every template."""
    if request.user.is_authenticated:
        return {"profile": get_profile(request.user)}
    return {"profile": None}
