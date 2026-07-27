/**
 * J.A.R.V.I.S. Desktop App — Main Process
 *
 * Electron main process that manages the application lifecycle,
 * creates the Iron Man HUD window, handles system tray integration,
 * global shortcuts, and bridges the renderer with the Python backend.
 */

const { app, BrowserWindow, Tray, Menu, globalShortcut, nativeImage, screen, ipcMain, systemPreferences, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');
const fs = require('fs');

// ── Configuration ──────────────────────────────────────────────────────────────

const CONFIG = {
    serverPort: 8000,
    serverHost: '127.0.0.1',
    windowWidth: 1100,
    windowHeight: 750,
    minWidth: 700,
    minHeight: 500,
    summonShortcut: 'CommandOrControl+Shift+J',
    voiceShortcut: 'CommandOrControl+Shift+V',
};

let mainWindow = null;
let tray = null;
let serverProcess = null;
let isQuitting = false;

// ── Python Backend Management ──────────────────────────────────────────────────

function getPythonCommand() {
    // Try python3 first, then python
    return process.platform === 'darwin' ? 'python3' : 'python';
}

function getJarvisPath() {
    // In development, the jarvis folder is at ../ relative to desktop-app
    const devPath = path.join(__dirname, '..');
    // In production (packaged app), jarvis is bundled
    const prodPath = path.join(process.resourcesPath, 'jarvis');
    return fs.existsSync(path.join(devPath, 'jarvis', 'server.py')) ? devPath : prodPath;
}

function startBackendServer() {
    const jarvisPath = getJarvisPath();
    const pythonCmd = getPythonCommand();

    console.log(`[JARVIS] Starting backend from: ${jarvisPath}`);
    console.log(`[JARVIS] Python command: ${pythonCmd}`);

    const env = {
        ...process.env,
        JARVIS_PORT: String(CONFIG.serverPort),
        JARVIS_HOST: CONFIG.serverHost,
        PYTHONUNBUFFERED: '1',
    };

    try {
        serverProcess = spawn(pythonCmd, ['-m', 'jarvis.server'], {
            cwd: jarvisPath,
            env: env,
            stdio: ['pipe', 'pipe', 'pipe'],
        });

        serverProcess.stdout.on('data', (data) => {
            console.log(`[Backend] ${data.toString().trim()}`);
        });

        serverProcess.stderr.on('data', (data) => {
            console.log(`[Backend:err] ${data.toString().trim()}`);
        });

        serverProcess.on('error', (err) => {
            console.error('[JARVIS] Failed to start backend:', err.message);
        });

        serverProcess.on('close', (code) => {
            console.log(`[JARVIS] Backend exited with code ${code}`);
            if (!isQuitting) {
                console.log('[JARVIS] Attempting to restart backend...');
                setTimeout(startBackendServer, 2000);
            }
        });

        return true;
    } catch (err) {
        console.error('[JARVIS] Error starting backend:', err);
        return false;
    }
}

function stopBackendServer() {
    if (serverProcess) {
        console.log('[JARVIS] Stopping backend server...');
        serverProcess.kill('SIGTERM');
        setTimeout(() => {
            if (serverProcess && !serverProcess.killed) {
                serverProcess.kill('SIGKILL');
            }
        }, 3000);
        serverProcess = null;
    }
}

function waitForServer(retries = 30, delay = 500) {
    return new Promise((resolve, reject) => {
        let attempts = 0;
        const check = () => {
            attempts++;
            const req = http.get(`http://${CONFIG.serverHost}:${CONFIG.serverPort}/api/health`, (res) => {
                if (res.statusCode === 200) {
                    resolve(true);
                } else if (attempts < retries) {
                    setTimeout(check, delay);
                } else {
                    reject(new Error('Server not healthy'));
                }
            });
            req.on('error', () => {
                if (attempts < retries) {
                    setTimeout(check, delay);
                } else {
                    reject(new Error('Server not reachable'));
                }
            });
            req.setTimeout(2000, () => {
                req.destroy();
                if (attempts < retries) {
                    setTimeout(check, delay);
                } else {
                    reject(new Error('Server timeout'));
                }
            });
        };
        check();
    });
}

// ── Window Creation ────────────────────────────────────────────────────────────

function createMainWindow() {
    const { width, height } = screen.getPrimaryDisplay().workAreaSize;

    mainWindow = new BrowserWindow({
        width: CONFIG.windowWidth,
        height: CONFIG.windowHeight,
        minWidth: CONFIG.minWidth,
        minHeight: CONFIG.minHeight,
        x: Math.round((width - CONFIG.windowWidth) / 2),
        y: Math.round((height - CONFIG.windowHeight) / 2),
        title: 'J.A.R.V.I.S.',
        icon: path.join(__dirname, 'assets', 'icon.png'),
        backgroundColor: '#050a0f',
        titleBarStyle: 'hiddenInset',
        vibrancy: 'dark',
        visualEffectState: 'active',
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: false,
        },
        show: false,
        frame: true,
        transparent: false,
    });

    // Load the HUD interface
    const hudPath = path.join(__dirname, 'renderer', 'hud.html');
    mainWindow.loadFile(hudPath);

    // Show window when ready (prevents white flash)
    mainWindow.once('ready-to-show', () => {
        mainWindow.show();
        // Fade in
        mainWindow.webContents.executeJavaScript(`
            document.body.style.opacity = '0';
            document.body.style.transition = 'opacity 0.5s ease-in';
            requestAnimationFrame(() => {
                document.body.style.opacity = '1';
            });
        `);
    });

    mainWindow.on('close', (e) => {
        if (!isQuitting) {
            e.preventDefault();
            mainWindow.hide();
        }
    });

    mainWindow.on('closed', () => {
        mainWindow = null;
    });

    return mainWindow;
}

