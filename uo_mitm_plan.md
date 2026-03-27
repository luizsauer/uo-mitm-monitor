# 🛡️ UO MITM Network Monitor — Plano de Implementação

## Objetivo
Sistema completo de monitoramento de tráfego de rede entre o cliente UO (ClassicUO) e o servidor ImperialShard,
usando um proxy man-in-the-middle local. Tudo em um único processo Python com UI web moderna (Flask + JS),
permitindo ver, analisar, filtrar e diagnosticar crashes e problemas de rede em tempo real.

---

## ❌ Problemas no [uo_mitm_app.py](file:///d:/UO/imperial-shard-imperialuoNova/uo_mitm_app.py) atual

1. **Parsing de pacotes errado** — O proxy faz `recv(4096)` e trata o bloco inteiro como um pacote. Em UO, 
   múltiplos packets podem chegar no mesmo recv(), ou um packet pode ser fragmentado. Sem framing correto, 
   `data[0]` frequentemente é lixo.

2. **Tabela PACKET_LENGTHS incompleta** — Só tem ~8 entradas. UO tem >200 opcodes. Sem saber o tamanho, 
   não dá para separar pacotes do stream TCP.

3. **Thread de UI (tkinter) + threads de proxy travando** — O tkinter não é thread-safe. As threads de
   forward chamam diretamente funções que usam widgets.

4. **Gráfico tkinter Canvas básico** — Difícil de ler, sem labels, sem zoom, sem hover.

5. **Sem filtros** — Não dá para filtrar por opcode, direção, tamanho, etc.

6. **Sem log persistente decente** — `mitm_trace.log` existe mas sem timestamps.

7. **Dashboard só mostra 30 linhas** — log_text só exibe os últimos 30 eventos.

---

## ✅ Arquitetura da Nova Solução

```
uo_mitm_proxy.py        — Proxy TCP puro (threading, sem UI)
uo_mitm_web.py          — Servidor Flask/SocketIO (API + WebSocket push)
static/
  index.html            — Dashboard HTML5 + Chart.js + DaisyUI/Tailwind CDN
  app.js                — Lógica de UI (filtros, gráficos, tabelas)
  style.css             — Estilos customizados
mitm_trace.jsonl        — Log persistente (JSON Lines, um packet por linha)
```

**Como rodar:** `python uo_mitm_web.py` → abre browser em `http://localhost:5000`

---

## 📁 Estrutura de Arquivos Completa

```
d:\UO\imperial-shard-imperialuoNova\
├── uo_mitm_proxy.py          (NOVO — proxy TCP robusto com framing)
├── uo_mitm_web.py            (NOVO — Flask + flask-socketio server)
├── static\
│   ├── index.html            (NOVO — dashboard principal)
│   ├── app.js                (NOVO — lógica JS)
│   └── style.css             (NOVO — estilos dark mode)
├── mitm_trace.jsonl          (auto-gerado em runtime)
└── [arquivos antigos mantidos]
```

---

## 🔧 Passo a Passo de Implementação

### PASSO 1 — [uo_mitm_proxy.py](file:///d:/UO/imperial-shard-imperialuoNova/uo_mitm_proxy.py) (Proxy TCP com framing de pacotes UO)

**Responsabilidades:**
- Escutar em `127.0.0.1:2593`
- Conectar ao servidor real `181.214.48.238:2593`
- Manter estado de framing por conexão (buffer acumulado)
- Interpretar packets UO corretamente (tabela de tamanhos + variable length)
- Publicar eventos para a camada web via `queue.Queue` compartilhada

