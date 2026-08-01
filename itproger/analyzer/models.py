"""
Модели для хранения данных платежных ведомостей
"""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class PaymentCode(models.Model):
    """Справочник кодов оплат"""
    
    TYPE_CHOICES = [
        ('income', 'Начисление'),
        ('deduction', 'Удержание'),
    ]
    
    code = models.CharField('Код', max_length=10, unique=True)
    description = models.CharField('Описание', max_length=255)
    code_type = models.CharField('Тип', max_length=10, choices=TYPE_CHOICES, default='income')
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)
    
    class Meta:
        verbose_name = 'Код оплаты'
        verbose_name_plural = 'Коды оплат'
        ordering = ['code']
    
    def __str__(self):
        return f"{self.code} - {self.description}"


class PaySlip(models.Model):
    """Платежная ведомость (квитанция)"""
    
    HALF_CHOICES = [
        (1, 'Первая половина (1-15)'),
        (2, 'Вторая половина (16-31)'),
    ]
    
    period = models.DateField('Период (месяц)')
    half = models.IntegerField(
        'Половина месяца', 
        choices=HALF_CHOICES,
        validators=[MinValueValidator(1), MaxValueValidator(2)]
    )
    
    total_income = models.DecimalField(
        'Итого начислено', 
        max_digits=12, 
        decimal_places=2, 
        default=0
    )
    total_deduction = models.DecimalField(
        'Итого удержано', 
        max_digits=12, 
        decimal_places=2, 
        default=0
    )
    net_pay = models.DecimalField(
        'К выплате', 
        max_digits=12, 
        decimal_places=2, 
        default=0
    )
    
    receipt_image = models.ImageField(
        'Изображение квитанции', 
        upload_to='receipts/', 
        blank=True, 
        null=True
    )
    
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)
    
    class Meta:
        verbose_name = 'Платежная ведомость'
        verbose_name_plural = 'Платежные ведомости'
        ordering = ['-period', '-half']
        unique_together = ['period', 'half']
    
    def __str__(self):
        half_str = "1-я пол." if self.half == 1 else "2-я пол."
        return f"{self.period.strftime('%B %Y')} ({half_str})"
    
    def calculate_totals(self):
        """Пересчитать итоговые суммы"""
        self.total_income = sum(
            item.amount for item in self.items.filter(item_type='income')
        )
        self.total_deduction = sum(
            item.amount for item in self.items.filter(item_type='deduction')
        )
        self.net_pay = self.total_income - self.total_deduction
        self.save()


class PaySlipItem(models.Model):
    """Строка платежной ведомости (начисление или удержание)"""
    
    TYPE_CHOICES = [
        ('income', 'Начисление'),
        ('deduction', 'Удержание'),
    ]
    
    payslip = models.ForeignKey(
        PaySlip, 
        on_delete=models.CASCADE, 
        related_name='items',
        verbose_name='Ведомость'
    )
    item_type = models.CharField('Тип', max_length=10, choices=TYPE_CHOICES)
    month = models.IntegerField(
        'Месяц', 
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    code = models.CharField('Код', max_length=10)
    code_ref = models.ForeignKey(
        PaymentCode, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name='Справочник кода'
    )
    rv = models.DecimalField(
        'РВ (часы/дни)', 
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    amount = models.DecimalField('Сумма', max_digits=12, decimal_places=2)
    
    class Meta:
        verbose_name = 'Строка ведомости'
        verbose_name_plural = 'Строки ведомости'
        ordering = ['item_type', 'month', 'code']
    
    def __str__(self):
        return f"{self.get_item_type_display()}: {self.code} = {self.amount}"
    
    @property
    def description(self):
        """Получить описание из справочника"""
        if self.code_ref:
            return self.code_ref.description
        return "Неизвестный код"


class CodeDictionary(models.Model):
    """Загруженные файлы справочников"""
    
    file = models.FileField('Файл справочника', upload_to='dictionaries/')
    uploaded_at = models.DateTimeField('Дата загрузки', auto_now_add=True)
    processed = models.BooleanField('Обработан', default=False)
    codes_count = models.IntegerField('Количество кодов', default=0)
    
    class Meta:
        verbose_name = 'Справочник'
        verbose_name_plural = 'Справочники'
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"Справочник от {self.uploaded_at.strftime('%d.%m.%Y %H:%M')}"
