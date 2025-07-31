package io.github.deluf.rcpp;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CaptureRequest;
import android.hardware.camera2.params.StreamConfigurationMap;
import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaFormat;
import android.os.Handler;
import android.os.HandlerThread;
import android.util.Size;
import android.view.Surface;

import androidx.annotation.NonNull;
import androidx.core.app.ActivityCompat;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

import io.github.deluf.rcpp.MainActivity.LogType;

public class StreamCameraManager {
    private static final int STREAM_WIDTH = 640;
    private static final int STREAM_HEIGHT = 480;
    private static final int STREAM_BITRATE = 1_000_000;
    private static final int STREAM_FRAMERATE = 30;
    private static final int I_FRAME_INTERVAL = 2; // seconds
    private static final String MIME_TYPE = MediaFormat.MIMETYPE_VIDEO_AVC; // H.264
    private static final int CAMERA_PERMISSION_REQUEST_CODE = 999;
    // This integer is used to identify the camera permission request when the result
    //  comes back in onRequestPermissionsResult. It can be any unique integer.
    // This is required because "camera" is considered by Android as a "dangerous" permission,
    //  i.e., a permission that must be granted at run-time by the user
    private final MainActivity activity;
    // Needed for Context (e.g., to get system services, request permissions),
    //  and for UI interactions (logging messages, showing toasts)
    private final SocketManager socketManager;
    // My custom socket manager class
    private final CameraManager cameraManager;
    // This is the entry point to the Camera2 API, used to discover, open, and manage camera devices
    private String cameraId;
    // The ID of the selected camera device
    private CameraDevice cameraDevice;
    // Represents the actual camera hardware
    private CameraCaptureSession captureSession;
    // Basically controls the camera (when and how to capture photos)
    private MediaCodec encoder;
    // Hardware H.264 encoder
    private Surface encoderSurface;
    // Surface for the encoder input
    private HandlerThread backgroundThread; // Defines the actual background thread
    private Handler backgroundHandler; // Communicates with the background thread
    // Camera operations (opening, capturing, processing) can be blocking and time-consuming.
    // Performing them on the main UI thread would lead to Application Not Responding (ANR)
    //  errors and a poor user experience.
    private final Semaphore cameraResourceLock = new Semaphore(1); //FIXME: Really needed?
    private boolean isStreaming = false;
    private int frameCount = 0; // Counter for frames processed
    private long lastFrameTime = System.currentTimeMillis(); // Timestamp of the last frame processed

    public StreamCameraManager(MainActivity activity, SocketManager socketManager) {
        this.activity = activity;
        this.socketManager = socketManager;
        this.cameraManager = (CameraManager) activity.getSystemService(Context.CAMERA_SERVICE);
    }

    public void startStreaming() {
        if (!checkCameraPermission()) {
            requestCameraPermission();
            return; // Wait for the user's response
        }
        startBackgroundThread();
        setupEncoder();
        openCamera();
    }

    private boolean checkCameraPermission() {
        return ActivityCompat.checkSelfPermission(activity, Manifest.permission.CAMERA)
                == PackageManager.PERMISSION_GRANTED;
    }

