/* ════════════════════════════════════════════════════════
    UO MITM Monitor — app.js
   ════════════════════════════════════════════════════════ */

let MAX_ROWS = 500;
let MAX_POINTS = 300; // 5 minutos de histórico

let allPackets = [];
let isRunning = false;
let filterDir = "";
let filterOpcode = "";
let filterName = "";

let chartPPS, chartBPS;

document.addEventListener("DOMContentLoaded", () => {
    initCharts();
    loadStatus();
    setInterval(loadStatus, 3000);
});

const socket = io();

socket.on("event", ev => {
    if (ev.type === "packet") {
        allPackets.push(ev);
        if (allPackets.length > 2000) allPackets.shift();
        if (matchesFilter(ev)) {
            appendRow(ev);
        }
    } else if (ev.type === "conn") {
        addConnLog(ev.msg, ev.status);
    }
});

socket.on("stats", data => {
    updateUI(data);
});

async function loadStatus() {
    try {
        const res = await fetch("/api/status");
        const data = await res.json();
        
        // Preenche inputs se não estiverem focados
        const inputs = ["target-ip", "target-port", "listen-port", "relay-ip"];
        inputs.forEach(id => {
            const el = document.getElementById(id);
            const val = data.config[id.replace("-", "_")];
            if (document.activeElement !== el && val !== undefined) {
                el.value = val;
            }
        });

        isRunning = data.running;
        const btn = document.getElementById("btn-toggle-proxy");
        const status = document.getElementById("proxy-status");
        
        if (isRunning) {
            btn.innerText = "⏹ Parar Proxy";
            btn.className = "btn btn-danger";
            status.innerText = "● LIVE";
            status.className = "badge badge-live";
            inputs.forEach(id => document.getElementById(id).disabled = true);
        } else {
            btn.innerText = "▶ Iniciar Proxy";
            btn.className = "btn btn-primary";
            status.innerText = "○ OFFLINE";
            status.className = "badge badge-info";
            inputs.forEach(id => document.getElementById(id).disabled = false);
        }
        
        document.getElementById("stat-conn").innerText = data.stats.connections;
        document.getElementById("uptime-badge").innerText = "⏱ " + fmtDuration(data.stats.uptime);
        document.getElementById("conn-badge").innerText = "🔌 " + data.stats.connections + " conexões";
    } catch(e) {}
}

