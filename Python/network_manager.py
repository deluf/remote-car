
import multiprocessing
import psutil
import time
import collections
import matplotlib
import matplotlib.animation as animation
import matplotlib.pyplot as plt

INTERFACE = "utun10" # Tailscale's interface name
REFRESH_INTERVAL_S = 0.5
HISTORY_SECONDS_S = 30

HISTORY_LEN = int(HISTORY_SECONDS_S / REFRESH_INTERVAL_S)
TIMES = [i * REFRESH_INTERVAL_S for i in range(-HISTORY_LEN + 1, 0 + 1)]

class Network_Manager:

    def __init__(self):
        self.process = None

    def _update_plot(self, _):
        latest_io_counters_time = time.time()
        latest_io_counters = psutil.net_io_counters(pernic=True)[INTERFACE]
        delta_time = latest_io_counters_time - self.previous_io_counters_time

        rx_Mbps = (latest_io_counters.bytes_recv - self.previous_io_counters.bytes_recv) / delta_time / 1024 / 1024 * 8
        tx_Mbps = (latest_io_counters.bytes_sent - self.previous_io_counters.bytes_sent) / delta_time / 1024 / 1024 * 8

        self.rx_vals.append(rx_Mbps)
        self.tx_vals.append(tx_Mbps)

        self.previous_io_counters = latest_io_counters
        self.previous_io_counters_time = latest_io_counters_time

        self.line_tx.set_data(TIMES, self.tx_vals)
        self.line_rx.set_data(TIMES, self.rx_vals)
        
        # Remove old fills
        for coll in [self.fill_rx, self.fill_tx]:
            coll.remove()
        self.fill_rx = self.ax.fill_between(TIMES, 0, self.rx_vals, color="#FF0000", alpha=0.4)
        self.fill_tx = self.ax.fill_between(TIMES, 0, self.tx_vals, color="#0000FF", alpha=0.4)

        max_value = max(max(self.rx_vals), max(self.tx_vals), 0.1)
        self.ax.set_ylim(0, max_value * 1.1)
        
        return self.line_tx, self.line_rx, self.fill_tx, self.fill_rx

    def _start(self):
        matplotlib.use("TkAgg")

        self.rx_vals = collections.deque([0] * HISTORY_LEN, maxlen=HISTORY_LEN)
        self.tx_vals = collections.deque([0] * HISTORY_LEN, maxlen=HISTORY_LEN)

        plt.rc('font', family='serif')
        plt.rc('font', size=10)
        #plt.rcParams["figure.figsize"] = (, 6)

        self.fig, self.ax = plt.subplots()
        ax = self.ax
        fig = self.fig

        self.line_tx, = ax.plot([], [], label="TX", linewidth=1, color="#0000FF")
        self.line_rx, = ax.plot([], [], label="RX", linewidth=1, color="#FF0000")
        self.fill_tx = ax.fill_between(TIMES, 0, self.tx_vals, color="#0000FF", alpha=0.4)
        self.fill_rx = ax.fill_between(TIMES, 0, self.rx_vals, color="#FF0000", alpha=0.4)

        fig.subplots_adjust(left=0.14, right=0.96, top=0.96, bottom=0.14)
        ax.margins(0)
        ax.set_xlim(-HISTORY_SECONDS_S, 0)
        plt.legend(loc='upper left', fancybox=False, edgecolor="black")
        ax.set_xlabel("Time [s]", labelpad=0)
        ax.set_ylabel("Throughput [Mbps]", labelpad=0)
        ax.tick_params(direction="in", length=2.5, width=1)
        ax.grid(alpha=0.5)

        self.previous_io_counters = psutil.net_io_counters(pernic=True)[INTERFACE]
        self.previous_io_counters_time = time.time()

        # Remove matplotlib's toolbar
        manager = plt.get_current_fig_manager()
        if hasattr(manager, 'toolbar') and manager.toolbar is not None:
            manager.toolbar.pack_forget()

        manager.window.overrideredirect(True)       # Borderless
        #manager.window.geometry("382x300+1112+300") # Set starting position
        manager.window.geometry(f"382x300+0+{900-300}") # Set starting position
        manager.window.attributes('-topmost', True) # Always on top

        # It's required to keep in memory the returned value of FuncAnimation before calling plt.show()
        _ = animation.FuncAnimation(self.fig, self._update_plot, interval=REFRESH_INTERVAL_S*1000, blit=False, save_count=HISTORY_LEN)
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