    private void requestCameraPermission() {
        ActivityCompat.requestPermissions(activity,
                new String[]{Manifest.permission.CAMERA},
                CAMERA_PERMISSION_REQUEST_CODE);
    }

    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        if (requestCode == CAMERA_PERMISSION_REQUEST_CODE) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                startStreaming();
            } else {
                activity.showToast("Camera permission is required for streaming");
            }
        }
    }

    private void startBackgroundThread() {
        backgroundThread = new HandlerThread("StreamCameraManager");
        backgroundThread.start();
        backgroundHandler = new Handler(backgroundThread.getLooper());
    }

    private void setupEncoder() {
        try {
            encoder = MediaCodec.createEncoderByType(MIME_TYPE);

            MediaFormat format = MediaFormat.createVideoFormat(MIME_TYPE, STREAM_WIDTH, STREAM_HEIGHT);
            format.setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface);
            format.setInteger(MediaFormat.KEY_BITRATE_MODE, MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_CBR);
            format.setInteger(MediaFormat.KEY_BIT_RATE, STREAM_BITRATE);
            format.setInteger(MediaFormat.KEY_FRAME_RATE, STREAM_FRAMERATE);
            format.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, I_FRAME_INTERVAL);
            format.setInteger(MediaFormat.KEY_PROFILE, MediaCodecInfo.CodecProfileLevel.AVCProfileBaseline);
            format.setInteger(MediaFormat.KEY_LEVEL, MediaCodecInfo.CodecProfileLevel.AVCLevel3);

            encoder.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
            encoderSurface = encoder.createInputSurface();

            encoder.setCallback(new MediaCodec.Callback() {
                @Override
                public void onInputBufferAvailable(@NonNull MediaCodec codec, int index) {
                    // Not used for Surface input
                }

                @Override
                public void onOutputBufferAvailable(@NonNull MediaCodec codec, int index, @NonNull MediaCodec.BufferInfo info) {
                    if (!isStreaming) return;

                    try {
                        ByteBuffer outputBuffer = codec.getOutputBuffer(index);
                        if (outputBuffer != null && info.size > 0) {
                            byte[] data = new byte[info.size];
                            outputBuffer.position(info.offset);
                            outputBuffer.get(data, 0, info.size);

                            // Send H.264 data directly
                            socketManager.sendStream(data);

                            // Statistics
                            frameCount++;
                            long currentTime = System.currentTimeMillis();
                            if (currentTime - lastFrameTime >= 5000) { // Log every 5 seconds
                                double fps = frameCount / ((currentTime - lastFrameTime) / 1000.0);
                                activity.logMessage(LogType.INFO,
                                        String.format("H.264 Streaming: %.1f FPS, %d bytes/frame",
                                                fps, info.size));
                                frameCount = 0;
                                lastFrameTime = currentTime;
                            }
                        }
                        codec.releaseOutputBuffer(index, false);
                    } catch (Exception e) {
                        activity.logMessage(LogType.ERROR, "Error processing H.264 output: " + e.getMessage());
                    }
                }

                @Override
                public void onError(@NonNull MediaCodec codec, @NonNull MediaCodec.CodecException e) {
                    activity.logMessage(LogType.ERROR, "H.264 encoder error: " + e.getMessage());
                }

                @Override
                public void onOutputFormatChanged(@NonNull MediaCodec codec, @NonNull MediaFormat format) {
                    // Could log format changes if needed
                }
            }, backgroundHandler);

            encoder.start();
            activity.logMessage(LogType.INFO, "H.264 encoder initialized");

        } catch (IOException e) {
            activity.logMessage(LogType.ERROR, "Failed to setup H.264 encoder: " + e.getMessage());
        }
    }

    private void openCamera() {
        try {
            int unlockTimeout = 2500;
            if (!cameraResourceLock.tryAcquire(unlockTimeout, TimeUnit.MILLISECONDS)) {
                activity.logMessage(LogType.WARNING, "Failed to open the camera: another thread is using it");
                return;
            }
            setUpCamera();

            if (ActivityCompat.checkSelfPermission(activity, Manifest.permission.CAMERA) // Double check, belt and braces
                    != PackageManager.PERMISSION_GRANTED) {
                // This check is mostly defensive. If startStreaming() was called, permission should have been granted
                // or requested. However, there could be edge cases or race conditions.
                activity.logMessage(LogType.ERROR, "Camera permission not granted");
                cameraResourceLock.release(); // Essential to release the lock if we're bailing out.
                return;
            }
            // WHY backgroundHandler for openCamera: Some camera drivers or underlying system
            // calls might block. Performing this on the background thread keeps the UI responsive.
            // The CameraDevice.StateCallback will also be invoked on this handler's thread.
            cameraManager.openCamera(cameraId, stateCallback, backgroundHandler);
        } catch (Exception e) { // Catching generic Exception is broad, but CameraAccessException and SecurityException are common here.
            activity.logMessage(LogType.ERROR, "Error opening camera: " + e.getMessage());
            cameraResourceLock.release(); // Crucial: always release the lock in case of an error.
        }
    }

    private void setUpCamera() {
        try {
            for (String cameraId : cameraManager.getCameraIdList()) {
                CameraCharacteristics characteristics = cameraManager.getCameraCharacteristics(cameraId);

                // Ignore the front camera (for now)
                Integer facing = characteristics.get(CameraCharacteristics.LENS_FACING);
                if (facing != null && facing == CameraCharacteristics.LENS_FACING_FRONT) {
                    continue;
                }

                StreamConfigurationMap map = characteristics.get(
                        CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
                if (map == null) continue;

                // Verify that our target resolution is supported
                Size[] outputSizes = map.getOutputSizes(MediaFormat.class);
                boolean sizeSupported = false;
                if (outputSizes != null) {
                    for (Size size : outputSizes) {
                        if (size.getWidth() == STREAM_WIDTH && size.getHeight() == STREAM_HEIGHT) {
                            sizeSupported = true;
                            break;
                        }
                    }
                }

                if (!sizeSupported) {
                    activity.logMessage(LogType.WARNING,
                            "Camera doesn't support " + STREAM_WIDTH + "x" + STREAM_HEIGHT + ", using anyway");
                }

                this.cameraId = cameraId;
                return; // Found and configured a suitable camera.
            }
        } catch (CameraAccessException e) {
            activity.logMessage(LogType.ERROR, "Camera access error: " + e.getMessage());
        }
    }

    public void stopStreaming() {
        isStreaming = false; // Important to set this first to stop processing more frames
        closeCamera();
        closeEncoder();
        stopBackgroundThread();
        activity.logMessage(LogType.INFO, "H.264 camera streaming stopped");
    }

    private final CameraDevice.StateCallback stateCallback = new CameraDevice.StateCallback() {
        // WHY this callback: It's essential for managing the lifecycle of the CameraDevice.
        // It informs about successful opening, disconnections, or errors.
        @Override
        public void onOpened(@NonNull CameraDevice camera) {
            cameraResourceLock.release(); // Camera is open, critical section finished.
            cameraDevice = camera;
            createCaptureSession(); // Next step after opening the camera.
        }

        @Override
        public void onDisconnected(CameraDevice camera) {
            cameraResourceLock.release();
            camera.close(); // Important to close the camera resource.
            cameraDevice = null;
            // WHY: The camera might get disconnected if another higher-priority app needs it,
            // or due to hardware issues. The app should handle this gracefully.
            activity.logMessage(LogType.WARNING, "Camera disconnected");
        }

        @Override
        public void onError(CameraDevice camera, int error) {
            cameraResourceLock.release();
            camera.close();
            cameraDevice = null;
            activity.logMessage(LogType.ERROR, "Camera error: " + error);
            // WHY: Various errors can occur (e.g., camera in use, hardware malfunction).
            // The error code provides more specific information.
        }
    };

    private void createCaptureSession() {
        try {
            // WHY TEMPLATE_RECORD: This template provides a standard configuration suitable for
            // video recording or continuous frame capture. It prioritizes smooth frame rates.
            // Alternatives: TEMPLATE_PREVIEW (for viewfinder display), TEMPLATE_STILL_CAPTURE (for photos).
            CaptureRequest.Builder captureRequestBuilder =
                    cameraDevice.createCaptureRequest(CameraDevice.TEMPLATE_RECORD);
            // Connect camera output directly to encoder input surface
            captureRequestBuilder.addTarget(encoderSurface);

            // WHY createCaptureSession: This is the mechanism to submit requests for capturing images.
            // We provide a list of output Surfaces (the encoder's input surface).
            // The StateCallback informs us when the session is ready or if configuration failed.
            cameraDevice.createCaptureSession(Arrays.asList(encoderSurface),
                    new CameraCaptureSession.StateCallback() {
                        @Override
                        public void onConfigured(CameraCaptureSession session) {
                            if (cameraDevice == null) return; // Camera might have been closed concurrently.

                            captureSession = session;
                            try {
                                // WHY CONTROL_AF_MODE_CONTINUOUS_VIDEO: For streaming, we generally want
                                // the camera to continuously adjust focus as the scene changes.
                                // Alternatives: CONTROL_AF_MODE_AUTO (focus once), CONTROL_AF_MODE_OFF (manual focus).
                                captureRequestBuilder.set(CaptureRequest.CONTROL_AF_MODE,
                                        CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_VIDEO);
                                // Other settings like AE (Auto Exposure) mode could also be set here.
                                CaptureRequest captureRequest = captureRequestBuilder.build();

                                // WHY setRepeatingRequest: This tells the capture session to continuously
                                // capture frames using the settings in `captureRequest`. This is what creates
                                // the video stream.
                                // The CaptureCallback (null here) could be used to get metadata about each captured frame.
                                // backgroundHandler: Ensures these requests are processed off the main thread.
                                captureSession.setRepeatingRequest(captureRequest, null, backgroundHandler);
                                isStreaming = true;
                                activity.logMessage(LogType.INFO, "H.264 camera streaming started at " +
                                        STREAM_WIDTH + "x" + STREAM_HEIGHT + " @ " + STREAM_FRAMERATE + "fps");
                            } catch (CameraAccessException e) {
                                activity.logMessage(LogType.ERROR, "Error starting capture: " + e.getMessage());
                            }
                        }

                        @Override
                        public void onConfigureFailed(CameraCaptureSession session) {
                            activity.logMessage(LogType.ERROR, "Camera capture session configuration failed");
                        }
                    }, null); // null handler for StateCallback: invokes on the backgroundHandler's thread.
        } catch (CameraAccessException e) {
            activity.logMessage(LogType.ERROR, "Error creating capture session: " + e.getMessage());
        }
    }

    private void closeCamera() {
        try {
            cameraResourceLock.acquire(); // Ensure exclusive access for closing.
            // WHY close in this order: Generally, stop the session, then close the device,
            // then release the Surface. This unwinds the setup order.
            if (captureSession != null) {
                captureSession.close();
                captureSession = null;
            }
            if (cameraDevice != null) {
                cameraDevice.close();
                cameraDevice = null;
            }
        } catch (InterruptedException e) {
            activity.logMessage(LogType.ERROR, "Interrupted while closing camera: " + e.getMessage());
            Thread.currentThread().interrupt(); // Preserve interrupt status.
        } finally {
            cameraResourceLock.release(); // CRITICAL: Always release the lock.
        }
    }

    private void closeEncoder() {
        if (encoderSurface != null) {
            encoderSurface.release();
            encoderSurface = null;
        }
        if (encoder != null) {
            try {
                encoder.stop();
                encoder.release();
            } catch (Exception e) {
                activity.logMessage(LogType.ERROR, "Error stopping encoder: " + e.getMessage());
            }
            encoder = null;
        }
    }

    private void stopBackgroundThread() {
        if (backgroundThread != null) {
            // WHY quitSafely(): Allows the Looper to process messages already in its queue
            // before quitting. quit() would discard them.
            backgroundThread.quitSafely();
            try {
                // WHY join(): Waits for the thread to actually terminate. This is important
                // to ensure resources are cleaned up before proceeding (e.g., if the app is exiting).
                backgroundThread.join();
                backgroundThread = null;
                backgroundHandler = null;
            } catch (InterruptedException e) {
                activity.logMessage(LogType.ERROR, "Error stopping camera thread: " + e.getMessage());
                Thread.currentThread().interrupt();
            }
        }
    }

    public void destroy() {
        // WHY: This method should be called when the component managing this (e.g., Activity or Fragment)
        // is being destroyed, to ensure all resources are released and background tasks are stopped.
        stopStreaming();
    }
}