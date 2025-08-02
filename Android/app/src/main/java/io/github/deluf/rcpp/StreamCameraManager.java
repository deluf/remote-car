package io.github.deluf.rcpp;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.graphics.SurfaceTexture;
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
import java.util.Collections;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

import io.github.deluf.rcpp.MainActivity.LogType;

public class StreamCameraManager {
    /**
     * Architecture overview
     * =====================
     * Camera Pipeline:
     *  Device Camera -> Camera2 API -> Surface -> MediaCodec H.264 Encoder -> Raw H.264 -> UDP Stream
     * Audio Pipeline: FIXME: magari in un file a parte
     *  Device Microphone -> AudioRecord -> MediaCodec AAC Encoder -> Raw AAC -> UDP Stream
     *
     *  fixme: uniformare l'uso di public in giro, dai usarlo sempre
     *  crasha quando si connette adruino? lol
     */
    private static final int STREAM_WIDTH = 320;
    private static final int STREAM_HEIGHT = 240;
    private static final int STREAM_BITRATE = 500_000;
    private static final int STREAM_FRAMERATE = 30;
    private static final int I_FRAME_INTERVAL_S = 2;
    // I_FRAMES are full frames that don't depend on previous frames to be decoded.
    // - Lower values (e.g., 1 second) mean faster recovery but worse compression
    // - Higher values (e.g., 5 seconds) mean better compression but slower recovery
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
    private CameraDevice cameraDevice;
    // Represents the actual camera hardware
    private CameraCaptureSession captureSession;
    // Basically controls the camera (when and how to capture photos)
    private MediaCodec encoder;
    // Hardware H.264 encoder
    private Surface encoderSurface;
    // Where the camera writes the captured frames, prior to encoding
    private HandlerThread backgroundThread; // Defines the actual background thread
    private Handler backgroundHandler; // Communicates with the background thread
    // Camera operations (opening, capturing, processing) can be blocking and time-consuming.
    // Performing them on the main UI thread would lead to Application Not Responding (ANR)
    //  errors and a poor user experience.
    private final Semaphore cameraResourceLock = new Semaphore(1); //FIXME: Really needed?
    private boolean isStreaming = false; // FIXME: really needed?

    public StreamCameraManager(MainActivity activity, SocketManager socketManager) {
        this.activity = activity;
        this.socketManager = socketManager;
        this.cameraManager = (CameraManager) activity.getSystemService(Context.CAMERA_SERVICE);
    }

    public void startStreaming() {
        startBackgroundThread();
        setupEncoder();
        openCamera();
    }

    private void startBackgroundThread() {
        backgroundThread = new HandlerThread("videoStreamer");
        backgroundThread.start();
        backgroundHandler = new Handler(backgroundThread.getLooper());
    }

    private void setupEncoder() {
        try {
            encoder = MediaCodec.createEncoderByType(MIME_TYPE);
            MediaFormat format = MediaFormat.createVideoFormat(MIME_TYPE, STREAM_WIDTH, STREAM_HEIGHT);

            // COLOR_FormatSurface tells the MediaCodec that it will receive input data
            //  directly from a Surface. This is a more efficient way for the camera to provide
            //  frames to the encoder, often leveraging hardware optimizations, as opposed to
            //  providing raw ByteBuffer data
            format.setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface);

            // Sets the bitrate control mode:
            // - BITRATE_MODE_CBR (Constant Bit Rate) attempts to maintain a steady bitrate, which can
            //  be useful for streaming over networks with predictable bandwidth.
            // - BITRATE_MODE_VBR (Variable Bit Rate) adjusts bitrate based on scene complexity,
            //    potentially offering better quality for the same average bitrate, but can have peaks.
            format.setInteger(MediaFormat.KEY_BITRATE_MODE, MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_CBR);
            // FIXME: provare entrambi

            format.setInteger(MediaFormat.KEY_BIT_RATE, STREAM_BITRATE);
            format.setInteger(MediaFormat.KEY_FRAME_RATE, STREAM_FRAMERATE);
            format.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, I_FRAME_INTERVAL_S);
            //format.setInteger(MediaFormat.KEY_ROTATION, 270); // Fixme: this has no effect??'

