# 🛡️ UO MITM Monitor

**UO MITM Monitor** é uma ferramenta de inspeção e monitoramento de rede (MITM Proxy) desenvolvida especificamente para o ecossistema **Ultima Online**. Ele atua entre o cliente e o servidor, permitindo a análise de pacotes em tempo real, detecção de floods e visualização de dados operacionais através de um dashboard web intuitivo.

## 🚀 Funcionalidades

- **MITM Proxy de Alta Performance:** Encaminha tráfego de forma transparente com buffer paralelo para inspeção sem latência perceptível.
- **Handshake de Login Inteligente:** Gerencia o seed inicial de 4 bytes e redirecionamento 0x8C (Server Relay) para manter a sessão estável em `127.0.0.1`.
- **Dashboard em Tempo Real:** Visualização de tráfego, contagem de pacotes e alertas de segurança via Flask e SocketIO.
- **Detecção de Flood:** Alerta visual instantâneo quando o limite de pacotes por segundo é excedido.
- **Persistência de Histórico:** Salva traços de pacotes no formato JSONL para análise forense ou auditoria.
- **Controle Dinâmico:** Botão de pausa/ativação do proxy diretamente pelo navegador.

## 🏗️ Arquitetura

O sistema é dividido em dois componentes principais:
1.  **Core Proxy (`uo_mitm_proxy.py`):** Motor TCP em Python que lida com o framing dos pacotes UO e a lógica de redirecionamento de login.
2.  **Web Dashboard (`uo_mitm_web.py`):** Interface moderna construída com Flask e Chart.js para telemetria em tempo real.

## 🛠️ Requisitos

- Python 3.10+
- Flask
- Flask-SocketIO
- Eventlet (para concorrência de alta performance)

## 🏃 Como Executar

1. Instale as dependências:
   ```bash
   pip install flask flask-socketio eventlet
   ```

2. Inicie o Monitor:
   ```bash
   python uo_mitm_web.py
   ```

3. Configure seu cliente de UO para conectar em `127.0.0.1` na porta `2593` (ou a porta configurada).

4. Acesse o dashboard em: `http://localhost:5000`

## 📂 Estrutura do Projeto

- `uo_mitm_proxy.py`: Lógica central de interceptação.
- `uo_mitm_web.py`: Servidor de API e WebSockets.
- `static/`: Frontend (HTML, CSS, JS).
- `.gitignore`: Configurado para ignorar logs e dados de captura sensíveis.

---
*Desenvolvido para uso exclusivo em ambientes de desenvolvimento e administração de servidores Ultima Online.*
