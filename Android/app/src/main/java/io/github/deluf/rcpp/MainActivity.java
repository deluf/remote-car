package io.github.deluf.rcpp;

import android.annotation.SuppressLint;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.text.Layout;
import android.text.Spannable;
import android.text.SpannableStringBuilder;
import android.text.method.ScrollingMovementMethod;
import android.text.style.ForegroundColorSpan;
import android.text.style.StyleSpan;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;

@SuppressLint("SetTextI18n")
public class MainActivity extends AppCompatActivity {

    private static final String TARGET_DEVICE_NAME = "Arduino UNO R3";
    private static final String CONTROLLER_IP = "100.92.38.63"; // Tailscale's IP of my computer
    private static final int CLEAR_MONITOR_THRESHOLD_LINES = 1000;
    private static final int COLOR_GREEN = Color.parseColor("#439846");
    private static final int COLOR_RED = Color.parseColor("#E91E63");
    private static final int COLOR_BLUE = Color.parseColor("#03A9F4");
    private static final int COLOR_ORANGE = Color.parseColor("#AB3C19");
    private static final int COLOR_BLACK = Color.parseColor("#000000");
    private static final int COLOR_GRAY = Color.parseColor("#808080");

    private TextView microcontrollerStatus;
    private TextView serverStatus;
    private TextView backCameraStatus;
    private TextView telemetrySocketStatus;
    private TextView controlSocketStatus;
    private TextView logsMonitor;
    private Button startApplicationButton;
    private StreamCameraManager streamCameraManager;