            // Parameters of the H.264 encoder:
            // - AVCProfileBaseline provides fast processing times (but no the maximum compression)
            // - AVCLevel3 is a common choice for SD streams (i.e., around 480p)
            format.setInteger(MediaFormat.KEY_PROFILE, MediaCodecInfo.CodecProfileLevel.AVCProfileBaseline);
            format.setInteger(MediaFormat.KEY_LEVEL, MediaCodecInfo.CodecProfileLevel.AVCLevel3);

            // Apply the configuration
            encoder.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);

            // The camera will later be configured to draw its preview frames directly onto this surface
            encoderSurface = encoder.createInputSurface();

            // Assigns the callbacks to the background thread
            encoder.setCallback(encoderCallback, backgroundHandler);

            encoder.start(); // The encoder now waits for the frames to arrive
            activity.logMessage(LogType.INFO, "H.264 encoder initialized");
        } catch (IOException e) {
            activity.logMessage(LogType.ERROR, "Failed to initialize H.264 encoder: " + e.getMessage());
        }
    }

    private final MediaCodec.Callback encoderCallback = new MediaCodec.Callback() {
        @Override
        public void onInputBufferAvailable(@NonNull MediaCodec codec, int index) {
            // This callback is not required since the camera writes directly to the input buffer
        }
        @Override
        public void onOutputBufferAvailable(@NonNull MediaCodec codec, int index, @NonNull MediaCodec.BufferInfo info) {
            // Called when the MediaCodec has finished encoding a chunk of data (i.e., one
            //  or more frames) and that encoded data is ready in an output buffer.
            if (!isStreaming) return; // Don't process if we've been told to stop
            try {
                ByteBuffer outputBuffer = codec.getOutputBuffer(index);
                if (outputBuffer != null && info.size > 0) {
                    // The outputBuffer might contain more data than just the encoded frame.
                    // info.offset and info.size tell us where the actual encoded data is within the buffer
                    byte[] data = new byte[info.size];
                    outputBuffer.position(info.offset);
                    outputBuffer.get(data, 0, info.size);
                    socketManager.sendVideoStream(data);
                }
                // Tell the encoder that you're done with the output buffer.
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
            // This callback is invoked if the output format of the encoder changes during operation.
            activity.logMessage(LogType.WARNING, "H.264 encoder output format changed: " + format);
        }
    };

    private void openCamera() {
        try {
            int unlockTimeout = 5000;
            if (!cameraResourceLock.tryAcquire(unlockTimeout, TimeUnit.MILLISECONDS)) {
                activity.logMessage(LogType.ERROR, "Failed to open the camera: another thread is using it");
                return; // FIXME: maybe stopStreaming() or openCamera()
            }

            // Checks for camera permission
            if (ActivityCompat.checkSelfPermission(activity, Manifest.permission.CAMERA)
                    != PackageManager.PERMISSION_GRANTED) {
                // Requests the permission if not granted
                ActivityCompat.requestPermissions(activity, new String[]{Manifest.permission.CAMERA},
                        CAMERA_PERMISSION_REQUEST_CODE);
                cameraResourceLock.release();
                return; // Wait for the user's response
            }

            String cameraId = setUpCamera();
            //FIXME: again to the same backgroundHandler? it's also doing h264 callbacks
            cameraManager.openCamera(cameraId, cameraCallback, backgroundHandler);
        } catch (Exception e) {
            cameraResourceLock.release();
            activity.logMessage(LogType.ERROR, "Error opening camera: " + e.getMessage());
        }
    }

    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        if (requestCode == CAMERA_PERMISSION_REQUEST_CODE) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                openCamera();
            } else {
                activity.showToast("Camera permission is required for streaming");
            }
        }
    }

    private String setUpCamera() throws Exception {
        for (String cameraId : cameraManager.getCameraIdList()) {
            CameraCharacteristics characteristics = cameraManager.getCameraCharacteristics(cameraId);

            Integer facing = characteristics.get(CameraCharacteristics.LENS_FACING);
            if (facing != null && facing == CameraCharacteristics.LENS_FACING_FRONT) {
                continue;
            }

            // Determine what output resolutions and formats the camera supports.
            StreamConfigurationMap map = characteristics.get(
                    CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
            if (map == null) {
                // Should not happen for a functioning camera
                continue;
            }

            Size[] outputSizes = map.getOutputSizes(SurfaceTexture.class);
            boolean sizeSupported = false;
            for (Size size : outputSizes) {
                if (size.getWidth() == STREAM_WIDTH && size.getHeight() == STREAM_HEIGHT) {
                    sizeSupported = true;
                    break;
                }
            }

            if (!sizeSupported) {
                throw new Exception("Camera " + cameraId + " doesn't directly support "
                        + STREAM_WIDTH + "x" + STREAM_HEIGHT);
            }

            return cameraId;
        }
        throw new Exception("No suitable camera found");
    }

    private final CameraDevice.StateCallback cameraCallback = new CameraDevice.StateCallback() {
        // FIXME: ALL OF THIS SMELLS
        @Override
        public void onOpened(@NonNull CameraDevice camera) {
            // Called after the camera got successfully opened
            cameraResourceLock.release();
            cameraDevice = camera;
            createCaptureSession(); // FIXME: just pass camera???
        }

        @Override
        public void onDisconnected(CameraDevice camera) {
            cameraResourceLock.release();
            camera.close();
            cameraDevice = null;
            activity.logMessage(LogType.ERROR, "Camera disconnected");
        }

        @Override
        public void onError(CameraDevice camera, int error) {
            cameraResourceLock.release();
            camera.close();
            cameraDevice = null;
            activity.logMessage(LogType.ERROR, "Camera error: " + error);
        }
    };

    private void createCaptureSession() {
        try {
            // TEMPLATE_RECORD is suitable for video recording or continuous frame capture.
            CaptureRequest.Builder captureRequestBuilder =
                    cameraDevice.createCaptureRequest(CameraDevice.TEMPLATE_RECORD);

            // Connect camera output directly to encoder input surface
            captureRequestBuilder.addTarget(encoderSurface);

            // Set the camera to continuously adjust focus as the scene changes
            captureRequestBuilder.set(CaptureRequest.CONTROL_AF_MODE,
                    CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_VIDEO);

            CaptureRequest captureRequest = captureRequestBuilder.build();

            // createCaptureSession is the mechanism to submit requests for capturing images.
            // The StateCallback informs us when the session is ready or if configuration failed
            cameraDevice.createCaptureSession(Collections.singletonList(encoderSurface),
                    new CameraCaptureSession.StateCallback() {
                        @Override
                        public void onConfigured(@NonNull CameraCaptureSession session) {
                            if (cameraDevice == null) return; // Camera might have been closed concurrently. FIXME ??

                            captureSession = session;
                            try {
                                // Tells the capture session to continuously capture frames using the specified settings.
                                // There is no listener because the camera writes directly to the encoder's input surface.
                                // backgroundHandler ensures that the requests are processed off the main thread //FIXME: Too much stuff running on background?
                                captureSession.setRepeatingRequest(captureRequest, null, backgroundHandler);
                                isStreaming = true;
                                activity.logMessage(LogType.INFO, "H.264 camera streaming started at " +
                                        STREAM_WIDTH + "x" + STREAM_HEIGHT + " @ " + STREAM_FRAMERATE + "fps");
                                // FIXME: maybe UI update
                            } catch (CameraAccessException e) {
                                activity.logMessage(LogType.ERROR, "Error starting capture: " + e.getMessage());
                            }
                        }

                        @Override
                        public void onConfigureFailed(@NonNull CameraCaptureSession session) {
                            activity.logMessage(LogType.ERROR, "Camera capture session configuration failed");
                        }
                    }, null); // This code is already running on the background thread
        } catch (CameraAccessException e) {
            activity.logMessage(LogType.ERROR, "Error creating capture session: " + e.getMessage());
        }
    }

    private final CameraCaptureSession.StateCallback captureSessionCallback = new CameraCaptureSession.StateCallback() {
        @Override
        public void onConfigureFailed(@NonNull CameraCaptureSession session) {

        }
        @Override
        public void onConfigured(@NonNull CameraCaptureSession session) {

        }
    };





    public void stopStreaming() {
        isStreaming = false; // Important to set this first to stop processing more frames
        closeCamera();
        closeEncoder();
        stopBackgroundThread();
        activity.logMessage(LogType.INFO, "H.264 camera streaming stopped");
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