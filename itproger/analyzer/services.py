"""
Сервисы для обработки файлов и OCR
"""

import re
import os
from decimal import Decimal
from typing import List, Dict, Tuple, Optional

# Для OCR
try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# Для PDF
try:
    import PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

from .models import PaymentCode, PaySlip, PaySlipItem


class CodeDictionaryParser:
    """Парсер справочника кодов"""
    
    # Паттерны для распознавания формата "код - описание"
    PATTERNS = [
        r'^(\d+)\s*[-–—]\s*(.+)$',  # "123 - Описание"
        r'^(\d+)\s+(.+)$',           # "123 Описание"
        r'^(\d+)\t(.+)$',            # "123\tОписание"
    ]
    
    def parse_text(self, text: str) -> List[Dict]:
        """Парсинг текста справочника"""
        codes = []
        lines = text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            for pattern in self.PATTERNS:
                match = re.match(pattern, line)
                if match:
                    code = match.group(1)
                    description = match.group(2).strip()
                    
                    # Определяем тип кода (начисление/удержание)
                    code_type = 'deduction' if int(code) >= 700 else 'income'
                    
                    codes.append({
                        'code': code,
                        'description': description,
                        'code_type': code_type
                    })
                    break
        
        return codes
    
    def parse_file(self, file_path: str) -> List[Dict]:
        """Парсинг файла справочника (TXT или PDF)"""
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext == '.txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                return self.parse_text(f.read())
        
        elif ext == '.pdf' and PDF_AVAILABLE:
            text = ''
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() + '\n'
            return self.parse_text(text)
        
        return []
    
    def save_codes(self, codes: List[Dict]) -> int:
        """Сохранение кодов в БД"""
        count = 0
        for code_data in codes:
            obj, created = PaymentCode.objects.update_or_create(
                code=code_data['code'],
                defaults={
                    'description': code_data['description'],
                    'code_type': code_data['code_type']
                }
            )
            if created:
                count += 1
        return count


class ReceiptOCR:
    """OCR для распознавания квитанций"""
    
    # Паттерны для распознавания данных квитанции
    INCOME_PATTERN = r'(\d{1,2})\s+(\d+)\s+(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)'
    DEDUCTION_PATTERN = r'(\d{1,2})\s+(\d+)\s+(\d+(?:[.,]\d+)?)'
    
    def __init__(self):
        if OCR_AVAILABLE:
            # Настройка Tesseract для русского языка
            self.tesseract_config = '--oem 3 --psm 6 -l rus+eng'
    
    def extract_text(self, image_path: str) -> str:
        """Извлечение текста из изображения"""
        if not OCR_AVAILABLE:
            return ""
        
        try:
            image = Image.open(image_path)
            text = pytesseract.image_to_string(image, config=self.tesseract_config)
            return text
        except Exception as e:
            print(f"OCR Error: {e}")
            return ""
    
    def parse_receipt(self, text: str) -> Tuple[List[Dict], List[Dict]]:
        """Парсинг распознанного текста квитанции"""
        income_items = []
        deduction_items = []
        
        lines = text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Пытаемся распознать начисление
            income_match = re.search(self.INCOME_PATTERN, line)
            if income_match:
                month = int(income_match.group(1))
                code = income_match.group(2)
                rv = self._parse_number(income_match.group(3))
                amount = self._parse_number(income_match.group(4))
                
                if amount > 0:
                    income_items.append({
                        'month': month,
                        'code': code,
                        'rv': rv,
                        'amount': amount
                    })
                continue
            
            # Пытаемся распознать удержание
            deduction_match = re.search(self.DEDUCTION_PATTERN, line)
            if deduction_match:
                month = int(deduction_match.group(1))
                code = deduction_match.group(2)
                amount = self._parse_number(deduction_match.group(3))
                
                if amount > 0 and int(code) >= 700:
                    deduction_items.append({
                        'month': month,
                        'code': code,
                        'rv': None,
                        'amount': amount
                    })
        
        return income_items, deduction_items
    
    def _parse_number(self, value: str) -> Decimal:
        """Преобразование строки в число"""
        try:
            value = value.replace(',', '.').replace(' ', '')
            return Decimal(value)
        except:
            return Decimal('0')


class PaySlipService:
    """Сервис для работы с платежными ведомостями"""
    
    def __init__(self):
        self.ocr = ReceiptOCR()
        self.code_parser = CodeDictionaryParser()
    
    def create_payslip(self, period, half: int, income_items: List[Dict], 
                       deduction_items: List[Dict], image=None) -> PaySlip:
        """Создание платежной ведомости с данными"""
        
        # Создаем или обновляем ведомость
        payslip, created = PaySlip.objects.update_or_create(
            period=period,
            half=half,
            defaults={'receipt_image': image} if image else {}
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
                amount=item['amount']
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
                amount=item['amount']
            )
        
        # Пересчитываем итоги
        payslip.calculate_totals()
        
        return payslip
    
    def process_receipt_image(self, image_path: str) -> Tuple[List[Dict], List[Dict]]:
        """Обработка изображения квитанции"""
        text = self.ocr.extract_text(image_path)
        return self.ocr.parse_receipt(text)
    
    def get_statistics(self, months: int = 6) -> Dict:
        """Получение статистики за последние N месяцев"""
        from django.db.models import Sum
        from datetime import date
        from dateutil.relativedelta import relativedelta
        
        start_date = date.today() - relativedelta(months=months)
        
        payslips = PaySlip.objects.filter(period__gte=start_date).order_by('period', 'half')
        
        stats = {
            'periods': [],
            'income': [],
            'deductions': [],
            'net_pay': [],
            'total_income': Decimal('0'),
            'total_deductions': Decimal('0'),
            'total_net_pay': Decimal('0'),
            'count': payslips.count()
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
        
        return stats
    
    def get_category_breakdown(self, payslip: PaySlip) -> Dict:
        """Разбивка по категориям для круговой диаграммы"""
        categories = {}
        
        for item in payslip.items.filter(item_type='income'):
            desc = item.description
            if desc not in categories:
                categories[desc] = Decimal('0')
            categories[desc] += item.amount
        
        return {
            'labels': list(categories.keys()),
            'values': [float(v) for v in categories.values()]
        }
    
    def compare_periods(self, payslip1: PaySlip, payslip2: PaySlip) -> Dict:
        """Сравнение двух периодов"""
        diff_income = payslip2.total_income - payslip1.total_income
        diff_deduction = payslip2.total_deduction - payslip1.total_deduction
        diff_net = payslip2.net_pay - payslip1.net_pay
        
        pct_income = (diff_income / payslip1.total_income * 100) if payslip1.total_income else 0
        pct_deduction = (diff_deduction / payslip1.total_deduction * 100) if payslip1.total_deduction else 0
        pct_net = (diff_net / payslip1.net_pay * 100) if payslip1.net_pay else 0
        
        return {
            'period1': {
                'label': str(payslip1),
                'income': float(payslip1.total_income),
                'deduction': float(payslip1.total_deduction),
                'net_pay': float(payslip1.net_pay)
            },
            'period2': {
                'label': str(payslip2),
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
