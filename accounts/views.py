from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render

from .forms import NewUserForm
from .permissions import get_profile

User = get_user_model()


@login_required
def user_management(request):
    profile = get_profile(request.user)
    if not profile or not profile.can_manage_users:
        raise PermissionDenied("فقط مدیر برنامه‌ریزی به این صفحه دسترسی دارد.")

    if request.method == "POST":
        form = NewUserForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"کاربر «{user.username}» ایجاد شد.")
            return redirect("user_management")
    else:
        form = NewUserForm()

    users = User.objects.select_related("profile").order_by("username")
    return render(
        request,
        "accounts/user_management.html",
        {"users": users, "form": form},
    )
