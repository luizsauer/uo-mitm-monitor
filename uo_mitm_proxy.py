"""
UO MITM Proxy — Arquitetura de Baixa Latência com Logs em Background.
"""

import socket
import threading
import time
import select
import queue
from collections import deque, Counter

# --- TABELAS DE PROTOCOLO UO ---
PACKET_LENGTHS = {
    0x02: 7, 0x05: 5, 0x06: 5, 0x07: 7, 0x09: 5, 0x34: 10, 0x5D: 73, 0x72: 5, 0x73: 2, 
    0x80: 62, 0x8C: 11, 0xA0: 3, 0x11: -1, 0x1A: -1, 0x1B: 37, 0x1C: -1, 0x1D: 5, 0x20: 19,
    0x21: 8, 0x22: 3, 0x25: 20, 0x3A: -1, 0x4E: 6, 0x4F: 2, 0x70: -1, 0x77: 17, 0x78: -1,
    0xA1: 9, 0xA8: -1, 0xAF: 13, 0xB0: -1, 0xB9: 3, 0xBC: 3, 0xBF: -1, 0xD6: -1, 0xF3: 24
}

PACKET_NAMES = {
    0x02: "MoveReq", 0x1B: "WorldItem", 0x1C: "Msg", 0x5D: "LoginChar",
    0x73: "Ping", 0x78: "MobileIncoming", 0x80: "LoginReq", 0x8C: "Relay",
    0xAD: "Speech", 0xBF: "GenInfo", 0xD6: "MegaCliloc", 0xBC: "Season"
}

# ─── Estado Global ────────────────────────────────────────────
stop_event = threading.Event()
event_queue = None

stats = {
    "c2s_bytes": 0, "s2c_bytes": 0, "c2s_pkts": 0, "s2c_pkts": 0,
    "c2s_ids": Counter(), "s2c_ids": Counter(), "connections": 0,
    "start_time": time.time(),
    "stats_times": deque(maxlen=300),
    "c2s_bps": deque(maxlen=300), "s2c_bps": deque(maxlen=300),
    "c2s_pps": deque(maxlen=300), "s2c_pps": deque(maxlen=300),
    "_c2s_bytes_since": 0, "_s2c_bytes_since": 0,
    "_c2s_pkts_since":  0, "_s2c_pkts_since":  0,
}
stats_lock = threading.Lock()

# Fila para não travar a rede
log_queue = queue.Queue(maxsize=1000)

def _push(ev):
    if event_queue:
        try: event_queue.put_nowait(ev)
        except: pass

def extract_packets(buf: bytearray) -> list:
    packets = []
    while len(buf) > 0:
        opcode = buf[0]
        expected = PACKET_LENGTHS.get(opcode)
        if expected is None:
            packets.append(bytes(buf))
            buf.clear(); break
        if expected >= 0:
            if len(buf) < expected: break
            packets.append(bytes(buf[:expected]))
            del buf[:expected]
        else:
            if len(buf) < 3: break
            pkt_len = (buf[1] << 8) | buf[2]
            if pkt_len < 3 or pkt_len > 15000:
                packets.append(bytes(buf))
                buf.clear(); break
            if len(buf) < pkt_len: break
            packets.append(bytes(buf[:pkt_len]))
            del buf[:pkt_len]
    return packets

def log_worker():
    """Thread separada para análise. Se ela ficar lenta, o jogo NÃO trava."""
    local_bufs = {"C2S": bytearray(), "S2C": bytearray()}
    while not stop_event.is_set():
        try:
            direction, data, cid = log_queue.get(timeout=0.5)
            buf = local_bufs[direction]
            buf.extend(data)
            
            pkts = extract_packets(buf)
            for p in pkts:
                opcode = p[0]
                with stats_lock:
                    if direction == "C2S":
                        stats["c2s_pkts"] += 1; stats["_c2s_pkts_since"] += 1; stats["c2s_ids"][opcode] += 1
                    else:
                        stats["s2c_pkts"] += 1; stats["_s2c_pkts_since"] += 1; stats["s2c_ids"][opcode] += 1
                
                _push({
                    "type": "packet", "dir": direction, "opcode": opcode,
                    "opcode_hex": f"0x{opcode:02X}", "name": PACKET_NAMES.get(opcode, "Unknown"),
                    "size": len(p), "ts": time.time(), "ts_str": time.strftime("%H:%M:%S"),
                    "raw_hex": p.hex().upper(), "conn_id": cid
                })
            
            if len(buf) > 10000: buf.clear()
        except queue.Empty: continue
        except: continue

