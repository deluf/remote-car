package io.github.deluf.rcpp;

import android.os.Handler;
import android.os.Looper;

import java.net.InetAddress;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ControllerManager {
    private static final int MONITORING_INTERVAL_MS = 3000;
    private static final int REACHABILITY_TIMEOUT_MS = 1000;

    private final Handler monitoringHandler;
    private final Runnable monitoringTask;
    private final ExecutorService monitoringExecutor;
    private boolean isControllerBeingMonitored = false;
    private boolean isControllerOnline = false;

    ControllerManager(MainActivity activity, String CONTROLLER_IP)  {
        monitoringHandler = new Handler(Looper.getMainLooper());
        monitoringExecutor = Executors.newSingleThreadExecutor();
        monitoringTask = new Runnable() {
            @Override
            public void run() {
                if (isControllerBeingMonitored) {
                    monitoringExecutor.execute(() -> {
                        try {
                            InetAddress address = InetAddress.getByName(CONTROLLER_IP);
                            //long startTime = System.currentTimeMillis();
                            boolean reachable = address.isReachable(REACHABILITY_TIMEOUT_MS);
                            //long pingTime = System.currentTimeMillis() - startTime;
                            isControllerOnline = reachable;
                            activity.updateControllerStatus(reachable);
                        } catch (Exception e) {
                            isControllerOnline = false;
                            activity.updateControllerStatus(false);
                        }
                    });
                    monitoringHandler.postDelayed(this, MONITORING_INTERVAL_MS);
                }
            }
        };

        resumeControllerMonitoring();
    }

    boolean isOnline() {
        return isControllerOnline;
    };

    void resumeControllerMonitoring() {
        if (!isControllerBeingMonitored) {
            isControllerBeingMonitored = true;
            monitoringHandler.post(monitoringTask);
        }
    }

    void pauseControllerMonitoring() {
        isControllerBeingMonitored = false;
        if (monitoringHandler != null) {
            monitoringHandler.removeCallbacks(monitoringTask);
        }
    }

    void destroyControllerMonitoring() {
        pauseControllerMonitoring();
        if (monitoringExecutor != null && !monitoringExecutor.isShutdown()) {
            monitoringExecutor.shutdown();
        }
    }

}
