import argparse
import base64
import datetime
import fcntl
import json
import os
import re
import socket
import subprocess
import threading
import time
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs


STATUS_OFFLINE = "Offline"
STATUS_ONLINE = "Online"
STATUS_STARTING = "Starting"
STATUS_RECORDING = "Recording"
STATUS_STOPPING = "Stopping"
STATUS_ERROR = "Error"

DEFAULT_CONFIG_JSON = "deploy/ingest/rtmp_ingest_manager_config.json"
DEFAULT_PUBLIC_HOST = "192.168.10.19"

SAFE_SEGMENT_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def detect_public_host() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def safe_segment(value: str) -> str:
    cleaned = SAFE_SEGMENT_RE.sub("_", value.strip())
    return cleaned or "unknown"


def run_cmd(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=False, capture_output=True, text=True)


def deep_merge_defaults(target: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    for key, value in defaults.items():
        if key not in target:
            target[key] = value
            continue
        if isinstance(target[key], dict) and isinstance(value, dict):
            deep_merge_defaults(target[key], value)
    return target


def read_json_or_default(path: Path, default_payload: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default_payload
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default_payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def default_config(public_host: str) -> dict[str, Any]:
    return {
        "version": 1,
        "server": {
            "transport": "rtmp",
            "public_host": public_host,
            "rtmp_port": 8554,
            "app_prefix": "surgwaze/v1",
            "stream_name": "stream",
            "query_key_param": "key",
            "api_host": "127.0.0.1",
            "api_port": 9997,
            "api_user": "api",
            "api_pass": "api",
        },
        "runtime": {
            "external_server": True,
            "container_name": "mediamtx_rtmp_receiver_test",
            "image": "bluenviron/mediamtx:latest",
            "rtsp_port_internal": 8556,
            "poll_interval_sec": 0.5,
            "autostart_recording": False,
            "max_concurrent_recordings": 64,
            "keep_container": False,
            "log_level": "info",
        },
        "scaling": {
            "process_model": "worker_pid_per_stream",
            "publisher_discovery": "mediamtx_api_rtmpconns_list",
            "notes": "Cada stream gravando roda em um processo FFmpeg isolado.",
        },
        "recording": {
            "user_id": 1,
            "ffmpeg_bin": "ffmpeg",
            "format": "matroska",
        },
        "storage": {
            "output_dir": "recordings/rtmp_ingest_manager",
            "runtime_dir": ".runtime/rtmp_ingest_manager",
            "status_file": ".runtime/rtmp_ingest_manager/receiver_status.json",
            "seq_file": ".runtime/rtmp_ingest_manager/sequence_db.json",
            "history_file": ".runtime/rtmp_ingest_manager/recording_history.json",
            "mediamtx_config_file": ".runtime/rtmp_ingest_manager/mediamtx.yml",
        },
        "routing_notes": {
            "recommended_primary_style": "rtmp://<host>:8554/surgwaze/v1/<device_key>/stream",
            "legacy_query_style": "rtmp://<host>:8554/surgwaze/v1/stream?key=<device_key>",
            "important": "No MediaMTX, cada path aceita 1 publisher simultaneo; para escala, use key no path.",
        },
        "lifecycle_status": ["Offline", "Online", "Starting", "Recording", "Stopping"],
    }


def load_or_create_config(config_path: Path, public_host: str) -> dict[str, Any]:
    defaults = default_config(public_host=public_host)
    if config_path.exists():
        current = read_json_or_default(config_path, defaults)
        merged = deep_merge_defaults(current, defaults)
        if merged != current:
            write_json(config_path, merged)
        return merged

    write_json(config_path, defaults)
    return defaults


def mask_sensitive_config(config: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(json.dumps(config))
    try:
        payload["server"]["api_pass"] = "***"
    except Exception:
        pass
    return payload


def api_request_json(url: str, user: str, password: str) -> dict[str, Any]:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(req, timeout=3.0) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def list_rtmp_publishers(api_host: str, api_port: int, api_user: str, api_pass: str) -> list[dict[str, Any]]:
    data = api_request_json(f"http://{api_host}:{api_port}/v3/rtmpconns/list", api_user, api_pass)
    items = data.get("items", [])
    return [item for item in items if item.get("state") == "publish"]


def extract_key_from_query(query: str, query_key_param: str) -> Optional[str]:
    parsed = parse_qs(query or "", keep_blank_values=True)
    values = parsed.get(query_key_param) or []
    if not values:
        return None
    key = values[0].strip()
    return key or None


def extract_key_from_path(path_name: str, app_prefix: str, stream_name: str) -> Optional[str]:
    app = app_prefix.strip("/ ")
    stream = stream_name.strip("/ ")
    path_clean = path_name.strip("/ ")

    if not path_clean.startswith(f"{app}/"):
        return None
    suffix = f"/{stream}"
    if not path_clean.endswith(suffix):
        return None

    middle = path_clean[len(app) + 1 : -len(suffix)]
    middle = middle.strip("/ ")
    if not middle or "/" in middle:
        return None
    return middle


def write_mediamtx_config(
    config_path: Path,
    *,
    log_level: str,
    rtmp_port: int,
    rtsp_port: int,
    api_port: int,
    api_user: str,
    api_pass: str,
) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    content = f"""logLevel: {log_level}
api: yes
apiAddress: :{api_port}
rtmpAddress: :{rtmp_port}
rtspAddress: :{rtsp_port}
pathDefaults:
  record: no
authInternalUsers:
  - user: any
    permissions:
      - action: publish
      - action: read
      - action: playback
  - user: {api_user}
    pass: {api_pass}
    permissions:
      - action: api
paths:
  all:
"""
    config_path.write_text(content, encoding="utf-8")


def docker_remove_container(name: str) -> None:
    run_cmd(["docker", "rm", "-f", name])


def docker_start_mediamtx(
    *,
    name: str,
    image: str,
    host_rtmp_port: int,
    host_api_port: int,
    config_path: Path,
) -> None:
    command = [
        "docker",
        "run",
        "-d",
        "--rm",
        "--name",
        name,
        "-p",
        f"{host_rtmp_port}:{host_rtmp_port}",
        "-p",
        f"{host_api_port}:{host_api_port}",
        "-v",
        f"{config_path.resolve()}:/mediamtx.yml:ro",
        image,
    ]
    result = run_cmd(command)
    if result.returncode != 0:
        msg = result.stderr.strip() or result.stdout.strip() or "erro desconhecido"
        raise RuntimeError(f"Falha ao iniciar MediaMTX: {msg}")


def docker_is_running(name: str) -> bool:
    result = run_cmd(["docker", "inspect", "-f", "{{.State.Running}}", name])
    return result.returncode == 0 and result.stdout.strip() == "true"


PublisherMap = dict[str, dict[str, Any]]


class IngestProtocolAdapter(ABC):
    @property
    @abstractmethod
    def protocol_name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def api_host(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def api_port(self) -> int:
        raise NotImplementedError

    @property
    @abstractmethod
    def api_user(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def api_pass(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def ingest_port(self) -> int:
        raise NotImplementedError

    @property
    @abstractmethod
    def monitor_detail(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def path_concurrency_note(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def discover_publishers(self) -> PublisherMap:
        raise NotImplementedError

    @abstractmethod
    def build_pull_url(self, path_name: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def query_style_push_url(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def scale_style_push_url(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def write_runtime_server_config(self, *, config_path: Path, log_level: str, rtsp_port: int) -> None:
        raise NotImplementedError


class RTMPProtocolAdapter(IngestProtocolAdapter):
    def __init__(self, server_config: dict[str, Any]) -> None:
        self.public_host = str(server_config["public_host"])
        self.rtmp_port = int(server_config["rtmp_port"])
        self.app_prefix = str(server_config["app_prefix"]).strip("/ ")
        self.stream_name = str(server_config["stream_name"]).strip("/ ")
        self.query_key_param = str(server_config.get("query_key_param", "key"))
        self._api_host = str(server_config["api_host"])
        self._api_port = int(server_config["api_port"])
        self._api_user = str(server_config["api_user"])
        self._api_pass = str(server_config["api_pass"])

    @property
    def protocol_name(self) -> str:
        return "rtmp"

    @property
    def api_host(self) -> str:
        return self._api_host

    @property
    def api_port(self) -> int:
        return self._api_port

    @property
    def api_user(self) -> str:
        return self._api_user

    @property
    def api_pass(self) -> str:
        return self._api_pass

    @property
    def ingest_port(self) -> int:
        return self.rtmp_port

    @property
    def monitor_detail(self) -> str:
        return "Monitorando conexoes RTMP"

    @property
    def path_concurrency_note(self) -> str:
        return "Obs: o mesmo path no MediaMTX aceita apenas 1 publisher simultaneo."

    def query_style_push_url(self) -> str:
        return (
            f"rtmp://{self.public_host}:{self.rtmp_port}/"
            f"{self.app_prefix}/{self.stream_name}?{self.query_key_param}=<device_key>"
        )

    def scale_style_push_url(self) -> str:
        return (
            f"rtmp://{self.public_host}:{self.rtmp_port}/"
            f"{self.app_prefix}/<device_key>/{self.stream_name}"
        )

    def _is_managed_path(self, path_name: str) -> bool:
        path_clean = path_name.strip("/ ")
        single_path = f"{self.app_prefix}/{self.stream_name}"
        if path_clean == single_path:
            return True
        return bool(extract_key_from_path(path_clean, self.app_prefix, self.stream_name))

    def _key_from_connection(self, conn: dict[str, Any]) -> str:
        path_name = str(conn.get("path") or "").strip("/ ")
        query = str(conn.get("query") or "")
        conn_id = str(conn.get("id") or "")

        key = extract_key_from_query(query, self.query_key_param)
        if key:
            return safe_segment(key)

        path_key = extract_key_from_path(path_name, self.app_prefix, self.stream_name)
        if path_key:
            return safe_segment(path_key)

        return f"conn_{safe_segment(conn_id[:12] or 'unknown')}"

    def discover_publishers(self) -> PublisherMap:
        publishers = list_rtmp_publishers(self._api_host, self._api_port, self._api_user, self._api_pass)
        by_key: PublisherMap = {}
        for conn in publishers:
            path_name = str(conn.get("path") or "").strip("/ ")
            if not path_name or not self._is_managed_path(path_name):
                continue

            key = self._key_from_connection(conn)
            if key in by_key:
                continue

            by_key[key] = {
                "key": key,
                "id": str(conn.get("id") or ""),
                "path": path_name,
                "query": str(conn.get("query") or ""),
                "remote_addr": str(conn.get("remoteAddr") or ""),
            }
        return by_key

    def build_pull_url(self, path_name: str) -> str:
        return f"rtmp://127.0.0.1:{self.rtmp_port}/{path_name}"

    def write_runtime_server_config(self, *, config_path: Path, log_level: str, rtsp_port: int) -> None:
        write_mediamtx_config(
            config_path,
            log_level=log_level,
            rtmp_port=self.rtmp_port,
            rtsp_port=rtsp_port,
            api_port=self._api_port,
            api_user=self._api_user,
            api_pass=self._api_pass,
        )


def build_protocol_adapter(server_config: dict[str, Any]) -> IngestProtocolAdapter:
    transport = str(server_config.get("transport", "rtmp")).strip().lower()
    if transport == "rtmp":
        return RTMPProtocolAdapter(server_config)
    raise ValueError(f"Protocolo de ingest nao suportado: {transport}")


class SequenceStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _default_payload() -> dict[str, Any]:
        return {
            "version": 1,
            "updated_at": now_iso(),
            "keys": {},
        }

    def next_seq(self, *, key: str, user_id: int) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.seek(0)
            raw = handle.read().strip()
            payload = self._default_payload() if not raw else json.loads(raw)
            keys = payload.setdefault("keys", {})
            entry = keys.get(key) or {"seq": 0, "user": {"id": user_id}}
            new_seq = int(entry.get("seq") or 0) + 1
            entry["seq"] = new_seq
            entry["user"] = {"id": user_id}
            entry["updated_at"] = now_iso()
            keys[key] = entry
            payload["updated_at"] = now_iso()

            handle.seek(0)
            handle.truncate()
            handle.write(json.dumps(payload, ensure_ascii=True, indent=2))
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            return new_seq

    def current_seq(self, key: str) -> Optional[int]:
        payload = read_json_or_default(self.path, self._default_payload())
        entry = (payload.get("keys") or {}).get(key) or {}
        seq = entry.get("seq")
        return int(seq) if seq is not None else None


class ManagerStatusStore:
    def __init__(self, path: Path, *, config_path: Path, config: dict[str, Any]) -> None:
        self.path = path
        self.config_path = str(config_path)
        self._lock = threading.Lock()
        self._payload = read_json_or_default(
            self.path,
            {
                "manager": {
                    "status": STATUS_OFFLINE,
                    "detail": "Inicializando",
                    "updated_at": now_iso(),
                },
                "config_file": self.config_path,
                "config": mask_sensitive_config(config),
                "streams": {},
            },
        )
        self._payload["config_file"] = self.config_path
        self._payload["config"] = mask_sensitive_config(config)
        self._write_locked()

    def _write_locked(self) -> None:
        write_json(self.path, self._payload)

    def set_manager(self, *, status: str, detail: str, publishers: int, recordings: int) -> None:
        with self._lock:
            self._payload["manager"] = {
                "status": status,
                "detail": detail,
                "publishers_online": publishers,
                "recordings_active": recordings,
                "updated_at": now_iso(),
            }
            self._write_locked()
        print(f"[MANAGER] {status} - {detail} | online={publishers} recording={recordings}")

    def set_stream(
        self,
        *,
        key: str,
        status: str,
        detail: str,
        user_id: int,
        seq: Optional[int],
        path_name: Optional[str],
        stream_id: Optional[str],
        pid: Optional[int],
        active_file: Optional[str],
    ) -> None:
        with self._lock:
            streams = self._payload.setdefault("streams", {})
            streams[key] = {
                "status": status,
                "detail": detail,
                "key": key,
                "user": {"id": user_id},
                "seq": seq,
                "path": path_name,
                "stream": {"id": stream_id},
                "pid": pid,
                "active_file": active_file,
                "updated_at": now_iso(),
            }
            self._write_locked()
        print(f"[STREAM {key}] {status} - {detail}")

    def snapshot_json(self) -> str:
        with self._lock:
            return json.dumps(self._payload, ensure_ascii=True, indent=2)

    def snapshot_stream(self, key: str) -> str:
        with self._lock:
            item = (self._payload.get("streams") or {}).get(key)
            if not item:
                return json.dumps({"detail": f"key '{key}' sem status"}, ensure_ascii=True, indent=2)
            return json.dumps(item, ensure_ascii=True, indent=2)


class RecordingHistoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            write_json(
                self.path,
                {
                    "version": 1,
                    "updated_at": now_iso(),
                    "records": [],
                },
            )

    def append(
        self,
        *,
        key: str,
        user_id: int,
        seq: int,
        stream_id: str,
        path_name: str,
        started_at: str,
        ended_at: str,
        file_path: str,
        reason: str,
        final_status: str,
    ) -> None:
        with self._lock:
            payload = read_json_or_default(
                self.path,
                {
                    "version": 1,
                    "updated_at": now_iso(),
                    "records": [],
                },
            )
            records = payload.setdefault("records", [])
            file_size = os.path.getsize(file_path) if file_path and os.path.exists(file_path) else 0
            records.append(
                {
                    "key": key,
                    "user": {"id": user_id},
                    "seq": seq,
                    "stream": {"id": stream_id},
                    "path": path_name,
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "file_path": file_path,
                    "file_size_bytes": file_size,
                    "stop_reason": reason,
                    "final_status": final_status,
                    "logged_at": now_iso(),
                }
            )
            payload["updated_at"] = now_iso()
            write_json(self.path, payload)

    def snapshot(self, *, key: Optional[str] = None, limit: int = 20) -> str:
        with self._lock:
            payload = read_json_or_default(
                self.path,
                {
                    "version": 1,
                    "updated_at": now_iso(),
                    "records": [],
                },
            )
            records = payload.get("records") or []
            if key:
                records = [item for item in records if item.get("key") == key]
            payload["records"] = records[-max(limit, 1):]
            return json.dumps(payload, ensure_ascii=True, indent=2)


@dataclass
class RecorderWorker:
    key: str
    path_name: str
    stream_id: str
    seq: int
    user_id: int
    file_path: str
    process: subprocess.Popen
    stderr_thread: threading.Thread
    started_at: str


class IngestManager:
    def __init__(self, config: dict[str, Any], config_path: Path) -> None:
        self.config = config
        self.config_path = config_path

        server = config["server"]
        runtime = config["runtime"]
        recording = config["recording"]
        storage = config["storage"]

        self.protocol = build_protocol_adapter(server)

        self.external_server = bool(runtime["external_server"])
        self.container_name = runtime["container_name"]
        self.image = runtime["image"]
        self.rtsp_port_internal = int(runtime["rtsp_port_internal"])
        self.poll_interval = float(runtime["poll_interval_sec"])
        self.autostart_recording = bool(runtime["autostart_recording"])
        self.max_concurrent_recordings = int(runtime["max_concurrent_recordings"])
        self.keep_container = bool(runtime["keep_container"])
        self.log_level = runtime["log_level"]

        self.user_id = int(recording["user_id"])
        self.ffmpeg_bin = recording["ffmpeg_bin"]
        self.format_name = recording["format"]

        self.output_root = Path(storage["output_dir"])
        self.runtime_root = Path(storage["runtime_dir"])
        self.status_file = Path(storage["status_file"])
        self.seq_file = Path(storage["seq_file"])
        self.history_file = Path(storage["history_file"])
        self.mediamtx_config_file = Path(storage["mediamtx_config_file"])

        self.seq_store = SequenceStore(self.seq_file)
        self.status_store = ManagerStatusStore(self.status_file, config_path=config_path, config=config)
        self.history_store = RecordingHistoryStore(self.history_file)

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._publishers: PublisherMap = {}
        self._workers: dict[str, RecorderWorker] = {}
        self._logged_workers: set[tuple[str, int, str]] = set()

    def _drain_ffmpeg_stderr(self, key: str, process: subprocess.Popen) -> None:
        if process.stderr is None:
            return
        for line in process.stderr:
            text = line.strip()
            if text:
                print(f"[REC {key}] {text}")

    def _build_target_file(self, key: str, user_id: int, stream_id: str, seq: int) -> Path:
        date_str = datetime.datetime.now().strftime("%Y_%m_%d")
        target_dir = self.output_root / safe_segment(key) / date_str
        target_dir.mkdir(parents=True, exist_ok=True)
        base = target_dir / f"{key}_{date_str}_{user_id}_{stream_id}.mkv"
        if not base.exists():
            return base
        return target_dir / f"{key}_{date_str}_{user_id}_{stream_id}_seq{seq}.mkv"

    def _worker_count(self) -> int:
        with self._lock:
            return len(self._workers)

    def _publisher_count(self) -> int:
        with self._lock:
            return len(self._publishers)

    def _ensure_capacity(self) -> bool:
        with self._lock:
            return len(self._workers) < self.max_concurrent_recordings

    def _log_recording_stop(self, worker: RecorderWorker, *, reason: str, final_status: str) -> None:
        token = (worker.key, worker.seq, worker.started_at)
        if token in self._logged_workers:
            return
        self._logged_workers.add(token)
        self.history_store.append(
            key=worker.key,
            user_id=worker.user_id,
            seq=worker.seq,
            stream_id=worker.stream_id,
            path_name=worker.path_name,
            started_at=worker.started_at,
            ended_at=now_iso(),
            file_path=worker.file_path,
            reason=reason,
            final_status=final_status,
        )

    def start_container(self) -> None:
        self.protocol.write_runtime_server_config(
            config_path=self.mediamtx_config_file,
            log_level=self.log_level,
            rtsp_port=self.rtsp_port_internal,
        )

        docker_remove_container(self.container_name)
        docker_start_mediamtx(
            name=self.container_name,
            image=self.image,
            host_rtmp_port=self.protocol.ingest_port,
            host_api_port=self.protocol.api_port,
            config_path=self.mediamtx_config_file,
        )

        started = time.time()
        while time.time() - started < 15:
            if not docker_is_running(self.container_name):
                time.sleep(0.5)
                continue
            try:
                api_request_json(
                    f"http://{self.protocol.api_host}:{self.protocol.api_port}/v3/paths/list",
                    self.protocol.api_user,
                    self.protocol.api_pass,
                )
                return
            except Exception:
                time.sleep(0.5)
        raise RuntimeError("MediaMTX nao respondeu na API a tempo.")

    def stop_container(self) -> None:
        if not self.keep_container:
            docker_remove_container(self.container_name)

    def start_recording(self, key: str, *, reason: str) -> None:
        key = safe_segment(key)
        with self._lock:
            if key in self._workers and self._workers[key].process.poll() is None:
                print(f"Ja existe gravacao ativa para key={key}.")
                return
            publisher = self._publishers.get(key)

        if publisher is None:
            self.status_store.set_stream(
                key=key,
                status=STATUS_OFFLINE,
                detail="Nao foi possivel iniciar: publisher offline",
                user_id=self.user_id,
                seq=self.seq_store.current_seq(key),
                path_name=None,
                stream_id=None,
                pid=None,
                active_file=None,
            )
            print(f"Nao foi possivel iniciar key={key}: publisher offline.")
            return
        if not self._ensure_capacity():
            self.status_store.set_stream(
                key=key,
                status=STATUS_ONLINE,
                detail=f"Capacidade maxima atingida ({self.max_concurrent_recordings})",
                user_id=self.user_id,
                seq=self.seq_store.current_seq(key),
                path_name=publisher["path"],
                stream_id=publisher["id"],
                pid=None,
                active_file=None,
            )
            print(f"Capacidade maxima atingida ({self.max_concurrent_recordings}).")
            return

        seq = self.seq_store.next_seq(key=key, user_id=self.user_id)
        stream_id = safe_segment(publisher["id"] or str(seq))
        file_path = self._build_target_file(key=key, user_id=self.user_id, stream_id=stream_id, seq=seq)
        self.status_store.set_stream(
            key=key,
            status=STATUS_STARTING,
            detail=f"{reason} | aguardando ffmpeg | stream.id={stream_id} | seq={seq}",
            user_id=self.user_id,
            seq=seq,
            path_name=publisher["path"],
            stream_id=stream_id,
            pid=None,
            active_file=str(file_path),
        )

        command = [
            self.ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "info",
            "-y",
            "-i",
            self.protocol.build_pull_url(publisher["path"]),
            "-map",
            "0",
            "-c",
            "copy",
            "-f",
            self.format_name,
            str(file_path),
        ]

        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        stderr_thread = threading.Thread(target=self._drain_ffmpeg_stderr, args=(key, proc), daemon=True)
        stderr_thread.start()

        worker = RecorderWorker(
            key=key,
            path_name=publisher["path"],
            stream_id=stream_id,
            seq=seq,
            user_id=self.user_id,
            file_path=str(file_path),
            process=proc,
            stderr_thread=stderr_thread,
            started_at=now_iso(),
        )
        with self._lock:
            self._workers[key] = worker

        self.status_store.set_stream(
            key=key,
            status=STATUS_RECORDING,
            detail=f"{reason} | stream.id={stream_id} | seq={seq}",
            user_id=self.user_id,
            seq=seq,
            path_name=publisher["path"],
            stream_id=stream_id,
            pid=proc.pid,
            active_file=str(file_path),
        )

    def stop_recording(self, key: str, *, reason: str) -> None:
        key = safe_segment(key)
        with self._lock:
            worker = self._workers.get(key)
            publisher = self._publishers.get(key)

        if worker is None or worker.process.poll() is not None:
            print(f"Nao existe gravacao ativa para key={key}.")
            return

        self.status_store.set_stream(
            key=key,
            status=STATUS_STOPPING,
            detail=f"{reason} | finalizando gravacao",
            user_id=worker.user_id,
            seq=worker.seq,
            path_name=worker.path_name,
            stream_id=worker.stream_id,
            pid=worker.process.pid,
            active_file=worker.file_path,
        )

        process = worker.process
        try:
            if process.stdin:
                process.stdin.write("q")
                process.stdin.flush()
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        except Exception:
            process.kill()
            process.wait()

        with self._lock:
            self._workers.pop(key, None)
            publisher = self._publishers.get(key)

        normalized_reason = safe_segment(reason).lower()
        if "timeout" in normalized_reason:
            final_status = "error_timeout"
        elif "error" in normalized_reason or "falha" in normalized_reason:
            final_status = "error_connection"
        else:
            final_status = f"stopped_{normalized_reason}"
        self._log_recording_stop(worker, reason=reason, final_status=final_status)

        new_status = STATUS_ONLINE if publisher else STATUS_OFFLINE
        new_detail = f"{reason} | key={key}" if publisher else f"{reason} | key={key} (offline)"
        self.status_store.set_stream(
            key=key,
            status=new_status,
            detail=new_detail,
            user_id=worker.user_id,
            seq=worker.seq,
            path_name=worker.path_name if publisher else None,
            stream_id=worker.stream_id if publisher else None,
            pid=None,
            active_file=None,
        )

    def start_all_online(self, *, reason: str) -> None:
        with self._lock:
            keys = sorted(self._publishers.keys())
        if not keys:
            print("Nenhum publisher online para iniciar gravacao.")
            return
        for key in keys:
            self.start_recording(key, reason=reason)

    def stop_all(self, *, reason: str) -> None:
        with self._lock:
            keys = sorted(self._workers.keys())
        if not keys:
            print("Nao existe gravacao ativa.")
            return
        for key in keys:
            self.stop_recording(key, reason=reason)

    def _reap_finished_workers(self) -> None:
        finished: list[tuple[str, RecorderWorker, int]] = []
        with self._lock:
            for key, worker in list(self._workers.items()):
                code = worker.process.poll()
                if code is None:
                    continue
                finished.append((key, worker, code))
                self._workers.pop(key, None)

        for key, worker, code in finished:
            with self._lock:
                publisher = self._publishers.get(key)

            if publisher:
                status = STATUS_ONLINE
                detail = f"Gravacao finalizada (code={code}) | key={key}"
                path_name = publisher["path"]
                stream_id = publisher["id"]
                reason = f"process_exit_{code}"
            else:
                status = STATUS_OFFLINE
                detail = f"Gravacao finalizada e stream offline (code={code}) | key={key}"
                path_name = None
                stream_id = None
                reason = "connection_lost" if code != 0 else f"process_exit_{code}"

            final_status = "completed" if code == 0 else f"error_process_{code}"
            self._log_recording_stop(worker, reason=reason, final_status=final_status)

            self.status_store.set_stream(
                key=key,
                status=status,
                detail=detail,
                user_id=worker.user_id,
                seq=worker.seq,
                path_name=path_name,
                stream_id=stream_id,
                pid=None,
                active_file=None,
            )

    def _monitor_loop(self) -> None:
        previous_online_keys: set[str] = set()
        while not self._stop_event.is_set():
            try:
                publishers = self.protocol.discover_publishers()
            except Exception as exc:
                self.status_store.set_manager(
                    status=STATUS_ERROR,
                    detail=f"Falha API: {exc}",
                    publishers=0,
                    recordings=self._worker_count(),
                )
                time.sleep(self.poll_interval)
                continue

            with self._lock:
                self._publishers = publishers
                active_workers = set(self._workers.keys())

            online_keys = set(publishers.keys())
            entered = sorted(online_keys - previous_online_keys)
            left = sorted(previous_online_keys - online_keys)

            for key in entered:
                pub = publishers[key]
                if key not in active_workers:
                    self.status_store.set_stream(
                        key=key,
                        status=STATUS_ONLINE,
                        detail=f"Cliente conectado | path={pub['path']}",
                        user_id=self.user_id,
                        seq=self.seq_store.current_seq(key),
                        path_name=pub["path"],
                        stream_id=pub["id"],
                        pid=None,
                        active_file=None,
                    )
                if self.autostart_recording:
                    self.start_recording(key, reason="START automatico")

            for key in left:
                if key in active_workers:
                    continue
                self.status_store.set_stream(
                    key=key,
                    status=STATUS_OFFLINE,
                    detail="Cliente desconectou",
                    user_id=self.user_id,
                    seq=self.seq_store.current_seq(key),
                    path_name=None,
                    stream_id=None,
                    pid=None,
                    active_file=None,
                )

            self._reap_finished_workers()
            self.status_store.set_manager(
                status=STATUS_ONLINE,
                detail=self.protocol.monitor_detail,
                publishers=len(online_keys),
                recordings=self._worker_count(),
            )
            previous_online_keys = online_keys
            time.sleep(self.poll_interval)

    def _print_online(self) -> None:
        with self._lock:
            if not self._publishers:
                print("Nenhum publisher online.")
                return
            for key, item in sorted(self._publishers.items()):
                print(f"- key={key} path={item['path']} stream.id={item['id']} remote={item['remote_addr']}")

    def _print_status(self, key: Optional[str]) -> None:
        if key:
            print(self.status_store.snapshot_stream(safe_segment(key)))
            return
        print(self.status_store.snapshot_json())

    def _print_history(self, key: Optional[str]) -> None:
        normalized_key = safe_segment(key) if key else None
        print(self.history_store.snapshot(key=normalized_key, limit=50))

    def _handle_command(self, line: str) -> bool:
        parts = line.strip().split()
        if not parts:
            return True
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else None

        if cmd == "help":
            print("Comandos: online | start <key|all> | stop <key|all> | status [key] | history [key] | exit")
            return True
        if cmd == "online":
            self._print_online()
            return True
        if cmd == "status":
            self._print_status(arg)
            return True
        if cmd == "history":
            self._print_history(arg)
            return True
        if cmd == "start":
            if not arg or arg == "all":
                self.start_all_online(reason="START autorizado")
            else:
                self.start_recording(arg, reason="START autorizado")
            return True
        if cmd == "stop":
            if not arg or arg == "all":
                self.stop_all(reason="STOP solicitado")
            else:
                self.stop_recording(arg, reason="STOP solicitado")
            return True
        if cmd in {"exit", "quit", "q"}:
            return False

        print("Comando invalido. Use: help | online | start <key|all> | stop <key|all> | status [key] | history [key] | exit")
        return True

    def run(self) -> None:
        print("Ingest Manager v4")
        print(f"Transporte: {self.protocol.protocol_name.upper()}")
        print(f"Config JSON: {self.config_path}")
        print(f"Status JSON: {self.status_file}")
        print(f"Sequence JSON: {self.seq_file}")
        print(f"History JSON: {self.history_file}")
        print("")
        print("URL de push recomendada (key no path):")
        print(self.protocol.scale_style_push_url())
        print("")
        print("URL legada (key na query):")
        print(self.protocol.query_style_push_url())
        print(self.protocol.path_concurrency_note)
        print("")
        print("Comandos: help | online | start <key|all> | stop <key|all> | status [key] | history [key] | exit")

        if not self.external_server:
            self.start_container()

        monitor = threading.Thread(target=self._monitor_loop, daemon=True)
        monitor.start()

        try:
            while True:
                try:
                    keep = self._handle_command(input("> "))
                except EOFError:
                    keep = False
                if not keep:
                    break
        finally:
            self._stop_event.set()
            self.stop_all(reason="STOP encerramento")
            self.status_store.set_manager(
                status=STATUS_OFFLINE,
                detail="Manager encerrado",
                publishers=0,
                recordings=0,
            )
            if not self.external_server:
                self.stop_container()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manager de ingest multi-stream com workers isolados e seq persistente estilo DB."
    )
    parser.add_argument(
        "--config-json",
        default=DEFAULT_CONFIG_JSON,
        help=f"Arquivo JSON de configuracao. Padrao: {DEFAULT_CONFIG_JSON}",
    )
    parser.add_argument(
        "--public-host",
        default=None,
        help="Override do host publico no config JSON (salva no arquivo).",
    )
    parser.add_argument(
        "--external-server",
        action="store_true",
        help="Override: usa servidor RTMP/API externo e nao sobe container.",
    )
    parser.add_argument(
        "--autostart",
        action="store_true",
        help="Override: inicia gravacao automaticamente quando publisher conectar.",
    )
    parser.add_argument(
        "--max-recordings",
        type=int,
        default=None,
        help="Override: limite maximo de gravacoes simultaneas.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config_json)
    public_host = args.public_host or detect_public_host() or DEFAULT_PUBLIC_HOST
    config = load_or_create_config(config_path, public_host=public_host)

    if args.public_host:
        config["server"]["public_host"] = args.public_host
    if args.external_server:
        config["runtime"]["external_server"] = True
    if args.autostart:
        config["runtime"]["autostart_recording"] = True
    if args.max_recordings is not None:
        config["runtime"]["max_concurrent_recordings"] = max(args.max_recordings, 1)

    write_json(config_path, config)

    manager = IngestManager(config=config, config_path=config_path)
    manager.run()


if __name__ == "__main__":
    main()
