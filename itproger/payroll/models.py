from django.db import models
from django.utils import timezone
import json


class PaymentCode(models.Model):
    """Справочник кодов оплат"""
    code = models.CharField(max_length=50, unique=True, verbose_name="Код")
    description = models.CharField(max_length=500, verbose_name="Описание")
    category = models.CharField(max_length=100, blank=True, verbose_name="Категория")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Код оплаты"
        verbose_name_plural = "Коды оплат"
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.description}"


class PayrollPeriod(models.Model):
    """Период платежной ведомости"""
    HALF_CHOICES = [
        (1, 'Первая половина месяца'),
        (2, 'Вторая половина месяца'),
    ]

    year = models.IntegerField(verbose_name="Год")
    month = models.IntegerField(verbose_name="Месяц")
    half = models.IntegerField(choices=HALF_CHOICES, default=2, verbose_name="Половина месяца")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Период"
        verbose_name_plural = "Периоды"
        unique_together = ['year', 'month', 'half']
        ordering = ['-year', '-month', '-half']

    def __str__(self):
        months = ['', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
        half_str = "1-я пол." if self.half == 1 else "2-я пол."
        return f"{months[self.month]} {self.year} ({half_str})"

    @property
    def period_key(self):
        return f"{self.year}-{self.month:02d}-{self.half}"


class PayrollEntry(models.Model):
    """Запись платежной ведомости"""
    period = models.ForeignKey(PayrollPeriod, on_delete=models.CASCADE,
                               related_name='entries', verbose_name="Период")
    payment_code = models.ForeignKey(PaymentCode, on_delete=models.SET_NULL,
                                     null=True, blank=True, verbose_name="Код оплаты")
    raw_code = models.CharField(max_length=50, verbose_name="Исходный код")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Сумма")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Запись ведомости"
        verbose_name_plural = "Записи ведомостей"

    def __str__(self):
        desc = self.payment_code.description if self.payment_code else self.raw_code
        return f"{desc}: {self.amount}"


class UploadedFile(models.Model):
    """Загруженные файлы"""
    FILE_TYPES = [
        ('codebook', 'Справочник кодов'),
        ('receipt', 'Квитанция'),
    ]

    file = models.FileField(upload_to='uploads/%Y/%m/', verbose_name="Файл")
    file_type = models.CharField(max_length=20, choices=FILE_TYPES, verbose_name="Тип файла")
    period = models.ForeignKey(PayrollPeriod, on_delete=models.SET_NULL,
                               null=True, blank=True, verbose_name="Период")
    processed = models.BooleanField(default=False, verbose_name="Обработан")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Загруженный файл"
        verbose_name_plural = "Загруженные файлы"

    def __str__(self):
        return f"{self.get_file_type_display()} - {self.file.name}"
