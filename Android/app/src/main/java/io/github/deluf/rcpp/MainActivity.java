package io.github.deluf.rcpp;

import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.text.Spannable;
import android.text.SpannableStringBuilder;
import android.text.method.ScrollingMovementMethod;
import android.text.style.ForegroundColorSpan;
import android.text.style.StyleSpan;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

public class MainActivity extends AppCompatActivity {

    // Constants
    private static final String TARGET_DEVICE_NAME = "Arduino UNO R3";
    private static final String CONTROLLER_IP = "100.92.38.63"; // Tailscale's IP of my computer
    private static final int DEFAULT_BAUD_RATE = 115200;
    private static final String[] BAUD_RATES = {"9600", "19200", "38400", "57600", "115200"};
    private static final int CLEAR_MONITOR_THRESHOLD_LINES = 1000;
    private static final int COLOR_GREEN = Color.parseColor("#4CAF50");
    private static final int COLOR_RED = Color.parseColor("#E91E63");
    private static final int COLOR_BLUE = Color.parseColor("#03A9F4");
    private static final int COLOR_ORANGE = Color.parseColor("#AB3C19");
    private static final int COLOR_BLACK = Color.parseColor("#000000");

    // UI elements
    private Spinner baudSpinner;
    private TextView serialStatus;
    private TextView controllerStatus;
    private TextView logsMonitor;
    private TextView serialMonitor;
    private EditText serialInput;
    private Button sendToSerialButton;
    private Button startApplicationButton;

    // Application logic
    private ControllerManager controllerManager;
    private SerialManager serialManager;
    private SocketManager socketManager;

    /**
     * TODO:
     * maybe log -> errorLog [sezione ----- DEBUG -----]
     * maybe different screens at this point
     * handle socket errors
     */

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        initViews();
        setupBaudRatesSpinner();
        controllerManager = new ControllerManager(this, CONTROLLER_IP);
        serialManager = new SerialManager(this, DEFAULT_BAUD_RATE);
        socketManager = new SocketManager(this, CONTROLLER_IP);
    }

    private void initViews() {
        baudSpinner = findViewById(R.id.spinner_baud_rate);
        serialStatus = findViewById(R.id.textview_serial_status);
        controllerStatus = findViewById(R.id.textview_controller_status);
        logsMonitor = findViewById(R.id.textview_logs_monitor);
        serialMonitor = findViewById(R.id.textview_serial_monitor);
        serialInput = findViewById(R.id.edittext_send_to_serial);
        sendToSerialButton = findViewById(R.id.button_send_to_serial);
        startApplicationButton = findViewById(R.id.start_application);

        startApplicationButton.setEnabled(true); // FIXME

        logsMonitor.setMovementMethod(new ScrollingMovementMethod());
        serialMonitor.setMovementMethod(new ScrollingMovementMethod());

        sendToSerialButton.setOnClickListener(v -> sendMessageToSerial());
        startApplicationButton.setOnClickListener(v -> startApplication());

        updateControllerStatus(false);
        updateSerialStatus(false);
    }

    private void setupBaudRatesSpinner() {
        ArrayAdapter<String> adapter = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item, BAUD_RATES);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        baudSpinner.setAdapter(adapter);

        // Sets the selected item to the initial baudRate value
        int defaultIndex = java.util.Arrays.asList(BAUD_RATES).indexOf(String.valueOf(DEFAULT_BAUD_RATE));
        if (defaultIndex != -1) {
            baudSpinner.setSelection(defaultIndex);
        }

        baudSpinner.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener() {
            public void onItemSelected(android.widget.AdapterView<?> parent, android.view.View view, int pos, long id) {
                int newBaudRate = Integer.parseInt(parent.getItemAtPosition(pos).toString());
                serialManager.setBaudRate(newBaudRate);
            }
            public void onNothingSelected(android.widget.AdapterView<?> parent) {}
        });
    }

    void updateControllerStatus(boolean online) {
        runOnUiThread(() -> {
            if (online) {
                controllerStatus.setTextColor(COLOR_GREEN);
                controllerStatus.setText("ONLINE");
            } else {
                controllerStatus.setTextColor(COLOR_RED);
                controllerStatus.setText("OFFLINE");
            }
            //startApplication.setEnabled(online && serialManager.isDeviceConnected()); FIXME
        });
    }

    void updateSerialStatus(boolean plugged_in) {
        runOnUiThread(() -> {
            if (plugged_in) {
                serialStatus.setTextColor(COLOR_GREEN);
                serialStatus.setText(TARGET_DEVICE_NAME);
                serialMonitor.setText("");
            } else {
                serialStatus.setTextColor(COLOR_RED);
                serialStatus.setText("UNPLUGGED");
            }
            //startApplication.setEnabled(plugged_in && controllerManager.isOnline()); FIXME
            sendToSerialButton.setEnabled(plugged_in);
            serialInput.setEnabled(plugged_in);
            baudSpinner.setEnabled(!plugged_in);
        });
    }

    private void sendMessageToSerial() {
        String message = serialInput.getText().toString().trim();
        serialManager.sendASCII(message);
    }

    private void startApplication() {
        socketManager.sendTelemetry("TEL.DUMMY");

        byte[] data = new byte[1];
        data[0] = 0x01;
        socketManager.sendStream(data);
    }

    enum LogType {
        TX("[TX]", COLOR_BLUE),
        RX("[RX]", COLOR_RED),
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
            // Clear old messages
            String current = textView.getText().toString();
            if (current.split("\n").length > CLEAR_MONITOR_THRESHOLD_LINES) {
                textView.setText("");
            }

            // Create a styled message if it's going to the serial monitor
            if (type == LogType.RX || type == LogType.TX) {
                SpannableStringBuilder sb = new SpannableStringBuilder();
                int start = sb.length();
                sb.append(type.tag).append(" ");
                sb.setSpan(new StyleSpan(Typeface.BOLD), start, sb.length(), Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
                sb.setSpan(new ForegroundColorSpan(type.color), start, sb.length(), Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
                sb.append(message).append("\n");
                textView.append(sb);
            }
            else {
                SpannableStringBuilder sb = new SpannableStringBuilder();
                int start = sb.length();
                sb.append(type.tag).append(" ").append(message).append("\n");
                if (type == LogType.ERROR) {
                    sb.setSpan(new StyleSpan(Typeface.BOLD), start, sb.length(), Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
                }
                sb.setSpan(new ForegroundColorSpan(type.color), start, sb.length(), Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
                textView.append(sb);
            }

            // Auto-scroll to bottom
            textView.post(() -> {
                int scrollAmount = textView.getLayout().getLineTop(textView.getLineCount()) - textView.getHeight();
                textView.scrollTo(0, Math.max(scrollAmount, 0));
            });
        });
    }

    void logSerialMessage(LogType direction, String message) {
        writeToTextView(serialMonitor, direction, message);
    }

    void logMessage(LogType type, String message) {
        writeToTextView(logsMonitor, type, message);
    }

    void showToast(String message) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        controllerManager.destroyControllerMonitoring();
        serialManager.closeSerialPort();
        socketManager.destroy();
    }

    @Override
    protected void onPause() {
        super.onPause();
        controllerManager.pauseControllerMonitoring();
    }

    @Override
    protected void onResume() {
        super.onResume();
        controllerManager.resumeControllerMonitoring();
    }
}
