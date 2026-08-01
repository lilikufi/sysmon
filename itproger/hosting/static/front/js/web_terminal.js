// static/front/js/web_terminal.js

class WebTerminal {
    constructor() {
        this.terminal = null;
        this.socket = null;
        this.fitAddon = null;
        this.isConnected = false;
        this.currentHost = null;
        this.sessionId = null;

        this.initModal();
    }

    initModal() {
        // Создаём модальное окно
        const modalHTML = `
            <div class="terminal-modal" id="terminalModal">
                <div class="terminal-window">
                    <div class="terminal-header">
                        <div class="terminal-title">
                            <span class="status-dot" id="terminalStatus"></span>
                            <span id="terminalTitleText">SSH Terminal</span>
                        </div>
                        <div class="terminal-controls">
                            <button class="terminal-btn" id="terminalReconnect" style="display: none;">
                                Reconnect
                            </button>
                            <button class="terminal-btn close" id="terminalClose">
                                ✕ Close
                            </button>
                        </div>
                    </div>
                    <div class="terminal-body">
                        <div id="terminalLogin" class="terminal-login">
                            <h3>🔐 SSH Connection</h3>
                            <form class="terminal-login-form" id="sshLoginForm">
                                <div class="terminal-input-group">
                                    <label>Host IP</label>
                                    <input type="text" id="sshHost" placeholder="192.168.1.1" required readonly>
                                </div>
                                <div class="terminal-input-group">
                                    <label>Username</label>
                                    <input type="text" id="sshUsername" placeholder="root" value="root">
                                </div>
                                <div class="terminal-input-group">
                                    <label>Password</label>
                                    <input type="password" id="sshPassword" placeholder="Enter password">
                                </div>
                                <div class="terminal-input-group">
                                    <label>Port</label>
                                    <input type="number" id="sshPort" placeholder="22" value="22">
                                </div>
                                <button type="submit" class="terminal-connect-btn" id="sshConnectBtn">
                                    Connect
                                </button>
                                <div class="terminal-error" id="sshError" style="display: none;"></div>
                            </form>
                        </div>
                        <div id="terminal-container" style="display: none;"></div>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHTML);

        // Обработчики событий
        document.getElementById('terminalClose').addEventListener('click', () => this.close());
        document.getElementById('terminalReconnect').addEventListener('click', () => this.reconnect());
        document.getElementById('sshLoginForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.connectSSH();
        });

        // Закрытие по Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && document.getElementById('terminalModal').classList.contains('active')) {
                this.close();
            }
        });
    }

    open(host, username = 'root') {
        this.currentHost = host;
        this.sessionId = this.generateSessionId();

        document.getElementById('sshHost').value = host;
        document.getElementById('sshUsername').value = username;
        document.getElementById('sshPassword').value = '';
        document.getElementById('sshError').style.display = 'none';

        document.getElementById('terminalLogin').style.display = 'flex';
        document.getElementById('terminal-container').style.display = 'none';

        document.getElementById('terminalModal').classList.add('active');
        document.getElementById('sshPassword').focus();

        this.setStatus('disconnected');
    }

    close() {
        this.disconnect();
        document.getElementById('terminalModal').classList.remove('active');

        // Очищаем терминал
        if (this.terminal) {
            this.terminal.dispose();
            this.terminal = null;
        }
    }

    generateSessionId() {
        return 'term_' + Math.random().toString(36).substr(2, 9);
    }

    setStatus(status, message = '') {
        const statusDot = document.getElementById('terminalStatus');
        const titleText = document.getElementById('terminalTitleText');
        const reconnectBtn = document.getElementById('terminalReconnect');

        statusDot.className = 'status-dot';

        switch (status) {
            case 'connecting':
                statusDot.classList.add('connecting');
                titleText.textContent = `Connecting to ${this.currentHost}...`;
                reconnectBtn.style.display = 'none';
                break;
            case 'connected':
                statusDot.classList.add('connected');
                titleText.textContent = `SSH: ${this.currentHost}`;
                reconnectBtn.style.display = 'none';
                break;
            case 'disconnected':
                titleText.textContent = 'SSH Terminal';
                reconnectBtn.style.display = 'none';
                break;
            case 'error':
                statusDot.classList.add('error');
                titleText.textContent = message || 'Connection Error';
                reconnectBtn.style.display = 'inline-block';
                break;
        }
    }

    async connectSSH() {
        const host = document.getElementById('sshHost').value;
        const username = document.getElementById('sshUsername').value || 'root';
        const password = document.getElementById('sshPassword').value;
        const port = parseInt(document.getElementById('sshPort').value) || 22;

        const connectBtn = document.getElementById('sshConnectBtn');
        const errorDiv = document.getElementById('sshError');

        connectBtn.disabled = true;
        connectBtn.textContent = 'Connecting...';
        errorDiv.style.display = 'none';

        this.setStatus('connecting');

        try {
            // Инициализируем терминал
            await this.initTerminal();

            // Подключаемся к WebSocket
            await this.connectWebSocket();

            // Отправляем команду подключения
            this.socket.send(JSON.stringify({
                type: 'connect',
                host: host,
                username: username,
                password: password,
                port: port,
                cols: this.terminal.cols,
                rows: this.terminal.rows
            }));

        } catch (error) {
            console.error('Connection error:', error);
            errorDiv.textContent = error.message;
            errorDiv.style.display = 'block';
            connectBtn.disabled = false;
            connectBtn.textContent = 'Connect';
            this.setStatus('error', 'Connection failed');
        }
    }

    async initTerminal() {
        // Загружаем xterm.js динамически, если ещё не загружен
        if (!window.Terminal) {
            await this.loadScript('https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.min.js');
            await this.loadScript('https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.min.js');
            await this.loadCSS('https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.min.css');
        }

        // Создаём терминал
        this.terminal = new Terminal({
            cursorBlink: true,
            cursorStyle: 'block',
            fontSize: 14,
            fontFamily: '"JetBrains Mono", "Fira Code", "Consolas", monospace',
            theme: {
                background: '#0a0e17',
                foreground: '#eaf7ff',
                cursor: '#00ffff',
                cursorAccent: '#0a0e17',
                selection: 'rgba(0, 255, 255, 0.3)',
                black: '#0a0e17',
                red: '#ff5050',
                green: '#00ff88',
                yellow: '#ffaa00',
                blue: '#00aaff',
                magenta: '#da70d6',
                cyan: '#00ffff',
                white: '#eaf7ff',
                brightBlack: '#4a5568',
                brightRed: '#ff6b6b',
                brightGreen: '#69ff94',
                brightYellow: '#fff06b',
                brightBlue: '#69b4ff',
                brightMagenta: '#ff69b4',
                brightCyan: '#69ffff',
                brightWhite: '#ffffff'
            },
            allowTransparency: true,
            scrollback: 10000
        });

        this.fitAddon = new FitAddon.FitAddon();
        this.terminal.loadAddon(this.fitAddon);

        const container = document.getElementById('terminal-container');
        container.innerHTML = '';
        this.terminal.open(container);

        // Подгоняем размер
        setTimeout(() => {
            this.fitAddon.fit();
        }, 100);

        // Обработка ввода
        this.terminal.onData(data => {
            if (this.socket && this.isConnected) {
                this.socket.send(JSON.stringify({
                    type: 'input',
                    data: data
                }));
            }
        });

        // Обработка изменения размера
        window.addEventListener('resize', () => {
            if (this.fitAddon && this.terminal) {
                this.fitAddon.fit();
                if (this.socket && this.isConnected) {
                    this.socket.send(JSON.stringify({
                        type: 'resize',
                        cols: this.terminal.cols,
                        rows: this.terminal.rows
                    }));
                }
            }
        });
    }

    connectWebSocket() {
        return new Promise((resolve, reject) => {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/terminal/${this.sessionId}/`;

            this.socket = new WebSocket(wsUrl);

            this.socket.onopen = () => {
                console.log('WebSocket connected');
                resolve();
            };

            this.socket.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            };

