package io.github.deluf.rcpp;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import io.github.deluf.rcpp.MainActivity.LogType;

public class SocketManager {
    private static final int STREAM_PORT = 8001;      // UDP port for video/audio streaming
    private static final int TELEMETRY_PORT = 8002;   // TCP port for telemetry data
    private static final int CONTROL_PORT = 8003;     // TCP port for control commands
    private static final int RECONNECT_DELAY_MS = 10000;
    private static final int SOCKET_READ_TIMEOUT_MS = 1000;

    private final MainActivity activity;
    private final String controllerIP;
    private volatile DatagramSocket streamSocket;
    private volatile Socket telemetrySocket;
    private volatile Socket controlSocket;
    private volatile InetSocketAddress streamAddress;
    private volatile PrintWriter telemetryWriter;
    private volatile BufferedReader controlReader;
    private final ExecutorService executorService;
    private final ScheduledExecutorService reconnectExecutor;
    private final AtomicBoolean isControlListening = new AtomicBoolean(false);
    private final AtomicBoolean streamReconnecting = new AtomicBoolean(false);
    private final AtomicBoolean telemetryReconnecting = new AtomicBoolean(false);
    private final AtomicBoolean controlReconnecting = new AtomicBoolean(false);

    public SocketManager(MainActivity activity, String controllerIP) {
        this.activity = activity;
        this.controllerIP = controllerIP;
        this.executorService = Executors.newCachedThreadPool();
        this.reconnectExecutor = Executors.newScheduledThreadPool(3);
        initializeSockets();
    }

    void initializeSockets() {
        executorService.execute(() -> {
            initializeStreamSocket();
            initializeTelemetrySocket();
            initializeControlSocket();
        });
    }

    private void initializeStreamSocket() {
        try {
            InetAddress address = InetAddress.getByName(controllerIP);
            streamSocket = new DatagramSocket();
            streamAddress = new InetSocketAddress(address, STREAM_PORT);
            streamReconnecting.set(false);
        } catch (IOException e) {
            activity.logMessage(LogType.ERROR, "Stream socket error: " + e.getMessage());
            streamReconnecting.set(false);
            scheduleStreamReconnect();
        }
    }

    private void initializeTelemetrySocket() {
        try {
            InetAddress address = InetAddress.getByName(controllerIP);
            telemetrySocket = new Socket(address, TELEMETRY_PORT);
            telemetryWriter = new PrintWriter(telemetrySocket.getOutputStream(), true);
            telemetryReconnecting.set(false);
        } catch (IOException e) {
            activity.logMessage(LogType.ERROR, "Telemetry socket error: " + e.getMessage());
            telemetryReconnecting.set(false);
            scheduleTelemetryReconnect();
        }
    }

    private void initializeControlSocket() {
        try {
            InetAddress address = InetAddress.getByName(controllerIP);
            controlSocket = new Socket(address, CONTROL_PORT);
            controlSocket.setSoTimeout(SOCKET_READ_TIMEOUT_MS);
            controlReader = new BufferedReader(new InputStreamReader(controlSocket.getInputStream()));
            startControlListener();
            controlReconnecting.set(false);
        } catch (IOException e) {
            activity.logMessage(LogType.ERROR, "Control socket error: " + e.getMessage());
            controlReconnecting.set(false);
            scheduleControlReconnect();
        }
    }

    private void startControlListener() {
        executorService.execute(() -> {
            isControlListening.set(true);
            try {
                String command;
                while (isControlListening.get()) {
                    try {
                        if (controlSocket.isClosed() || !controlSocket.isConnected()) break;
                        command = controlReader.readLine();
                        if (command == null) break;
                        handleIncomingCommand(command);
                    } catch (SocketTimeoutException e) {
                        // Timeout is expected, continue loop to check socket state
                    }
                }
            } catch (IOException e) {
                activity.logMessage(LogType.ERROR, "Control socket error: " + e.getMessage());
            } finally {
                scheduleControlReconnect();
            }
        });
    }

    private void scheduleStreamReconnect() {
        if (!streamReconnecting.compareAndSet(false, true)) return;
        activity.logMessage(LogType.FAIL_SAFE, "Reconnecting to stream socket...");
        reconnectExecutor.schedule(this::initializeStreamSocket, RECONNECT_DELAY_MS, TimeUnit.MILLISECONDS);
    }

    private void scheduleTelemetryReconnect() {
        if (!telemetryReconnecting.compareAndSet(false, true)) return;
        activity.logMessage(LogType.FAIL_SAFE, "Reconnecting to telemetry socket...");
        reconnectExecutor.schedule(this::initializeTelemetrySocket, RECONNECT_DELAY_MS, TimeUnit.MILLISECONDS);
    }

    private void scheduleControlReconnect() {
        if (!controlReconnecting.compareAndSet(false, true)) return;
        activity.logMessage(LogType.FAIL_SAFE, "Reconnecting to control socket...");
        isControlListening.set(false);
        reconnectExecutor.schedule(this::initializeControlSocket, RECONNECT_DELAY_MS, TimeUnit.MILLISECONDS);
    }

    public void destroy() {
        if (!reconnectExecutor.isShutdown()) {
            reconnectExecutor.shutdownNow();
        }
        isControlListening.set(false);

        executorService.execute(() -> {
            try {
                if (controlReader != null) {
                    controlReader.close();
                }
                if (controlSocket != null) {
                    controlSocket.close();
                }
                if (telemetryWriter != null) {
                    telemetryWriter.close();
                }
                if (telemetrySocket != null) {
                    telemetrySocket.close();
                }
                if (streamSocket != null) {
                    streamSocket.close();
                }
            } catch (IOException e) {
                activity.logMessage(LogType.ERROR, "Error destroying sockets: " + e.getMessage());
            }
        });

        if (!executorService.isShutdown()) {
            executorService.shutdown();
        }
    }

    public void sendStream(byte[] data) {
        if (streamSocket == null || streamSocket.isClosed() || streamAddress == null) {
            if (!streamReconnecting.get()) {
                scheduleStreamReconnect();
            }
            return;
        }

        if (data == null || data.length == 0) {
            return;
        }

        executorService.execute(() -> {
            try {
                DatagramPacket packet = new DatagramPacket(data, data.length, streamAddress);
                streamSocket.send(packet);
                activity.logMessage(LogType.INFO, "Sent " + data.length + " bytes of stream data");
            } catch (IOException e) {
                activity.logMessage(LogType.ERROR, "Failed to send stream data: " + e.getMessage());
                scheduleStreamReconnect();
            }
        });
    }

    public void sendTelemetry(String telemetryData) {
        if (telemetryWriter == null || telemetrySocket == null || !telemetrySocket.isConnected()) {
            if (!telemetryReconnecting.get()) {
                scheduleTelemetryReconnect();
            }
            return;
        }

        if (telemetryData == null || telemetryData.trim().isEmpty()) {
            return;
        }

        executorService.execute(() -> {
            try {
                telemetryWriter.println(telemetryData);
                if (telemetryWriter.checkError())
                    throw new IOException("telemetryWriter check error");
                activity.logMessage(LogType.INFO, "Sent telemetry data: " + telemetryData);
            } catch (Exception e) {
                activity.logMessage(LogType.ERROR, "Failed to send telemetry data: " + e.getMessage());
                scheduleTelemetryReconnect();
            }
        });
    }

    private void handleIncomingCommand(String command) {
        if (command == null || command.trim().isEmpty()) {
            return;
        }
        activity.logMessage(LogType.INFO, "Received control command: " + command);
    }
}