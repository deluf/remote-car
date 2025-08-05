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

import java.nio.ByteBuffer;
import java.util.HashMap;
import java.util.Map;

public class TelemetryManager implements SensorEventListener {

    private final MainActivity mainActivity;
    private SensorManager sensorManager;
    private Sensor magnetometer;
    private Sensor accelerometer;
    private LocationManager locationManager;
    private TelephonyManager telephonyManager;

    private static final int LOCATION_UPDATE_INTERVAL_MS = 1000;
    private static final int HEADING_UPDATE_INTERVAL_US = 500_000;
    private static final int MAX_LOCATION_PRECISION = 5; // decimal places: 5 ~ 1.1 m

    // Variables required to perform heading computations
    private final float[] accelerometerReading = new float[3];
    private final float[] magnetometerReading = new float[3];
    private final float[] rotationMatrix = new float[9];
    private final float[] orientationAngles = new float[3];

    private long lastGPSFix = 0;

    private enum Metric {
        BATTERY_PERCENT,    // [0-100]  | int
        BATTERY_TEMP,       // celsius  | int
        BATTERY_CHARGING,   // [0-1]    | int
        LATITUDE,           // degrees  | float
        LONGITUDE,          // degrees  | float
        ALTITUDE,           // meters   | int
        LOCATION_ACCURACY,  // meters   | int
        SPEED,              // km/h     | int
        BEARING,            // degrees  | int
        HEADING,            // degrees  | int
        SIGNAL_LEVEL,       // [0-4]    | int
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

        IntentFilter batteryFilter = new IntentFilter(Intent.ACTION_BATTERY_CHANGED);
        mainActivity.registerReceiver(batteryReceiver, batteryFilter);

        startCellularMonitoring();
        startLocationMonitoring();
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
        // - value: bytes 1 to 4 (can take up to ints and floats)
        ByteBuffer buffer = ByteBuffer.allocate(5);
        buffer.put((byte) metric.ordinal());
        if (newValue instanceof Integer) {
            buffer.putInt((Integer) newValue);
        }
        else if (newValue instanceof Float) {
            buffer.putFloat((Float) newValue);
        }
        else {
            throw new IllegalArgumentException(
                    "Unsupported type for serialization: " + newValue.getClass());
        }

        mainActivity.socketManager.sendTelemetryData(buffer.array());
    }

    private final BroadcastReceiver batteryReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            int level = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
            int scale = intent.getIntExtra(BatteryManager.EXTRA_SCALE, -1);
            int rawTemperature = intent.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, -1);
            int status = intent.getIntExtra(BatteryManager.EXTRA_STATUS, -1);

            if (level != -1 && scale != -1) {
                int chargePercentage = (level * 100) / scale;
                updateMetricIfChanged(Metric.BATTERY_PERCENT, chargePercentage);
            }

            if (rawTemperature != -1) {
                int temperature = rawTemperature / 10; // rawTemperature is in tenths of degrees
                updateMetricIfChanged(Metric.BATTERY_TEMP, temperature);
            }

            if (status != -1) {
                int charging = status == BatteryManager.BATTERY_STATUS_CHARGING ? 1 : 0;
                updateMetricIfChanged(Metric.BATTERY_CHARGING, charging);
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
            locationManager.requestLocationUpdates(
                    LocationManager.GPS_PROVIDER, LOCATION_UPDATE_INTERVAL_MS, 1.0f, this::onFineLocationChanged);
        }
        if (locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) {
            locationManager.requestLocationUpdates(
                    LocationManager.NETWORK_PROVIDER, LOCATION_UPDATE_INTERVAL_MS, 1.0f, this::onCoarseLocationChanged);
        }
    }

    public void onFineLocationChanged(Location location) {
        lastGPSFix = System.currentTimeMillis();

        float precisionMultiplier = (float) Math.pow(10, MAX_LOCATION_PRECISION);
        float latitude = Math.round(location.getLatitude() * precisionMultiplier) / precisionMultiplier;
        float longitude = Math.round(location.getLongitude() * precisionMultiplier) / precisionMultiplier;

        int accuracy = (int) location.getAccuracy();
        int altitude = location.hasAltitude() ? (int) location.getAltitude() : 0;
        int speed = location.hasSpeed() ? (int) (location.getSpeed() * 3.6) : 0;
        int bearing = location.hasBearing() ? (int) location.getBearing() : 0;

        updateMetricIfChanged(Metric.LATITUDE, latitude);
        updateMetricIfChanged(Metric.LONGITUDE, longitude);
        updateMetricIfChanged(Metric.ALTITUDE, altitude);
        updateMetricIfChanged(Metric.LOCATION_ACCURACY, accuracy);
        updateMetricIfChanged(Metric.SPEED, speed);
        updateMetricIfChanged(Metric.BEARING, bearing);
    }

    public void onCoarseLocationChanged(Location location) {
        // If the GPS signal is stale, use the coarse location
        if (System.currentTimeMillis() - lastGPSFix > LOCATION_UPDATE_INTERVAL_MS * 3) {
            onFineLocationChanged(location);
        }
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

        // Unregister battery receiver
        try {
            mainActivity.unregisterReceiver(batteryReceiver);
        } catch (IllegalArgumentException e) {
            // Receiver was not registered
        }
    }
}
