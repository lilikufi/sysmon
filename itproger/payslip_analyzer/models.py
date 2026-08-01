
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
class PaymentCode(models.Model):
    """Справочник кодов оплат"""

    TYPE_CHOICES = [
        ('income', 'Начисление'),
        ('deduction', 'Удержание'),
    ]

    code = models.CharField('Код', max_length=10, unique=True, db_index=True)
    description = models.CharField('Описание', max_length=255)
    code_type = models.CharField('Тип', max_length=10, choices=TYPE_CHOICES, default='income')
    is_active = models.BooleanField('Активен', default=True)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)

    class Meta:
        verbose_name = 'Код оплаты'
        verbose_name_plural = 'Коды оплат'
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.description}"

    @classmethod
    def get_default_codes(cls):
        """Стандартные коды для быстрого добавления"""
        return [
            # Начисления
            {'code': '4', 'description': 'Оклад по дням', 'code_type': 'income'},
            {'code': '22', 'description': 'Доплата за совмещение', 'code_type': 'income'},
            {'code': '38', 'description': 'Премия', 'code_type': 'income'},
            {'code': '64', 'description': 'Надбавка за стаж', 'code_type': 'income'},
            {'code': '67', 'description': 'Доплата за вредность', 'code_type': 'income'},
            {'code': '69', 'description': 'Компенсация питания', 'code_type': 'income'},
            {'code': '71', 'description': 'Районный коэффициент', 'code_type': 'income'},
            {'code': '89', 'description': 'Ночные часы', 'code_type': 'income'},
            {'code': '95', 'description': 'Оплата праздничных дней', 'code_type': 'income'},
            # Удержания
            {'code': '700', 'description': 'НДФЛ', 'code_type': 'deduction'},
            {'code': '702', 'description': 'Профсоюзные взносы', 'code_type': 'deduction'},
            {'code': '718', 'description': 'Добровольное страхование', 'code_type': 'deduction'},
            {'code': '720', 'description': 'Аванс', 'code_type': 'deduction'},
            {'code': '730', 'description': 'Алименты', 'code_type': 'deduction'},
            {'code': '740', 'description': 'Кредит', 'code_type': 'deduction'},
        ]
class PaySlip(models.Model):
    """Платежная ведомость (квитанция)"""

    HALF_CHOICES = [
        (1, 'Первая половина (1-15)'),
        (2, 'Вторая половина (16-31)'),
    ]

    period = models.DateField('Период (месяц)', db_index=True)
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
        upload_to='payslip_analyzer/receipts/%Y/%m/',
        blank=True,
        null=True
    )

    notes = models.TextField('Примечания', blank=True)

    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)

    class Meta:
        verbose_name = 'Платежная ведомость'
        verbose_name_plural = 'Платежные ведомости'
        ordering = ['-period', '-half']
        unique_together = ['period', 'half']
        indexes = [
            models.Index(fields=['period', 'half']),
        ]

    def __str__(self):
        half_str = "1-я пол." if self.half == 1 else "2-я пол."
        return f"{self.period.strftime('%B %Y')} ({half_str})"

    def get_period_display(self):
        """Форматированное отображение периода"""
        months = [
            '', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
            'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
        ]
        half_str = "1-я половина" if self.half == 1 else "2-я половина"
        return f"{months[self.period.month]} {self.period.year} ({half_str})"

    def calculate_totals(self):
        """Пересчитать итоговые суммы"""
        from django.db.models import Sum

        income = self.items.filter(item_type='income').aggregate(
            total=Sum('amount')
        )['total'] or 0

        deduction = self.items.filter(item_type='deduction').aggregate(
            total=Sum('amount')
        )['total'] or 0

        self.total_income = income
        self.total_deduction = deduction
        self.net_pay = income - deduction
        self.save(update_fields=['total_income', 'total_deduction', 'net_pay', 'updated_at'])

    def get_income_items(self):
        """Получить все начисления"""
        return self.items.filter(item_type='income').select_related('code_ref')

    def get_deduction_items(self):
        """Получить все удержания"""
        return self.items.filter(item_type='deduction').select_related('code_ref')
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
    item_type = models.CharField('Тип', max_length=10, choices=TYPE_CHOICES, db_index=True)
    month = models.IntegerField(
        'Месяц',
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    code = models.CharField('Код', max_length=10, db_index=True)
    code_ref = models.ForeignKey(
        PaymentCode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Справочник кода',
        related_name='payslip_items'
    )
    rv = models.DecimalField(
        'РВ (часы/дни)',
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Рабочее время: часы или дни'
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

    def save(self, *args, **kwargs):
        # Автоматически привязываем код из справочника
        if not self.code_ref and self.code:
            self.code_ref = PaymentCode.objects.filter(code=self.code).first()
        super().save(*args, **kwargs)
class CodeDictionary(models.Model):
    """Загруженные файлы справочников"""

    file = models.FileField('Файл справочника', upload_to='payslip_analyzer/dictionaries/')
    original_filename = models.CharField('Оригинальное имя файла', max_length=255)
    uploaded_at = models.DateTimeField('Дата загрузки', auto_now_add=True)
    processed = models.BooleanField('Обработан', default=False)
    codes_found = models.IntegerField('Найдено кодов', default=0)
    codes_added = models.IntegerField('Добавлено кодов', default=0)
    error_message = models.TextField('Ошибка обработки', blank=True)

    class Meta:
        verbose_name = 'Загруженный справочник'
        verbose_name_plural = 'Загруженные справочники'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.original_filename} ({self.uploaded_at.strftime('%d.%m.%Y %H:%M')})"
