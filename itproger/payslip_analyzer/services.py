
import re
import os
import json
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Tuple, Optional
from datetime import date
from django.db.models import Sum, Avg
from django.core.files.storage import default_storage
# Опциональные импорты для OCR и PDF
try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("⚠️ pytesseract или Pillow не установлены. OCR недоступен.")
try:
    import PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print("⚠️ PyPDF2 не установлен. Парсинг PDF недоступен.")
from .models import PaymentCode, PaySlip, PaySlipItem
class CodeDictionaryParser:
    """Парсер справочника кодов оплат"""

    # Паттерны для распознавания формата "код - описание"
    PATTERNS = [
        r'^(\d+)\s*[-–—:]\s*(.+)$',     # "123 - Описание" или "123: Описание"
        r'^(\d+)\s{2,}(.+)$',            # "123   Описание" (несколько пробелов)
        r'^(\d+)\t+(.+)$',               # "123\tОписание" (табуляция)
        r'^код\s*(\d+)\s*[-–—:]\s*(.+)$',  # "код 123 - Описание"
    ]

    def parse_text(self, text: str) -> List[Dict]:
        """Парсинг текста справочника"""
        codes = []
        lines = text.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):  # Пропускаем пустые и комментарии
                continue

            for pattern in self.PATTERNS:
                match = re.match(pattern, line, re.IGNORECASE)
                if match:
                    code = match.group(1).strip()
                    description = match.group(2).strip()

                    # Убираем лишние символы из описания
                    description = re.sub(r'\s+', ' ', description)

                    if code and description:
                        # Определяем тип кода (начисление/удержание)
                        # Коды >= 700 обычно удержания
                        try:
                            code_type = 'deduction' if int(code) >= 700 else 'income'
                        except ValueError:
                            code_type = 'income'

                        codes.append({
                            'code': code,
                            'description': description,
                            'code_type': code_type
                        })
                    break

        return codes

    def parse_file(self, file_path: str) -> Tuple[List[Dict], str]:
        """
        Парсинг файла справочника (TXT или PDF)
        Возвращает: (список кодов, сообщение об ошибке или '')
        """
        ext = os.path.splitext(file_path)[1].lower()

        try:
            if ext == '.txt':
                # Пробуем разные кодировки
                for encoding in ['utf-8', 'cp1251', 'latin-1']:
                    try:
                        with open(file_path, 'r', encoding=encoding) as f:
                            text = f.read()
                        return self.parse_text(text), ''
                    except UnicodeDecodeError:
                        continue
                return [], 'Не удалось определить кодировку файла'

            elif ext == '.pdf':
                if not PDF_AVAILABLE:
                    return [], 'PyPDF2 не установлен. Установите: pip install PyPDF2'

                text = ''
                with open(file_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + '\n'

                if not text.strip():
                    return [], 'Не удалось извлечь текст из PDF'

                return self.parse_text(text), ''

            else:
                return [], f'Неподдерживаемый формат файла: {ext}'

        except Exception as e:
            return [], f'Ошибка чтения файла: {str(e)}'

    def save_codes(self, codes: List[Dict]) -> Tuple[int, int]:
        """
        Сохранение кодов в БД
        Возвращает: (найдено, добавлено)
        """
        added = 0
        for code_data in codes:
            obj, created = PaymentCode.objects.update_or_create(
                code=code_data['code'],
                defaults={
                    'description': code_data['description'],
                    'code_type': code_data['code_type']
                }
            )
            if created:
                added += 1
        return len(codes), added
class ReceiptOCR:
    """OCR для распознавания квитанций"""

    def __init__(self):
        self.available = OCR_AVAILABLE
        if self.available:
            # Настройка Tesseract для русского языка
            self.tesseract_config = '--oem 3 --psm 6 -l rus+eng'

    def extract_text(self, image_path: str) -> Tuple[str, str]:
        """
        Извлечение текста из изображения
        Возвращает: (текст, ошибка)
        """
        if not self.available:
            return '', 'pytesseract не установлен. Установите: pip install pytesseract Pillow'

        try:
            image = Image.open(image_path)

            # Предобработка изображения для лучшего распознавания
            # Конвертируем в градации серого
            if image.mode != 'L':
                image = image.convert('L')

            text = pytesseract.image_to_string(image, config=self.tesseract_config)
            return text, ''

        except Exception as e:
            return '', f'Ошибка OCR: {str(e)}'

    def parse_receipt_text(self, text: str) -> Tuple[List[Dict], List[Dict]]:
        """
        Парсинг распознанного текста квитанции
        Возвращает: (начисления, удержания)
        """
        income_items = []
        deduction_items = []

        # Паттерны для распознавания строк
        # Формат: "месяц код рв сумма" или "месяц код сумма"
        patterns = [
            # Мес код РВ сумма (начисление)
            r'(\d{1,2})\s+(\d+)\s+(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)',
            # Мес код сумма (удержание или без РВ)
            r'(\d{1,2})\s+(\d+)\s+(\d+(?:[.,]\d+)?)',
        ]

        lines = text.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Пробуем паттерн с РВ
            match = re.search(patterns[0], line)
            if match:
                month = int(match.group(1))
                code = match.group(2)
                rv = self._parse_number(match.group(3))
                amount = self._parse_number(match.group(4))

                if 1 <= month <= 12 and amount > 0:
                    item = {
                        'month': month,
                        'code': code,
                        'rv': float(rv) if rv else None,
                        'amount': float(amount)
                    }

                    # Определяем тип по коду
                    if int(code) >= 700:
                        deduction_items.append(item)
                    else:
                        income_items.append(item)
                continue

            # Пробуем паттерн без РВ
            match = re.search(patterns[1], line)
            if match:
                month = int(match.group(1))
                code = match.group(2)
                amount = self._parse_number(match.group(3))

                if 1 <= month <= 12 and amount > 0:
                    item = {
                        'month': month,
                        'code': code,
                        'rv': None,
                        'amount': float(amount)
                    }

                    if int(code) >= 700:
                        deduction_items.append(item)
                    else:
                        income_items.append(item)

        return income_items, deduction_items

    def _parse_number(self, value: str) -> Decimal:
        """Преобразование строки в число"""
        try:
            value = value.replace(',', '.').replace(' ', '').strip()
            return Decimal(value)
        except (InvalidOperation, ValueError):
            return Decimal('0')
class PaySlipService:
    """Основной сервис для работы с платежными ведомостями"""

    def __init__(self):
        self.ocr = ReceiptOCR()
        self.code_parser = CodeDictionaryParser()

    def create_payslip(
        self,
        period: date,
        half: int,
        income_items: List[Dict],
        deduction_items: List[Dict],
        image=None,
        notes: str = ''
    ) -> PaySlip:
        """Создание платежной ведомости с данными"""

        # Создаем или обновляем ведомость
        payslip, created = PaySlip.objects.update_or_create(
            period=period,
            half=half,
            defaults={
                'receipt_image': image,
                'notes': notes
            } if image else {'notes': notes}
        )

        # Удаляем старые строки если обновляем
        if not created:
            payslip.items.all().delete()

        # Добавляем начисления
        for item in income_items:
            code_ref = PaymentCode.objects.filter(code=item['code']).first()
            PaySlipItem.objects.create(
                payslip=payslip,
                item_type='income',
                month=item['month'],
                code=item['code'],
                code_ref=code_ref,
                rv=item.get('rv'),
                amount=Decimal(str(item['amount']))
            )

        # Добавляем удержания
        for item in deduction_items:
            code_ref = PaymentCode.objects.filter(code=item['code']).first()
            PaySlipItem.objects.create(
                payslip=payslip,
                item_type='deduction',
                month=item['month'],
                code=item['code'],
                code_ref=code_ref,
                rv=item.get('rv'),
                amount=Decimal(str(item['amount']))
            )

        # Пересчитываем итоги
        payslip.calculate_totals()

        return payslip

    def process_receipt_image(self, image_path: str) -> Tuple[List[Dict], List[Dict], str]:
        """
        Обработка изображения квитанции
        Возвращает: (начисления, удержания, ошибка)
        """
        text, error = self.ocr.extract_text(image_path)
        if error:
            return [], [], error

        income_items, deduction_items = self.ocr.parse_receipt_text(text)
        return income_items, deduction_items, ''

    def get_statistics(self, months: int = 6) -> Dict:
        """Получение статистики за последние N месяцев"""
        from dateutil.relativedelta import relativedelta

        start_date = date.today() - relativedelta(months=months)

        payslips = PaySlip.objects.filter(
            period__gte=start_date
        ).order_by('period', 'half')

        stats = {
            'periods': [],
            'income': [],
            'deductions': [],
            'net_pay': [],
            'total_income': Decimal('0'),
            'total_deductions': Decimal('0'),
            'total_net_pay': Decimal('0'),
            'count': payslips.count(),
            'avg_income': Decimal('0'),
            'avg_deductions': Decimal('0'),
            'avg_net_pay': Decimal('0'),
        }

        for ps in payslips:
            half_str = '(1)' if ps.half == 1 else '(2)'
            period_label = f"{ps.period.strftime('%b')} {half_str}"

            stats['periods'].append(period_label)
            stats['income'].append(float(ps.total_income))
            stats['deductions'].append(float(ps.total_deduction))
            stats['net_pay'].append(float(ps.net_pay))

            stats['total_income'] += ps.total_income
            stats['total_deductions'] += ps.total_deduction
            stats['total_net_pay'] += ps.net_pay

        # Средние значения
        if stats['count'] > 0:
            stats['avg_income'] = stats['total_income'] / stats['count']
            stats['avg_deductions'] = stats['total_deductions'] / stats['count']
            stats['avg_net_pay'] = stats['total_net_pay'] / stats['count']

        return stats

    def get_category_breakdown(self, payslip: PaySlip) -> Dict:
        """Разбивка по категориям для круговой диаграммы"""
        categories = {}

        for item in payslip.items.filter(item_type='income').select_related('code_ref'):
            desc = item.description
            if desc not in categories:
                categories[desc] = Decimal('0')
            categories[desc] += item.amount

        # Сортируем по сумме
        sorted_categories = dict(
            sorted(categories.items(), key=lambda x: x[1], reverse=True)
        )

        return {
            'labels': list(sorted_categories.keys()),
            'values': [float(v) for v in sorted_categories.values()]
        }

    def compare_periods(self, payslip1: PaySlip, payslip2: PaySlip) -> Dict:
        """Сравнение двух периодов"""
        diff_income = payslip2.total_income - payslip1.total_income
        diff_deduction = payslip2.total_deduction - payslip1.total_deduction
        diff_net = payslip2.net_pay - payslip1.net_pay

        # Процентные изменения
        pct_income = (diff_income / payslip1.total_income * 100) if payslip1.total_income else 0
        pct_deduction = (diff_deduction / payslip1.total_deduction * 100) if payslip1.total_deduction else 0
        pct_net = (diff_net / payslip1.net_pay * 100) if payslip1.net_pay else 0

        return {
            'period1': {
                'id': payslip1.pk,
                'label': payslip1.get_period_display(),
                'income': float(payslip1.total_income),
                'deduction': float(payslip1.total_deduction),
                'net_pay': float(payslip1.net_pay)
            },
            'period2': {
                'id': payslip2.pk,
                'label': payslip2.get_period_display(),
                'income': float(payslip2.total_income),
                'deduction': float(payslip2.total_deduction),
                'net_pay': float(payslip2.net_pay)
            },
            'diff': {
                'income': float(diff_income),
                'deduction': float(diff_deduction),
                'net_pay': float(diff_net)
            },
            'percent': {
                'income': float(pct_income),
                'deduction': float(pct_deduction),
                'net_pay': float(pct_net)
            }
        }

    def get_trends(self, code: str, months: int = 12) -> Dict:
        """Получить тренды по конкретному коду оплаты"""
        from dateutil.relativedelta import relativedelta

        start_date = date.today() - relativedelta(months=months)

        items = PaySlipItem.objects.filter(
            code=code,
            payslip__period__gte=start_date
        ).select_related('payslip_analyzer').order_by('payslip__period', 'payslip__half')

        data = {
            'code': code,
            'periods': [],
            'amounts': [],
            'total': Decimal('0'),
            'avg': Decimal('0'),
            'min': None,
            'max': None
        }

        for item in items:
            half_str = '(1)' if item.payslip.half == 1 else '(2)'
            period_label = f"{item.payslip.period.strftime('%b %Y')} {half_str}"

            data['periods'].append(period_label)
            data['amounts'].append(float(item.amount))
            data['total'] += item.amount

            if data['min'] is None or item.amount < data['min']:
                data['min'] = item.amount
            if data['max'] is None or item.amount > data['max']:
                data['max'] = item.amount

        if items.count() > 0:
            data['avg'] = data['total'] / items.count()

        data['min'] = float(data['min']) if data['min'] else 0
        data['max'] = float(data['max']) if data['max'] else 0
        data['total'] = float(data['total'])
        data['avg'] = float(data['avg'])

        return data

    def load_default_codes(self) -> int:
        """Загрузить стандартные коды в справочник"""
        codes = PaymentCode.get_default_codes()
        created = 0
        for code_data in codes:
            obj, is_created = PaymentCode.objects.get_or_create(
                code=code_data['code'],
                defaults=code_data
            )
            if is_created:
                created += 1
        return created
