from django import forms
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm


class CustomAuthenticationForm(AuthenticationForm):
    username = forms.CharField(max_length=100, label='Имя пользователя', widget=forms.TextInput(attrs={'class': 'form-control'}))
    password = forms.CharField(label='Пароль', strip=False, widget=forms.PasswordInput(attrs={'class': 'form-control'}))

class UserPasswordChangeForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args,**kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({
                'class':'form-control',
                'autocomplete':'off'
            })