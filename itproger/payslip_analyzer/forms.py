
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
            'accept': '.txt,.pdf',
            'id': 'codeFile'
        }),
        help_text='Поддерживаемые форматы: TXT, PDF. Формат данных: "код - описание"'
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
            'accept': '.jpg,.jpeg,.png,.pdf',
            'id': 'receiptFile'
        }),
        help_text='Поддерживаемые форматы: JPG, PNG, PDF'
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
        }),
        initial=1
    )
class PaySlipForm(forms.ModelForm):
    """Форма создания/редактирования ведомости"""

    class Meta:
        model = PaySlip
        fields = ['period', 'half', 'receipt_image', 'notes']
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
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            })
        }
class PaySlipItemForm(forms.ModelForm):
    """Форма добавления строки ведомости"""

    class Meta:
        model = PaySlipItem
        fields = ['item_type', 'month', 'code', 'rv', 'amount']
        widgets = {
            'item_type': forms.Select(attrs={'class': 'form-control'}),
            'month': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 12,
                'placeholder': '10'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '4'
            }),
            'rv': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': '20'
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': '0.00'
            })
        }
class PaymentCodeForm(forms.ModelForm):
    """Форма для добавления/редактирования кода в справочник"""

    class Meta:
        model = PaymentCode
        fields = ['code', 'description', 'code_type', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '4'
            }),
            'description': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Оклад по дням'
            }),
            'code_type': forms.Select(attrs={
                'class': 'form-control'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
class ComparePeriodsForm(forms.Form):
    """Форма для сравнения периодов"""

    period1 = forms.ModelChoiceField(
        label='Первый период',
        queryset=PaySlip.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'}),
        empty_label='Выберите период'
    )

    period2 = forms.ModelChoiceField(
        label='Второй период',
        queryset=PaySlip.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'}),
        empty_label='Выберите период'
    )

    def clean(self):
        cleaned_data = super().clean()
        period1 = cleaned_data.get('period1')
        period2 = cleaned_data.get('period2')

        if period1 and period2 and period1 == period2:
            raise forms.ValidationError('Выберите разные периоды для сравнения')

        return cleaned_data
class BulkItemsForm(forms.Form):
    """Форма для массового добавления строк (JSON)"""

    period = forms.DateField(
        label='Период',
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'month'
        })
    )

    half = forms.ChoiceField(
        label='Половина месяца',
        choices=PaySlip.HALF_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    income_data = forms.CharField(
        label='Начисления (JSON)',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 5,
            'placeholder': '[{"month": 10, "code": "4", "rv": 20, "amount": 29017.39}]'
        }),
        required=False
    )

    deduction_data = forms.CharField(
        label='Удержания (JSON)',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 5,
            'placeholder': '[{"month": 10, "code": "700", "amount": 16462.38}]'
        }),
        required=False
    )
