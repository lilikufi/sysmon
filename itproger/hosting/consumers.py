# your_app/consumers.py

import json
import asyncio
import paramiko
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
import logging

logger = logging.getLogger(__name__)


class SSHConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer для SSH терминала.
    Работает как мост между браузером и SSH сервером.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ssh_client = None
        self.channel = None
        self.connected = False
        self.read_task = None
        self.session_id = None

    async def connect(self):
        """Принимаем WebSocket соединение"""
        self.session_id = self.scope['url_route']['kwargs'].get('session_id', 'unknown')
        logger.info(f"WebSocket connect: {self.session_id}")
        await self.accept()

        await self.send(json.dumps({
            'type': 'status',
            'message': 'WebSocket connected. Ready for SSH credentials.'
        }))

    async def disconnect(self, close_code):
        """Закрываем все соединения"""
        logger.info(f"WebSocket disconnect: {self.session_id}, code: {close_code}")
        await self.cleanup()

    async def cleanup(self):
        """Очистка ресурсов"""
        self.connected = False

        # Отменяем задачу чтения
        if self.read_task and not self.read_task.done():
            self.read_task.cancel()
            try:
                await self.read_task
            except asyncio.CancelledError:
                pass

        # Закрываем SSH канал
        if self.channel:
            try:
                self.channel.close()
            except Exception:
                pass
            self.channel = None

        # Закрываем SSH клиент
        if self.ssh_client:
            try:
                self.ssh_client.close()
            except Exception:
                pass
            self.ssh_client = None

    async def receive(self, text_data):
        """Обработка входящих сообщений от клиента"""
        try:
            data = json.loads(text_data)
            msg_type = data.get('type')

            logger.debug(f"Received message type: {msg_type}")

            if msg_type == 'connect':
                await self.handle_ssh_connect(data)
            elif msg_type == 'input':
                await self.handle_ssh_input(data.get('data', ''))
            elif msg_type == 'resize':
                await self.handle_ssh_resize(
                    data.get('cols', 80),
                    data.get('rows', 24)
                )
            elif msg_type == 'disconnect':
                await self.cleanup()
                await self.send(json.dumps({
                    'type': 'disconnected',
                    'message': 'Disconnected by user'
                }))
            else:
                logger.warning(f"Unknown message type: {msg_type}")

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            await self.send(json.dumps({
                'type': 'error',
                'message': 'Invalid JSON message'
            }))
        except Exception as e:
            logger.error(f"Receive error: {e}")
            await self.send(json.dumps({
                'type': 'error',
                'message': f'Error: {str(e)}'
            }))

    @sync_to_async
    def _create_ssh_connection(self, host, username, password, port):
        """Создаём SSH соединение (синхронно, обёрнуто в async)"""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        client.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            timeout=15,
            allow_agent=False,
            look_for_keys=False,
            banner_timeout=15
        )

        return client

    @sync_to_async
    def _create_shell_channel(self, cols, rows):
        """Создаём интерактивный shell канал"""
        channel = self.ssh_client.invoke_shell(
            term='xterm-256color',
            width=cols,
            height=rows,
            height_pixels=0,
            width_pixels=0
        )
        channel.setblocking(0)
        return channel

    async def handle_ssh_connect(self, data):
        """Подключаемся к SSH серверу"""
        host = data.get('host', '').strip()
        username = data.get('username', 'root').strip()
        password = data.get('password', '')
        port = int(data.get('port', 22))
        cols = int(data.get('cols', 120))
        rows = int(data.get('rows', 30))

        # Валидация
        if not host:
            await self.send(json.dumps({
                'type': 'error',
                'message': 'Host IP is required'
            }))
            return

        if not password:
            await self.send(json.dumps({
                'type': 'error',
                'message': 'Password is required'
            }))
            return

        logger.info(f"SSH connecting to {username}@{host}:{port}")

        await self.send(json.dumps({
            'type': 'status',
            'message': f'Connecting to {host}...'
        }))

        try:
            # Создаём SSH соединение
            self.ssh_client = await self._create_ssh_connection(
                host, username, password, port
            )

            # Создаём shell канал
            self.channel = await self._create_shell_channel(cols, rows)
            self.connected = True

            logger.info(f"SSH connected to {host}")

            # Отправляем успех
            await self.send(json.dumps({
                'type': 'connected',
                'message': f'Connected to {username}@{host}'
            }))

            # Запускаем чтение вывода SSH
            self.read_task = asyncio.create_task(self._read_ssh_output())

        except paramiko.AuthenticationException:
            logger.warning(f"SSH auth failed for {username}@{host}")
            await self.send(json.dumps({
                'type': 'error',
                'message': 'Authentication failed. Wrong username or password.'
            }))
            await self.cleanup()

        except paramiko.SSHException as e:
            logger.error(f"SSH error: {e}")
            await self.send(json.dumps({
                'type': 'error',
                'message': f'SSH protocol error: {str(e)}'
            }))
            await self.cleanup()

        except TimeoutError:
            logger.error(f"SSH timeout to {host}")
            await self.send(json.dumps({
                'type': 'error',
                'message': f'Connection timeout. Host {host} not responding.'
            }))
            await self.cleanup()

        except OSError as e:
            logger.error(f"Network error: {e}")
            await self.send(json.dumps({
                'type': 'error',
                'message': f'Network error: {str(e)}'
            }))
            await self.cleanup()

        except Exception as e:
            logger.exception(f"Unexpected error connecting to {host}")
            await self.send(json.dumps({
                'type': 'error',
                'message': f'Connection failed: {str(e)}'
            }))
            await self.cleanup()

    async def _read_ssh_output(self):
        """Читаем вывод SSH и отправляем в браузер"""
        logger.debug("Starting SSH output reader")

        try:
            while self.connected and self.channel:
                # Проверяем, есть ли данные для чтения
                if self.channel.recv_ready():
                    try:
                        data = self.channel.recv(4096)
                        if data:
                            text = data.decode('utf-8', errors='replace')
                            await self.send(json.dumps({
                                'type': 'output',
                                'data': text
                            }))
                    except Exception as e:
                        logger.error(f"Error reading SSH data: {e}")
                        break

                # Проверяем stderr
                if self.channel.recv_stderr_ready():
                    try:
                        data = self.channel.recv_stderr(4096)
                        if data:
                            text = data.decode('utf-8', errors='replace')
                            await self.send(json.dumps({
                                'type': 'output',
                                'data': text
                            }))
                    except Exception as e:
                        logger.error(f"Error reading SSH stderr: {e}")

                # Проверяем, закрыт ли канал
                if self.channel.closed or self.channel.exit_status_ready():
                    logger.info("SSH channel closed by server")
                    self.connected = False
                    await self.send(json.dumps({
                        'type': 'disconnected',
                        'message': 'Session closed by remote host'
                    }))
                    break

                # Небольшая пауза для снижения нагрузки CPU
                await asyncio.sleep(0.01)

        except asyncio.CancelledError:
            logger.debug("SSH reader cancelled")
            raise
        except Exception as e:
            logger.exception(f"SSH reader error: {e}")
            if self.connected:
                await self.send(json.dumps({
                    'type': 'error',
                    'message': f'Connection lost: {str(e)}'
                }))
        finally:
            self.connected = False
            logger.debug("SSH output reader stopped")

    async def handle_ssh_input(self, data):
        """Отправляем данные в SSH"""
        if not self.connected or not self.channel:
            return

        try:
            # Отправляем синхронно, но в thread pool
            await sync_to_async(self.channel.send)(data.encode('utf-8'))
        except Exception as e:
            logger.error(f"Error sending to SSH: {e}")
            await self.send(json.dumps({
                'type': 'error',
                'message': f'Send error: {str(e)}'
            }))

    async def handle_ssh_resize(self, cols, rows):
        """Изменяем размер терминала"""
        if not self.connected or not self.channel:
            return

        try:
            await sync_to_async(self.channel.resize_pty)(
                width=cols,
                height=rows
            )
            logger.debug(f"Terminal resized to {cols}x{rows}")
        except Exception as e:
            logger.warning(f"Resize error: {e}")
