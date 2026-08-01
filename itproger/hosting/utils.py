import subprocess
import re


def get_device_info_via_snmp(ip, community_strings=['public', 'private']):
    """Получение информации об устройстве через SNMP"""
    for community in community_strings:
        try:
            info = {}

            # Системное описание
            cmd = ['snmpget', '-v2c', '-c', community, ip, '1.3.6.1.2.1.1.1.0']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                info['description'] = extract_snmp_value(result.stdout)

            # Имя системы
            cmd = ['snmpget', '-v2c', '-c', community, ip, '1.3.6.1.2.1.1.5.0']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                info['sysname'] = extract_snmp_value(result.stdout)

            return info

        except Exception as e:
            continue

    return {}


def extract_snmp_value(snmp_output):
    """Извлечение значения из вывода SNMP"""
    match = re.search(r'STRING:\s*"([^"]*)"', snmp_output)
    if match:
        return match.group(1)
    return ""