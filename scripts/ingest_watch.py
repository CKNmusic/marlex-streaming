import argparse
import base64
import datetime
import json
import time
import urllib.request
from pathlib import Path


STATUS_OFFLINE = "Offline"
STATUS_ONLINE = "Online"
STATUS_RECORDING = "Recording"


def _auth_header(user: str, password: str) -> str:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def fetch_paths(api_url: str, user: str, password: str) -> list[dict]:
    req = urllib.request.Request(f"{api_url.rstrip('/')}/v3/paths/list")
    req.add_header("Authorization", _auth_header(user, password))
    with urllib.request.urlopen(req, timeout=3.0) as response:
        body = response.read().decode("utf-8")
    data = json.loads(body)
    return data.get("items", [])


def choose_path(items: list[dict], expected_path: str, allow_fallback: bool) -> tuple[str, dict | None, bool]:
    for item in items:
        if item.get("name") == expected_path:
            return expected_path, item, False

    if allow_fallback:
        online_items = [item for item in items if item.get("online", False)]
        if online_items:
            selected = online_items[0]
            name = str(selected.get("name", expected_path))
            return name, selected, True

    return expected_path, None, False


class StatusWriter:
    def __init__(self, file_path: Path, source_url: str) -> None:
        self.file_path = file_path
        self.source_url = source_url
        self._last_signature: tuple | None = None

    def write(self, status: str, detail: str, path_name: str, bytes_received: int | None) -> None:
        signature = (status, detail, path_name, bytes_received)
        if signature == self._last_signature:
            return

        payload = {
            "status": status,
            "detail": detail,
            "path": path_name,
            "publish_url": self.source_url,
            "bytes_received": bytes_received,
            "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        self._last_signature = signature
        print(f"[STATUS] {status} - {detail}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor de ingestao RTMP (MediaMTX API) com status Offline/Online/Recording."
    )
    parser.add_argument("--api-url", default="http://127.0.0.1:9997", help="URL base da API do MediaMTX.")
    parser.add_argument("--api-user", default="api", help="Usuario da API.")
    parser.add_argument("--api-pass", default="api", help="Senha da API.")
    parser.add_argument("--expected-path", default="live/myStream", help="Path esperado de publish.")
    parser.add_argument("--public-host", default="127.0.0.1", help="Host publico usado para montar publish_url.")
    parser.add_argument("--rtmp-port", type=int, default=10080, help="Porta RTMP.")
    parser.add_argument("--status-file", default="recordings/ingest_status/receiver_status.json", help="Arquivo JSON de status.")
    parser.add_argument("--poll-interval", type=float, default=0.25, help="Intervalo de polling em segundos.")
    parser.add_argument(
        "--strict-path",
        action="store_true",
        help="Nao usar fallback automatico para outros paths online.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    publish_url = f"rtmp://{args.public_host}:{args.rtmp_port}/{args.expected_path}"
    writer = StatusWriter(Path(args.status_file), publish_url)

    print("Monitor de ingestao iniciado.")
    print(f"API: {args.api_url}")
    print(f"Path esperado: {args.expected_path}")
    print(f"Status JSON: {args.status_file}")
    print("Ctrl+C para encerrar.")

    last_bytes_by_path: dict[str, int] = {}
    allow_fallback = not args.strict_path

    while True:
        try:
            items = fetch_paths(args.api_url, args.api_user, args.api_pass)
            current_path, item, dynamic = choose_path(items, args.expected_path, allow_fallback)
        except Exception as exc:
            writer.write(
                STATUS_OFFLINE,
                f"Falha ao consultar API: {exc}",
                args.expected_path,
                None,
            )
            time.sleep(args.poll_interval)
            continue

        if item is None or not item.get("online", False):
            writer.write(STATUS_OFFLINE, "Aguardando cliente RTMP", args.expected_path, None)
            last_bytes_by_path = {}
            time.sleep(args.poll_interval)
            continue

        current_bytes = int(item.get("bytesReceived", 0))
        previous_bytes = last_bytes_by_path.get(current_path)
        path_msg = f" (path detectado: {current_path})" if dynamic else ""

        if previous_bytes is None:
            writer.write(STATUS_ONLINE, f"Cliente conectado{path_msg}", current_path, current_bytes)
        elif current_bytes > previous_bytes:
            writer.write(STATUS_RECORDING, f"Fluxo recebendo e gravando{path_msg}", current_path, current_bytes)
        else:
            writer.write(
                STATUS_ONLINE,
                f"Cliente conectado (sem novos bytes){path_msg}",
                current_path,
                current_bytes,
            )

        last_bytes_by_path[current_path] = current_bytes
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
