
const { app, BrowserWindow, screen } = require('electron')
const path = require('path')
const fs = require('fs')

const WINDOW_WIDTH = 382
const WINDOW_HEIGHT = 300

function createWindow() {
	// Calculate bottom-left position
	const { width, height } = screen.getPrimaryDisplay().workAreaSize
	const x = width - WINDOW_WIDTH
	const y = 0

	// Create the browser window
	const window = new BrowserWindow({
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
		webPreferences: {
			nodeIntegration: false,
			contextIsolation: true,
		}
	})

	window.loadURL('https://gamepad.e7d.io/?type=ds4&background=dimgrey&color=white&triggers=meter')
}

app.whenReady().then(createWindow)
