from django.db import models
from django.urls import reverse


class Hosting(models.Model):
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True)
    time_create = models.DateTimeField(auto_now_add=True)
    time_update = models.DateTimeField(auto_now=True)
    is_published = models.BooleanField(default=True)
    cat = models.ForeignKey('Category', on_delete=models.PROTECT, null=True)

    def __str__(self):
        return self.title


class Category(models.Model):
    name = models.CharField(max_length=100, db_index=True)

    def __str__(self):
        return self.name
    # class Meta:
    #     verbose_name = 'Категория'
    #     verbose_name_plural = 'Категории'
    #     ordering = ['id']


class Host(models.Model):
    """store host information"""
    ipaddr = models.GenericIPAddressField(max_length=15)
    hostname = models.CharField(max_length=50, null=True, blank=True)
    vendor = models.CharField(max_length=30, null=True, blank=True)
    sn = models.CharField(max_length=30, null=True, blank=True)
    product = models.CharField(max_length=30, null=True, blank=True)
    cpu_model = models.CharField(max_length=50, null=True, blank=True)
    cpu_num = models.CharField(max_length=2, null=True, blank=True)
    cpu_vendor = models.CharField(max_length=30, null=True, blank=True)
    memory_part_number = models.CharField(max_length=30, null=True, blank=True)
    memory_manufacturer = models.CharField(max_length=30, null=True, blank=True)
    memory_size = models.CharField(max_length=20, null=True, blank=True)
    device_model = models.CharField(max_length=30, null=True, blank=True)
    device_version = models.CharField(max_length=30, null=True, blank=True)
    device_sn = models.CharField(max_length=30, null=True, blank=True)
    device_size = models.CharField(max_length=30, null=True, blank=True)
    osver = models.CharField(max_length=30, null=True, blank=True)
    os_release = models.CharField(max_length=30, null=True, blank=True)
    cat = models.ForeignKey('Category', on_delete=models.PROTECT, null=True, verbose_name='Категория', blank=True)
    time_create = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    time_update = models.DateTimeField(auto_now=True, null=True)
    online = models.BooleanField(default=False)
    SNMP = models.BooleanField(default=False)
    com_str = models.CharField(max_length=30, null=True, blank=True)
    place = models.CharField(max_length=100, null=True, blank=True)

    cpu_1_min = models.BooleanField(default=False)
    cpu_5_min = models.BooleanField(default=False)
    uptime = models.BooleanField(default=False)
    mem_free = models.BooleanField(default=False)
    mem_used = models.BooleanField(default=False)
    mem_util = models.BooleanField(default=False)

    bat_temp = models.BooleanField(default=False)
    bat_time_work = models.BooleanField(default=False)
    bat_vol = models.BooleanField(default=False)
    run_reman = models.BooleanField(default=False)
    stat_charge = models.BooleanField(default=False)

    checkbox_field = models.BooleanField(default=False)
    nagios_flag = models.BooleanField(default=False)
    hide_flag = models.BooleanField(default=False)
    parents = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')

    DEVICE_CHOICES = (
        ('servers', 'Сервер'),
        ('switches', 'Коммутатор'),
        ('routers', 'Маршрутизатор'),  # ДОБАВЛЕНО
        ('computers', 'Компьютер'),  # ДОБАВЛЕНО
        ('network-printers', 'Принтер'),
        ('UPS', 'ИБП'),
    )
    device_type = models.CharField(max_length=50, choices=DEVICE_CHOICES, default=False, blank=True, null=True)

    latitude = models.FloatField(default=0.0)
    longitude = models.FloatField(default=0.0)

    def __str__(self):
        return self.hostname or self.ipaddr

    def get_absolute_url(self):
        return reverse("", kwargs={'pk': self.pk})

    # def get_absolute_url(self):
    #     return reverse('host-update', kwargs={'pk': self.pk})
from django.db import models

class NodePosition(models.Model):
    ipaddr = models.CharField(max_length=255, unique=True)
    x = models.FloatField()
    y = models.FloatField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.ipaddr} ({self.x:.1f}, {self.y:.1f})'

class Service(models.Model):
    """Store service status information for a specific host"""
    host = models.ForeignKey(Host, related_name='services', on_delete=models.CASCADE)
    description = models.CharField(max_length=255)  # Например, 'CPU Usage', 'Memory Usage', и т.д.
    status = models.CharField(max_length=255)  # Например, CRITICAL, OK и т.д.
    last_checked = models.DateTimeField(auto_now=True)
    status_information = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        unique_together = (('host', 'description'),)

    def __str__(self):
        return f"{self.description} on {self.host.hostname or self.host.ipaddr}"


class HostGroup(models.Model):
    name = models.CharField(max_length=30)
    members = models.ManyToManyField(Host)


class Ports(models.Model):
    """Store service status information for a specific host"""
    host = models.ForeignKey(Host, related_name='ports', on_delete=models.CASCADE)
    ifdescr = models.CharField(max_length=255)  # Например, 'CPU Usage', 'Memory Usage', и т.д.
    status = models.CharField(max_length=255)  # Например, CRITICAL, OK и т.д.
    last_checked = models.DateTimeField(auto_now=True)
    ifinoct = models.CharField(max_length=255, blank=True, null=True)
    ifoutoct = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        unique_together = (('host', 'ifdescr'),)

    def __str__(self):
        return f"{self.ifdescr} on {self.host.hostname or self.host.ipaddr}"




class LineSettings(models.Model):
    LINE_TYPES = [
        ('solid', 'Сплошная'),
        ('dashed', 'Пунктирная'),
        ('dotted', 'Точечная'),
        ('dash-dot', 'Штрих-пунктирная'),
    ]

    line_id = models.CharField(max_length=255, unique=True)
    color = models.CharField(max_length=7)  # HEX цвет, например, #FF0000
    weight = models.IntegerField()
    line_type = models.CharField(max_length=10, choices=LINE_TYPES, default='solid')  # Новое поле

    def __str__(self):
        return f"{self.line_id} - {self.color} - {self.weight} - {self.get_line_type_display()}"


class Route(models.Model):
    parent = models.ForeignKey(Host, on_delete=models.CASCADE, related_name='parent_routes')
    child = models.ForeignKey(Host, on_delete=models.CASCADE, related_name='child_routes')
    waypoints = models.JSONField(default=list)  # Промежуточные точки маршрута

    def __str__(self):
        return f"Маршрут от {self.parent.ipaddr} до {self.child.ipaddr}"


# Добавьте этот метод в класс Host
def get_neighbors(self):
    """Получить всех соседей устройства"""
    neighbors = {
        'parents': [],
        'children': []
    }

    # Устройства, которые подключены к этому устройству
    children_routes = Route.objects.filter(parent=self)
    for route in children_routes:
        neighbors['children'].append(route.child)

    # Устройства, к которым подключено это устройство
    parent_routes = Route.objects.filter(child=self)
    for route in parent_routes:
        neighbors['parents'].append(route.parent)

    return neighbors


def get_topology_tree(self):
    """Получить древовидную структуру топологии начиная с этого устройства"""

    def build_tree(host, visited=None):
        if visited is None:
            visited = set()

        if host.ipaddr in visited:
            return None

        visited.add(host.ipaddr)

        tree = {
            'host': host,
            'children': []
        }

        # Получаем непосредственных детей
        child_routes = Route.objects.filter(parent=host)
        for route in child_routes:
            child_tree = build_tree(route.child, visited)
            if child_tree:
                tree['children'].append(child_tree)

        return tree

    return build_tree(self)
