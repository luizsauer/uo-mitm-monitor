# 🛡️ UO MITM Monitor — Guia Completo

O **UO MITM Monitor** é uma ferramenta poderosa e fácil de usar para monitorar a conexão entre o seu jogo (**Ultima Online**) e o servidor. 

Imagine que é como uma "câmera de segurança" para a sua internet no jogo: ele mostra exatamente o que o servidor está enviando para você e o que você está enviando para o servidor em tempo real. Isso ajuda a descobrir por que o jogo trava, se há "floods" de pacotes ou se a conexão está instável.

---

## 🌟 O que ele faz?
- **Gráficos em Tempo Real:** Veja o tráfego da sua conexão de forma visual.
- **Histórico de Pacotes:** Saiba exatamente qual comando (andar, falar, usar item) causou um erro.
- **Dashboard Web:** Você controla tudo pelo seu navegador (Chrome, Edge, etc.).
- **Fácil de Usar:** Não precisa ser programador para instalar e rodar.

---

## 🛠️ Como Instalar (Passo a Passo)

Siga estas etapas simples para colocar tudo funcionando:

### 1. Instale o Python
Se você ainda não tem o Python no seu Windows:
1. Vá para [python.org/downloads](https://www.python.org/downloads/) e clique no botão amarelo **Download Python**.
2. **IMPORTANTE:** Na hora de instalar, marque a caixinha que diz **"Add Python to PATH"** (Adicionar Python ao PATH). Isso é fundamental!
3. Finalize a instalação.

### 2. Baixe o Sistema
Baixe os arquivos deste projeto para uma pasta no seu computador.

### 3. Instale as Dependências
Abra o **Prompt de Comando** (digite `cmd` no menu iniciar), navegue até a pasta do projeto e digite o seguinte comando:
```bash
pip install -r requirements.txt
```
*Isso vai instalar automaticamente as ferramentas necessárias para o monitor funcionar.*

---

## ⚙️ Como Configurar

Antes de abrir o jogo, você precisa dizer ao monitor qual é o servidor real do UO.
1. Abra o arquivo `config.json` com o Bloco de Notas.
2. Altere os campos:
   - `"target_ip"`: O endereço IP do servidor real (ex: `181.214.48.238`).
   - `"target_port"`: A porta do servidor (geralmente `2593`).
   - `"listen_port"`: Deixe em `2593` (é onde o seu jogo vai conectar localmente).
3. Salve o arquivo.

---

## 🚀 Como Usar

Agora vem a parte divertida:

1. **Inicie o Monitor:**
   Você tem duas opções:
   - **Fácil:** Basta dar um duplo-clique no arquivo `run_monitor.bat` que eu criei para você. Ele vai configurar tudo e abrir o servidor sozinho.
   - **Manual:** No Prompt de Comando, dentro da pasta do projeto, digite:
   ```bash
   python uo_mitm_web.py
   ```
2. **Abra o Dashboard:**
   Abra o seu navegador e acesse: [http://localhost:5000](http://localhost:5000)
   Você verá o painel de controle!

3. **Conecte o seu Jogo (ClassicUO / Razor / Orion):**
   No seu Launcher ou Client de UO, altere o endereço do servidor para:
   - **IP:** `127.0.0.1`
   - **Porta:** `2593` (ou a mesma que você colocou em `listen_port`)
   
   *Agora, quando você clicar em "Login", o tráfego passará pelo monitor e aparecerá no Dashboard!*

---

## 📊 Entendendo o Dashboard

- **LIVE / STOP:** Você pode pausar o monitoramento a qualquer momento.
- **Filtros:** Quer ver só quando você "fala" no jogo? Digite `Speech` no filtro de nome.
- **Exportar:** Clique em "Export" para baixar um arquivo com todo o histórico da sua sessão (útil para enviar para os administradores do servidor analisarem um erro).
- **Anomalias:** Se o sistema detectar algo estranho (como um pacote de tamanho errado), ele avisará você.

---

## ❓ Problemas Comuns

- **"A porta já está em uso":** Garanta que você não tem outro monitor aberto ou que o seu servidor de UO local (se tiver) não está usando a porta 2593.
- **O Dashboard não carrega:** Verifique se o comando `python uo_mitm_web.py` ainda está rodando no Prompt de Comando.
- **O jogo não conecta:** Verifique se o IP no `config.json` está correto e se você colocou `127.0.0.1` no seu Client de UO.

---

*Desenvolvido para ajudar jogadores e administradores a terem uma conexão mais estável e transparente.* 🛡️
