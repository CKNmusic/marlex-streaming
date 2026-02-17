# Medical Streaming API

Backend de alta performance com **FastAPI** para gestão e gravação de vídeos médicos via streaming (RTMP e outros protocolos suportados).

## 🚀 Funcionalidades Chave

- **Gestão de Dispositivos**: Cadastro e controle de equipamentos de streaming.
- **Gravação Sob Demanda**: Controle de Start/Stop de gravação via FFmpeg (Processos independentes).
- **Streaming Adaptativo**: Suporte a H.265 (HEVC) para 4K e HLS para playback.
- **Hierarquia de Acesso**: 
  - **Master (Admin)**: Gestão total.
  - **Médico (User)**: Acesso apenas aos seus procedimentos.
- **Segurança**: Autenticação JWT e validação de dispositivos via Token.

## 🛠️ Tech Stack

- **Linguagem**: Python 3.12+
- **Framework Web**: FastAPI
- **Banco de Dados**: PostgreSQL (Async SQLAlchemy 2.0)
- **Validação**: Pydantic V2
- **Streaming**: FFmpeg + Asyncio Subprocess

## 📦 Como Rodar

```bash
# Clone o repositório
git clone git@github.com:MarlexBrasil/streaming_api.git

# Instale as dependências
pip install -r requirements.txt

# Suba o banco
docker compose up -d db adminer

# Recrie schema + seed essencial (reset destrutivo sem backup)
scripts/rebuild_from_zero.sh

# Inicie o servidor
PYTHONPATH=. .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8001

# (Opcional) Validar carga minima via API
PYTHONPATH=. .venv/bin/python3 scripts/seed_via_api.py \
  --base-url http://127.0.0.1:8001/surgwaze/v1 \
  --admin-user admin \
  --admin-pass 123 \
  --app-host http://192.168.10.19
```

## 🌐 Servidor de Ingestão RTMP (Local/VPS)

Suba um servidor RTMP robusto com MediaMTX (porta padrão deste projeto: `8554`):

```bash
docker compose -f docker-compose.ingest.yml up -d
```

Gate de custo no ingest:
- O MediaMTX usa autenticação HTTP (`/surgwaze/v1/device-auth/ingest-auth`) para decidir se aceita `publish`.
- Sem usuário online e sem gravação ativa, o `publish` é bloqueado na borda.
- O recorder interno do MediaMTX fica desativado neste projeto (gateway apenas); a gravação oficial é controlada pela API.
- A API consulta o MediaMTX com fallback automático entre endpoints `/v2` e `/v3`.

URL de publish esperada:

```text
rtmp://<HOST_PUBLICO>:8554/surgwaze/v1/<device_key>/stream
```

Configuração recomendada no DVR (campos separados):

```text
Stream URL: rtmp://<HOST_PUBLICO>:8554/surgwaze/v1/<device_key>/stream
Stream Key: (vazio)
```

Monitor de status (`Offline | Online | Starting | Recording | Stopping`):

```bash
python scripts/ingest_watch.py \
  --api-url http://127.0.0.1:9997 \
  --public-host <HOST_PUBLICO> \
  --expected-path surgwaze/v1/<device_key>/stream \
  --rtmp-port 8554 \
  --status-file recordings/ingest_status/receiver_status.json
```

Parar ingestão:

```bash
docker compose -f docker-compose.ingest.yml down
```

## ✅ Validação Local (confirmada)

Teste validado em rede local com status:
`Offline -> Online -> Recording -> Offline`.

## 🔀 Ingestão Multi-Stream (PID isolado por stream)

Para testes de escala com múltiplas keys simultâneas, use:

```bash
python scripts/ingest_manager.py \
  --config-json deploy/ingest/rtmp_ingest_manager_config.json
```

Comandos do manager:

```text
online
start <key|all>
stop <key|all>
status [key]
exit
```

Arquivos JSON do runtime:

- Status: `.runtime/rtmp_ingest_manager/receiver_status.json`
- Sequência (estilo DB por key): `.runtime/rtmp_ingest_manager/sequence_db.json`
- Histórico de finalização (start/end/size/reason/final_status): `.runtime/rtmp_ingest_manager/recording_history.json`

Observação de escala:

- Padrão recomendado: `rtmp://<host>:8554/surgwaze/v1/<device_key>/stream` (1 path por device).
- Formato legado `rtmp://<host>:8554/surgwaze/v1/stream?key=<key>` compartilha path e limita concorrência.

Runner de estresse (ciclos START/STOP + contagem delta por key):

```bash
python scripts/ingest_stress_runner.py \
  --public-host 192.168.10.19 \
  --rtmp-port 8554 \
  --key-in-path \
  --cycles 20 \
  --record-seconds 1 \
  --interval-seconds 1 \
  --stop-wait-seconds 6
```

## 📡 Realtime (WebSocket) + Métricas de Manager

- WebSocket: `ws://<API_HOST>:8001/surgwaze/v1/realtime/ws?token=<JWT>[&dashboard=manager]`
- Eventos enviados:
  - `device_status` (status por device, com filtro por permissão do usuário)
  - `record_status` (mudanças de gravação start/stop/final_status)
  - `manager_metrics` (CPU/Memória/Rede/Publicadores/Gravações)
  - `snapshot` (estado inicial ao conectar)

Endpoints para dashboard manager:

```text
GET /surgwaze/v1/manager-runtime/metrics/current
GET /surgwaze/v1/manager-runtime/metrics/history?limit=120
```

Observações:

- A coleta de métricas roda por demanda: por padrão só coleta/publica quando há manager conectado no WebSocket.
- Histórico de métricas: `.runtime/manager_metrics/metrics_history.jsonl`.

### Alternar Realtime `memory`/`redis` em 1 comando

```bash
# modo local (sem Redis)
bash scripts/realtime_mode.sh memory

# modo distribuido (Redis + WS)
bash scripts/realtime_mode.sh redis
```

Arquivos relacionados:

- `docker-compose.realtime.yml`
- `.env.realtime.memory`
- `.env.realtime.redis`
- `docs/realtime_event_bus.md`

## 📚 Documentacao Tecnica

- Indice: `docs/arquitetura/README.md`
- Como documentar API: `docs/arquitetura/como_documentar_api.md`
- Design Patterns: `docs/arquitetura/design_patterns.md`
- Arquitetura de software: `docs/arquitetura/arquitetura_software.md`
- WebSockets e SSE: `docs/arquitetura/websockets_sse.md`
- Microsservicos: `docs/arquitetura/microsservicos.md`
- Comunicacao assíncrona: `docs/arquitetura/comunicacao_assincrona.md`

Regras de negócio de presença, START/STOP, interrupção e capacidade:

- Ver `docs/requisitos_negocio.md`.
