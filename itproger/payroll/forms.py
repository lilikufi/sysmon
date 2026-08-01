from django import forms
from .models import PayrollPeriod, UploadedFile
import datetime
class CodebookUploadForm(forms.Form):
    """Форма загрузки справочника кодов"""
    file = forms.FileField(
        label='Файл справочника',
        help_text='Поддерживаемые форматы: TXT, PDF',
        widget=forms.FileInput(attrs={
            'accept': '.txt,.pdf',
            'class': 'file-input'
        })
    )
    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            ext = file.name.split('.')[-1].lower()
            if ext not in ['txt', 'pdf']:
                raise forms.ValidationError('Поддерживаются только TXT и PDF файлы')
        return file
class ReceiptUploadForm(forms.Form):
    """Форма загрузки квитанции"""
    MONTH_CHOICES = [
        (1, 'Январь'), (2, 'Февраль'), (3, 'Март'), (4, 'Апрель'),
        (5, 'Май'), (6, 'Июнь'), (7, 'Июль'), (8, 'Август'),
        (9, 'Сентябрь'), (10, 'Октябрь'), (11, 'Ноябрь'), (12, 'Декабрь')
    ]
    HALF_CHOICES = [
        (1, 'Первая половина'),
        (2, 'Вторая половина'),
    ]

    file = forms.FileField(
        label='Файл квитанции',
        help_text='Поддерживаемые форматы: TXT, JPG, PNG, PDF',
        widget=forms.FileInput(attrs={
            'accept': '.txt,.jpg,.jpeg,.png,.pdf',
            'class': 'file-input'
        })
    )
    year = forms.IntegerField(
        label='Год',
        initial=datetime.datetime.now().year,
        min_value=2000,
        max_value=2100,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    month = forms.ChoiceField(
        label='Месяц',
        choices=MONTH_CHOICES,
        initial=datetime.datetime.now().month,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    half = forms.ChoiceField(
        label='Половина месяца',
        choices=HALF_CHOICES,
        initial=2,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            ext = file.name.split('.')[-1].lower()
            if ext not in ['txt', 'jpg', 'jpeg', 'png', 'pdf']:
                raise forms.ValidationError('Поддерживаются только TXT, JPG, PNG и PDF файлы')
        return file
class ManualEntryForm(forms.Form):
    """Форма ручного ввода данных"""
    MONTH_CHOICES = [
        (1, 'Январь'), (2, 'Февраль'), (3, 'Март'), (4, 'Апрель'),
        (5, 'Май'), (6, 'Июнь'), (7, 'Июль'), (8, 'Август'),
        (9, 'Сентябрь'), (10, 'Октябрь'), (11, 'Ноябрь'), (12, 'Декабрь')
    ]
    HALF_CHOICES = [
        (1, 'Первая половина'),
        (2, 'Вторая половина'),
    ]

    year = forms.IntegerField(
        label='Год',
        initial=datetime.datetime.now().year,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    month = forms.ChoiceField(
        label='Месяц',
        choices=MONTH_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    half = forms.ChoiceField(
        label='Половина месяца',
        choices=HALF_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    entries_data = forms.CharField(
        label='Данные (код - сумма, каждая запись с новой строки)',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 10,
            'placeholder': '4 - 29017.39\n22 - 2393.93\n38 - 16624.00\n64 - 23347.83'
        })
    )
class PeriodFilterForm(forms.Form):
    """Форма фильтрации по периоду"""
    period = forms.ModelChoiceField(
        queryset=PayrollPeriod.objects.all(),
        label='Период',
        required=False,
        empty_label='Все периоды',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