def forward(source, target, direction, cid, listen_port):
    """Ponte de Rede Ultra-Rápida. Apenas entrega pacotes."""
    proxy_ip = b'\x7f\x00\x00\x01'
    proxy_port = int(listen_port).to_bytes(2, 'big')
    bytes_transferred = 0

    while not stop_event.is_set():
        try:
            r, _, _ = select.select([source], [], [], 0.05)
            if not r: continue
            
            data = source.recv(32768)
            if not data: break

            modified = bytearray(data)
            
            # Interceptação Segura 0x8C (Relay)
            # O 0x8C ocorre apenas no inicio da conexão com o Login Server. Ao restringir para
            # os primeiros 200 bytes, garantimos que não haja corrupção acidental do tráfego
            # compactado de mapa/jogo (que pode gerar chunks iniciando em 0x8C por coincidência).
            if direction == "S2C" and bytes_transferred < 200 and len(modified) >= 11:
                idx = modified.find(b'\x8C')
                if idx != -1 and idx + 11 <= len(modified):
                    print(f"[RELAY] Corrigindo redirecionamento offset {idx} para 127.0.0.1:{listen_port}")
                    modified[idx+1:idx+5] = proxy_ip
                    modified[idx+5:idx+7] = proxy_port

            bytes_transferred += len(modified)
            
            # ENTREGA IMEDIATA (Prioridade 1)
            target.sendall(modified)

            # Contabilidade Rápida (Prioridade 2)
            with stats_lock:
                if direction == "C2S":
                    stats["c2s_bytes"] += len(data); stats["_c2s_bytes_since"] += len(data)
                else:
                    stats["s2c_bytes"] += len(data); stats["_s2c_bytes_since"] += len(data)

            # Joga para o log em background (Não espera terminar)
            try:
                log_queue.put_nowait((direction, bytes(modified), cid))
            except: pass # Se a fila lotar, ignora o log para salvar o jogo

        except: break

    try: source.close(); target.close()
    except: pass

class UOProxy:
    def __init__(self, target_host, target_port, listen_port, listen_host='0.0.0.0'):
        self.target_host = target_host
        self.target_port = int(target_port)
        self.listen_port = int(listen_port)
        self.listen_host = listen_host
        self.running = False
        self.server_sock = None

    def start(self):
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_sock.bind((self.listen_host, self.listen_port))
            self.server_sock.listen(50)
            self.running = True
            stop_event.clear()
            
            # Inicia o analisador em background
            threading.Thread(target=log_worker, daemon=True).start()
            
            print(f"[PROXY] Ativado: {self.listen_port} -> {self.target_host}:{self.target_port}")
            while not stop_event.is_set():
                try:
                    self.server_sock.settimeout(0.5)
                    client, addr = self.server_sock.accept()
                    threading.Thread(target=self.handle_client, args=(client, addr), daemon=True).start()
                except socket.timeout: continue
                except: break
        except Exception as e:
            print(f"[ERRO] Proxy: {e}")
            self.running = False
            return False
        return True

    def stop(self):
        stop_event.set()
        self.running = False
        if self.server_sock: self.server_sock.close()

    def handle_client(self, client_sock, addr):
        remote_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            remote_sock.connect((self.target_host, self.target_port))
        except: client_sock.close(); return

        with stats_lock: stats["connections"] += 1
        cid = int(time.time() * 1000) % 10000
        _push({"type":"conn", "msg":f"Conectado: {addr}", "status":"connected", "ts_str":time.strftime("%H:%M:%S")})

        t1 = threading.Thread(target=forward, args=(client_sock, remote_sock, "C2S", cid, self.listen_port), daemon=True)
        t2 = threading.Thread(target=forward, args=(remote_sock, client_sock, "S2C", cid, self.listen_port), daemon=True)
        t1.start(); t2.start()
        t1.join(); t2.join()

        with stats_lock: stats["connections"] -= 1
        _push({"type":"conn", "msg":f"Desconectado", "status":"disconnected", "ts_str":time.strftime("%H:%M:%S")})

def reset_stats():
    with stats_lock:
        for k in ["c2s_bytes", "s2c_bytes", "c2s_pkts", "s2c_pkts", "_c2s_bytes_since", "_s2c_bytes_since", "_c2s_pkts_since", "_s2c_pkts_since"]:
            stats[k] = 0
        stats["c2s_ids"].clear(); stats["s2c_ids"].clear(); stats["start_time"] = time.time()
