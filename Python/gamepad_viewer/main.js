const { app, BrowserWindow, screen } = require('electron')

const WINDOW_WIDTH = 382
const WINDOW_HEIGHT = 280

function createWindow() {
    const { height } = screen.getPrimaryDisplay().workAreaSize
    const x = 0
    const y = height - 300 - WINDOW_HEIGHT

    const window = new BrowserWindow({
        width: WINDOW_WIDTH,
        height: WINDOW_HEIGHT,
        x,
        y,
        titleBarStyle: 'customButtonsOnHover', 
        titleBarOverlay: false,
        frame: false,
        resizable: false,
        alwaysOnTop: true,
        roundedCorners: false,
        show: true,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
        }
    })

    window.loadURL('https://gamepad.e7d.io/?type=ds4&background=dimgrey&color=white&triggers=meter')

    // Once the page is ready, inject the script
    window.webContents.on('did-finish-load', () => {
        window.webContents.executeJavaScript(`
            // Make the gamepad a little smaller
            function scale_gamepad() {
                const gamepad_div = document.getElementById('gamepad');
                if (gamepad_div) { 
                    gamepad_div.style.transform = 'translate(-50%, -50%) scale(0.45, 0.45)';
                }
            }
            scale_gamepad();

            // Keep enforcing it if the page changes styles dynamically
            const observer = new MutationObserver(scale_gamepad);
            observer.observe(document.body, { attributes: true, childList: true, subtree: true });
        `)
    })
}

app.whenReady().then(createWindow)
