import socket
import threading
import time
import select
from collections import Counter, deque
import tkinter as tk
from tkinter import ttk

# CONFIGURAÇÃO
LOCAL_ADDR = "127.0.0.1"  # o cliente UO aponta aqui
LOCAL_PORT = 2593
REMOTE_HOST = "181.214.48.238"  # seu servidor real
REMOTE_PORT = 2593

DEBUG_PRINT = True

# controle de parada / conexões
stop_event = threading.Event()
active_connections = []

# stats globais compartilhadas
stats = {
    "sent_bytes": 0,
    "recv_bytes": 0,
    "sent_pkts": 0,
    "recv_pkts": 0,
    "sent_ids": Counter(),
    "recv_ids": Counter(),
    "recent_log": deque(maxlen=200),
    "sent_bps": deque(maxlen=60),
    "recv_bps": deque(maxlen=60),
    "sent_pps": deque(maxlen=60),
    "recv_pps": deque(maxlen=60),
    "last_sample_time": time.time(),
    "sent_since_last": 0,
    "recv_since_last": 0,
    "sent_pkts_since_last": 0,
    "recv_pkts_since_last": 0,
}
stats_lock = threading.Lock()

# Minimal packet length table (exemplo UO). -1 = variable
PACKET_LENGTHS = {
    0x00: 3,
    0x01: 7,
    0x02: 3,
    0x0A: 5,
    0x1D: 3,
    0x25: 9,
    0x73: 5,
    0xD6: -1,
    0xDC: -1,
}


def packet_info(direction, data):
    if not data:
        return
    packet_id = data[0]
    pkt_len = len(data)
    expected = PACKET_LENGTHS.get(packet_id)
    if expected is None:
        expected_text = "unknown"
    elif expected < 0:
        expected_text = "variable"
    else:
        expected_text = str(expected)

    hex_payload = data[:32].hex().upper()
    summary = f"{direction} id=0x{packet_id:02X} len={pkt_len} expected={expected_text} raw={hex_payload}" + ("..." if len(data) > 32 else "")
    if expected is not None and expected >= 0 and expected != pkt_len:
        summary += " [len mismatch]"

    with stats_lock:
        stats["recent_log"].appendleft(summary)

    # sempre grava no arquivo para copiar rapidamente
    with open("mitm_trace.log", "a", encoding="utf-8", errors="ignore") as f:
        f.write(summary + "\n")

    if DEBUG_PRINT:
        print(summary)

    return packet_id


