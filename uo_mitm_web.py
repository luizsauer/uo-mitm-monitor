"""
UO MITM Web Server — Flask + SocketIO
"""

import threading
import queue
import time
import json
import os
from collections import deque

from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO

import uo_mitm_proxy as proxy

# ─── Configurações ────────────────────────────────────────────
WEB_HOST    = "0.0.0.0"
WEB_PORT    = 5000
LOG_FILE    = "mitm_trace.jsonl"
CONFIG_FILE = "config.json"
MAX_HISTORY = 5000
# ──────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder="static")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

event_queue = queue.Queue(maxsize=50000)
packet_history = deque(maxlen=MAX_HISTORY)
proxy.event_queue = event_queue

proxy_instance = None
proxy_thread = None

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except: pass
    return {
        "target_ip": "181.214.48.238",
        "target_port": 2593,
        "listen_port": 2593,
        "relay_ip": "0.0.0.0",
        "auto_start": False
    }

config = load_config()

def event_broadcaster():
    while True:
        try:
            ev = event_queue.get(timeout=0.05)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev) + "\n")
            packet_history.append(ev)
            socketio.emit("event", ev)
        except queue.Empty: continue
        except: pass

def stats_broadcaster():
    while True:
        time.sleep(1)
        with proxy.stats_lock:
            s = proxy.stats
            now_ts = time.strftime("%H:%M:%S")
            s["stats_times"].append(now_ts)
            s["c2s_bps"].append(s["_c2s_bytes_since"])
            s["s2c_bps"].append(s["_s2c_bytes_since"])
            s["c2s_pps"].append(s["_c2s_pkts_since"])
            s["s2c_pps"].append(s["_s2c_pkts_since"])
            
            payload = {
                "c2s_bytes": s["c2s_bytes"], "s2c_bytes": s["s2c_bytes"],
                "c2s_pkts": s["c2s_pkts"], "s2c_pkts": s["s2c_pkts"],
                "connections": s["connections"],
                "stats_times": list(s["stats_times"]),
                "c2s_bps": list(s["c2s_bps"]), "s2c_bps": list(s["s2c_bps"]),
                "c2s_pps": list(s["c2s_pps"]), "s2c_pps": list(s["s2c_pps"]),
                "top_c2s": [(f"0x{k:02X}", proxy.PACKET_NAMES.get(k, "Unknown"), v) for k, v in s["c2s_ids"].most_common(15)],
                "top_s2c": [(f"0x{k:02X}", proxy.PACKET_NAMES.get(k, "Unknown"), v) for k, v in s["s2c_ids"].most_common(15)],
                "uptime": int(time.time() - s["start_time"]),
                "proxy_running": proxy_instance.running if proxy_instance else False
            }
            s["_c2s_bytes_since"] = 0; s["_s2c_bytes_since"] = 0
            s["_c2s_pkts_since"] = 0; s["_s2c_pkts_since"] = 0
            
        socketio.emit("stats", payload)

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/status")
def api_status():
    return jsonify({
        "running": proxy_instance.running if proxy_instance else False,
        "config": config,
        "stats": {
            "connections": proxy.stats["connections"],
            "uptime": int(time.time() - proxy.stats["start_time"])
        }
    })

@app.route("/api/config/save", methods=["POST"])
def api_config_save():
    global config
    data = request.json
    config.update(data)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)
    return jsonify({"status": "ok", "msg": "Configuração salva com sucesso."})

@app.route("/api/proxy/start", methods=["POST"])
def api_proxy_start():
    global proxy_instance, proxy_thread, config
    if proxy_instance and proxy_instance.running:
        return jsonify({"status": "error", "msg": "Proxy já está rodando."})
    
    # Atualiza config com dados do request
    data = request.json
    config.update(data)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)
    
    proxy_instance = proxy.UOProxy(config["target_ip"], config["target_port"], config["listen_port"], config["relay_ip"])
    proxy_thread = threading.Thread(target=proxy_instance.start, daemon=True)
    proxy_thread.start()
    
    time.sleep(0.5) # Espera bind
    if proxy_instance.running:
        return jsonify({"status": "ok", "msg": "Proxy iniciado com sucesso."})
    else:
        return jsonify({"status": "error", "msg": "Falha ao iniciar proxy. Verifique se a porta está em uso."})

@app.route("/api/proxy/stop", methods=["POST"])
def api_proxy_stop():
    global proxy_instance
    if proxy_instance:
        proxy_instance.stop()
    return jsonify({"status": "ok", "msg": "Proxy parado."})

@app.route("/api/reset", methods=["POST"])
def api_reset():
    packet_history.clear()
    if os.path.exists(LOG_FILE):
        try: os.remove(LOG_FILE)
        except: pass
    proxy.reset_stats()
    return jsonify({"status": "ok"})

@app.route("/api/export")
def api_export():
    if os.path.exists(LOG_FILE):
        return send_from_directory(".", LOG_FILE, as_attachment=True)
    return "Arquivo não encontrado", 404

if __name__ == "__main__":
    threading.Thread(target=event_broadcaster, daemon=True).start()
    threading.Thread(target=stats_broadcaster, daemon=True).start()
    print(f"[WEB] Servidor em http://localhost:{WEB_PORT}")
    socketio.run(app, host="0.0.0.0", port=WEB_PORT, debug=False)
