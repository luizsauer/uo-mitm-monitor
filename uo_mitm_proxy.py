"""
UO MITM Proxy — Núcleo TCP resiliente e controlável.
"""

import socket
import threading
import time
import select
import queue
from collections import deque, Counter

# --- TABELAS DE PROTOCOLO UO ---
PACKET_LENGTHS = {
    0x00: 104, 0x01: 5,   0x02: 7,   0x03: -1,  0x04: 2,
    0x05: 5,   0x06: 5,   0x07: 7,   0x08: 14,  0x09: 5,
    0x0A: 11,  0x0B: 7,   0x0C: -1,  0x0D: -1,  0x0E: 6,
    0x0F: -1,  0x10: -1,  0x11: -1,  0x12: -1,  0x13: -1,
    0x14: 6,   0x15: 9,   0x16: -1,  0x17: -1,  0x18: -1,
    0x1A: -1,  0x1B: 37,  0x1C: -1,  0x1D: 5,   0x1E: 4,
    0x20: 19,  0x21: 8,   0x22: 3,   0x23: -1,  0x24: 9,
    0x25: 21,  0x26: 10,  0x27: 2,   0x28: 2,   0x29: 1,
    0x2A: 5,   0x2B: 2,   0x2C: 2,   0x2D: 23,  0x2E: 27,
    0x2F: 10,  0x30: 14,  0x31: 1,   0x32: 2,   0x33: -1,
    0x34: 10,  0x36: -1,  0x38: 7,   0x3A: -1,  0x3B: -1,
    0x3C: -1,  0x3E: 8,   0x3F: -1,  0x40: -1,  0x42: 2,
    0x45: 5,   0x46: -1,  0x47: 11,  0x4B: 11,  0x4C: 2,
    0x4D: 2,   0x4E: 2,   0x4F: 2,   0x54: -1,  0x55: 1,
    0x56: -1,  0x57: -1,  0x58: -1,  0x5D: 73,  0x61: -1,
    0x62: -1,  0x65: 4,   0x66: -1,  0x69: -1,  0x6C: 19,
    0x6D: 3,   0x6E: 14,  0x6F: -1,  0x70: -1,  0x71: -1,
    0x72: 5,   0x73: 2,   0x74: -1,  0x75: -1,  0x76: 16,
    0x77: 17,  0x78: -1,  0x79: -1,  0x7C: -1,  0x80: 62,
    0x81: 2,   0x82: 2,   0x83: -1,  0x86: -1,  0x88: -1,
    0x89: -1,  0x8A: -1,  0x8B: 2,   0x8C: 11,  0x8D: -1,
    0x8E: -1,  0x8F: -1,  0x91: 65,  0x93: -1,  0x95: 9,
    0x97: 2,   0x98: -1,  0x99: -1,  0x9A: -1,  0x9B: -1,
    0x9E: -1,  0x9F: -1,  0xA0: 3,   0xA1: 9,   0xA2: 5,
    0xA3: 9,   0xA4: 149, 0xA5: -1,  0xA6: -1,  0xA8: -1,
    0xA9: -1,  0xAA: -1,  0xAC: -1,  0xAD: -1,  0xAE: -1,
    0xAF: 10,  0xB0: -1,  0xB2: -1,  0xB5: -1,  0xB6: -1,
    0xB7: -1,  0xB8: -1,  0xB9: 5,   0xBB: 9,   0xBC: 3,
    0xBD: -1,  0xBE: -1,  0xBF: -1,  0xC0: 36,  0xC1: -1,
    0xC2: -1,  0xC4: -1,  0xC6: 1,   0xC8: 2,   0xC9: 6,
    0xCA: 6,   0xCB: 7,   0xD3: -1,  0xD4: -1,  0xD6: -1,
    0xD7: -1,  0xD8: -1,  0xD9: -1,  0xDC: 9,   0xDD: -1,
    0xDE: -1,  0xDF: -1,  0xE0: -1,  0xE1: -1,  0xE2: 4,
    0xE3: -1,  0xE5: -1,  0xEF: -1,  0xF0: -1,  0xF1: -1,
    0xF2: -1,  0xF3: -1,  0xF5: -1,  0xF6: -1,  0xF7: -1,
}