def close_connection(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except Exception:
        pass
    try:
        sock.close()
    except Exception:
        pass


def forward(source, target, direction):
    # direction f.e. "C2S" ou "S2C"
    while not stop_event.is_set():
        try:
            ready, _, _ = select.select([source], [], [], 0.2)
        except Exception:
            break

        if not ready:
            continue

        try:
            data = source.recv(4096)
        except Exception as ex:
            if DEBUG_PRINT:
                print(f"forward({direction}) recv erro: {ex}")
            break

        if not data:
            if DEBUG_PRINT:
                print(f"forward({direction}) socket fechado (0 bytes)")
            break

        packet_id = packet_info(direction, data)

        with stats_lock:
            if direction == "C2S":
                stats["sent_bytes"] += len(data)
                stats["sent_pkts"] += 1
                stats["sent_pkts_since_last"] += 1
                stats["sent_since_last"] += len(data)
                stats["sent_ids"][packet_id] += 1
            else:
                stats["recv_bytes"] += len(data)
                stats["recv_pkts"] += 1
                stats["recv_pkts_since_last"] += 1
                stats["recv_since_last"] += len(data)
                stats["recv_ids"][packet_id] += 1

        try:
            target.sendall(data)
        except Exception:
            break

    with stats_lock:
        if source in active_connections:
            active_connections.remove(source)
        if target in active_connections:
            active_connections.remove(target)

    close_connection(target)
    close_connection(source)


def handle_client(client_socket, client_addr):
    with stats_lock:
        active_connections.append(client_socket)
    with client_socket:
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.settimeout(8)
            server_socket.connect((REMOTE_HOST, REMOTE_PORT))
            server_socket.settimeout(None)
        except Exception as e:
            msg = f"ERROR conectando distante {REMOTE_HOST}:{REMOTE_PORT}: {e}"
            print(msg)
            with stats_lock:
                stats["recent_log"].appendleft(msg)
            return

        with server_socket:
            with stats_lock:
                active_connections.append(server_socket)

            msg = f"Conexão estabelecida cliente {client_addr} -> servidor {REMOTE_HOST}:{REMOTE_PORT}"
            print(msg)
            with stats_lock:
                stats["recent_log"].appendleft(msg)

            t1 = threading.Thread(target=forward, args=(client_socket, server_socket, "C2S"), daemon=True)
            t2 = threading.Thread(target=forward, args=(server_socket, client_socket, "S2C"), daemon=True)
            t1.start(); t2.start()
            t1.join(); t2.join()


def start_proxy():
    if not REMOTE_HOST or REMOTE_HOST.lower() in ("ip_do_servidor", "server.imperialshard.com.br"):
        msg = f"[ERRO] REMOTE_HOST inválido: {REMOTE_HOST}. Atualize o script e rode novamente."
        print(msg)
        with stats_lock:
            stats["recent_log"].appendleft(msg)
        return

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listener.bind((LOCAL_ADDR, LOCAL_PORT))
        listener.listen(1)
    except OSError as e:
        msg = f"[ERRO] Falha ao bind em {LOCAL_ADDR}:{LOCAL_PORT} - {e}"
        print(msg)
        with stats_lock:
            stats["recent_log"].appendleft(msg)
        return

    with listener:
        msg = f"Proxy ativo {LOCAL_ADDR}:{LOCAL_PORT} -> {REMOTE_HOST}:{REMOTE_PORT}"
        print(msg)
        with stats_lock:
            stats["recent_log"].appendleft(msg)

        while not stop_event.is_set():
            try:
                client_sock, client_addr = listener.accept()
            except Exception as e:
                if stop_event.is_set():
                    break
                msg = f"[ERRO] accept(): {e}"
                print(msg)
                with stats_lock:
                    stats["recent_log"].appendleft(msg)
                break

            with stats_lock:
                stats["recent_log"].appendleft(f"Conexão cliente {client_addr}")

            threading.Thread(target=handle_client, args=(client_sock, client_addr), daemon=True).start()


def update_rate():
    while True:
        time.sleep(1.0)
        with stats_lock:
            stats["sent_bps"].append(stats["sent_since_last"])
            stats["recv_bps"].append(stats["recv_since_last"])
            stats["sent_pps"].append(stats["sent_pkts_since_last"])
            stats["recv_pps"].append(stats["recv_pkts_since_last"])
            stats["sent_since_last"] = 0
            stats["recv_since_last"] = 0
            stats["sent_pkts_since_last"] = 0
            stats["recv_pkts_since_last"] = 0


def draw_graph(canvas, values, color, y0, y1):
    canvas.delete("graph")
    if not values:
        return
    w = int(canvas.winfo_width() or 400)
    h = int(canvas.winfo_height() or 120)
    n = len(values)
    sx = w / max(n - 1, 1)
    maxv = max(values) if values else 1
    maxv = max(maxv, 1)
    prev = None
    for i, v in enumerate(values):
        x = int(i * sx)
        y = h - int((v / maxv) * h)
        if prev is not None:
            canvas.create_line(prev[0], prev[1], x, y, fill=color, tags="graph")
        prev = (x, y)


def start_dashboard():
    root = tk.Tk()
    root.title("UO MITM Proxy Dashboard")

    top = ttk.Frame(root, padding=6)
    top.pack(fill=tk.X)

    sent_label = ttk.Label(top, text="sent bytes: 0")
    sent_label.grid(row=0, column=0, sticky="w", padx=4)
    recv_label = ttk.Label(top, text="recv bytes: 0")
    recv_label.grid(row=0, column=1, sticky="w", padx=4)
    pps_label = ttk.Label(top, text="pps C2S/S2C: 0/0")
    pps_label.grid(row=0, column=2, sticky="w", padx=4)

    def export_log():
        with stats_lock:
            text = "\n".join(list(stats["recent_log"])[:200])
        with open("mitm_trace_export.txt", "w", encoding="utf-8", errors="ignore") as f:
            f.write(text)

    def copy_log():
        with stats_lock:
            text = "\n".join(list(stats["recent_log"])[:200])
        root.clipboard_clear()
        root.clipboard_append(text)
        if DEBUG_PRINT:
            print("Copiado para clipboard: mitm logs")

    btn_copy = ttk.Button(top, text="Copiar Log (clipboard)", command=copy_log)
    btn_copy.grid(row=0, column=3, sticky="w", padx=4)

    btn_export = ttk.Button(top, text="Exportar Log (arquivo)", command=export_log)
    btn_export.grid(row=0, column=4, sticky="w", padx=4)

    center = ttk.Frame(root, padding=6)
    center.pack(fill=tk.BOTH, expand=True)

    log_frame = ttk.Labelframe(center, text="Últimos eventos", width=400, height=250)
    log_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
    log_text = tk.Text(log_frame, state="disabled", wrap="none", height=20)
    log_text.pack(fill=tk.BOTH, expand=True)

    rhs = ttk.Frame(center)
    rhs.pack(side=tk.RIGHT, fill=tk.Y)

    sent_frame = ttk.Labelframe(rhs, text="Top SEND IDs")
    sent_frame.pack(fill=tk.BOTH, padx=4, pady=4)
    sent_list = tk.Listbox(sent_frame, height=10)
    sent_list.pack(fill=tk.BOTH)

    recv_frame = ttk.Labelframe(rhs, text="Top RECV IDs")
    recv_frame.pack(fill=tk.BOTH, padx=4, pady=4)
    recv_list = tk.Listbox(recv_frame, height=10)
    recv_list.pack(fill=tk.BOTH)

    graph_frame = ttk.Labelframe(root, text="Tráfego (bytes/s)")
    graph_frame.pack(fill=tk.BOTH, expand=False, padx=4, pady=4)
    graph = tk.Canvas(graph_frame, width=800, height=180, bg="white")
    graph.pack(fill=tk.BOTH, expand=True)

    def refresh():
        with stats_lock:
            sbytes = stats["sent_bytes"]
            rbytes = stats["recv_bytes"]
            spp = int(stats["sent_pps"][-1] if stats["sent_pps"] else 0)
            rpp = int(stats["recv_pps"][-1] if stats["recv_pps"] else 0)
            recent = list(stats["recent_log"])
            ts = stats["sent_ids"].most_common(10)
            tr = stats["recv_ids"].most_common(10)
            bps = list(stats["sent_bps"])
            rps = list(stats["recv_bps"])

        sent_label.config(text=f"sent bytes: {sbytes}")
        recv_label.config(text=f"recv bytes: {rbytes}")
        pps_label.config(text=f"pps C2S/S2C: {spp}/{rpp}")

        log_text.configure(state="normal")
        log_text.delete("1.0", tk.END)
        for line in recent[:30]:
            log_text.insert(tk.END, line + "\n")
        log_text.configure(state="disabled")

        sent_list.delete(0, tk.END)
        for pid, c in ts:
            sent_list.insert(tk.END, f"0x{pid:02X}: {c}")

        recv_list.delete(0, tk.END)
        for pid, c in tr:
            recv_list.insert(tk.END, f"0x{pid:02X}: {c}")

        graph.delete("all")
        draw_graph(graph, bps, "blue", 0, 0)
        draw_graph(graph, rps, "red", 0, 0)

        root.after(500, refresh)

    def close_all():
        if not stop_event.is_set():
            stop_event.set()
        with stats_lock:
            for sock in list(active_connections):
                close_connection(sock)
            active_connections.clear()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close_all)

    root.after(500, refresh)
    root.mainloop()


def main():
    threading.Thread(target=start_proxy, daemon=True).start()
    threading.Thread(target=update_rate, daemon=True).start()
    start_dashboard()


if __name__ == "__main__":
    main()
