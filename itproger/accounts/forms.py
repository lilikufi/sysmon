from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm


class CustomAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        max_length=100,
        label='Username',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    password = forms.CharField(
        label='Password',
        strip=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
    )


class UserPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update(
                {
                    'class': 'form-control',
                    'autocomplete': 'off',
                }
            )