async function toggleProxy() {
    const endpoint = isRunning ? "/api/proxy/stop" : "/api/proxy/start";
    const body = isRunning ? {} : {
        target_ip: document.getElementById("target-ip").value,
        target_port: document.getElementById("target-port").value,
        listen_port: document.getElementById("listen-port").value,
        relay_ip: document.getElementById("relay-ip").value
    };

    try {
        const res = await fetch(endpoint, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (data.status === "error") alert(data.msg);
        loadStatus();
    } catch(e) { alert("Erro ao comunicar com o servidor."); }
}

function updateUI(data) {
    document.getElementById("c2s-bytes").innerText = fmtSize(data.c2s_bytes);
    document.getElementById("s2c-bytes").innerText = fmtSize(data.s2c_bytes);
    document.getElementById("c2s-pkts").innerText = fmtNum(data.c2s_pkts);
    document.getElementById("s2c-pkts").innerText = fmtNum(data.s2c_pkts);
    
    const lastPPS_C2S = data.c2s_pps.slice(-1)[0] || 0;
    const lastPPS_S2C = data.s2c_pps.slice(-1)[0] || 0;
    document.getElementById("c2s-pps").innerText = lastPPS_C2S + " pkt/s";
    document.getElementById("s2c-pps").innerText = lastPPS_S2C + " pkt/s";
    document.getElementById("c2s-bps").innerText = fmtSize(data.c2s_bps.slice(-1)[0] || 0) + "/s";
    document.getElementById("s2c-bps").innerText = fmtSize(data.s2c_bps.slice(-1)[0] || 0) + "/s";

    // Logica de Network Health (Flood Detection)
    const totalPPS = lastPPS_C2S + lastPPS_S2C;
    const healthEl = document.getElementById("stat-health");
    const healthDesc = document.getElementById("health-desc");
    const healthCard = document.getElementById("card-flood");
    
    if (totalPPS > 500) {
        healthEl.innerText = "FLOOD!";
        healthDesc.innerText = "Taxa Crítica (>500/s)";
        healthCard.style.border = "1px solid var(--red)";
    } else if (totalPPS > 200) {
        healthEl.innerText = "ALTO";
        healthDesc.innerText = "Tráfego Intenso";
        healthCard.style.border = "1px solid var(--yellow)";
    } else {
        healthEl.innerText = "OK";
        healthDesc.innerText = "Tráfego Estável";
        healthCard.style.border = "1px solid var(--border)";
    }

    updateRank("top-c2s", data.top_c2s);
    updateRank("top-s2c", data.top_s2c);
    
    chartPPS.data.datasets[0].data = data.c2s_pps.slice(-MAX_POINTS);
    chartPPS.data.datasets[1].data = data.s2c_pps.slice(-MAX_POINTS);
    chartPPS.update();

    chartBPS.data.datasets[0].data = data.c2s_bps.slice(-MAX_POINTS);
    chartBPS.data.datasets[1].data = data.s2c_bps.slice(-MAX_POINTS);
    chartBPS.update();
}

function appendRow(ev) {
    const tbody = document.getElementById("packet-tbody");
    const tr = document.createElement("tr");
    const dirClass = ev.dir === "C2S" ? "dir-c2s" : "dir-s2c";
    
    tr.innerHTML = `
        <td style="color:var(--text-muted)">${ev.opcode}</td>
        <td class="time">${ev.ts_str}</td>
        <td class="${dirClass}">${ev.dir}</td>
        <td class="opcode">${ev.opcode_hex}</td>
        <td class="pkt-name">${ev.name}</td>
        <td class="pkt-size">${ev.size}</td>
        <td class="pkt-hex">${ev.raw_hex.substring(0, 64)}</td>
    `;
    tr.onclick = () => showModal(ev);
    tbody.prepend(tr);
    if (tbody.rows.length > MAX_ROWS) tbody.deleteRow(MAX_ROWS);
    document.getElementById("visible-count").innerText = tbody.rows.length;
}

function matchesFilter(ev) {
    if (filterDir && ev.dir !== filterDir) return false;
    if (filterOpcode && !ev.opcode_hex.toLowerCase().includes(filterOpcode.toLowerCase())) return false;
    if (filterName && !ev.name.toLowerCase().includes(filterName.toLowerCase())) return false;
    return true;
}

function applyFilters() {
    filterDir = document.getElementById("f-dir").value;
    filterOpcode = document.getElementById("f-opcode").value;
    filterName = document.getElementById("f-name").value;
    const tbody = document.getElementById("packet-tbody");
    tbody.innerHTML = "";
    allPackets.filter(matchesFilter).slice(-MAX_ROWS).reverse().forEach(appendRow);
}

function clearFilters() {
    document.getElementById("f-dir").value = "";
    document.getElementById("f-opcode").value = "";
    document.getElementById("f-name").value = "";
    applyFilters();
}

function addConnLog(msg, status) {
    const log = document.getElementById("conn-log");
    const div = document.createElement("div");
    div.className = "conn-item " + (status || "");
    div.innerText = `[${new Date().toLocaleTimeString()}] ${msg}`;
    log.prepend(div);
}

function updateRank(id, data) {
    const tbody = document.querySelector(`#${id} tbody`);
    tbody.innerHTML = data.map(d => `<tr><td>${d[0]}</td><td>${d[1]}</td><td>${d[2]}</td></tr>`).join("");
}

function showModal(ev) {
    document.getElementById("modal-title").innerText = `Packet ${ev.opcode_hex}: ${ev.name}`;
    document.getElementById("modal-meta").innerHTML = `
        <div class="info-item"><div class="info-label">Direção</div><div class="info-value">${ev.dir}</div></div>
        <div class="info-item"><div class="info-label">Tamanho</div><div class="info-value">${ev.size} bytes</div></div>
        <div class="info-item"><div class="info-label">Tempo</div><div class="info-value">${ev.ts_str}</div></div>
    `;
    
    let hex = ev.raw_hex;
    let dump = "";
    for(let i=0; i < hex.length; i += 32) {
        let chunk = hex.substr(i, 32);
        let bytes = chunk.match(/.{1,2}/g).join(" ");
        let ascii = "";
        for(let j=0; j < chunk.length; j += 2) {
            let code = parseInt(chunk.substr(j, 2), 16);
            ascii += (code >= 32 && code <= 126) ? String.fromCharCode(code) : ".";
        }
        dump += `<span class="hex-offset">${(i/2).toString(16).padStart(4,'0')}</span>  <span class="hex-bytes">${bytes.padEnd(48, ' ')}</span>  <span class="hex-ascii">${ascii}</span>\n`;
    }
    document.getElementById("modal-hex").innerHTML = dump;
    document.getElementById("modal").classList.remove("hidden");
}

function closeModal() { document.getElementById("modal").classList.add("hidden"); }

function initCharts() {
    const zoomOptions = {
        zoom: {
            wheel: { enabled: true },
            pinch: { enabled: true },
            mode: 'x',
        },
        pan: {
            enabled: true,
            mode: 'x',
        }
    };

    const commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: {
            x: { display: false },
            y: { 
                beginAtZero: true, 
                grid: { color: "rgba(255,255,255,0.05)" },
                ticks: { color: "#5a6480", font: { size: 10 } }
            }
        },
        plugins: { 
            legend: { display: false },
            zoom: zoomOptions,
            tooltip: {
                enabled: true,
                mode: 'index',
                intersect: false,
                backgroundColor: 'rgba(20, 23, 32, 0.9)',
                titleColor: '#8892aa',
                bodyColor: '#e2e8f0',
                borderColor: '#2a2f47',
                borderWidth: 1
            }
        },
        elements: { 
            point: { radius: 0 },
            line: { tension: 0.3, borderWidth: 2 }
        }
    };

    chartPPS = new Chart(document.getElementById("chart-pps"), {
        type: "line",
        data: {
            labels: Array(MAX_POINTS).fill(""),
            datasets: [
                { label: "C2S", data: [], borderColor: "#3b82f6", backgroundColor: "rgba(59, 130, 246, 0.1)", fill: true },
                { label: "S2C", data: [], borderColor: "#10b981", backgroundColor: "rgba(16, 185, 129, 0.1)", fill: true }
            ]
        },
        options: commonOptions
    });

    chartBPS = new Chart(document.getElementById("chart-bps"), {
        type: "line",
        data: {
            labels: Array(MAX_POINTS).fill(""),
            datasets: [
                { label: "C2S", data: [], borderColor: "#3b82f6", backgroundColor: "rgba(59, 130, 246, 0.1)", fill: true },
                { label: "S2C", data: [], borderColor: "#10b981", backgroundColor: "rgba(16, 185, 129, 0.1)", fill: true }
            ]
        },
        options: commonOptions
    });
}

async function clearHistory() {
    if (confirm("Limpar?")) {
        await fetch("/api/reset", {method: "POST"});
        allPackets = [];
        document.getElementById("packet-tbody").innerHTML = "";
    }
}

function fmtNum(n) { return n.toLocaleString(); }
function fmtSize(b) { if (b < 1024) return b + " B"; if (b < 1024*1024) return (b/1024).toFixed(1) + " KB"; return (b/(1024*1024)).toFixed(1) + " MB"; }
function fmtDuration(s) { const h = Math.floor(s/3600); const m = Math.floor((s%3600)/60); const sec = s%60; return [h,m,sec].map(v => v.toString().padStart(2,'0')).join(':'); }