**Lógica de framing UO:**
```python
# Packet size table — UO tem 3 categorias:
# 1. Tamanho fixo: PACKET_LENGTHS[opcode] = N
# 2. Tamanho variável (2 bytes depois do opcode): PACKET_LENGTHS[opcode] = -1
# 3. Tamanho variável (4 bytes): PACKET_LENGTHS[opcode] = -2

PACKET_LENGTHS = {
    0x00: 104, 0x01: 5, 0x02: 7, 0x03: -1, 0x04: 2,
    0x05: 5, 0x06: 5, 0x07: 7, 0x08: 14, 0x09: 5,
    0x0A: 11, 0x0B: 7, 0x0C: -1, 0x0D: -1, 0x0E: 6,
    0x0F: -1, 0x10: -1, 0x11: -1, 0x12: -1, 0x13: -1,
    0x14: 6, 0x15: 9, 0x16: -1, 0x17: -1, 0x18: -1,
    0x1A: -1, 0x1B: 37, 0x1C: -1, 0x1D: 5, 0x1E: 4,
    0x20: 19, 0x21: 8, 0x22: 3, 0x23: -1, 0x24: 9,
    0x25: 21, 0x26: 10, 0x27: 2, 0x28: 2, 0x29: 1,
    0x2A: 5, 0x2B: 2, 0x2C: 2, 0x2D: 23, 0x2E: 27,
    0x2F: 10, 0x30: 14, 0x31: 1, 0x32: 2, 0x33: -1,
    0x34: 10, 0x36: -1, 0x38: 7, 0x3A: -1, 0x3B: -1,
    0x3C: -1, 0x3E: 8, 0x3F: -1, 0x40: -1, 0x42: 2,
    0x45: 5, 0x46: -1, 0x47: 11, 0x4B: 11, 0x4C: 2,
    0x4D: 2, 0x4E: 2, 0x4F: 2, 0x54: -1, 0x55: 1,
    0x56: -1, 0x57: -1, 0x58: -1, 0x5D: 73, 0x61: -1,
    0x62: -1, 0x65: 4, 0x66: -1, 0x69: -1, 0x6C: 19,
    0x6D: 3, 0x6E: 14, 0x6F: -1, 0x70: -1, 0x71: -1,
    0x72: 5, 0x73: 2, 0x74: -1, 0x75: -1, 0x76: 16,
    0x77: 17, 0x78: -1, 0x79: -1, 0x7C: -1, 0x80: 62,
    0x81: 2, 0x82: 2, 0x83: -1, 0x86: -1, 0x88: -1,
    0x89: -1, 0x8A: -1, 0x8B: 2, 0x8C: 11, 0x8D: -1,
    0x8E: -1, 0x8F: -1, 0x91: 65, 0x93: -1, 0x95: 9,
    0x97: 2, 0x98: -1, 0x99: -1, 0x9A: -1, 0x9B: -1,
    0x9E: -1, 0x9F: -1, 0xA0: 3, 0xA1: 9, 0xA2: 5,
    0xA3: 9, 0xA4: 149, 0xA5: -1, 0xA6: -1, 0xA8: -1,
    0xA9: -1, 0xAA: -1, 0xAC: -1, 0xAD: -1, 0xAE: -1,
    0xAF: 10, 0xB0: -1, 0xB2: -1, 0xB5: -1, 0xB6: -1,
    0xB7: -1, 0xB8: -1, 0xB9: 5, 0xBB: 9, 0xBC: 3,
    0xBD: -1, 0xBE: -1, 0xBF: -1, 0xC0: 36, 0xC1: -1,
    0xC2: -1, 0xC4: -1, 0xC6: 1, 0xC8: 2, 0xC9: 6,
    0xCA: 6, 0xCB: 7, 0xD3: -1, 0xD4: -1, 0xD6: -1,
    0xD7: -1, 0xD8: -1, 0xD9: -1, 0xDC: 9, 0xDD: -1,
    0xDE: -1, 0xDF: -1, 0xE0: -1, 0xE1: -1, 0xE2: 4,
    0xE3: -1, 0xE5: -1, 0xEF: -1, 0xF0: -1, 0xF1: -1,
    0xF2: -1, 0xF3: -1, 0xF5: -1, 0xF6: -1, 0xF7: -1,
}

# Nomes conhecidos de packets UO
PACKET_NAMES = {
    0x00: "CreateCharacter", 0x01: "Disconnect", 0x02: "MoveReq",
    0x03: "AsciiSpeech", 0x04: "GodCommand", 0x05: "AttackReq",
    0x06: "DoubleClickReq", 0x07: "PickUpItem", 0x08: "DropItem",
    0x09: "SingleClickReq", 0x0A: "DeleteChar", 0x0B: "RestartVersion",
    0x0D: "ArticleText", 0x11: "MobileStatus", 0x1B: "WorldItem",
    0x1C: "AsciiMessage", 0x1D: "RemoveObject", 0x20: "MobileUpdate",
    0x21: "MoveDenied", 0x22: "MoveACK", 0x25: "EquipItem",
    0x2E: "EquipUpdate", 0x34: "PlayerQuery", 0x3A: "Skills",
    0x3B: "BuyItems", 0x3C: "ContainerContents", 0x4E: "PersonalLight",
    0x4F: "GlobalLight", 0x54: "PlaySound", 0x55: "LoginConfirm",
    0x5D: "LoginChar", 0x65: "Weather", 0x6C: "Target",
    0x6D: "PlayMusic", 0x6E: "MobAnimation", 0x72: "WarMode",
    0x73: "Ping", 0x74: "ContainerOpen", 0x76: "LoginComplete",
    0x77: "MobileUpdMoving", 0x78: "MobileIncoming", 0x80: "LoginReq",
    0x82: "LoginDenied", 0x8C: "ServerRelay", 0x91: "GameLogin",
    0xA0: "SelectServer", 0xA8: "ServerList", 0xA9: "CharacterList",
    0xAD: "UnicodeSpeech", 0xAE: "UniMessage", 0xAF: "Death",
    0xB9: "Features", 0xBC: "Season", 0xBD: "ClientVersion",
    0xBF: "GeneralInfo", 0xC0: "GraphicEffect", 0xC1: "LocalizedMessage",
    0xD6: "MegaCliloc", 0xD7: "EncodedCommand", 0xDC: "ObjRevision",
    0xDD: "CompressedGump", 0xE2: "MobileStatus", 0xEF: "LoginSeed",
    0xF0: "KREncryptionResponse", 0xF3: "NewWorldItem",
}
```

