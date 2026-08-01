import subprocess

from django.forms import ModelForm, TextInput

from .models import Host
from django import forms
# doch/forms.py
from django import forms
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm


# class CustomLoginForm(AuthenticationForm):
#     username = forms.CharField(label='Имя пользователя', max_length=150)
#     password = forms.CharField(label='Пароль', widget=forms.PasswordInput)


class HostForm(ModelForm):
    class Meta:
        model = Host
        fields = ['ipaddr', 'hostname', 'cat']
        widgets = {
            'ipaddr': TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'IP адрес'
            }),
            'hostname': TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Имя хоста'
            }),

            # 'cpu_model': TextInput(attrs= {
            #     'class': 'form-control',
            #     'placeholder': 'Модель cpu'
            # }),

        }


# class CheckForm(ModelForm):
#     class Meta:
#         model = Host
#         fields =['cpu_1_min','cpu_5_min','uptime','mem_free','mem_used','mem_util', 'hostname',]
#         widgets = {
#             'hostname': TextInput(attrs={
#                 'class': 'form-control',
#                 'placeholder': 'Введите имя хоста'
#
#             }),
#
#         }
from django.forms import ModelForm, TextInput, BooleanField
from .models import Host


class CheckForm(forms.ModelForm):
    # class Meta:
    #     model = Host
    #     fields = '__all__'
    class Meta:
        model = Host
        fields = ['ipaddr', 'hostname', 'com_str','cpu_5_min', 'uptime', 'mem_free', 'mem_used', 'mem_util', 'parents',
                  'bat_temp', 'bat_time_work', 'bat_vol', 'run_reman', 'stat_charge',
                  'device_type']
        widgets = {
            'ipaddr': TextInput(attrs={
                'class': 'form-control1',
                'placeholder': 'IP адрес'
            }),
            'hostname': TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Введите имя хоста'
            }),
            # 'parents': TextInput(attrs={
            #     'class': 'form-control',
            #     'placeholder': 'Родитель'
            # }),

        }
        parents = forms.ModelChoiceField(
            queryset=Host.objects.all(),
            required=False,
            widget=forms.Select(attrs={
                'class': 'form-control',
                'placeholder': 'Родитель'
            })
        )
    cpu_5_min = BooleanField(label='CPU 5 min load', required=False)
    uptime = BooleanField(label='Uptime', required=False)
    mem_free = BooleanField(label='Memory Free', required=False)
    mem_used = BooleanField(label='Memory Used', required=False)
    mem_util = BooleanField(label='Memory Utilization', required=False)
    bat_temp = BooleanField(label='CPU 5 min load', required=False)
    bat_time_work = BooleanField(label='Uptime', required=False)
    bat_vol = BooleanField(label='Memory Free', required=False)
    run_reman = BooleanField(label='Memory Used', required=False)
    stat_charge = BooleanField(label='Memory Utilization', required=False)


class CheckForm1(forms.ModelForm):
    # class Meta:
    #     model = Host
    #     fields = '__all__'
    class Meta:
        model = Host
        fields = ['hostname', 'cpu_5_min', 'uptime', 'mem_free', 'mem_used', 'mem_util', ]
        widgets = {

            'hostname': TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Введите имя хоста'
            }),

        }

    # def clean_ip(self):
    #     ipaddr = self.cleaned_data.get('ipaddr')
    #     cmd = f"snmpwalk -v 2c -c public {ipaddr} sysName.0"
    #     try:
    #         result = subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    #                                 text=True)
    #     except subprocess.CalledProcessError:
    #         self.add_error('ip', 'SNMP не настроен на указанном IP. Заполнение чекбоксов недоступно.')
    #     return ipaddr
    # cpu_1_min = BooleanField(label='CPU Load 1 Min', required=False)
    cpu_5_min = BooleanField(label='CPU 5 min load', required=False)
    uptime = BooleanField(label='Uptime', required=False)
    mem_free = BooleanField(label='Memory Free', required=False)
    mem_used = BooleanField(label='Memory Used', required=False)
    mem_util = BooleanField(label='Memory Utilization', required=False)
class UserPasswordChangeForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args,**kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({
                'class':'form-control',
                'autocomplete':'off'
            })

from django import forms
from .models import LineSettings

class LineSettingsForm(forms.ModelForm):
    class Meta:
        model = LineSettings
        fields = ['line_id', 'color', 'weight', 'line_type']
        widgets = {
            'color': forms.TextInput(attrs={'type': 'color'}),
            'line_type': forms.Select(choices=LineSettings.LINE_TYPES),
        }