package io.github.deluf.rcpp;

import static android.content.Context.RECEIVER_NOT_EXPORTED;

import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.hardware.usb.UsbDevice;
import android.hardware.usb.UsbDeviceConnection;
import android.hardware.usb.UsbManager;
import android.os.Build;
import android.util.Log;

import com.hoho.android.usbserial.driver.UsbSerialDriver;
import com.hoho.android.usbserial.driver.UsbSerialPort;
import com.hoho.android.usbserial.driver.UsbSerialProber;
import com.hoho.android.usbserial.util.SerialInputOutputManager;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;

import io.github.deluf.rcpp.MainActivity.LogType;

public class SerialManager implements SerialInputOutputManager.Listener {
    private static final String ACTION_USB_PERMISSION = "io.github.deluf.rcpp.USB_PERMISSION";
    private static final int TARGET_VENDOR_ID = 9025;   // Arduino
    private static final int TARGET_PRODUCT_ID = 67;    // UNO R3

    private final UsbManager usbManager;
    private UsbSerialPort serialPort;
    private SerialInputOutputManager ioManager;
    private UsbDevice devicePendingPermission;
    private final MainActivity activity;
    private int baudRate;

    SerialManager(MainActivity activity, int baudRate) {
        this.activity = activity;
        this.baudRate = baudRate;
        usbManager = (UsbManager) activity.getSystemService(Context.USB_SERVICE);
        registerUsbReceiver();
        findAndConnectToTargetDevice();
    }

    void setBaudRate(int baudRate) {
        this.baudRate = baudRate;
    }

    private void findAndConnectToTargetDevice() {
        List<UsbSerialDriver> drivers = UsbSerialProber.getDefaultProber().findAllDrivers(usbManager);
        for (UsbSerialDriver driver : drivers) {
            UsbDevice device = driver.getDevice();
            if (isTargetDevice(device)) {
                if (usbManager.hasPermission(device)) {
                    connectToDevice(device);
                } else {
                    requestPermission(device);
                }
                return;
            }
        }
    }

    private boolean isTargetDevice(UsbDevice device) {
        return device.getVendorId() == TARGET_VENDOR_ID && device.getProductId() == TARGET_PRODUCT_ID;
    }

    private void requestPermission(UsbDevice device) {
        devicePendingPermission = device;
        int flags = Build.VERSION.SDK_INT >= Build.VERSION_CODES.S ? PendingIntent.FLAG_MUTABLE : 0;
        PendingIntent intent = PendingIntent.getBroadcast(activity, 0, new Intent(ACTION_USB_PERMISSION), flags);
        usbManager.requestPermission(device, intent);
    }

    private void registerUsbReceiver() {
        IntentFilter filter = new IntentFilter();
        filter.addAction(ACTION_USB_PERMISSION);
        filter.addAction(UsbManager.ACTION_USB_DEVICE_ATTACHED);
        filter.addAction(UsbManager.ACTION_USB_DEVICE_DETACHED);

        // A BroadcastReceiver receives system-wide intents
        // We are interested in three intents:
        BroadcastReceiver receiver = new BroadcastReceiver() {
            public void onReceive(Context context, Intent intent) {
                String action = intent.getAction();
                UsbDevice device = intent.getParcelableExtra(UsbManager.EXTRA_DEVICE);

                // 1. When the user responds to a USB permission request dialog
                if (ACTION_USB_PERMISSION.equals(action)) {
                    if (intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false)
                            && device != null && device.equals(devicePendingPermission)) {
                        connectToDevice(device);
                    }
                    devicePendingPermission = null;
                }

                // 2. When a USB device is plugged in
                else if (UsbManager.ACTION_USB_DEVICE_ATTACHED.equals(action)) {
                    if (device != null && isTargetDevice(device) && !isDeviceConnected()) {
                        if (usbManager.hasPermission(device)) {
                            connectToDevice(device);
                        } else {
                            requestPermission(device);
                        }
                    }
                }

                // 3. When a USB device is unplugged
                else if (UsbManager.ACTION_USB_DEVICE_DETACHED.equals(action)) {
                    if (device != null && serialPort != null && serialPort.getDriver().getDevice().equals(device)) {
                        closeSerialPort();
                    }
                }
            }
        };

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            activity.registerReceiver(receiver, filter, RECEIVER_NOT_EXPORTED);
        } else {
            activity.registerReceiver(receiver, filter);
        }
    }

    private void connectToDevice(UsbDevice device) {
        if (isDeviceConnected()) closeSerialPort();

        UsbSerialDriver driver = UsbSerialProber.getDefaultProber().probeDevice(device);
        if (driver == null || driver.getPorts().isEmpty()) {
            return;
        }

        serialPort = driver.getPorts().get(0);
        UsbDeviceConnection connection = usbManager.openDevice(device);
        if (connection == null) {
            activity.logMessage(LogType.ERROR, "Failed to open serial connection");
            return;
        }

        try {
            serialPort.open(connection);
            serialPort.setParameters(baudRate, 8, UsbSerialPort.STOPBITS_1, UsbSerialPort.PARITY_NONE);
            ioManager = new SerialInputOutputManager(serialPort, this);
            ioManager.start();
            activity.updateSerialStatus(true);
        } catch (IOException e) {
            activity.logMessage(LogType.ERROR, "Serial connection error: " + e.getMessage());
            closeSerialPort();
        }
    }

    boolean isDeviceConnected() {
        return serialPort != null && serialPort.isOpen();
    }

    void closeSerialPort() {
        if (ioManager != null) {
            ioManager.setListener(null);
            ioManager.stop();
            ioManager = null;
        }
        if (serialPort != null) {
            try { serialPort.close(); } catch (IOException ignored) {}
            serialPort = null;
        }
        activity.updateSerialStatus(false);
    }

    void sendASCII(String message) {
        if (!isDeviceConnected()) {
            activity.showToast("Connect a serial device first");
            return;
        }

        if (message.isEmpty()) {
            activity.showToast("Cannot send an empty message");
            return;
        }

        try {
            serialPort.write((message).getBytes(StandardCharsets.UTF_8), 500);
            activity.logSerialMessage(LogType.TX, message);
        } catch (IOException e) {
            activity.logMessage(LogType.ERROR, "Unable to write to serial: " + e.getMessage());
        }
    }

    @Override
    public void onNewData(byte[] data) {
        // Interprets the received data as ASCII text and logs it
        String ASCIImessage = new String(data, StandardCharsets.UTF_8).trim();
        activity.logSerialMessage(LogType.RX, ASCIImessage);
    }

    @Override
    public void onRunError(Exception e) {
        closeSerialPort();
        String errorMessage = e.getMessage();
        if (e instanceof IOException && errorMessage != null
                && errorMessage.equals("USB get_status request failed")) {
            return;
        }
        activity.logMessage(LogType.ERROR, "Uncaught error in serial port: " + e.getMessage());
    }
}