// ── System Tray ────────────────────────────────────────────────────────────────

function createTray() {
    // Create a simple tray icon (16x16 PNG)
    const iconSize = 16;
    const trayIcon = nativeImage.createEmpty();

    // Use a simple template image
    const iconPath = path.join(__dirname, 'assets', 'tray-icon.png');
    if (fs.existsSync(iconPath)) {
        tray = new Tray(iconPath);
    } else {
        // Create a minimal icon programmatically
        const canvas = Buffer.alloc(iconSize * iconSize * 4);
        // Simple blue dot
        for (let i = 0; i < canvas.length; i += 4) {
            canvas[i] = 0;     // R
            canvas[i + 1] = 212; // G
            canvas[i + 2] = 255; // B
            canvas[i + 3] = 255; // A
        }
        const img = nativeImage.createFromBuffer(canvas, { width: iconSize, height: iconSize });
        tray = new Tray(img);
    }

    tray.setToolTip('J.A.R.V.I.S. — At your service, sir.');

    const contextMenu = Menu.buildFromTemplate([
        {
            label: 'Show J.A.R.V.I.S.',
            click: () => {
                if (mainWindow) {
                    mainWindow.show();
                    mainWindow.focus();
                }
            },
        },
        {
            label: 'Voice Mode',
            type: 'checkbox',
            checked: false,
            click: (menuItem) => {
                if (mainWindow) {
                    mainWindow.webContents.send('toggle-voice', menuItem.checked);
                }
            },
        },
        { type: 'separator' },
        {
            label: 'System Status',
            click: () => {
                if (mainWindow) {
                    mainWindow.show();
                    mainWindow.webContents.send('show-status');
                }
            },
        },
        { type: 'separator' },
        {
            label: 'Quit J.A.R.V.I.S.',
            click: () => {
                isQuitting = true;
                stopBackendServer();
                app.quit();
            },
        },
    ]);

    tray.setContextMenu(contextMenu);

    tray.on('click', () => {
        if (mainWindow) {
            if (mainWindow.isVisible()) {
                mainWindow.hide();
            } else {
                mainWindow.show();
                mainWindow.focus();
            }
        }
    });
}

// ── Global Shortcuts ───────────────────────────────────────────────────────────

function registerGlobalShortcuts() {
    // Summon shortcut
    globalShortcut.register(CONFIG.summonShortcut, () => {
        if (mainWindow) {
            if (mainWindow.isVisible()) {
                mainWindow.hide();
            } else {
                mainWindow.show();
                mainWindow.focus();
                mainWindow.webContents.send('summon');
            }
        }
    });

    // Voice shortcut
    globalShortcut.register(CONFIG.voiceShortcut, () => {
        if (mainWindow) {
            mainWindow.show();
            mainWindow.focus();
            mainWindow.webContents.send('start-voice');
        }
    });
}

// ── IPC Handlers ───────────────────────────────────────────────────────────────

function setupIPC() {
    ipcMain.handle('get-server-url', () => {
        return `http://${CONFIG.serverHost}:${CONFIG.serverPort}`;
    });

    ipcMain.handle('get-ws-url', () => {
        return `ws://${CONFIG.serverHost}:${CONFIG.serverPort}/ws/chat`;
    });

    ipcMain.handle('get-config', () => {
        return CONFIG;
    });

    ipcMain.handle('restart-backend', async () => {
        stopBackendServer();
        startBackendServer();
        try {
            await waitForServer(20, 500);
            return { success: true };
        } catch (e) {
            return { success: false, error: e.message };
        }
    });

    ipcMain.on('set-tray-voice', (event, enabled) => {
        // Update tray menu voice checkbox
        if (tray) {
            const menu = tray.getContextMenu();
            const voiceItem = menu.items.find(item => item.label === 'Voice Mode');
            if (voiceItem) {
                voiceItem.checked = enabled;
            }
        }
    });

    ipcMain.on('hide-window', () => {
        if (mainWindow) {
            mainWindow.hide();
        }
    });

    ipcMain.on('minimize-window', () => {
        if (mainWindow) {
            mainWindow.minimize();
        }
    });

    ipcMain.handle('get-system-info', async () => {
        try {
            const response = await fetch(`http://${CONFIG.serverHost}:${CONFIG.serverPort}/api/system`);
            return await response.json();
        } catch (e) {
            return { info: 'System info unavailable' };
        }
    });
}

// ── App Lifecycle ──────────────────────────────────────────────────────────────

app.whenReady().then(async () => {
    console.log('[JARVIS] Starting up...');

    // Setup IPC
    setupIPC();

    // Start Python backend
    startBackendServer();

    // Create window
    createMainWindow();

    // Create tray
    createTray();

    // Register shortcuts
    registerGlobalShortcuts();

    // Wait for backend to be ready
    console.log('[JARVIS] Waiting for backend server...');
    try {
        await waitForServer();
        console.log('[JARVIS] Backend server is ready!');
        if (mainWindow) {
            mainWindow.webContents.send('backend-ready');
        }
    } catch (e) {
        console.error('[JARVIS] Backend failed to start:', e.message);
        if (mainWindow) {
            mainWindow.webContents.send('backend-error', e.message);
        }
    }
});

app.on('window-all-closed', () => {
    // Don't quit on macOS — keep running in tray
    if (process.platform !== 'darwin') {
        isQuitting = true;
        stopBackendServer();
        app.quit();
    }
});

app.on('before-quit', () => {
    isQuitting = true;
    stopBackendServer();
    globalShortcut.unregisterAll();
});

app.on('activate', () => {
    // macOS: re-create window when dock icon clicked
    if (!mainWindow) {
        createMainWindow();
    } else {
        mainWindow.show();
        mainWindow.focus();
    }
});