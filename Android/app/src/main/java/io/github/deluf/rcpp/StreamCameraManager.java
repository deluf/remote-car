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
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CaptureRequest;
import android.hardware.camera2.params.StreamConfigurationMap;
import android.media.Image;
import android.media.ImageReader;
import android.os.Handler;
import android.os.HandlerThread;

import androidx.annotation.NonNull;
import androidx.core.app.ActivityCompat;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

import io.github.deluf.rcpp.MainActivity.LogType;

public class StreamCameraManager {
    private static final int STREAM_WIDTH = 320;
    private static final int STREAM_HEIGHT = 240;
    private static final int JPEG_COMPRESSION_QUALITY = 70;
    // FIXME: WebP, H264 ?
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
    private ImageReader imageReader;
    // Provides direct access to raw image data buffers from the camera
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
                // FIXME: This is useles, unless you want to display the supported raw resolutions

                // WHY YUV_420_888: This is a common raw image format provided by Android cameras.
                // It's planar (Y, U, V data are in separate buffers or have specific strides/offsets),
                // and it's a good intermediate format before converting to JPEG. It offers a good
                // balance between data size and quality for video processing.
                // Alternatives: ImageFormat.JPEG (camera does JPEG conversion, less control but simpler if
                // no processing needed), ImageFormat.NV21 (another YUV format, sometimes more directly
                // convertible to formats expected by some encoders/renderers).
                // The '2' for maxImages: This is the number of images that ImageReader can hold.
                // A value of 2 allows for a "double buffer" like system: one image is being processed while
                // the camera can be writing to the next. This helps prevent frame drops.
                imageReader = ImageReader.newInstance(STREAM_WIDTH, STREAM_HEIGHT,
                        ImageFormat.YUV_420_888, 2);
                // WHY setOnImageAvailableListener: This is the callback mechanism for ImageReader.
                // When the camera has written a new frame to one of the ImageReader's Surfaces,
                // this listener is invoked.
                imageReader.setOnImageAvailableListener(onImageAvailableListener, backgroundHandler);
                // WHY backgroundHandler here: The onImageAvailable callback can involve significant processing
                // (JPEG conversion, network sending). It MUST run on a background thread to avoid
                // blocking the camera pipeline and the UI.

