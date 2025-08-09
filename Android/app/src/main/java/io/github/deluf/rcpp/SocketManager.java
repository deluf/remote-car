
package io.github.deluf.rcpp;

import java.io.IOException;
import java.io.InputStream;
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
    private static final int CONTROL_PORT = 8003;
    private static final int RECONNECT_DELAY_MS = 3000;
    private static final int SOCKET_READ_TIMEOUT_MS = 1000;

    public enum Command {
        MARCH,
        STEER,
        SWITCH_CAMERA
    }

    private final MainActivity mainActivity;
    private final String controllerIP;

    private volatile DatagramSocket videoStreamSocket;
    private volatile DatagramSocket audioStreamSocket;
    private volatile InetSocketAddress videoStreamAddress;
    private volatile InetSocketAddress audioStreamAddress;

    private volatile Socket controlSocket;

    private final ExecutorService executorService;
    private final ScheduledExecutorService reconnectExecutor;

    private final AtomicBoolean videoStreamReconnecting = new AtomicBoolean(false);
    private final AtomicBoolean audioStreamReconnecting = new AtomicBoolean(false);
    private final AtomicBoolean controlReconnecting = new AtomicBoolean(false);
    private final AtomicBoolean isControlListening = new AtomicBoolean(false);

    public SocketManager(MainActivity mainActivity, String controllerIP) {
        this.mainActivity = mainActivity;
        this.controllerIP = controllerIP;
        this.executorService = Executors.newCachedThreadPool();
        this.reconnectExecutor = Executors.newScheduledThreadPool(4);
        initializeSockets();
    }

    void initializeSockets() {
        executorService.execute(() -> {
            initializeVideoStreamSocket();
            initializeAudioStreamSocket();
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
            mainActivity.logMessage(LogType.ERROR, "Video stream socket error: " + e.getMessage());
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
            mainActivity.logMessage(LogType.ERROR, "Audio stream socket error: " + e.getMessage());
            audioStreamReconnecting.set(false);
            scheduleAudioStreamReconnect();
        }
    }

    private void initializeControlSocket() {
        try {
            InetAddress address = InetAddress.getByName(controllerIP);
            controlSocket = new Socket(address, CONTROL_PORT);
            controlSocket.setSoTimeout(SOCKET_READ_TIMEOUT_MS);
            startControlListener(controlSocket.getInputStream());
            mainActivity.updateControlSocketStatus(true);
            controlReconnecting.set(false);
        } catch (IOException e) {
            // If the error is one of the "expected" ones, just update the ui - done in scheduleControlReconnect
            if (isUnknownSocketError(e)) {
                mainActivity.logMessage(LogType.ERROR, "Unknown control socket error: " + e.getMessage());
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

            int maxCommandLen = 3;
            byte[] readBuffer = new byte[maxCommandLen]; // Only allocate it once for all the commands
            while (isControlListening.get()) {
                try { recvCommand(inputStream, readBuffer); }
                catch (SocketTimeoutException ignored) { }
                catch (IOException e) {
                    mainActivity.logMessage(LogType.ERROR, "Control socket error: " + e.getMessage());
                    break;
                }
            }

            scheduleControlReconnect();
        });
    }

    private void recvCommand(InputStream inputStream, byte[] readBuffer) throws IOException {
        int ret;
        ret = inputStream.read(readBuffer, 0, 1);
        if (ret <= 0) { throw new IOException("Connection closed"); }

        if (readBuffer[0] >= Command.values().length) {
            throw new IllegalArgumentException("Invalid command");
        }
        Command command = Command.values()[readBuffer[0]];

        if (command == Command.MARCH || command == Command.STEER) {
            // Read two more bytes: direction and speed
            int bytesRead = 1;
            while (bytesRead < 3) {
                ret = inputStream.read(readBuffer, bytesRead, 3 - bytesRead);
                if (ret <= 0) { throw new IOException("Connection closed"); }
                bytesRead += ret;
            }
            mainActivity.microcontrollerManager.sendBytes(readBuffer);
        }
        else if (command == Command.SWITCH_CAMERA) {
            mainActivity.switchCamera();
        }
    }

    private void scheduleVideoStreamReconnect() {
        if (!videoStreamReconnecting.compareAndSet(false, true)) return;
        reconnectExecutor.schedule(this::initializeVideoStreamSocket, RECONNECT_DELAY_MS, TimeUnit.MILLISECONDS);
    }

    private void scheduleAudioStreamReconnect() {
        if (!audioStreamReconnecting.compareAndSet(false, true)) return;
        reconnectExecutor.schedule(this::initializeAudioStreamSocket, RECONNECT_DELAY_MS, TimeUnit.MILLISECONDS);
    }

    private void scheduleControlReconnect() {
        if (!controlReconnecting.compareAndSet(false, true)) return;
        mainActivity.updateControlSocketStatus(false);
        isControlListening.set(false);
        reconnectExecutor.schedule(this::initializeControlSocket, RECONNECT_DELAY_MS, TimeUnit.MILLISECONDS);
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
            }
            catch (IOException e) { scheduleVideoStreamReconnect(); }
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
            }
            catch (IOException e) { scheduleAudioStreamReconnect(); }
        });
    }

    public void sendTelemetryData(byte[] telemetryData) {
        if (controlSocket == null || !controlSocket.isConnected()) {
            if (!controlReconnecting.get()) {
                scheduleControlReconnect();
            }
            return;
        }

        executorService.execute(() -> {
            try {
                controlSocket.getOutputStream().write(telemetryData, 0, telemetryData.length);
            }
            catch (IOException e) { scheduleControlReconnect(); }
        });
    }

    public void destroy() {
        if (!reconnectExecutor.isShutdown()) {
            reconnectExecutor.shutdownNow();
        }
        isControlListening.set(false);
        executorService.execute(() -> {
            try {
                if (controlSocket != null) controlSocket.close();
                if (videoStreamSocket != null) videoStreamSocket.close();
                if (audioStreamSocket != null) audioStreamSocket.close();
            } catch (IOException e) {
                mainActivity.logMessage(LogType.ERROR, "Error destroying sockets: " + e.getMessage());
            }
        });

        if (!executorService.isShutdown()) {
            executorService.shutdown();
        }
        mainActivity.updateControlSocketStatus(false);
    }
}
