package io.github.deluf.rcpp;

import android.Manifest;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.location.Location;
import android.location.LocationManager;
import android.os.BatteryManager;
import android.telephony.PhoneStateListener;
import android.telephony.SignalStrength;
import android.telephony.TelephonyManager;

import androidx.core.app.ActivityCompat;

import java.io.BufferedReader;
import java.io.FileReader;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public class TelemetryManager implements SensorEventListener {

    private final MainActivity mainActivity;
    private SensorManager sensorManager;
    private Sensor magnetometer;
    private Sensor accelerometer;
    private LocationManager locationManager;
    private TelephonyManager telephonyManager;
    private ScheduledExecutorService temperatureService;

    private static final int TEMPERATURE_UPDATE_INTERVAL_MS = 5000;
    private static final int HEADING_UPDATE_INTERVAL_US = 500_000;
    private static final int MIN_LOCATION_UPDATE_INTERVAL_MS = 10_000;
    private static final int MIN_LOCATION_UPDATE_DISTANCE_M = 10;
    private static final int MAX_LOCATION_PRECISION = 5; // decimal places: 5 ~ 1.1 m

    private long lastGPSFix = 0;
    // If the last GPS fix is older than this threshold, then use network-based location
    private static final int GPS_STALENESS_THRESHOLD_MS = 60_000;


    // Variables required to perform heading computations
    private final float[] accelerometerReading = new float[3];
    private final float[] magnetometerReading = new float[3];
    private final float[] rotationMatrix = new float[9];
    private final float[] orientationAngles = new float[3];

    private enum Metric {
        // The sensors id of the temp metrics refers to the thermal zone id
        MODEM_TEMP(3),              // celsius  | int
        CAMERA_TEMP(5),             // celsius  | int
        CPU_TEMP(6),                // celsius  | int  (Average temp of the high performance core cluster)
        GPU_TEMP(12),               // celsius  | int
        PHONE_BATTERY_TEMP(42),     // celsius  | int

        PHONE_BATTERY_PERCENT(100), // [0-100]   | int
        POSITION(101),              // LATITUDE  | float,
                                            // LONGITUDE | float,
                                            // ACCURACY  | int
        HEADING(102),               // degrees   | int
        SIGNAL_LEVEL(103),          // [0-5]     | int
        CAR_BATTERY_VOLTAGE(104),   // centiVolt | int
        ELECTRONICS_BATTERY_VOLTAGE(105);   // centiVolt | int

        private final int sensorId;

        Metric(int sensorId) {
            this.sensorId = sensorId;
        }

        public int getSensorId() {
            return sensorId;
        }
    }

    private final Map<Metric, Object> lastKnownValues = new HashMap<>();

    public TelemetryManager(MainActivity mainActivity) {
        this.mainActivity = mainActivity;
        initializeManagers();
        initializeSensors();
    }

    private void initializeManagers() {
        sensorManager = (SensorManager) mainActivity.getSystemService(Context.SENSOR_SERVICE);
        locationManager = (LocationManager) mainActivity.getSystemService(Context.LOCATION_SERVICE);
        telephonyManager = (TelephonyManager) mainActivity.getSystemService(Context.TELEPHONY_SERVICE);
    }

    private void initializeSensors() {
        magnetometer = sensorManager.getDefaultSensor(Sensor.TYPE_MAGNETIC_FIELD);
        accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER);
    }

    public void startCollecting() {
        sensorManager.registerListener(this, magnetometer,
                HEADING_UPDATE_INTERVAL_US, HEADING_UPDATE_INTERVAL_US * 2);
        sensorManager.registerListener(this, accelerometer,
                HEADING_UPDATE_INTERVAL_US, HEADING_UPDATE_INTERVAL_US * 2);
        mainActivity.logMessage(MainActivity.LogType.INFO, "Heading monitoring enabled");

        IntentFilter batteryFilter = new IntentFilter(Intent.ACTION_BATTERY_CHANGED);
        mainActivity.registerReceiver(batteryReceiver, batteryFilter);
        mainActivity.logMessage(MainActivity.LogType.INFO, "Battery monitoring enabled");

        startCellularMonitoring();
        startLocationMonitoring();
        startTemperatureMonitoring();
        startVoltageMonitoring();
    }

    @Override
    public void onAccuracyChanged(Sensor sensor, int accuracy) {
        // Not used
    }

    @Override
    public void onSensorChanged(SensorEvent event) {
        switch (event.sensor.getType()) {
            case Sensor.TYPE_ACCELEROMETER:
                System.arraycopy(event.values, 0, accelerometerReading, 0, accelerometerReading.length);
                computeHeading();
                break;
            case Sensor.TYPE_MAGNETIC_FIELD:
                System.arraycopy(event.values, 0, magnetometerReading, 0, magnetometerReading.length);
                computeHeading();
                break;
        }
    }

    private void computeHeading() {
        if (SensorManager.getRotationMatrix(rotationMatrix, null, accelerometerReading, magnetometerReading)) {
            SensorManager.getOrientation(rotationMatrix, orientationAngles);

            // Convert radians to degrees and normalize to 0-360
            int azimuthDegrees = (int) Math.toDegrees(orientationAngles[0]);
            if (azimuthDegrees < 0) {
                azimuthDegrees += 360;
            }

            updateMetricIfChanged(Metric.HEADING, azimuthDegrees);
        }
    }

    private void updateMetricIfChanged(Metric metric, Object newValue) {
        Object oldValue = lastKnownValues.get(metric);
        if (newValue.equals(oldValue)) { return; }
        lastKnownValues.put(metric, newValue);

        // Telemetry data is sent as a byte array with the following format:
        // - metric type: first byte
        // - values: 4 bytes per value (int or float)
        ByteBuffer buffer;
        if (metric == Metric.POSITION) {
            buffer = ByteBuffer.allocate(1 + 3*4);
            buffer.put((byte) metric.getSensorId());
            ArrayList<Number> position = (ArrayList<Number>) newValue;
            buffer.putFloat((Float) position.get(0));
            buffer.putFloat((Float) position.get(1));
            buffer.putInt((Integer) position.get(2));
        }
        else {
            buffer = ByteBuffer.allocate(5);
            buffer.put((byte) metric.getSensorId());
            buffer.putInt((Integer) newValue);
        }
        mainActivity.socketManager.sendTelemetryData(buffer.array());
    }

    private final BroadcastReceiver batteryReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            int level = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
            int scale = intent.getIntExtra(BatteryManager.EXTRA_SCALE, -1);
            if (level != -1 && scale != -1) {
                int chargePercentage = (level * 100) / scale;
                updateMetricIfChanged(Metric.PHONE_BATTERY_PERCENT, chargePercentage);
            }
        }
    };

    private void startCellularMonitoring() {
        if (ActivityCompat.checkSelfPermission(
                mainActivity, Manifest.permission.READ_PHONE_STATE) != PackageManager.PERMISSION_GRANTED) {
            mainActivity.logMessage(MainActivity.LogType.WARNING, "Phone state permissions not granted");
            return;
        }
        telephonyManager.listen(phoneStateListener, PhoneStateListener.LISTEN_SIGNAL_STRENGTHS);
        mainActivity.logMessage(MainActivity.LogType.INFO, "Phone state monitoring enabled");
    }

    private final PhoneStateListener phoneStateListener = new PhoneStateListener() {
        @Override
        public void onSignalStrengthsChanged(SignalStrength signalStrength) {
            super.onSignalStrengthsChanged(signalStrength);
            int signalLevel = signalStrength.getLevel();
            updateMetricIfChanged(Metric.SIGNAL_LEVEL, signalLevel);
        }
    };

    private void startLocationMonitoring() {
        if (ActivityCompat.checkSelfPermission(
                mainActivity, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED &&
            ActivityCompat.checkSelfPermission(
                mainActivity, Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            mainActivity.logMessage(MainActivity.LogType.WARNING, "Location permissions not granted");
            return;
        }

        if (locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER)) {
            mainActivity.logMessage(MainActivity.LogType.INFO, "GPS positioning enabled");
            locationManager.requestLocationUpdates(
                    LocationManager.GPS_PROVIDER, MIN_LOCATION_UPDATE_INTERVAL_MS,
                    MIN_LOCATION_UPDATE_DISTANCE_M, this::onFineLocationChanged);
        }
        if (locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) {
            mainActivity.logMessage(MainActivity.LogType.INFO, "Network positioning enabled");
            locationManager.requestLocationUpdates(
                    LocationManager.NETWORK_PROVIDER, MIN_LOCATION_UPDATE_INTERVAL_MS,
                    MIN_LOCATION_UPDATE_DISTANCE_M, this::onCoarseLocationChanged);
        }
    }

    private void onLocationChanged(Location location) {
        float precisionMultiplier = (float) Math.pow(10, MAX_LOCATION_PRECISION);
        float latitude = Math.round(location.getLatitude() * precisionMultiplier) / precisionMultiplier;
        float longitude = Math.round(location.getLongitude() * precisionMultiplier) / precisionMultiplier;
        int accuracy = location.hasAccuracy() ? (int) location.getAccuracy() : 0;

        ArrayList<Number> position = new ArrayList<>(3);
        position.add(latitude);
        position.add(longitude);
        position.add(accuracy);
        updateMetricIfChanged(Metric.POSITION, position);
    }

    private void onFineLocationChanged(Location location) {
        lastGPSFix = System.currentTimeMillis();
        onLocationChanged(location);
    }

    private void onCoarseLocationChanged(Location location) {
        // If the GPS signal is stale, use the coarse location
        if (System.currentTimeMillis() - lastGPSFix > GPS_STALENESS_THRESHOLD_MS) {
            onLocationChanged(location);
        }
    }

    private void startTemperatureMonitoring() {
        temperatureService = Executors.newSingleThreadScheduledExecutor();
        temperatureService.scheduleWithFixedDelay(this::readTemperatures,
                0, TEMPERATURE_UPDATE_INTERVAL_MS, TimeUnit.MILLISECONDS);
        mainActivity.logMessage(MainActivity.LogType.INFO, "Temperature monitoring enabled");
    }

    private void readTemperatures() {
        readTemperature(Metric.MODEM_TEMP);
        readTemperature(Metric.CAMERA_TEMP);
        readTemperature(Metric.CPU_TEMP);
        readTemperature(Metric.GPU_TEMP);
        readTemperature(Metric.PHONE_BATTERY_TEMP);
    }

    private void readTemperature(Metric metric) {
        String thermalZonePath = "/sys/class/thermal/thermal_zone" + metric.getSensorId() + "/temp";

        try (BufferedReader reader = new BufferedReader(new FileReader(thermalZonePath))) {
            String tempString = reader.readLine();
            if (tempString != null && !tempString.trim().isEmpty()) {
                // Temperature is in milli-Celsius, convert to Celsius and round to int
                int tempMilliC = Integer.parseInt(tempString.trim());
                int tempC = Math.round(tempMilliC / 1000.0f);
                updateMetricIfChanged(metric, tempC);
            }
        } catch (IOException e) {
            mainActivity.logMessage(MainActivity.LogType.ERROR,
                    "Error reading " + metric.name() + ": " + e.getMessage());
        }
    }

    // FIXME: magari dovrei mettere le variabili usate solo nell funzioni anche altrove (invece che in cima a prescindere)
    private boolean collectVoltages = false;
    private void startVoltageMonitoring() {
        mainActivity.logMessage(MainActivity.LogType.INFO, "Voltage monitoring enabled");
        collectVoltages = true;
    }
    public void onNewCarBatteryVoltage(byte voltage) {
        if (!collectVoltages) { return; }
        updateMetricIfChanged(Metric.CAR_BATTERY_VOLTAGE, (int)voltage);
    }
    public void onNewElectronicsBatteryVoltage(byte voltage) {
        if (!collectVoltages) { return; }
        updateMetricIfChanged(Metric.ELECTRONICS_BATTERY_VOLTAGE, (int)voltage);
    }

    public void stopCollecting() {
        // Unregister sensor listeners
        if (sensorManager != null) {
            sensorManager.unregisterListener(this);
        }

        // Stop location updates
        if (locationManager != null) {
            locationManager.removeUpdates(this::onFineLocationChanged);
            locationManager.removeUpdates(this::onCoarseLocationChanged);
        }

        // Stop cellular monitoring
        if (telephonyManager != null) {
            telephonyManager.listen(phoneStateListener, PhoneStateListener.LISTEN_NONE);
        }

        // Stop temperature monitoring
        if (temperatureService != null && !temperatureService.isShutdown()) {
            temperatureService.shutdown();
        }

        // Unregister battery receiver
        try {
            mainActivity.unregisterReceiver(batteryReceiver);
        } catch (IllegalArgumentException e) {
            // Receiver was not registered
        }
    }
}