                this.cameraId = cameraId;
                return; // Found and configured a suitable camera.
            }
        } catch (CameraAccessException e) {
            activity.logMessage(LogType.ERROR, "Camera access error: " + e.getMessage());
        }
    }








    public void stopStreaming() {
        isStreaming = false; // Important to set this first to stop onImageAvailable from processing more frames
        closeCamera();
        stopBackgroundThread();
        activity.logMessage(LogType.INFO, "Camera streaming stopped");
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
            // WHY addTarget(imageReader.getSurface()): This tells the camera to send its output
            // (the frames) to the Surface provided by our ImageReader. The ImageReader then makes
            // this data available to our app.
            captureRequestBuilder.addTarget(imageReader.getSurface());

            // WHY createCaptureSession: This is the mechanism to submit requests for capturing images.
            // We provide a list of output Surfaces (just one in this case: the ImageReader's).
            // The StateCallback informs us when the session is ready or if configuration failed.
            cameraDevice.createCaptureSession(Arrays.asList(imageReader.getSurface()),
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
                    }, null); // null handler for StateCallback: invokes on the backgroundHandler's thread.
        } catch (CameraAccessException e) {
            activity.logMessage(LogType.ERROR, "Error creating capture session: " + e.getMessage());
        }
    }

    private final ImageReader.OnImageAvailableListener onImageAvailableListener =
            new ImageReader.OnImageAvailableListener() {
                @Override
                public void onImageAvailable(ImageReader reader) {
                    if (!isStreaming) return; // Check if we should still be processing.

                    Image image = null;
                    try {
                        // WHY acquireLatestImage(): If processing is slower than frame production,
                        // this discards older frames and gets the most recent one. This is good for
                        // real-time streaming to reduce latency.
                        // Alternatives: acquireNextImage() gets frames in strict sequence, but can
                        // lead to a backlog if processing is slow.
                        image = reader.acquireLatestImage();
                        if (image == null) return;

                        byte[] jpegData = convertToJPEG(image);

                        if (jpegData != null && jpegData.length > 0) {
                            sendFrameData(jpegData);
                            // Statistics logic for FPS and data rate.
                            frameCount++;
                            long currentTime = System.currentTimeMillis();
                            if (currentTime - lastFrameTime >= 5000) { // Log every 5 seconds.
                                double fps = frameCount / ((currentTime - lastFrameTime) / 1000.0);
                                activity.logMessage(LogType.INFO,
                                        String.format("Streaming: %.1f FPS, %d KB/frame",
                                                fps, jpegData.length / 1024));
                                frameCount = 0;
                                lastFrameTime = currentTime;
                            }
                        }
                    } catch (Exception e) { // Catching general Exception to prevent crashes in the callback.
                        activity.logMessage(LogType.ERROR, "Error processing frame: " + e.getMessage());
                    } finally {
                        // WHY image.close(): This is CRITICAL. Images from ImageReader are a finite resource.
                        // If you don't close them, the ImageReader will eventually run out of available
                        // buffers, and onImageAvailable will stop being called.
                        if (image != null) {
                            image.close();
                        }
                    }
                }
            };

    private byte[] convertToJPEG(Image image) {
        // WHY this conversion: YUV_420_888 is a raw format. JPEG is compressed and widely viewable.
        // This conversion happens on the device to reduce network bandwidth.
        try {
            Image.Plane[] planes = image.getPlanes();
            ByteBuffer yBuffer = planes[0].getBuffer();
            ByteBuffer uBuffer = planes[1].getBuffer();
            ByteBuffer vBuffer = planes[2].getBuffer();

            int ySize = yBuffer.remaining();
            int uSize = uBuffer.remaining();
            int vSize = vBuffer.remaining();

            // WHY NV21: YuvImage class, used for JPEG compression here, often expects NV21 or YUY2.
            // NV21 is a common YUV format where Y plane is followed by an interleaved V/U plane.
            // The conversion from YUV_420_888 (which is planar) to NV21 (semi-planar) is necessary.
            byte[] nv21 = new byte[ySize + uSize + vSize]; // uSize + vSize should be ySize / 2 for NV21

            yBuffer.get(nv21, 0, ySize);

            // The original UV to NV21 conversion logic was a bit problematic.
            // For YUV_420_888, planes[0] is Y. planes[1] is U. planes[2] is V.
            // Pixel stride for U and V is often 2, row stride might be different from width.
            // NV21 format: YYYYYYYY... UVUVUV... (or VUVUVU... depending on interpretation, YuvImage expects VU).
            // This part is the most complex and error-prone.
            // A robust YUV conversion often relies on understanding the exact strides and layout
            // provided by the camera for the YUV_420_888 format.
            // The key is that for NV21, the second part of the buffer should contain interleaved V and U values.

            // Corrected (simplified) NV21 conversion assuming planes[1] is U and planes[2] is V,
            // and their pixel stride is 2 (meaning they are already somewhat interleaved or subsampled)
            // and we need to interleave them as V U V U ...
            // This assumes Y, U, V planes from ImageFormat.YUV_420_888
            // Y plane: data for Y channel
            // U plane: data for U channel (chroma)
            // V plane: data for V channel (chroma)
            // For NV21, we need Y plane first, then an interleaved VU plane.
            // If planes[1] (U) and planes[2] (V) have pixelStride == 1, they are planar.
            // If pixelStride == 2, they might already be somewhat interleaved (e.g. U V U V for one, and V U V U for other, or just U _ U _ and V _ V _)

            // The crucial part for YUV_420_888 to NV21 (which is Y + interleaved VU):
            // planes[0] = Y (buffer, rowStride, pixelStride=1)
            // planes[1] = U (buffer, rowStride, pixelStride may be 1 or 2)
            // planes[2] = V (buffer, rowStride, pixelStride may be 1 or 2)
            // NV21 expects all Y values, then V, U, V, U...
            // Size of NV21: width * height * 3 / 2
            // Y component size: width * height
            // VU component size: width * height / 2

            // Assuming planes[1] is U and planes[2] is V, and they are planar (pixelStride = 1)
            // and we need to interleave them into nv21 starting at ySize, as V, U, V, U ...
            // This is a common pattern required by YuvImage.
            int chromaRowStride = planes[1].getRowStride(); // Assuming U and V have same row stride
            int chromaPixelStride = planes[1].getPixelStride(); // Assuming U and V have same pixel stride

            byte[] uBytes = new byte[uBuffer.capacity()];
            uBuffer.get(uBytes);
            byte[] vBytes = new byte[vBuffer.capacity()];
            vBuffer.get(vBytes);

            int dstIndex = ySize;
            // Iterate over chroma plane (half width, half height)
            for (int y = 0; y < STREAM_HEIGHT / 2; y++) {
                for (int x = 0; x < STREAM_WIDTH / 2; x++) {
                    int uIndex = y * chromaRowStride + x * chromaPixelStride;
                    int vIndex = y * planes[2].getRowStride() + x * planes[2].getPixelStride(); // Use V's strides

                    if (dstIndex < nv21.length -1 && vIndex < vBytes.length && uIndex < uBytes.length) {
                        nv21[dstIndex++] = vBytes[vIndex]; // V
                        nv21[dstIndex++] = uBytes[uIndex]; // U
                    } else {
                        // Avoid out of bounds, though ideally sizes should match up
                        break;
                    }
                }
                if (dstIndex >= nv21.length -1) break;
            }


            // WHY YuvImage and compressToJpeg: This is a standard Android utility class
            // to perform software JPEG compression from YUV data.
            // Alternatives: Using a native library (like libjpeg-turbo) via JNI could be faster
            // but adds complexity. Hardware JPEG encoders might be available on some devices
            // but are harder to access directly from Camera2 for this kind of flexible pipeline.
            YuvImage yuvImage = new YuvImage(nv21, ImageFormat.NV21, STREAM_WIDTH, STREAM_HEIGHT, null);
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            yuvImage.compressToJpeg(new Rect(0, 0, STREAM_WIDTH, STREAM_HEIGHT), JPEG_COMPRESSION_QUALITY, out);
            return out.toByteArray();

        } catch (Exception e) {
            activity.logMessage(LogType.ERROR, "JPEG conversion error: " + e.getMessage() + " Image format: " + image.getFormat());
            // It's helpful to log the image format if conversion fails.
            return null;
        }
    }

    private void sendFrameData(byte[] data) {
        // It might fail if the size of the frame exceeds the maximum allowed UDP packet size (~2^16 bytes).
        socketManager.sendStream(data);
    }

    private void closeCamera() {
        try {
            cameraResourceLock.acquire(); // Ensure exclusive access for closing.
            // WHY close in this order: Generally, stop the session, then close the device,
            // then release the ImageReader. This unwinds the setup order.
            if (captureSession != null) {
                captureSession.close();
                captureSession = null;
            }
            if (cameraDevice != null) {
                cameraDevice.close();
                cameraDevice = null;
            }
            if (imageReader != null) {
                imageReader.close(); // Releases the Surface and associated resources.
                imageReader = null;
            }
        } catch (InterruptedException e) {
            activity.logMessage(LogType.ERROR, "Interrupted while closing camera: " + e.getMessage());
            Thread.currentThread().interrupt(); // Preserve interrupt status.
        } finally {
            cameraResourceLock.release(); // CRITICAL: Always release the lock.
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