**Dados de cada evento (packet_event dict):**
```python
{
    "ts": timestamp_float,           # time.time()
    "ts_str": "HH:MM:SS.mmm",       # string para exibição
    "dir": "C2S" | "S2C",
    "opcode": 0x77,                  # int
    "opcode_hex": "0x77",            # string
    "name": "MobileUpdMoving",       # string ou "Unknown"
    "size": 17,                      # tamanho real em bytes
    "expected_size": 17,             # da tabela ou None
    "size_ok": True,                 # False = possível anomalia
    "raw_hex": "77...",              # primeiros 64 bytes em hex
    "conn_id": "127.0.0.1:55099",   # identificador da conexão
}
```

**Loop de framing:**
```python
def extract_packets(buf: bytearray) -> list[bytes]:
    """Extrai packets completos do buffer acumulado."""
    packets = []
    while len(buf) > 0:
        opcode = buf[0]
        expected = PACKET_LENGTHS.get(opcode)
        if expected is None:
            # desconhecido — consome 1 byte e tenta next
            packets.append(bytes(buf[:1]))
            del buf[:1]
            continue
        if expected >= 0:
            # tamanho fixo
            if len(buf) < expected:
                break  # incompleto, aguarda mais dados
            packets.append(bytes(buf[:expected]))
            del buf[:expected]
        else:
            # variável: bytes 1-2 são o tamanho total
            if len(buf) < 3:
                break
            pkt_len = (buf[1] << 8) | buf[2]
            if pkt_len < 3:
                del buf[:1]  # corrompido
                continue
            if len(buf) < pkt_len:
                break  # incompleto
            packets.append(bytes(buf[:pkt_len]))
            del buf[:pkt_len]
    return packets
```

**Eventos enviados para a queue:**
- `packet_event` — um packet capturado
- `conn_event` — conexão estabelecida/derrubada  
- `stat_event` — stats periódicos (bytes/pkt totais)

---

### PASSO 2 — `uo_mitm_web.py` (Servidor Flask + SocketIO)

**Responsabilidades:**
- Iniciar o proxy em thread daemon
- Servir arquivos estáticos (`static/`)
- REST API:
  - `GET /api/stats` — counters gerais
  - `GET /api/packets?dir=&opcode=&limit=&offset=` — histórico paginado
  - `GET /api/packet_types` — tabela de opcodes vistos + contagem
  - `GET /api/connections` — conexões ativas
  - `GET /api/export` — baixar mitm_trace.jsonl
  - `GET /api/anomalies` — packets com tamanho incorreto ou suspeitos
