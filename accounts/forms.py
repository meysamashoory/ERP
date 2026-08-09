from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import Role

User = get_user_model()


class NewUserForm(forms.Form):
    username = forms.CharField(label="نام کاربری", max_length=150)
    first_name = forms.CharField(label="نام", max_length=150, required=False)
    last_name = forms.CharField(label="نام خانوادگی", max_length=150, required=False)
    password = forms.CharField(label="گذرواژه", widget=forms.PasswordInput)
    role = forms.ChoiceField(label="نقش", choices=Role.choices)
    can_edit_others = forms.BooleanField(
        label="اجازه ویرایش داده دیگران", required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name != "can_edit_others":
                field.widget.attrs.setdefault("class", "input")

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("این نام کاربری قبلاً ثبت شده است.")
        return username

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password

    def save(self):
        data = self.cleaned_data
        user = User.objects.create_user(
            username=data["username"],
            password=data["password"],
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
        )
        profile = user.profile
        profile.role = data["role"]
        profile.can_edit_others = data["can_edit_others"]
        profile.save()
        return user
