import argparse
import json
import re
import subprocess
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Iterable


DEFAULT_KEYS = ["1f0929ac30c7", "zzzzzzzzzzzzz", "aaaaaaaaaaa"]
DEFAULT_MANAGER_SCRIPT = str(Path(__file__).resolve().with_name("ingest_manager.py"))
DEFAULT_CONFIG_JSON = "deploy/ingest/rtmp_ingest_manager_config.json"
DEFAULT_HISTORY_JSON = ".runtime/rtmp_ingest_manager/recording_history.json"

SAFE_NAME_RE = re.compile(r"[^a-z0-9]+")


def run_cmd(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True)


def safe_name(value: str) -> str:
    return SAFE_NAME_RE.sub("-", value.lower()).strip("-") or "unknown"


def discover_sample_file(explicit_path: str | None) -> Path:
    if explicit_path:
        path = Path(explicit_path)
        if not path.exists():
            raise RuntimeError(f"Arquivo de sample nao encontrado: {path}")
        return path

    recordings_root = Path("recordings")
    if recordings_root.exists():
        for extension in ("*.mkv", "*.mp4"):
            files = sorted(recordings_root.rglob(extension))
            if files:
                return files[0]
    raise RuntimeError("Nenhum sample de video encontrado em recordings/ (mkv/mp4).")


def push_url(host: str, port: int, app: str, stream: str, key: str, *, key_in_path: bool) -> str:
    app_clean = app.strip("/")
    stream_clean = stream.strip("/")
    if key_in_path:
        return f"rtmp://{host}:{port}/{app_clean}/{key}/{stream_clean}"
    return f"rtmp://{host}:{port}/{app_clean}/{stream_clean}?key={key}"


def start_loop_publisher(
    *,
    key: str,
    sample_file: Path,
    host: str,
    port: int,
    app: str,
    stream: str,
    key_in_path: bool,
) -> str:
    name = f"rtmp-loop-{safe_name(key)[:24]}"
    run_cmd(["docker", "rm", "-f", name])
    url = push_url(host=host, port=port, app=app, stream=stream, key=key, key_in_path=key_in_path)
    command = [
        "docker",
        "run",
        "-d",
        "--rm",
        "--name",
        name,
        "-v",
        f"{sample_file.resolve()}:/input/sample.mkv:ro",
        "jrottenberg/ffmpeg:6.1-alpine",
        "-re",
        "-stream_loop",
        "-1",
        "-i",
        "/input/sample.mkv",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-tune",
        "zerolatency",
        "-an",
        "-f",
        "flv",
        url,
    ]
    result = run_cmd(command)
    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip() or "erro desconhecido"
        raise RuntimeError(f"Falha ao subir publisher key={key}: {error}")
    return name


def stop_loop_publishers(names: Iterable[str]) -> None:
    for name in names:
        run_cmd(["docker", "rm", "-f", name])


def stream_manager_output(process: subprocess.Popen[str]) -> None:
    if process.stdout is None:
        return
    for line in process.stdout:
        text = line.rstrip()
        if text:
            print(f"[MANAGER] {text}")


def send_manager_command(process: subprocess.Popen[str], command: str) -> None:
    if process.stdin is None:
        raise RuntimeError("stdin do manager nao esta disponivel.")
    process.stdin.write(f"{command}\n")
    process.stdin.flush()
    print(f"[RUNNER] > {command}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Runner de estresse para ingestao RTMP com multiplas keys e START/STOP controlado."
    )
    parser.add_argument("--public-host", default="192.168.10.19", help="Host usado no publish URL.")
    parser.add_argument("--rtmp-port", type=int, default=8554, help="Porta RTMP do servidor.")
    parser.add_argument("--app", default="surgwaze/v1", help="App prefix do path RTMP.")
    parser.add_argument("--stream", default="stream", help="Nome do stream RTMP.")
    parser.add_argument("--key-in-path", action="store_true", help="Usa URL escalavel: /<app>/<key>/<stream>.")
    parser.add_argument("--keys", default=",".join(DEFAULT_KEYS), help="Lista de keys separadas por virgula.")
    parser.add_argument("--sample-file", default=None, help="Arquivo de video usado no loop publisher.")
    parser.add_argument("--manager-script", default=DEFAULT_MANAGER_SCRIPT, help="Script do manager.")
    parser.add_argument("--config-json", default=DEFAULT_CONFIG_JSON, help="Arquivo de config do manager.")
    parser.add_argument("--history-json", default=DEFAULT_HISTORY_JSON, help="Arquivo JSON de historico.")
    parser.add_argument("--record-seconds", type=int, default=8, help="Duracao de cada gravacao por ciclo.")
    parser.add_argument("--interval-seconds", type=int, default=10, help="Intervalo entre acoes.")
    parser.add_argument("--cycles", type=int, default=3, help="Quantidade de ciclos START/STOP ALL.")
    parser.add_argument(
        "--stop-wait-seconds",
        type=int,
        default=8,
        help="Tempo de espera apos STOP ALL para garantir finalizacao dos workers.",
    )
    parser.add_argument(
        "--run-sequence-demo",
        action="store_true",
        help="Executa cenario: start all -> stop z -> stop a -> start z -> stop real -> stop z.",
    )
    parser.add_argument("--keep-publishers", action="store_true", help="Nao derruba os publishers ao final.")
    return parser.parse_args()


