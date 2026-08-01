"""
Формы для загрузки файлов и ввода данных
"""

from django import forms
from django.core.validators import FileExtensionValidator
from .models import PaySlip, PaySlipItem, PaymentCode
from datetime import date


class CodeDictionaryUploadForm(forms.Form):
    """Форма загрузки справочника кодов"""
    
    file = forms.FileField(
        label='Файл справочника',
        validators=[FileExtensionValidator(allowed_extensions=['txt', 'pdf'])],
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.txt,.pdf'
        })
    )


class ReceiptUploadForm(forms.Form):
    """Форма загрузки квитанции"""
    
    HALF_CHOICES = [
        (1, 'Первая половина (1-15)'),
        (2, 'Вторая половина (16-31)'),
    ]
    
    file = forms.FileField(
        label='Изображение квитанции',
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'pdf'])],
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.jpg,.jpeg,.png,.pdf'
        })
    )
    
    period = forms.DateField(
        label='Период',
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'month'
        }),
        initial=date.today().replace(day=1)
    )
    
    half = forms.ChoiceField(
        label='Половина месяца',
        choices=HALF_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )


class PaySlipForm(forms.ModelForm):
    """Форма создания/редактирования ведомости"""
    
    class Meta:
        model = PaySlip
        fields = ['period', 'half', 'receipt_image']
        widgets = {
            'period': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'month'
            }),
            'half': forms.Select(attrs={
                'class': 'form-control'
            }),
            'receipt_image': forms.FileInput(attrs={
                'class': 'form-control'
            })
        }


class PaySlipItemForm(forms.ModelForm):
    """Форма добавления строки ведомости"""
    
    class Meta:
        model = PaySlipItem
        fields = ['item_type', 'month', 'code', 'rv', 'amount']
        widgets = {
            'item_type': forms.Select(attrs={'class': 'form-control'}),
            'month': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 12}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'rv': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
        }


class ManualEntryForm(forms.Form):
    """Форма для ручного ввода данных квитанции"""
    
    HALF_CHOICES = [
        (1, 'Первая половина (1-15)'),
        (2, 'Вторая половина (16-31)'),
    ]
    
    period = forms.DateField(
        label='Период',
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'month'
        })
    )
    
    half = forms.ChoiceField(
        label='Половина месяца',
        choices=HALF_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    # Поля будут добавляться динамически через JavaScript


class PaymentCodeForm(forms.ModelForm):
    """Форма для добавления кода в справочник"""
    
    class Meta:
        model = PaymentCode
        fields = ['code', 'description', 'code_type']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'code_type': forms.Select(attrs={'class': 'form-control'})
        }


class ComparePeriodsForm(forms.Form):
    """Форма для сравнения периодов"""
    
    period1 = forms.ModelChoiceField(
        label='Первый период',
        queryset=PaySlip.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    period2 = forms.ModelChoiceField(
        label='Второй период',
        queryset=PaySlip.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
