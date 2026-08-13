from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models


class NetworkSegment(models.Model):
    class DefaultAction(models.TextChoices):
        ALLOW = 'allow', 'Allow'
        DENY = 'deny', 'Deny'

    name = models.CharField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    color = models.CharField(
        max_length=7,
        default='#7a5cff',
        validators=[RegexValidator(r'^#[0-9A-Fa-f]{6}$', 'Enter a valid HEX color.')],
    )
    default_action = models.CharField(
        max_length=5,
        choices=DefaultAction.choices,
        default=DefaultAction.DENY,
    )

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class SegmentPolicy(models.Model):
    class Action(models.TextChoices):
        ALLOW = 'allow', 'Allow'
        DENY = 'deny', 'Deny'

    class Protocol(models.TextChoices):
        ANY = 'any', 'Any'
        TCP = 'tcp', 'TCP'
        UDP = 'udp', 'UDP'
        ICMP = 'icmp', 'ICMP'

    name = models.CharField(max_length=120)
    source = models.ForeignKey(
        NetworkSegment,
        on_delete=models.CASCADE,
        related_name='outbound_policies',
    )
    destination = models.ForeignKey(
        NetworkSegment,
        on_delete=models.CASCADE,
        related_name='inbound_policies',
    )
    action = models.CharField(max_length=5, choices=Action.choices)
    protocol = models.CharField(
        max_length=4,
        choices=Protocol.choices,
        default=Protocol.ANY,
    )
    port = models.PositiveIntegerField(null=True, blank=True)
    enabled = models.BooleanField(default=True)
    priority = models.PositiveIntegerField(default=100)

    class Meta:
        ordering = ('priority', 'pk')
        verbose_name_plural = 'segment policies'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(port__isnull=True)
                | models.Q(port__gte=1, port__lte=65535),
                name='hosting_segment_policy_valid_port',
            ),
            models.CheckConstraint(
                condition=models.Q(protocol__in=('tcp', 'udp'))
                | models.Q(port__isnull=True),
                name='hosting_segment_policy_port_protocol',
            ),
            models.UniqueConstraint(
                fields=('source', 'destination', 'priority'),
                name='hosting_segment_policy_unique_priority',
            ),
        ]

    def clean(self):
        super().clean()
        if self.port is not None and self.protocol not in (
            self.Protocol.TCP,
            self.Protocol.UDP,
        ):
            raise ValidationError(
                {'port': 'A port can only be specified for TCP or UDP policies.'}
            )

    def __str__(self):
        return f'{self.source} → {self.destination}: {self.action}'


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


class Host(models.Model):
    """Store host information."""
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
    segment = models.ForeignKey(
        NetworkSegment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='hosts',
    )

    DEVICE_CHOICES = (
        ('servers', 'Сервер'),
        ('switches', 'Коммутатор'),
        ('routers', 'Маршрутизатор'),
        ('computers', 'Компьютер'),
        ('network-printers', 'Принтер'),
        ('UPS', 'ИБП'),
    )
    device_type = models.CharField(max_length=50, choices=DEVICE_CHOICES, default=False, blank=True, null=True)

    latitude = models.FloatField(default=0.0)
    longitude = models.FloatField(default=0.0)

    def __str__(self):
        return self.hostname or self.ipaddr

class NodePosition(models.Model):
    ipaddr = models.CharField(max_length=255, unique=True)
    x = models.FloatField()
    y = models.FloatField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.ipaddr} ({self.x:.1f}, {self.y:.1f})'

class Service(models.Model):
    """Store service status information for a specific host."""
    host = models.ForeignKey(Host, related_name='services', on_delete=models.CASCADE)
    description = models.CharField(max_length=255)
    status = models.CharField(max_length=255)
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
    """Store interface status information for a specific host."""
    host = models.ForeignKey(Host, related_name='ports', on_delete=models.CASCADE)
    ifdescr = models.CharField(max_length=255)
    status = models.CharField(max_length=255)
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
    color = models.CharField(max_length=7)
    weight = models.IntegerField()
    line_type = models.CharField(max_length=10, choices=LINE_TYPES, default='solid')

    def __str__(self):
        return f"{self.line_id} - {self.color} - {self.weight} - {self.get_line_type_display()}"


class Route(models.Model):
    parent = models.ForeignKey(Host, on_delete=models.CASCADE, related_name='parent_routes')
    child = models.ForeignKey(Host, on_delete=models.CASCADE, related_name='child_routes')
    waypoints = models.JSONField(default=list)

    def __str__(self):
        return f"Маршрут от {self.parent.ipaddr} до {self.child.ipaddr}"
