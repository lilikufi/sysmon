import ipaddress
import json
import os
import platform
import re
import shutil
import subprocess

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

from .models import Host


def _validated_ip(value):
    if not value:
        raise ValueError('IP address is required')
    return str(ipaddress.ip_address(value))


@login_required
@require_GET
def get_host_id_by_ip(request):
    try:
        ip_address = _validated_ip(request.GET.get('ip'))
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    host_id = Host.objects.filter(ipaddr=ip_address).values_list('pk', flat=True).first()
    if host_id is None:
        return JsonResponse({'error': 'Host not found'}, status=404)
    return JsonResponse({'id': host_id})


@login_required
@require_POST
@csrf_protect
def open_terminal(request):
    try:
        data = json.loads(request.body)
        ip_address = _validated_ip(data.get('ip'))
        protocol = data.get('protocol', 'ssh')
        username = data.get('username', 'root')
        port = int(data.get('port', 22 if protocol == 'ssh' else 23))
        if protocol not in {'ssh', 'telnet'}:
            raise ValueError('Unsupported protocol')
        if not re.fullmatch(r'[A-Za-z0-9._-]{1,64}', username):
            raise ValueError('Invalid username')
        if not 1 <= port <= 65535:
            raise ValueError('Invalid port')
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return JsonResponse({'success': False, 'message': str(exc)}, status=400)

    handlers = {
        'Windows': _open_windows_terminal,
        'Linux': _open_linux_terminal,
        'Darwin': _open_macos_terminal,
    }
    system = platform.system()
    handler = handlers.get(system)
    if handler is None:
        return JsonResponse(
            {'success': False, 'message': f'Unsupported OS: {system}'},
            status=501,
        )
    return JsonResponse(handler(ip_address, protocol, username, port))


def _open_windows_terminal(ip_address, protocol, username, port):
    putty_paths = [
        r'C:\Program Files\PuTTY\putty.exe',
        r'C:\Program Files (x86)\PuTTY\putty.exe',
        r'C:\PuTTY\putty.exe',
        os.path.expanduser(r'~\AppData\Local\Programs\PuTTY\putty.exe'),
    ]
    putty_path = next((path for path in putty_paths if os.path.exists(path)), None)
    putty_path = putty_path or shutil.which('putty')
    if not putty_path:
        plink_path = shutil.which('plink')
        if plink_path:
            return _open_with_plink(ip_address, protocol, username, port, plink_path)
        return {
            'success': False,
            'message': 'PuTTY was not found. Install PuTTY and add it to PATH.',
            'fallback': 'copy_command',
        }

    if protocol == 'ssh':
        command = [putty_path, '-ssh', f'{username}@{ip_address}', '-P', str(port)]
    else:
        command = [putty_path, '-telnet', ip_address, '-P', str(port)]
    return _spawn_terminal(command, f'PuTTY opened for {ip_address}', windows=True)


def _open_with_plink(ip_address, protocol, username, port, plink_path):
    if protocol == 'ssh':
        command = [plink_path, '-ssh', f'{username}@{ip_address}', '-P', str(port)]
    else:
        command = [plink_path, '-telnet', ip_address, '-P', str(port)]
    return _spawn_terminal(command, f'Plink opened for {ip_address}', windows=True)


def _open_linux_terminal(ip_address, protocol, username, port):
    terminals = [
        ('gnome-terminal', ['gnome-terminal', '--']),
        ('konsole', ['konsole', '-e']),
        ('xfce4-terminal', ['xfce4-terminal', '-e']),
        ('xterm', ['xterm', '-e']),
        ('mate-terminal', ['mate-terminal', '-e']),
        ('terminator', ['terminator', '-e']),
        ('tilix', ['tilix', '-e']),
        ('alacritty', ['alacritty', '-e']),
        ('kitty', ['kitty']),
    ]
    selected = next(((name, command) for name, command in terminals if shutil.which(name)), None)
    if selected is None:
        return {
            'success': False,
            'message': 'Terminal not found. Install gnome-terminal, konsole, or xterm.',
            'fallback': 'copy_command',
        }

    terminal_name, terminal_command = selected
    if protocol == 'ssh':
        connection_command = ['ssh', f'{username}@{ip_address}', '-p', str(port)]
    else:
        connection_command = ['telnet', ip_address, str(port)]

    if terminal_name in {'konsole', 'xfce4-terminal', 'mate-terminal', 'terminator', 'tilix'}:
        command = terminal_command + [' '.join(connection_command)]
    else:
        command = terminal_command + connection_command
    return _spawn_terminal(command, f'{terminal_name} opened for {ip_address}')


def _open_macos_terminal(ip_address, protocol, username, port):
    if protocol == 'ssh':
        connection_command = f'ssh {username}@{ip_address} -p {port}'
    else:
        connection_command = f'telnet {ip_address} {port}'
    script = (
        'tell application "Terminal"\n'
        'activate\n'
        f'do script "{connection_command}"\n'
        'end tell'
    )
    return _spawn_terminal(
        ['osascript', '-e', script],
        f'Terminal.app opened for {ip_address}',
    )


def _spawn_terminal(command, success_message, windows=False):
    kwargs = {
        'start_new_session': True,
        'stdout': subprocess.DEVNULL,
        'stderr': subprocess.DEVNULL,
    }
    if windows:
        kwargs['creationflags'] = subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS
    try:
        subprocess.Popen(command, **kwargs)
    except (FileNotFoundError, OSError) as exc:
        return {'success': False, 'message': f'Terminal launch error: {exc}'}
    return {'success': True, 'message': success_message}
