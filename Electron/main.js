
const { app, BrowserWindow, screen } = require('electron')
const path = require('path')
const fs = require('fs')

const WINDOW_WIDTH = 382
const WINDOW_HEIGHT = 450
const MAP_PATH = path.join(__dirname, '..', 'Python', 'map.html') // ../Python/map.html
const MAP_UPDATE_INTERVAL_MS = 1000

function createWindow() {
	// Calculate bottom-left position
	const { height } = screen.getPrimaryDisplay().workAreaSize
	const x = 0
	const y = height - WINDOW_HEIGHT

	// Create the browser window
	const mainWindow = new BrowserWindow({
		width: WINDOW_WIDTH,
		height: WINDOW_HEIGHT,
		x: x,
		y: y,
		// Completely hide the OS title bar
		titleBarStyle: 'customButtonsOnHover', 
		titleBarOverlay: false,
		frame: false,
		resizable: false,
		alwaysOnTop: true,
		roundedCorners: false,
		show: true,
		backgroundColor: '#2e3440',
		webPreferences: {
			nodeIntegration: false,
			contextIsolation: true,
			// Allow loading local files
			webSecurity: false,
			allowRunningInsecureContent: true,
			// Keep animations smooth
			backgroundThrottling: false 
		}
	})
	
	if (fs.existsSync(MAP_PATH)) {
		mainWindow.loadFile(MAP_PATH)
	}
	
	// Automatic reloading
	let lastModified = 0
	setInterval(() => {
		if (!fs.existsSync(MAP_PATH)) {
			return
		}
		
		// Only reload if file was actually modified since last check
		const stats = fs.statSync(MAP_PATH)
		const fileTime = stats.mtime.getTime()
		if (fileTime <= lastModified) {
			return;
		}

		if (lastModified == 0) {
			mainWindow.loadFile(MAP_PATH)
			lastModified = fileTime
			return
		}

		// Use executeJavaScript to reload content smoothly
		mainWindow.webContents.executeJavaScript(`
			document.body.style.transition = 'opacity 0.2s ease-in-out';
			document.body.style.opacity = '0.8';
			setTimeout(() => {
				window.location.reload();
			}, 100);
		`).catch(() => {
			mainWindow.webContents.reload()
		})

		lastModified = fileTime
	}, MAP_UPDATE_INTERVAL_MS)
}

app.whenReady().then(createWindow)

// Handle certificate errors for local file loading
app.on('certificate-error', (event, webContents, url, error, certificate, callback) => {
  	event.preventDefault()
  	callback(true)
})
