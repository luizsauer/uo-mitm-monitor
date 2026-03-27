import tkinter as tk
from tkinter import scrolledtext
import threading
import time
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from collections import deque

from uo_mitm_proxy import stats, lock  # importa estado global do proxy

history = {
    "ts": deque(maxlen=120),
    "sent_bytes": deque(maxlen=120),
    "recv_bytes": deque(maxlen=120),
    "sent_pkts": deque(maxlen=120),
    "recv_pkts": deque(maxlen=120)
}

def refresh_loop(text_widget, sent_var, recv_var, fig_canvas):
    while True:
        time.sleep(1)
        with lock:
            sent_bytes = stats["sent_bytes"]
            recv_bytes = stats["recv_bytes"]
            sent_pkts = stats["sent_pkts"]
            recv_pkts = stats["recv_pkts"]
            line_list = list(stats["log"])[-20:]
            send_top = stats["sent_ids"].most_common(10)
            recv_top = stats["recv_ids"].most_common(10)
        sent_var.set(f"{sent_bytes:,}")
        recv_var.set(f"{recv_bytes:,}")

        text_widget.configure(state="normal")
        text_widget.delete("1.0", tk.END)
        text_widget.insert(tk.END, "Últimos eventos:\n")
        for L in line_list:
            text_widget.insert(tk.END, L + "\n")
        text_widget.insert(tk.END, "\nTop SEND packet IDs:\n")
        for k,v in send_top:
            text_widget.insert(tk.END, f"0x{k}: {v}\n")
        text_widget.insert(tk.END, "\nTop RECV packet IDs:\n")
        for k,v in recv_top:
            text_widget.insert(tk.END, f"0x{k}: {v}\n")
        text_widget.configure(state="disabled")

        t = time.time()
        history["ts"].append(t)
        history["sent_bytes"].append(sent_bytes)
        history["recv_bytes"].append(recv_bytes)
        history["sent_pkts"].append(sent_pkts)
        history["recv_pkts"].append(recv_pkts)

        ax1, ax2 = fig_canvas.figure.axes
        ax1.clear(); ax2.clear()
        ax1.plot(history["ts"], history["sent_bytes"], label="sent bytes")
        ax1.plot(history["ts"], history["recv_bytes"], label="recv bytes")
        ax1.legend(loc="upper left")
        ax1.set_ylabel("bytes")
        ax2.plot(history["ts"], history["sent_pkts"], label="sent pkt")
        ax2.plot(history["ts"], history["recv_pkts"], label="recv pkt")
        ax2.legend(loc="upper left")
        ax2.set_ylabel("packets")
        fig_canvas.draw_idle()

def start_dashboard():
    root = tk.Tk()
    root.title("UO MITM Dashboard")
    frm = tk.Frame(root)
    frm.pack(fill="both", expand=True)

    row = tk.Frame(frm); row.pack(fill="x")
    sent_var = tk.StringVar(value="0")
    recv_var = tk.StringVar(value="0")
    tk.Label(row, text="Sent bytes:").pack(side="left")
    tk.Label(row, textvariable=sent_var).pack(side="left", padx=8)
    tk.Label(row, text="Recv bytes:").pack(side="left", padx=20)
    tk.Label(row, textvariable=recv_var).pack(side="left", padx=8)

    text_widget = scrolledtext.ScrolledText(frm, height=18, width=100, state="disabled", font=("Consolas", 10))
    text_widget.pack(fill="both", expand=True, padx=4, pady=4)

    fig = Figure(figsize=(10, 4), dpi=100)
    ax1 = fig.add_subplot(211); ax2 = fig.add_subplot(212, sharex=ax1)
    canvas = FigureCanvasTkAgg(fig, master=frm)
    canvas.get_tk_widget().pack(fill="both", expand=True)

    threading.Thread(target=refresh_loop, args=(text_widget, sent_var, recv_var, canvas), daemon=True).start()
    root.mainloop()

if __name__ == "__main__":
    start_dashboard()