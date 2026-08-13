from django import forms
from django.contrib.auth.forms import SetPasswordForm

from .models import Host, LineSettings


class HostForm(forms.ModelForm):
    class Meta:
        model = Host
        fields = ['ipaddr', 'hostname', 'cat']
        widgets = {
            'ipaddr': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'IP адрес'}
            ),
            'hostname': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Имя хоста'}
            ),
        }


class CheckForm(forms.ModelForm):
    cpu_5_min = forms.BooleanField(label='CPU 5 min load', required=False)
    uptime = forms.BooleanField(label='Uptime', required=False)
    mem_free = forms.BooleanField(label='Memory Free', required=False)
    mem_used = forms.BooleanField(label='Memory Used', required=False)
    mem_util = forms.BooleanField(label='Memory Utilization', required=False)
    bat_temp = forms.BooleanField(label='CPU 5 min load', required=False)
    bat_time_work = forms.BooleanField(label='Uptime', required=False)
    bat_vol = forms.BooleanField(label='Memory Free', required=False)
    run_reman = forms.BooleanField(label='Memory Used', required=False)
    stat_charge = forms.BooleanField(label='Memory Utilization', required=False)

    class Meta:
        model = Host
        fields = [
            'ipaddr',
            'hostname',
            'com_str',
            'cpu_5_min',
            'uptime',
            'mem_free',
            'mem_used',
            'mem_util',
            'parents',
            'bat_temp',
            'bat_time_work',
            'bat_vol',
            'run_reman',
            'stat_charge',
            'device_type',
        ]
        widgets = {
            'ipaddr': forms.TextInput(
                attrs={'class': 'form-control1', 'placeholder': 'IP адрес'}
            ),
            'hostname': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Введите имя хоста'}
            ),
        }


class CheckForm1(forms.ModelForm):
    cpu_5_min = forms.BooleanField(label='CPU 5 min load', required=False)
    uptime = forms.BooleanField(label='Uptime', required=False)
    mem_free = forms.BooleanField(label='Memory Free', required=False)
    mem_used = forms.BooleanField(label='Memory Used', required=False)
    mem_util = forms.BooleanField(label='Memory Utilization', required=False)

    class Meta:
        model = Host
        fields = ['hostname', 'cpu_5_min', 'uptime', 'mem_free', 'mem_used', 'mem_util']
        widgets = {
            'hostname': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Введите имя хоста'}
            ),
        }


class UserPasswordChangeForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control', 'autocomplete': 'off'})


class LineSettingsForm(forms.ModelForm):
    class Meta:
        model = LineSettings
        fields = ['line_id', 'color', 'weight', 'line_type']
        widgets = {
            'color': forms.TextInput(attrs={'type': 'color'}),
            'line_type': forms.Select(choices=LineSettings.LINE_TYPES),
        }