PACKET_NAMES = {
    0x00: "CreateCharacter",    0x01: "Disconnect",
    0x02: "MoveReq",            0x03: "AsciiSpeech",
    0x11: "MobileStatus",       0x1B: "WorldItem",
    0x1C: "AsciiMessage",       0x1D: "RemoveObject",
    0x20: "MobileUpdate",       0x22: "MoveACK",
    0x25: "EquipItem",          0x34: "PlayerQuery",
    0x3A: "Skills",             0x3C: "ContainerContents",
    0x55: "LoginConfirm",       0x5D: "LoginChar",
    0x6C: "Target",             0x72: "WarMode",
    0x73: "Ping",               0x78: "MobileIncoming",
    0x80: "LoginReq",           0x8C: "ServerRelay",
    0x91: "GameLogin",          0xA8: "ServerList",
    0xA9: "CharacterList",      0xAE: "UniMessage",
    0xBF: "GeneralInfo",        0xD6: "MegaCliloc",
    0xDD: "CompressedGump",     0xEF: "LoginSeed",
}

# ─── Estado Global ────────────────────────────────────────────
stop_event = threading.Event()
proxy_enabled = True
event_queue = None

stats = {
    "c2s_bytes": 0, "s2c_bytes": 0,
    "c2s_pkts":  0, "s2c_pkts":  0,
    "c2s_ids": Counter(), "s2c_ids": Counter(),
    "connections": 0,
    "start_time": time.time(),
    "c2s_bps": deque([0]*60, maxlen=60), "s2c_bps": deque([0]*60, maxlen=60),
    "c2s_pps": deque([0]*60, maxlen=60), "s2c_pps": deque([0]*60, maxlen=60),
    "_c2s_bytes_since": 0, "_s2c_bytes_since": 0,
    "_c2s_pkts_since":  0, "_s2c_pkts_since":  0,
}
stats_lock = threading.Lock()

def reset_stats():
    with stats_lock:
        for k in ["c2s_bytes", "s2c_bytes", "c2s_pkts", "s2c_pkts", "_c2s_bytes_since", "_s2c_bytes_since", "_c2s_pkts_since", "_s2c_pkts_since"]:
            stats[k] = 0
        stats["c2s_ids"].clear()
        stats["s2c_ids"].clear()
        stats["start_time"] = time.time()

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
            packets.append(bytes(buf[:1]))
            del buf[:1]
            continue
        if expected >= 0:
            if len(buf) < expected: break
            packets.append(bytes(buf[:expected]))
            del buf[:expected]
        else:
            if len(buf) < 3: break
            pkt_len = (buf[1] << 8) | buf[2]
            if pkt_len < 3 or pkt_len > 15000:
                del buf[:1]
                continue
            if len(buf) < pkt_len: break
            packets.append(bytes(buf[:pkt_len]))
            del buf[:pkt_len]
    return packets

