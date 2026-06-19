import collections
import multiprocessing
import time
import matplotlib
import matplotlib.animation as animation
import matplotlib.pyplot as plt
import psutil

# Use non-interactive backend for background plotting window
INTERFACE = "utun6" # Tailscale interface name
REFRESH_INTERVAL = 0.5
HISTORY_SECONDS = 30

HISTORY_LEN = int(HISTORY_SECONDS / REFRESH_INTERVAL)
TIMES = [i * REFRESH_INTERVAL for i in range(-HISTORY_LEN + 1, 1)]

class NetworkManager:
    def __init__(self):
        self.process = None

    def _update_plot(self, _):
        now = time.time()
        try:
            counters = psutil.net_io_counters(pernic=True)[INTERFACE]
        except KeyError:
            # Interface not found, log 0
            self.rx_vals.append(0)
            self.tx_vals.append(0)
            return self.line_tx, self.line_rx, self.fill_tx, self.fill_rx

        delta = now - self.prev_time
        if delta <= 0:
            delta = 0.001

        # Calculate throughput in Mbps
        rx_mbps = (counters.bytes_recv - self.prev_counters.bytes_recv) / delta / 1024 / 1024 * 8
        tx_mbps = (counters.bytes_sent - self.prev_counters.bytes_sent) / delta / 1024 / 1024 * 8

        self.rx_vals.append(rx_mbps)
        self.tx_vals.append(tx_mbps)

        self.prev_counters = counters
        self.prev_time = now

        self.line_tx.set_data(TIMES, self.tx_vals)
        self.line_rx.set_data(TIMES, self.rx_vals)

        # Recreate polygon fills for plot
        self.fill_rx.remove()
        self.fill_tx.remove()
        self.fill_rx = self.ax.fill_between(TIMES, 0, self.rx_vals, color="#FF0000", alpha=0.4)
        self.fill_tx = self.ax.fill_between(TIMES, 0, self.tx_vals, color="#0000FF", alpha=0.4)

        max_val = max(max(self.rx_vals), max(self.tx_vals), 0.1)
        self.ax.set_ylim(0, max_val * 1.1)

        return self.line_tx, self.line_rx, self.fill_tx, self.fill_rx

    def _start(self):
        matplotlib.use("TkAgg")

        self.rx_vals = collections.deque([0.0] * HISTORY_LEN, maxlen=HISTORY_LEN)
        self.tx_vals = collections.deque([0.0] * HISTORY_LEN, maxlen=HISTORY_LEN)

        plt.rc('font', family='serif', size=10)
        self.fig, self.ax = plt.subplots()

        self.line_tx, = self.ax.plot([], [], label="TX", linewidth=1, color="#0000FF")
        self.line_rx, = self.ax.plot([], [], label="RX", linewidth=1, color="#FF0000")
        self.fill_tx = self.ax.fill_between(TIMES, 0, self.tx_vals, color="#0000FF", alpha=0.4)
        self.fill_rx = self.ax.fill_between(TIMES, 0, self.rx_vals, color="#FF0000", alpha=0.4)

        self.fig.subplots_adjust(left=0.14, right=0.96, top=0.96, bottom=0.14)
        self.ax.margins(0)
        self.ax.set_xlim(-HISTORY_SECONDS, 0)
        plt.legend(loc='upper left', fancybox=False, edgecolor="black")
        self.ax.set_xlabel("Time [s]", labelpad=0)
        self.ax.set_ylabel("Throughput [Mbps]", labelpad=0)
        self.ax.tick_params(direction="in", length=2.5, width=1)
        self.ax.grid(alpha=0.5)

        try:
            self.prev_counters = psutil.net_io_counters(pernic=True)[INTERFACE]
        except KeyError:
            # Fallback if interface is missing
            self.prev_counters = collections.namedtuple('IOCounters', ['bytes_recv', 'bytes_sent'])(0, 0)
        self.prev_time = time.time()

        # Configure borderless topmost matplotlib window
        manager = plt.get_current_fig_manager()
        if hasattr(manager, 'toolbar') and manager.toolbar is not None:
            manager.toolbar.pack_forget()

        # Tkinter window settings
        manager.window.overrideredirect(True)
        manager.window.geometry("382x300+0+600")
        manager.window.attributes('-topmost', True)

        # Store animation object to prevent it from being garbage collected
        self.anim = animation.FuncAnimation(
            self.fig, self._update_plot, interval=int(REFRESH_INTERVAL * 1000), blit=False, save_count=HISTORY_LEN
        )
        plt.show()

    def start_monitoring(self):
        if self.process and self.process.is_alive():
            print("NETWORK MANAGER process already launched")
            return
        self.process = multiprocessing.Process(target=self._start)
        self.process.start()
        print("NETWORK MANAGER process launched")

    def stop_monitoring(self):
        if self.process:
            self.process.terminate()
            self.process = None
            print("NETWORK MANAGER process terminated")
        else:
            print("No NETWORK MANAGER process to terminate")
