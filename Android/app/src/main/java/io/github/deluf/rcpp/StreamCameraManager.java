package io.github.deluf.rcpp;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.graphics.ImageFormat;
import android.graphics.Rect;
import android.graphics.YuvImage;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CaptureRequest;
import android.hardware.camera2.params.StreamConfigurationMap;
import android.media.Image;
import android.media.ImageReader;
import android.os.Handler;
import android.os.HandlerThread;

import androidx.core.app.ActivityCompat;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

import io.github.deluf.rcpp.MainActivity.LogType;

public class StreamCameraManager {
    private static final int STREAM_WIDTH = 640;
    private static final int STREAM_HEIGHT = 480;
    private static final int JPEG_QUALITY = 60;
    private static final int CAMERA_PERMISSION_REQUEST = 200;
    private static final int MAX_PACKET_SIZE = 32768; // 32KB max packet size

    private final MainActivity activity;
    private final SocketManager socketManager;
    private final android.hardware.camera2.CameraManager cameraManager;

    private String cameraId;
    private CameraDevice cameraDevice;
    private CameraCaptureSession captureSession;
    private ImageReader imageReader;

    private HandlerThread backgroundThread;
    private Handler backgroundHandler;
    private final Semaphore cameraOpenCloseLock = new Semaphore(1);

    private boolean isStreaming = false;
    private int frameCount = 0;
    private long lastFrameTime = System.currentTimeMillis();

    public StreamCameraManager(MainActivity activity, SocketManager socketManager) {
        this.activity = activity;
        this.socketManager = socketManager;
        this.cameraManager = (android.hardware.camera2.CameraManager) activity.getSystemService(Context.CAMERA_SERVICE);
    }

    public void startStreaming() {
        if (!checkCameraPermission()) {
            requestCameraPermission();
            return;
        }

        startBackgroundThread();
        openCamera();
    }

    public void stopStreaming() {
        isStreaming = false;
        closeCamera();
        stopBackgroundThread();
        activity.logMessage(LogType.INFO, "Camera streaming stopped");
    }

    private boolean checkCameraPermission() {
        return ActivityCompat.checkSelfPermission(activity, Manifest.permission.CAMERA)
                == PackageManager.PERMISSION_GRANTED;
    }

    private void requestCameraPermission() {
        ActivityCompat.requestPermissions(activity,
                new String[]{Manifest.permission.CAMERA},
                CAMERA_PERMISSION_REQUEST);
    }

    private void openCamera() {
        try {
            if (!cameraOpenCloseLock.tryAcquire(2500, TimeUnit.MILLISECONDS)) {
                activity.logMessage(LogType.ERROR, "Camera opening timeout");
                return;
            }

            setUpCamera();

            if (ActivityCompat.checkSelfPermission(activity, Manifest.permission.CAMERA)
                    != PackageManager.PERMISSION_GRANTED) {
                activity.logMessage(LogType.ERROR, "Camera permission not granted");
                return;
            }

            cameraManager.openCamera(cameraId, stateCallback, backgroundHandler);

        } catch (Exception e) {
            activity.logMessage(LogType.ERROR, "Error opening camera: " + e.getMessage());
            cameraOpenCloseLock.release();
        }
    }

