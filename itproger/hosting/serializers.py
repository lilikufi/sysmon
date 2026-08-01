from rest_framework import serializers

from .models import Hosting


class HostingSerializer(serializers.ModelSerializer):
    class Meta:
        module = Hosting
        fields = ('title', 'cat_id')

from rest_framework import serializers
from .models import Host

class HostSerializer(serializers.ModelSerializer):
    class Meta:
        model = Host
        fields = ['id', 'ipaddr', 'latitude', 'longitude']