package io.github.deluf.rcpp;

import android.os.Handler;
import android.os.Looper;

import java.net.InetAddress;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

public class ServerManager {
    private static final int MONITORING_INTERVAL_MS = 1000;

    // The server is considered unreachable if it takes more than this amount of time to respond
    private static final int REACHABILITY_TIMEOUT_MS = 500;

    // Only set the reachability status to false if the server did not respond for a while
    private static final int STALENESS_THRESHOLD_MS = 5000;
    private long lastReachableTime = 0;

    private final Handler monitoringHandler;
    private final Runnable monitoringTask;
    private final ExecutorService monitoringExecutor;

    // Prevents the background thread from updating the ui after pauseControllerMonitoring is called
    private final AtomicBoolean isRunning = new AtomicBoolean(false);

    ServerManager(MainActivity activity, String CONTROLLER_IP)  {
        monitoringHandler = new Handler(Looper.getMainLooper());
        monitoringExecutor = Executors.newSingleThreadExecutor();
        monitoringTask = new Runnable() {
            @Override
            public void run() {
                monitoringExecutor.execute(() -> {
                    try {
                        InetAddress address = InetAddress.getByName(CONTROLLER_IP);
                        boolean reachable = address.isReachable(REACHABILITY_TIMEOUT_MS);
                        lastReachableTime = System.currentTimeMillis();
                        if (isRunning.get()) { activity.updateServerStatus(reachable); }
                    } catch (Exception e) {
                        long currentTime = System.currentTimeMillis();
                        if (currentTime - lastReachableTime >= STALENESS_THRESHOLD_MS && isRunning.get()) {
                            activity.updateServerStatus(false);
                        }
                    }
                });
                monitoringHandler.postDelayed(this, MONITORING_INTERVAL_MS);
            }
        };
        resumeControllerMonitoring();
    }

    void resumeControllerMonitoring() {
        isRunning.set(true);
        monitoringHandler.post(monitoringTask);
    }

    void pauseControllerMonitoring() {
        isRunning.set(false);
        monitoringHandler.removeCallbacks(monitoringTask);
    }

    void stopControllerMonitoring() {
        pauseControllerMonitoring();
        if (!monitoringExecutor.isShutdown()) {
            monitoringExecutor.shutdown();
        }
    }

}