    private void setUpCamera() {
        try {
            for (String cameraId : cameraManager.getCameraIdList()) {
                CameraCharacteristics characteristics = cameraManager.getCameraCharacteristics(cameraId);

                // Use back camera
                Integer facing = characteristics.get(CameraCharacteristics.LENS_FACING);
                if (facing != null && facing == CameraCharacteristics.LENS_FACING_FRONT) {
                    continue;
                }

                StreamConfigurationMap map = characteristics.get(
                        CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
                if (map == null) continue;

                // Set up ImageReader with fixed resolution for streaming
                imageReader = ImageReader.newInstance(STREAM_WIDTH, STREAM_HEIGHT,
                        ImageFormat.YUV_420_888, 2);
                imageReader.setOnImageAvailableListener(onImageAvailableListener, backgroundHandler);

                this.cameraId = cameraId;
                return;
            }
        } catch (CameraAccessException e) {
            activity.logMessage(LogType.ERROR, "Camera access error: " + e.getMessage());
        }
    }

    private final CameraDevice.StateCallback stateCallback = new CameraDevice.StateCallback() {
        @Override
        public void onOpened(CameraDevice camera) {
            cameraOpenCloseLock.release();
            cameraDevice = camera;
            createCaptureSession();
        }

        @Override
        public void onDisconnected(CameraDevice camera) {
            cameraOpenCloseLock.release();
            camera.close();
            cameraDevice = null;
            activity.logMessage(LogType.WARNING, "Camera disconnected");
        }

        @Override
        public void onError(CameraDevice camera, int error) {
            cameraOpenCloseLock.release();
            camera.close();
            cameraDevice = null;
            activity.logMessage(LogType.ERROR, "Camera error: " + error);
        }
    };

    private void createCaptureSession() {
        try {
            CaptureRequest.Builder captureRequestBuilder =
                    cameraDevice.createCaptureRequest(CameraDevice.TEMPLATE_RECORD);
            captureRequestBuilder.addTarget(imageReader.getSurface());

            cameraDevice.createCaptureSession(Arrays.asList(imageReader.getSurface()),
                    new CameraCaptureSession.StateCallback() {
                        @Override
                        public void onConfigured(CameraCaptureSession session) {
                            if (cameraDevice == null) return;

                            captureSession = session;
                            try {
                                captureRequestBuilder.set(CaptureRequest.CONTROL_AF_MODE,
                                        CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_VIDEO);
                                CaptureRequest captureRequest = captureRequestBuilder.build();

                                captureSession.setRepeatingRequest(captureRequest, null, backgroundHandler);
                                isStreaming = true;
                                activity.logMessage(LogType.INFO, "Camera streaming started at " +
                                        STREAM_WIDTH + "x" + STREAM_HEIGHT);

                            } catch (CameraAccessException e) {
                                activity.logMessage(LogType.ERROR, "Error starting capture: " + e.getMessage());
                            }
                        }

                        @Override
                        public void onConfigureFailed(CameraCaptureSession session) {
                            activity.logMessage(LogType.ERROR, "Camera capture session configuration failed");
                        }
                    }, null);
        } catch (CameraAccessException e) {
            activity.logMessage(LogType.ERROR, "Error creating capture session: " + e.getMessage());
        }
    }

    private final ImageReader.OnImageAvailableListener onImageAvailableListener =
            new ImageReader.OnImageAvailableListener() {
                @Override
                public void onImageAvailable(ImageReader reader) {
                    if (!isStreaming) return;

                    Image image = reader.acquireLatestImage();
                    if (image == null) return;

                    try {
                        // Convert to JPEG for smaller size
                        byte[] jpegData = convertToJPEG(image);

                        if (jpegData != null && jpegData.length > 0) {
                            // Split large frames if needed
                            sendFrameData(jpegData);

                            // Log statistics
                            frameCount++;
                            long currentTime = System.currentTimeMillis();
                            if (currentTime - lastFrameTime >= 5000) {
                                double fps = frameCount / ((currentTime - lastFrameTime) / 1000.0);
                                activity.logMessage(LogType.INFO,
                                        String.format("Streaming: %.1f FPS, %d KB/frame",
                                                fps, jpegData.length / 1024));
                                frameCount = 0;
                                lastFrameTime = currentTime;
                            }
                        }
                    } catch (Exception e) {
                        activity.logMessage(LogType.ERROR, "Error processing frame: " + e.getMessage());
                    } finally {
                        image.close();
                    }
                }
            };

    private byte[] convertToJPEG(Image image) {
        try {
            Image.Plane[] planes = image.getPlanes();
            ByteBuffer yBuffer = planes[0].getBuffer();
            ByteBuffer uBuffer = planes[1].getBuffer();
            ByteBuffer vBuffer = planes[2].getBuffer();

            int ySize = yBuffer.remaining();
            int uSize = uBuffer.remaining();
            int vSize = vBuffer.remaining();

            byte[] nv21 = new byte[ySize + uSize + vSize];

            yBuffer.get(nv21, 0, ySize);

            // Convert UV to NV21 format
            int uvStride = planes[1].getRowStride();
            int uvPixelStride = planes[1].getPixelStride();

            if (uvPixelStride == 1) {
                uBuffer.get(nv21, ySize, uSize);
                vBuffer.get(nv21, ySize + uSize, vSize);
            } else {
                // Interleave U and V for NV21
                byte[] uvBuffer = new byte[uSize];
                uBuffer.get(uvBuffer);
                for (int i = 0; i < uSize; i += uvPixelStride) {
                    nv21[ySize + i] = uvBuffer[i];
                }

                vBuffer.get(uvBuffer);
                for (int i = 0; i < vSize; i += uvPixelStride) {
                    nv21[ySize + i + 1] = uvBuffer[i];
                }
            }

            YuvImage yuvImage = new YuvImage(nv21, ImageFormat.NV21, STREAM_WIDTH, STREAM_HEIGHT, null);
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            yuvImage.compressToJpeg(new Rect(0, 0, STREAM_WIDTH, STREAM_HEIGHT), JPEG_QUALITY, out);
            return out.toByteArray();

        } catch (Exception e) {
            activity.logMessage(LogType.ERROR, "JPEG conversion error: " + e.getMessage());
            return null;
        }
    }

    private void sendFrameData(byte[] data) {
        if (data.length <= MAX_PACKET_SIZE) {
            // Send as single packet
            socketManager.sendStream(data);
        } else {
            // Split into smaller packets
            int offset = 0;
            int packetIndex = 0;

            while (offset < data.length) {
                int packetSize = Math.min(MAX_PACKET_SIZE - 8, data.length - offset); // Reserve 8 bytes for header
                byte[] packet = new byte[packetSize + 8];

                // Add simple packet header: [frame_id(4)][packet_index(2)][total_packets(2)][data...]
                int frameId = frameCount;
                int totalPackets = (data.length + MAX_PACKET_SIZE - 9) / (MAX_PACKET_SIZE - 8);

                packet[0] = (byte)(frameId & 0xFF);
                packet[1] = (byte)((frameId >> 8) & 0xFF);
                packet[2] = (byte)((frameId >> 16) & 0xFF);
                packet[3] = (byte)((frameId >> 24) & 0xFF);
                packet[4] = (byte)(packetIndex & 0xFF);
                packet[5] = (byte)((packetIndex >> 8) & 0xFF);
                packet[6] = (byte)(totalPackets & 0xFF);
                packet[7] = (byte)((totalPackets >> 8) & 0xFF);

                System.arraycopy(data, offset, packet, 8, packetSize);
                socketManager.sendStream(packet);

                offset += packetSize;
                packetIndex++;
            }
        }
    }

    private void closeCamera() {
        try {
            cameraOpenCloseLock.acquire();

            if (captureSession != null) {
                captureSession.close();
                captureSession = null;
            }

            if (cameraDevice != null) {
                cameraDevice.close();
                cameraDevice = null;
            }

            if (imageReader != null) {
                imageReader.close();
                imageReader = null;
            }

        } catch (InterruptedException e) {
            activity.logMessage(LogType.ERROR, "Interrupted while closing camera: " + e.getMessage());
        } finally {
            cameraOpenCloseLock.release();
        }
    }

    private void startBackgroundThread() {
        backgroundThread = new HandlerThread("CameraBackground");
        backgroundThread.start();
        backgroundHandler = new Handler(backgroundThread.getLooper());
    }

    private void stopBackgroundThread() {
        if (backgroundThread != null) {
            backgroundThread.quitSafely();
            try {
                backgroundThread.join();
                backgroundThread = null;
                backgroundHandler = null;
            } catch (InterruptedException e) {
                activity.logMessage(LogType.ERROR, "Error stopping camera thread: " + e.getMessage());
            }
        }
    }

    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        if (requestCode == CAMERA_PERMISSION_REQUEST) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                startStreaming();
            } else {
                activity.logMessage(LogType.ERROR, "Camera permission denied");
                activity.showToast("Camera permission required for streaming");
            }
        }
    }

    public void destroy() {
        stopStreaming();
    }
}