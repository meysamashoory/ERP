from django.conf import settings
from django.db import models


class Role(models.TextChoices):
    """System access levels described in the specification."""

    PLANNING_MANAGER = "planning_manager", "مدیر برنامه‌ریزی"
    PLANNING_EXPERT = "planning_expert", "کارشناس برنامه‌ریزی"
    PLANNING_CLERK = "planning_clerk", "کارمند برنامه‌ریزی"
    VIEWER = "viewer", "مشاهده‌گر"


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(
        max_length=32, choices=Role.choices, default=Role.VIEWER
    )
    # Grants an expert/clerk permission to edit records created by others.
    can_edit_others = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"{self.user.get_username()} — {self.get_role_display()}"

    # --- Capability helpers used across the app -------------------------
    @property
    def is_manager(self) -> bool:
        return self.role == Role.PLANNING_MANAGER

    @property
    def can_manage_users(self) -> bool:
        return self.is_manager

    @property
    def can_view_conflicts(self) -> bool:
        """Expert/clerk/manager may open conflict review; viewers cannot."""
        return self.role in {
            Role.PLANNING_MANAGER,
            Role.PLANNING_EXPERT,
            Role.PLANNING_CLERK,
        }

    @property
    def can_resolve_conflicts(self) -> bool:
        """Only the planning manager may apply conflict fixes."""
        return self.is_manager

    @property
    def can_enter_data(self) -> bool:
        """Viewers are read-only; everyone else may enter operational data."""
        return self.role in {
            Role.PLANNING_MANAGER,
            Role.PLANNING_EXPERT,
            Role.PLANNING_CLERK,
        }

    @property
    def can_create_plans(self) -> bool:
        """Clerks may view weekly plans but not create them."""
        return self.role in {Role.PLANNING_MANAGER, Role.PLANNING_EXPERT}

    @property
    def can_approve_plans(self) -> bool:
        return self.is_manager

    @property
    def can_backup(self) -> bool:
        return self.is_manager

    @property
    def can_create_reports(self) -> bool:
        """Viewers are read-only; everyone else may create reports/forms."""
        return self.can_enter_data

    def can_edit_record(self, record) -> bool:
        """Whether this profile may edit a record with a ``created_by`` field."""
        if not self.can_enter_data:
            return False
        if self.is_manager or self.can_edit_others:
            return True
        owner_id = getattr(record, "created_by_id", None)
        return owner_id == self.user_id
