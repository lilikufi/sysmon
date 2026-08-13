import os

from dotenv import load_dotenv
from fabric.connection import Connection


load_dotenv()

server_host = os.getenv('NAG_SERVER')
username = os.getenv('NAG_USERNAME')
password = os.getenv('NAG_PASSWORD')
snmp_communities = tuple(
    value.strip()
    for value in os.getenv('SYSMON_SNMP_COMMUNITIES', 'public').split(',')
    if value.strip()
)
lenovo_snmp_community = os.getenv('SYSMON_LENOVO_SNMP_COMMUNITY', 'private')


class LazyMonitoringConnection:
    """Create the external SSH connection only when an integration action needs it."""

    def __init__(self):
        self._connection = None

    def _get_connection(self):
        if not server_host:
            raise RuntimeError('NAG_SERVER is not configured')
        if self._connection is None:
            self._connection = Connection(
                server_host,
                port=22,
                user=username,
                connect_kwargs={'password': password},
            )
        return self._connection

    def run(self, *args, **kwargs):
        return self._get_connection().run(*args, **kwargs)

    def sftp(self):
        return self._get_connection().sftp()


connector = LazyMonitoringConnection()