def forward(source, target, direction, conn_id, target_host):
    log_buf = bytearray()
    
    # Pre-calcular bytes do IP remoto para interceptação rápida
    try:
        remote_ip_bytes = socket.inet_aton(target_host)
    except:
        remote_ip_bytes = None

    while not stop_event.is_set():
        try:
            r, _, _ = select.select([source], [], [], 0.2)
            if not r: continue
            
            data = source.recv(32768)
            if not data: break

            with stats_lock:
                if direction == "C2S":
                    stats["c2s_bytes"] += len(data)
                    stats["_c2s_bytes_since"] += len(data)
                else:
                    stats["s2c_bytes"] += len(data)
                    stats["_s2c_bytes_since"] += len(data)

            if proxy_enabled:
                modified = bytearray(data)
                
                # Interceptação de Relay (0x8C)
                if direction == "S2C" and remote_ip_bytes:
                    # Se o pacote 0x8C contiver o IP do servidor real, mudamos para 127.0.0.1
                    idx = modified.find(b'\x8c' + remote_ip_bytes)
                    if idx != -1:
                        print(f"[PROXY] Interceptado Relay em offset {idx}. Redirecionando para 127.0.0.1")
                        modified[idx+1:idx+5] = b'\x7f\x00\x00\x01'
                
                target.sendall(modified)

                # Logging
                log_buf.extend(modified)
                pkts = extract_packets(log_buf)
                if pkts:
                    for p in pkts:
                        opcode = p[0]
                        with stats_lock:
                            if direction == "C2S":
                                stats["c2s_pkts"] += 1
                                stats["_c2s_pkts_since"] += 1
                                stats["c2s_ids"][opcode] += 1
                            else:
                                stats["s2c_pkts"] += 1
                                stats["_s2c_pkts_since"] += 1
                                stats["s2c_ids"][opcode] += 1
                        
                        _push({
                            "type": "packet", "dir": direction, "opcode": opcode,
                            "opcode_hex": f"0x{opcode:02X}", "name": PACKET_NAMES.get(opcode, "Unknown"),
                            "size": len(p), "ts": time.time(), "ts_str": time.strftime("%H:%M:%S"),
                            "raw_hex": p.hex().upper(), "conn_id": conn_id
                        })
                
                if len(log_buf) > 4096:
                    _push({
                        "type": "packet", "dir": direction, "opcode": 0xFF,
                        "opcode_hex": "0x--", "name": "Data Chunk / Compressed",
                        "size": len(log_buf), "ts": time.time(), "ts_str": time.strftime("%H:%M:%S"),
                        "raw_hex": log_buf[:128].hex().upper() + "...", "conn_id": conn_id
                    })
                    log_buf.clear()

        except: break

    try: source.close()
    except: pass
    try: target.close()
    except: pass

class UOProxy:
    def __init__(self, target_host, target_port, listen_port, listen_host='0.0.0.0'):
        self.target_host = target_host
        self.target_port = int(target_port)
        self.listen_port = int(listen_port)
        self.listen_host = listen_host
        self.running = False
        self.server_sock = None
        self.threads = []

    def start(self):
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_sock.bind((self.listen_host, self.listen_port))
            self.server_sock.listen(50)
            self.running = True
            print(f"[PROXY] Escutando em {self.listen_host}:{self.listen_port} -> {self.target_host}:{self.target_port}")
        except Exception as e:
            print(f"[PROXY] Erro ao iniciar: {e}")
            self.running = False
            return False

        stop_event.clear()
        
        while not stop_event.is_set():
            try:
                self.server_sock.settimeout(0.5)
                client_sock, addr = self.server_sock.accept()
                t = threading.Thread(target=self.handle_client, args=(client_sock, addr), daemon=True)
                t.start()
                self.threads.append(t)
            except socket.timeout: continue
            except: break
        
        self.stop()
        return True

    def stop(self):
        stop_event.set()
        self.running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except: pass
        print("[PROXY] Parado.")

    def handle_client(self, client_sock, addr):
        remote_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        remote_sock.settimeout(5.0)
        try:
            remote_sock.connect((self.target_host, self.target_port))
            remote_sock.settimeout(None)
        except:
            client_sock.close()
            return

        with stats_lock: stats["connections"] += 1
        cid = int(time.time() * 1000) % 10000
        _push({"type": "conn", "msg": f"Nova Conexão: {addr}", "status": "connected", "ts_str": time.strftime("%H:%M:%S")})

        t1 = threading.Thread(target=forward, args=(client_sock, remote_sock, "C2S", cid, self.target_host), daemon=True)
        t2 = threading.Thread(target=forward, args=(remote_sock, client_sock, "S2C", cid, self.target_host), daemon=True)
        t1.start(); t2.start()
        t1.join(); t2.join()

        with stats_lock: stats["connections"] -= 1
        _push({"type": "conn", "msg": f"Fechado: {addr}", "status": "disconnected", "ts_str": time.strftime("%H:%M:%S")})