            this.socket.onclose = (event) => {
                console.log('WebSocket closed', event);
                this.isConnected = false;
                if (this.terminal) {
                    this.terminal.writeln('\r\n\x1b[31mConnection closed\x1b[0m');
                }
                this.setStatus('error', 'Disconnected');
            };

            this.socket.onerror = (error) => {
                console.error('WebSocket error:', error);
                reject(new Error('WebSocket connection failed'));
            };
        });
    }

    handleMessage(data) {
        const errorDiv = document.getElementById('sshError');
        const connectBtn = document.getElementById('sshConnectBtn');

        switch (data.type) {
            case 'output':
                if (this.terminal) {
                    this.terminal.write(data.data);
                }
                break;

            case 'connected':
                this.isConnected = true;
                document.getElementById('terminalLogin').style.display = 'none';
                document.getElementById('terminal-container').style.display = 'block';
                this.setStatus('connected');

                setTimeout(() => {
                    this.fitAddon.fit();
                    this.terminal.focus();
                }, 100);
                break;

            case 'error':
                errorDiv.textContent = data.message;
                errorDiv.style.display = 'block';
                connectBtn.disabled = false;
                connectBtn.textContent = 'Connect';
                this.setStatus('error', data.message);
                break;

            case 'disconnected':
                this.isConnected = false;
                if (this.terminal) {
                    this.terminal.writeln('\r\n\x1b[33m' + data.message + '\x1b[0m');
                }
                this.setStatus('error', 'Session ended');
                break;

            case 'status':
                console.log('Status:', data.message);
                break;
        }
    }

    disconnect() {
        if (this.socket) {
            if (this.socket.readyState === WebSocket.OPEN) {
                this.socket.send(JSON.stringify({ type: 'disconnect' }));
            }
            this.socket.close();
            this.socket = null;
        }
        this.isConnected = false;
    }

    reconnect() {
        this.disconnect();
        document.getElementById('terminalLogin').style.display = 'flex';
        document.getElementById('terminal-container').style.display = 'none';
        document.getElementById('sshConnectBtn').disabled = false;
        document.getElementById('sshConnectBtn').textContent = 'Connect';
        document.getElementById('sshPassword').value = '';
        this.setStatus('disconnected');
    }

    loadScript(src) {
        return new Promise((resolve, reject) => {
            if (document.querySelector(`script[src="${src}"]`)) {
                resolve();
                return;
            }
            const script = document.createElement('script');
            script.src = src;
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }

    loadCSS(href) {
        return new Promise((resolve) => {
            if (document.querySelector(`link[href="${href}"]`)) {
                resolve();
                return;
            }
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = href;
            link.onload = resolve;
            document.head.appendChild(link);
        });
    }
}

// Создаём глобальный экземпляр
const webTerminal = new WebTerminal();
