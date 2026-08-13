import logging
import os
import platform
import re
import smtplib
import subprocess
import time
from email.mime.text import MIMEText
from pathlib import Path

from django.http import HttpResponse
from fabric.connection import Connection

from hosting.models import Host, Service
from dotenv import load_dotenv


load_dotenv()
logger = logging.getLogger(__name__)
port = 22
host = os.getenv('NAG_SERVER')
usernamy = os.getenv('NAG_USERNAME')
passy = os.getenv('NAG_PASSWORD')
sys_mail_password = os.getenv('SYSMON_MAIL_PASSWORD')
sys_mail_from = os.getenv('SYSMON_MAIL_FROM', '')
sys_mail_to = os.getenv('SYSMON_MAIL_TO', '')
sys_mail_server = os.getenv('SYSMON_MAIL_SERVER', 'localhost')
status_dir = Path(os.getenv('NAGIOS_STATUS_DIR', 'nagios_stat'))
connector = Connection(host, port=22, user=usernamy, connect_kwargs={'password': passy})


def send_error_email(message, subject):
    msg = MIMEText(message)
    msg['Subject'] = subject
    msg['From'] = sys_mail_from
    msg['To'] = sys_mail_to

    with smtplib.SMTP(sys_mail_server, 465) as server:
        server.login(sys_mail_from, sys_mail_password)
        try:
            server.send_message(msg)
            logger.info('Notification email sent')
        except Exception as exc:
            logger.exception('Unable to send notification email')
            return HttpResponse(f'Ошибка отправки письма: {exc}')

notify = False


def check_nagios_stat():
    global notify
    monitored_host, created = Host.objects.get_or_create(ipaddr=host)
    try:
        reload_cm = 'sudo systemctl restart nagios'
        reload = connector.run(reload_cm)

        if not reload.failed:
            monitored_host.online = True
            monitored_host.save()
            notify = False
        elif 'with error' in reload:
            logger.error('Nagios is unavailable')
            monitored_host.online = False
            monitored_host.save()
            if not notify:
                mes = "Nagios down"
                send_error_email(mes,"nagios")
                notify = True

        else:
            logger.error('Nagios is unavailable')
            monitored_host.online = False
            monitored_host.save()
            if not notify:
                mes = "Nagios down"
                send_error_email(mes,"nagios")
                notify = True

    except Exception as exc:
        logger.exception('Nagios status check failed: %s', exc)
        monitored_host.online = False
        monitored_host.save(update_fields=['online'])
        if not notify:
            mes = "Nagios down"
            send_error_email(mes,"nagios")
            notify = True
            time.sleep(60)

    finally:
        connector.close()

last_notified_status = {}


def check_hosts_status_back():
    logger.info('Starting host status check')
    hosts = Host.objects.all()
    file_path = status_dir / 'status.dat'


    for host in hosts:
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        command = ['ping', param, '1', '-W', '2', str(host.ipaddr)]

        try:
            result = subprocess.run(command, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=3)
            host.online = (result.returncode == 0)
        except subprocess.TimeoutExpired:
            host.online = False
        host.save()

        try:
            with open(file_path, 'r') as file:
                content = file.read()

                host_blocks = re.findall(r'hoststatus\s*{([^}]+)}', content)
                for block in host_blocks:
                    lines = block.strip().splitlines()
                    host_info = {}
                    for line in lines:
                        if '=' in line:
                            key, value = line.split('=', 1)
                            host_info[key.strip()] = value.strip()

                    host_name = host_info.get('host_name')
                    if host_name:
                        ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
                        try:
                            if re.match(ip_pattern, host_name):
                                host, created = Host.objects.get_or_create(ipaddr=host_name)
                            else:
                                host, created = Host.objects.get_or_create(hostname=host_name)
                            host.nagios_flag = True
                            ping_output = host_info.get('plugin_output')
                            ping_status = 'UNKNOWN'
                            if 'PING OK' in ping_output:
                                ping_status = 'ОК'

                            elif 'WARNING' in ping_output in ping_output:
                                ping_status = 'WARNING'
                            elif 'CRITICAL' in ping_output:
                                ping_status = 'CRITICAL'

                            if host_name not in last_notified_status or last_notified_status[host_name] != ping_status:
                                host.online = (ping_status == "ОК")
                                host.save()

                                if ping_status == 'CRITICAL':
                                    message = f"Host {host_name} is in CRITICAL state."
                                    logger.info('Host alert: %s', message)

                                    last_notified_status[host_name] = ping_status

                        except Host.DoesNotExist:
                            logging.error(f"Host with {host_name} not found.")
                            continue
                        except Exception:
                            continue

                service_blocks = re.findall(r'servicestatus\s*{([^}]+)}', content)
                for block in service_blocks:
                    lines = block.strip().splitlines()
                    service_info = {}
                    for line in lines:

                        line = line.strip()
                        if '=' in line:
                            parts = line.split('=', 1)
                            if len(parts) == 2:
                                key = parts[0].strip()
                                value = parts[1].strip()

                                if key in ["host_name", "service_description", "plugin_output", "last_update"]:
                                    service_info[key] = value

                                if "host_name" in service_info and "service_description" in service_info:
                                    host_name_serv = service_info["host_name"]
                                    ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
                                    try:
                                        if re.match(ip_pattern, host_name_serv):
                                            host_for_service, created = Host.objects.get_or_create(ipaddr=host_name_serv)
                                        else:
                                            host_for_service = Host.objects.get(hostname=host_name_serv)

                                        service_description = service_info["service_description"]
                                        service_status = 'Pending'

                                        if "plugin_output" in service_info:
                                            output = service_info["plugin_output"]
                                            if 'OK' in output:
                                                service_status = 'ОК'
                                            elif 'CRITICAL' in output:
                                                service_status = 'CRITICAL'

                                        service, created = Service.objects.get_or_create(
                                            host=host_for_service,
                                            description=service_description,
                                            defaults={'status': service_status}
                                        )
                                        if not created:
                                            service.status = service_status

                                        service.last_checked = service_info.get("last_update")
                                        service.status_information = service_info.get("plugin_output")
                                        service.save()
                                        service_key = f"{host_name_serv}:{service_description}"
                                        if service_key not in last_notified_status or last_notified_status[
                                            service_key] != service_status:
                                            if service_status == 'CRITICAL':
                                                message = f"Service '{service_description}' on host '{host_name_serv}' is in CRITICAL state."

                                    except Host.DoesNotExist:
                                        continue
                                    except Exception:
                                        continue

        except Exception as exc:
            logger.error('Error reading status file: %s', exc)
            time.sleep(1)