def history_counts(history_path: Path) -> Counter[str]:
    if not history_path.exists():
        return Counter()
    payload = json.loads(history_path.read_text(encoding="utf-8"))
    return Counter(str(item.get("key") or "") for item in (payload.get("records") or []))


def main() -> None:
    args = parse_args()
    keys = [item.strip() for item in args.keys.split(",") if item.strip()]
    if not keys:
        raise SystemExit("Lista de keys vazia.")

    sample_file = discover_sample_file(args.sample_file)
    history_path = Path(args.history_json)
    before_counts = history_counts(history_path)
    print(f"[RUNNER] Sample: {sample_file}")
    print(f"[RUNNER] Keys: {', '.join(keys)}")

    publisher_names: list[str] = []
    manager_process: subprocess.Popen[str] | None = None
    manager_reader: threading.Thread | None = None

    try:
        for key in keys:
            name = start_loop_publisher(
                key=key,
                sample_file=sample_file,
                host=args.public_host,
                port=args.rtmp_port,
                app=args.app,
                stream=args.stream,
                key_in_path=args.key_in_path,
            )
            publisher_names.append(name)
            print(f"[RUNNER] Publisher online key={key} container={name}")

        time.sleep(4)

        manager_cmd = [
            "python",
            args.manager_script,
            "--config-json",
            args.config_json,
            "--external-server",
            "--public-host",
            args.public_host,
        ]
        manager_process = subprocess.Popen(
            manager_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        manager_reader = threading.Thread(target=stream_manager_output, args=(manager_process,), daemon=True)
        manager_reader.start()

        time.sleep(3)
        send_manager_command(manager_process, "online")
        time.sleep(1)

        if args.run_sequence_demo and len(keys) >= 3:
            key_real = keys[0]
            key_z = keys[1]
            key_a = keys[2]
            send_manager_command(manager_process, "start all")
            time.sleep(args.interval_seconds)
            send_manager_command(manager_process, f"stop {key_z}")
            time.sleep(args.interval_seconds)
            send_manager_command(manager_process, f"stop {key_a}")
            time.sleep(args.interval_seconds)
            send_manager_command(manager_process, f"start {key_z}")
            time.sleep(args.interval_seconds)
            send_manager_command(manager_process, f"stop {key_real}")
            time.sleep(args.interval_seconds)
            send_manager_command(manager_process, f"stop {key_z}")
            time.sleep(args.interval_seconds)

        for index in range(args.cycles):
            print(f"[RUNNER] Cycle {index + 1}/{args.cycles}")
            send_manager_command(manager_process, "start all")
            time.sleep(max(args.record_seconds, 1))
            send_manager_command(manager_process, "stop all")
            time.sleep(max(args.stop_wait_seconds, 1))
            if index < args.cycles - 1:
                time.sleep(max(args.interval_seconds, 1))

        send_manager_command(manager_process, "history")
        time.sleep(2)
        send_manager_command(manager_process, "exit")

        try:
            manager_process.wait(timeout=120)
        except subprocess.TimeoutExpired:
            manager_process.kill()
            manager_process.wait()
        if manager_reader is not None:
            manager_reader.join(timeout=2)

        if history_path.exists():
            payload = json.loads(history_path.read_text(encoding="utf-8"))
            records = payload.get("records") or []
            by_key: dict[str, int] = {}
            for item in records:
                key = str(item.get("key") or "")
                by_key[key] = by_key.get(key, 0) + 1
            print(f"[RUNNER] Historico total: {len(records)} entradas")
            for key in keys:
                after_total = by_key.get(key, 0)
                delta = after_total - before_counts.get(key, 0)
                print(f"[RUNNER] key={key} -> total={after_total} delta={delta}")
        else:
            print(f"[RUNNER] Historico nao encontrado: {history_path}")
    finally:
        if manager_process and manager_process.poll() is None:
            try:
                send_manager_command(manager_process, "exit")
            except Exception:
                pass
            try:
                manager_process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                manager_process.kill()
                manager_process.wait()
        if not args.keep_publishers:
            stop_loop_publishers(publisher_names)


if __name__ == "__main__":
    main()
