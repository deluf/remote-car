package io.github.deluf.rcpp;

import android.os.Handler;
import android.os.Looper;

import java.net.InetAddress;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ServerManager {
    private static final int MONITORING_INTERVAL_MS = 1000;
    private static final int REACHABILITY_TIMEOUT_MS = 500;

    private final Handler monitoringHandler;
    private final Runnable monitoringTask;
    private final ExecutorService monitoringExecutor;
    private long lastReachableTime = 0;

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
                        activity.updateServerStatus(reachable);
                    } catch (Exception e) {
                        long currentTime = System.currentTimeMillis();
                        // Only set the reachability status to false if the server
                        //  does not respond for more than 3 monitoring intervals in a row
                        if (currentTime - lastReachableTime >= MONITORING_INTERVAL_MS * 3) {
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
        monitoringHandler.post(monitoringTask);
    }

    void pauseControllerMonitoring() {
        monitoringHandler.removeCallbacks(monitoringTask);
    }

    void stopControllerMonitoring() {
        pauseControllerMonitoring();
        if (!monitoringExecutor.isShutdown()) {
            monitoringExecutor.shutdown();
        }
    }

}