- WebSocket (SocketIO):
  - Emite evento [packet](file:///d:/UO/imperial-shard-imperialuoNova/uo_mitm_app.py#56-85) em tempo real para cada packet capturado
  - Emite `stats` a cada 1 segundo

**Instalação de dependências:**
```
pip install flask flask-socketio
```

**Estrutura do servidor:**
```python
from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO
import threading, queue, time, json

app = Flask(__name__, static_folder='static')
socketio = SocketIO(app, cors_allowed_origins="*")
event_queue = queue.Queue(maxsize=10000)

# Histórico em memória (últimos 5000 packets)
packet_history = deque(maxlen=5000)

# Thread que drena a queue e faz broadcast
def event_broadcaster():
    while True:
        try:
            ev = event_queue.get(timeout=0.1)
            packet_history.append(ev)
            # salva no .jsonl
            with open("mitm_trace.jsonl", "a") as f:
                f.write(json.dumps(ev) + "\n")
            # push via websocket
            socketio.emit("packet", ev)
        except queue.Empty:
            pass
```

---

### PASSO 3 — `static/index.html` (Dashboard UI)

**Design:** Dark mode, moderno, premium. Usa Chart.js (CDN) + Socket.IO client (CDN).

**Layout (4 seções):**

#### Seção 1 — Header + Summary Cards
```
┌─────────────────────────────────────────────────────────┐
│  🛡️ UO MITM Monitor    [● LIVE]  [⏹ Stop]  [📥 Export] │
├──────────┬──────────┬──────────┬──────────┬─────────────┤
│ C2S Pkts │ S2C Pkts │ C2S Bytes│ S2C Bytes│ Connections │
│  12,345  │  45,678  │  2.3 MB  │  8.1 MB  │     1       │
└──────────┴──────────┴──────────┴──────────┴─────────────┘
```

#### Seção 2 — Gráficos em tempo real (Chart.js)
```
┌────────────────────────────────────────┐
│  📈 Packets/s    [C2S ─] [S2C ─]       │
│  [sparkline em tempo real, 60 pontos]  │
├────────────────────────────────────────┤
│  📈 Bytes/s       [C2S ─] [S2C ─]      │
│  [sparkline em tempo real, 60 pontos]  │
└────────────────────────────────────────┘
```

#### Seção 3 — Tabela de Packets (live feed com filtros)
```
┌──────────────────────────────────────────────────────────────┐
│  Filtros: [Direção ▼] [Opcode: 0x__] [Nome: ___] [Limpar]    │
├────┬──────────┬────────┬──────────────────┬──────┬───────────┤
│ #  │  Tempo   │  Dir   │    Opcode/Nome   │  Len │  Raw Hex  │
├────┼──────────┼────────┼──────────────────┼──────┼───────────┤
│ 1  │ 14:32:01 │  S2C   │ 0x77 MoveMob     │  17  │ 77AA...   │
│ 2  │ 14:32:01 │  C2S   │ 0x02 MoveReq     │   7  │ 023B...   │
└────┴──────────┴────────┴──────────────────┴──────┴───────────┘
▶ Click na linha = expande raw hex completo / detalhes
```

#### Seção 4 — Top Opcodes + Anomalias
```
┌──────────────────────┬─────────────────────────────────┐
│  Top C2S Opcodes     │  Top S2C Opcodes                │
│  0xD6 MegaCliloc 45k │  0x77 MoveMob 55k              │
│  0xF0 KREnc    34k   │  0xDC ObjRev  20k              │
│  ...                 │  ...                            │
├──────────────────────┴─────────────────────────────────┤
│  ⚠️ Anomalias — packets com tamanho divergente         │
│  [tabela de anomalias detectadas]                      │
└──────────────────────────────────────────────────────────┘
```

---

### PASSO 4 — `static/app.js` (Lógica de UI)

**Funcionalidades JS:**
1. Conecta ao WebSocket SocketIO
2. Recebe eventos [packet](file:///d:/UO/imperial-shard-imperialuoNova/uo_mitm_app.py#56-85) → adiciona à tabela (max 500 linhas visíveis)
3. Atualiza counters a cada segundo
4. Filtro client-side (direção, opcode, nome) sem re-request
5. Gráficos Chart.js:
   - `packets_per_sec` — line chart com 60 pontos deslizantes
   - `bytes_per_sec` — line chart com 60 pontos deslizantes
6. Click na linha → modal com raw hex formatado (grupos de 16 bytes)
7. Botão "Pause" → para de adicionar novas linhas (útil para analisar)
8. Botão "Export" → faz GET /api/export para baixar o .jsonl
9. Tabela de anomalias — busca /api/anomalies a cada 5s

**Filtros disponíveis:**
- Direção: All / C2S / S2C
- Opcode: campo de texto (busca parcial, ex: "77" ou "0x77")
- Nome: campo de texto (busca parcial, ex: "Move")
- Tamanho mínimo / máximo
- Apenas anomalias (checkbox)

---

### PASSO 5 — Melhorias no [log_summary.py](file:///d:/UO/imperial-shard-imperialuoNova/log_summary.py)

O arquivo já está bom. Possível melhoria futura:
- Adicionar flag `--correlate mitm_trace.jsonl` para cruzar dados do proxy com o log do cliente

---

## 🚀 Como usar (passo a passo do usuário)

1. **Instalar dependências:**
   ```
   pip install flask flask-socketio
   ```

2. **Configurar o IP do servidor em `uo_mitm_web.py`:**
   ```python
   REMOTE_HOST = "181.214.48.238"
   REMOTE_PORT = 2593
   ```

3. **Rodar o sistema:**
   ```
   python uo_mitm_web.py
   ```
   → Abre browser em `http://localhost:5000`

4. **Configurar o cliente UO:**
   - Alterar o IP do servidor para `127.0.0.1` (porta 2593)
   - Ou usar o launcher com IP `127.0.0.1`

5. **Jogar normalmente** — todos os packets são capturados

6. **Analisar crashes:**
   - Ver anomalias na seção 4
   - Filtrar por last packets antes de freeze/crash
   - Exportar `.jsonl` para análise mais profunda

---

## 📋 Ordem de criação dos arquivos

1. [uo_mitm_proxy.py](file:///d:/UO/imperial-shard-imperialuoNova/uo_mitm_proxy.py) — **Núcleo do proxy** (framing, queue de eventos)
2. `uo_mitm_web.py` — **Servidor Flask** (API + SocketIO + runner)  
3. `static/index.html` — **HTML principal** (estrutura do dashboard)
4. `static/style.css` — **CSS dark mode** (estilos premium)
5. `static/app.js` — **JavaScript** (filtros, gráficos, websocket)

---

## ⚙️ Configurações editáveis (topo de `uo_mitm_web.py`)

```python
LOCAL_ADDR  = "127.0.0.1"
LOCAL_PORT  = 2593
REMOTE_HOST = "181.214.48.238"
REMOTE_PORT = 2593
WEB_PORT    = 5000
LOG_FILE    = "mitm_trace.jsonl"
MAX_HISTORY = 5000     # packets em memória
DEBUG_PROXY = True     # printa packets no console
```

---

## 🔍 Notas sobre diagnóstico de crashes

Com base no [summary.txt](file:///d:/UO/imperial-shard-imperialuoNova/summary.txt) analisado:
- **24 freezes** detectados nos logs
- Picos suspeitos em `+420s`, `+1740s`, `+3540s`, `+5400s`, `+7200s`, `+9060s` — todos com 
  enorme quantidade de `send_0xD6` (~100k+) em uma janela de 30s (isso é anormal!)
- `0xD6 MegaCliloc` com >100.000 enviados em 30 segundos — possível flood/bug no servidor
- Com o MITM rodando, poderemos ver exatamente quando isso acontece e capturar os bytes

---

## ✅ Checklist de Implementação

- [ ] [uo_mitm_proxy.py](file:///d:/UO/imperial-shard-imperialuoNova/uo_mitm_proxy.py) — proxy com framing correto e queue
- [ ] `uo_mitm_web.py` — Flask + SocketIO + REST API
- [ ] `static/index.html` — estrutura HTML
- [ ] `static/style.css` — dark mode premium
- [ ] `static/app.js` — filtros, gráficos, websocket
- [ ] Testar proxy com cliente UO conectando
- [ ] Verificar que todos packets são capturados (não apenas login)
- [ ] Verificar gráficos em tempo real
- [ ] Testar filtros
- [ ] Testar export .jsonl