    private ServerManager serverManager;
    public MicrocontrollerManager microcontrollerManager;
    public SocketManager socketManager;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        initViews();
        serverManager = new ServerManager(this, CONTROLLER_IP);
        microcontrollerManager = new MicrocontrollerManager(this);
        socketManager = new SocketManager(this, CONTROLLER_IP);
        streamCameraManager = new StreamCameraManager(this);
    }

    private void initViews() {
        microcontrollerStatus = findViewById(R.id.textview_serial_status);
        serverStatus = findViewById(R.id.textview_controller_status);
        backCameraStatus = findViewById(R.id.textview_back_camera_status);
        telemetrySocketStatus = findViewById(R.id.textview_telemetry_socket_status);
        controlSocketStatus = findViewById(R.id.textview_control_socket_status);
        logsMonitor = findViewById(R.id.textview_logs_monitor);
        startApplicationButton = findViewById(R.id.start_application);

        startApplicationButton.setEnabled(true); // FIXME

        logsMonitor.setMovementMethod(new ScrollingMovementMethod());

        startApplicationButton.setOnClickListener(v -> startApplication());

        updateServerStatus(false);
        updateMicrocontrollerStatus(false);
        updateBackCameraStatus(false, "");
        updateTelemetrySocketStatus(false);
        updateControlSocketStatus(false);
    }

    void updateServerStatus(boolean reachable) {
        runOnUiThread(() -> {
            if (reachable) {
                serverStatus.setTextColor(COLOR_GREEN);
                serverStatus.setText("REACHABLE");
            } else {
                serverStatus.setTextColor(COLOR_RED);
                serverStatus.setText("UNREACHABLE");
            }
            //startApplication.setEnabled(online && serialManager.isDeviceConnected()); FIXME
        });
    }

    void updateMicrocontrollerStatus(boolean plugged) {
        runOnUiThread(() -> {
            if (plugged) {
                microcontrollerStatus.setTextColor(COLOR_GREEN);
                microcontrollerStatus.setText(TARGET_DEVICE_NAME + "@" + MicrocontrollerManager.BAUD_RATE);
            } else {
                microcontrollerStatus.setTextColor(COLOR_RED);
                microcontrollerStatus.setText("UNPLUGGED");
            }
            //startApplication.setEnabled(plugged_in && controllerManager.isOnline()); FIXME
        });
    }

    void updateBackCameraStatus(boolean ready, String details) {
        runOnUiThread(() -> {
            if (ready) {
                backCameraStatus.setTextColor(COLOR_GREEN);
                backCameraStatus.setText(details);
            } else {
                backCameraStatus.setTextColor(COLOR_RED);
                backCameraStatus.setText("NOT CONFIGURED");
            }
            //startApplication.setEnabled(online && serialManager.isDeviceConnected()); FIXME
        });
    }

    void updateTelemetrySocketStatus(boolean connected) {
        runOnUiThread(() -> {
            if (connected) {
                telemetrySocketStatus.setTextColor(COLOR_GREEN);
                telemetrySocketStatus.setText("CONNECTED");
            } else {
                telemetrySocketStatus.setTextColor(COLOR_RED);
                telemetrySocketStatus.setText("NOT CONNECTED");
            }
            //startApplication.setEnabled(online && serialManager.isDeviceConnected()); FIXME
        });
    }

    void updateControlSocketStatus(boolean connected) {
        runOnUiThread(() -> {
            if (connected) {
                controlSocketStatus.setTextColor(COLOR_GREEN);
                controlSocketStatus.setText("CONNECTED");
            } else {
                controlSocketStatus.setTextColor(COLOR_RED);
                controlSocketStatus.setText("NOT CONNECTED");
            }
            //startApplication.setEnabled(online && serialManager.isDeviceConnected()); FIXME
        });
    }

    private void startApplication() {
        streamCameraManager.startStreaming();

        serverManager.stopControllerMonitoring();
        serverStatus.setTextColor(COLOR_GRAY);
        serverStatus.setText("-");

        startApplicationButton.setEnabled(false);
    }

    enum LogType {
        ERROR("[ERROR]", COLOR_RED),
        WARNING("[WARNING]", COLOR_ORANGE),
        INFO("[INFO]", COLOR_BLACK),
        FAIL_SAFE("[FAIL_SAFE]", COLOR_GREEN);

        public final String tag;
        public final int color;

        LogType(String tag, int color) {
            this.tag = tag;
            this.color = color;
        }
    }

    private void writeToTextView(TextView textView, LogType type, String message) {
        runOnUiThread(() -> {
            // Check if user is at the bottom before appending text
            Layout layout = textView.getLayout();
            boolean shouldScroll = true;
            if (layout != null) {
                int scrollY = textView.getScrollY();
                int viewHeight = textView.getHeight();
                int contentHeight = layout.getLineTop(textView.getLineCount());
                shouldScroll = scrollY + viewHeight + 10 >= contentHeight;
                // 10 is safety margin, in pixels
            }

            // Clear old messages
            String current = textView.getText().toString();
            if (current.split("\n").length > CLEAR_MONITOR_THRESHOLD_LINES) {
                textView.setText("");
            }

            // Build the styled message
            SpannableStringBuilder sb = new SpannableStringBuilder();
            int start = sb.length();
            sb.append(type.tag).append(" ").append(message).append("\n");

            if (type == LogType.ERROR) {
                sb.setSpan(new StyleSpan(Typeface.BOLD), start, sb.length(), Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
            }
            sb.setSpan(new ForegroundColorSpan(type.color), start, sb.length(), Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
            textView.append(sb);

            // Scroll only if the user was at the bottom before
            if (shouldScroll) {
                textView.post(() -> {
                    Layout updatedLayout = textView.getLayout();
                    if (updatedLayout != null) {
                        int scrollAmount = updatedLayout.getLineTop(textView.getLineCount()) - textView.getHeight();
                        textView.scrollTo(0, Math.max(scrollAmount, 0));
                    }
                });
            }
        });
    }

    void logMessage(LogType type, String message) {
        writeToTextView(logsMonitor, type, message);
    }

    void showToast(String message) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions, @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        streamCameraManager.onRequestPermissionsResult(requestCode, permissions, grantResults);
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        serverManager.stopControllerMonitoring();
        microcontrollerManager.closeSerialPort();
        socketManager.destroy();
        streamCameraManager.stopStreaming();
    }

    @Override
    protected void onPause() {
        super.onPause();
        serverManager.pauseControllerMonitoring();
    }

    @Override
    protected void onResume() {
        super.onResume();
        serverManager.resumeControllerMonitoring();
    }
}
