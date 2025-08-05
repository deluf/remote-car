
package io.github.deluf.rcpp;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
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
    private static final int VIDEO_STREAM_PORT = 8001;
    private static final int AUDIO_STREAM_PORT = 8002;
    private static final int TELEMETRY_PORT = 8003;
    private static final int CONTROL_PORT = 8004;
    private static final int RECONNECT_DELAY_MS = 3000;
    private static final int SOCKET_READ_TIMEOUT_MS = 1000;

    private final MainActivity activity;
    private final String controllerIP;

    private volatile DatagramSocket videoStreamSocket;
    private volatile DatagramSocket audioStreamSocket;
    private volatile InetSocketAddress videoStreamAddress;
    private volatile InetSocketAddress audioStreamAddress;

    private volatile Socket telemetrySocket;
    private volatile Socket controlSocket;
    private volatile PrintWriter telemetryWriter;
    private volatile BufferedReader controlReader;

    private final ExecutorService executorService;
    private final ScheduledExecutorService reconnectExecutor;

    private final AtomicBoolean videoStreamReconnecting = new AtomicBoolean(false);
    private final AtomicBoolean audioStreamReconnecting = new AtomicBoolean(false);
    private final AtomicBoolean telemetryReconnecting = new AtomicBoolean(false);
    private final AtomicBoolean controlReconnecting = new AtomicBoolean(false);
    private final AtomicBoolean isControlListening = new AtomicBoolean(false);

    public SocketManager(MainActivity activity, String controllerIP) {
        this.activity = activity;
        this.controllerIP = controllerIP;
        this.executorService = Executors.newCachedThreadPool();
        this.reconnectExecutor = Executors.newScheduledThreadPool(4);
        initializeSockets();
    }

    void initializeSockets() {
        executorService.execute(() -> {
            initializeVideoStreamSocket();
            initializeAudioStreamSocket();
            initializeTelemetrySocket();
            initializeControlSocket();
        });
    }

    private void initializeVideoStreamSocket() {
        try {
            InetAddress address = InetAddress.getByName(controllerIP);
            videoStreamSocket = new DatagramSocket();
            videoStreamAddress = new InetSocketAddress(address, VIDEO_STREAM_PORT);
            videoStreamReconnecting.set(false);
        } catch (IOException e) {
            activity.logMessage(LogType.ERROR, "Video stream socket error: " + e.getMessage());
            videoStreamReconnecting.set(false);
            scheduleVideoStreamReconnect();
        }
    }

    private void initializeAudioStreamSocket() {
        try {
            InetAddress address = InetAddress.getByName(controllerIP);
            audioStreamSocket = new DatagramSocket();
            audioStreamAddress = new InetSocketAddress(address, AUDIO_STREAM_PORT);
            audioStreamReconnecting.set(false);
        } catch (IOException e) {
            activity.logMessage(LogType.ERROR, "Audio stream socket error: " + e.getMessage());
            audioStreamReconnecting.set(false);
            scheduleAudioStreamReconnect();
        }
    }

    private void initializeTelemetrySocket() {
        try {
            InetAddress address = InetAddress.getByName(controllerIP);
            telemetrySocket = new Socket(address, TELEMETRY_PORT);
            telemetryWriter = new PrintWriter(telemetrySocket.getOutputStream(), true);
            activity.updateTelemetrySocketStatus(true);
            telemetryReconnecting.set(false);
        } catch (IOException e) {
            if (isUnknownSocketError(e)) {
                activity.logMessage(LogType.ERROR, "Telemetry socket error: " + e.getMessage());
            }
            telemetryReconnecting.set(false);
            scheduleTelemetryReconnect();
        }
    }

    private void initializeControlSocket() {
        try {
            InetAddress address = InetAddress.getByName(controllerIP);
            controlSocket = new Socket(address, CONTROL_PORT);
            controlSocket.setSoTimeout(SOCKET_READ_TIMEOUT_MS);
            startControlListener(controlSocket.getInputStream());
            activity.updateControlSocketStatus(true);
            controlReconnecting.set(false);
        } catch (IOException e) {
            if (isUnknownSocketError(e)) {
                activity.logMessage(LogType.ERROR, "Control socket error: " + e.getMessage());
            }
            controlReconnecting.set(false);
            scheduleControlReconnect();
        }
    }

    private boolean isUnknownSocketError(IOException e) {
        return e.getMessage() == null || (!e.getMessage().contains("ETIMEDOUT")
                && !e.getMessage().contains("ECONNREFUSED"));
    }

    private void startControlListener(InputStream inputStream) {
        executorService.execute(() -> {
            isControlListening.set(true);
            try {
                byte[] read_buffer = new byte[MicrocontrollerManager.COMMAND_LEN];
                while (isControlListening.get()) {
                    try {
                        if (controlSocket.isClosed() || !controlSocket.isConnected()) break;

                        int bytesRead = 0;
                        int bytesToRead = MicrocontrollerManager.COMMAND_LEN;
                        while (bytesRead < bytesToRead) {
                            int ret = inputStream.read(read_buffer, bytesRead, bytesToRead - bytesRead);
                            if (ret <= 0) { break; }
                            bytesRead += ret;
                        }

                        StringBuilder hexBuilder = new StringBuilder();
                        for (byte b : read_buffer) {
                            hexBuilder.append(String.format("%02X ", b));
                        }
                        activity.logMessage(LogType.INFO, hexBuilder.toString());

                        //activity.microcontrollerManager.sendBytes(bytes);

                    } catch (SocketTimeoutException e) {
                        // A timeout is expected, continue the loop to check the socket's state
                    }
                }
            } catch (IOException e) {
                activity.logMessage(LogType.ERROR, "Control socket error: " + e.getMessage());
            } finally {
                scheduleControlReconnect();
            }
        });
    }

    private void scheduleVideoStreamReconnect() {
        if (!videoStreamReconnecting.compareAndSet(false, true)) return;
        reconnectExecutor.schedule(this::initializeVideoStreamSocket, RECONNECT_DELAY_MS, TimeUnit.MILLISECONDS);
    }

    private void scheduleAudioStreamReconnect() {
        if (!audioStreamReconnecting.compareAndSet(false, true)) return;
        reconnectExecutor.schedule(this::initializeAudioStreamSocket, RECONNECT_DELAY_MS, TimeUnit.MILLISECONDS);
    }

    private void scheduleTelemetryReconnect() {
        if (!telemetryReconnecting.compareAndSet(false, true)) return;
        activity.updateTelemetrySocketStatus(false);
        reconnectExecutor.schedule(this::initializeTelemetrySocket, RECONNECT_DELAY_MS, TimeUnit.MILLISECONDS);
    }

    private void scheduleControlReconnect() {
        if (!controlReconnecting.compareAndSet(false, true)) return;
        activity.updateControlSocketStatus(false);
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
                if (controlReader != null) controlReader.close();
                if (controlSocket != null) controlSocket.close();
                if (telemetryWriter != null) telemetryWriter.close();
                if (telemetrySocket != null) telemetrySocket.close();
                if (videoStreamSocket != null) videoStreamSocket.close();
                if (audioStreamSocket != null) audioStreamSocket.close();
            } catch (IOException e) {
                activity.logMessage(LogType.ERROR, "Error destroying sockets: " + e.getMessage());
            }
        });

        if (!executorService.isShutdown()) {
            executorService.shutdown();
        }
        activity.updateControlSocketStatus(false);
        activity.updateTelemetrySocketStatus(false);
    }

    void sendVideoStream(byte[] data) {
        if (videoStreamSocket == null || videoStreamSocket.isClosed() || videoStreamAddress == null) {
            if (!videoStreamReconnecting.get()) {
                scheduleVideoStreamReconnect();
            }
            return;
        }

        if (data == null || data.length == 0) {
            return;
        }

        executorService.execute(() -> {
            try {
                DatagramPacket packet = new DatagramPacket(data, data.length, videoStreamAddress);
                videoStreamSocket.send(packet);
            } catch (IOException e) {
                activity.logMessage(LogType.ERROR, "Failed to send video stream data: " + e.getMessage());
                scheduleVideoStreamReconnect();
            }
        });
    }

    void sendAudioStream(byte[] data) {
        if (audioStreamSocket == null || audioStreamSocket.isClosed() || audioStreamAddress == null) {
            if (!audioStreamReconnecting.get()) {
                scheduleAudioStreamReconnect();
            }
            return;
        }

        if (data == null || data.length == 0) {
            return;
        }

        executorService.execute(() -> {
            try {
                DatagramPacket packet = new DatagramPacket(data, data.length, audioStreamAddress);
                audioStreamSocket.send(packet);
            } catch (IOException e) {
                activity.logMessage(LogType.ERROR, "Failed to send audio stream data: " + e.getMessage());
                scheduleAudioStreamReconnect();
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
                if (telemetryWriter.checkError()) throw new IOException("telemetryWriter check error");
                activity.logMessage(LogType.INFO, "[TELEMETRY]: " + telemetryData);
            } catch (Exception e) {
                activity.logMessage(LogType.ERROR, "Failed to send telemetry data: " + e.getMessage());
                scheduleTelemetryReconnect();
            }
        });
    }

}
