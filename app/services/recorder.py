import asyncio
import datetime
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

from app.services.stream_protocols import ffmpeg_input_args_for_url


def normalize_recordings_dir(path: Optional[str]) -> str:
    raw = (path or "").strip()
    if not raw:
        return "/recordings"
    normalized = os.path.normpath(os.path.expanduser(raw))
    if normalized in {".", ""}:
        return "/recordings"
    return normalized


@dataclass
class RecordingRuntime:
    record_id: int
    output_path: str
    work_dir: str
    output_format: str = "mp4"
    segment_extension: str = "mp4"
    started_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)
    attempts: int = 0
    run_dirs: List[str] = field(default_factory=list)
    last_measurement_ts: float = 0.0
    last_measurement_bytes: int = 0
    transfer_rate_bps: float = 0.0


class RecorderService:
    def __init__(self):
        # Maps device_id (int) -> subprocess instance
        self._active_recordings: Dict[int, Optional[asyncio.subprocess.Process]] = {}
        # Maps device_id (int) -> record_id (int)
        self._recording_map: Dict[int, int] = {}
        # Runtime metadata for each active recording
        self._recording_runtime: Dict[int, RecordingRuntime] = {}
        self._recording_watchdog: Dict[int, asyncio.Task] = {}
        self._stop_events: Dict[int, asyncio.Event] = {}
        self._state_by_device: Dict[int, str] = {}
        self._last_stop_info: Dict[int, Dict[str, Any]] = {}

        # Ensure recordings directory exists
        self.recordings_dir = "/recordings"
        self.set_recordings_dir(os.getenv("RECORDER_OUTPUT_DIR", "/recordings"))

        self.segment_seconds = int(os.getenv("RECORDER_SEGMENT_SECONDS", "120"))
        self.restart_delay_seconds = float(os.getenv("RECORDER_RESTART_DELAY_SECONDS", "2"))
        self.start_attempts = max(1, int(os.getenv("RECORDER_START_ATTEMPTS", "3")))
        # Real ffmpeg recording is enabled by default when ffmpeg exists.
        # Set RECORDER_ENABLE_FFMPEG=0 to force simulated mode.
        self._ffmpeg_available = bool(shutil.which("ffmpeg")) and (
            os.getenv("RECORDER_ENABLE_FFMPEG", "1").strip().lower() in {"1", "true", "yes", "on"}
        )
        self.min_free_space_bytes = 500 * 1024 * 1024  # 500 MB limit


    def set_recordings_dir(self, path: Optional[str]) -> str:
        normalized = normalize_recordings_dir(path)
        try:
            os.makedirs(normalized, exist_ok=True)
            self.recordings_dir = normalized
            return normalized
        except PermissionError:
            # Local/dev fallback when root-level mount is unavailable.
            fallback = os.path.normpath("recordings")
            os.makedirs(fallback, exist_ok=True)
            self.recordings_dir = fallback
            return fallback

    def _process_alive(self, process: Optional[asyncio.subprocess.Process]) -> bool:
        if process is None:
            return True
        return process.returncode is None

    def _clear_runtime_tracking(self, device_id: int) -> None:
        self._active_recordings.pop(device_id, None)
        self._recording_map.pop(device_id, None)
        self._recording_runtime.pop(device_id, None)
        self._recording_watchdog.pop(device_id, None)
        self._stop_events.pop(device_id, None)

    def _set_state(self, device_id: int, state: str) -> None:
        self._state_by_device[device_id] = state

    def _normalize_stream_key(self, raw_key: Optional[str]) -> str:
        value = str(raw_key or "").strip()
        if not value:
            return ""
        cleaned = re.sub(r"[^A-Za-z0-9]", "", value).upper()
        return cleaned

    def _extract_stream_key(self, source_url: str) -> str:
        payload = str(source_url or "").strip()
        if not payload:
            return ""
        try:
            parsed = urlparse(payload)
            parts = [unquote(item).strip() for item in parsed.path.split("/") if item.strip()]
            if not parts:
                return ""
            candidate = parts[-2] if len(parts) >= 2 and parts[-1].lower() == "stream" else parts[-1]
            return self._normalize_stream_key(candidate)
        except Exception:
            return ""

    def _runtime_recorded_size_bytes(self, runtime: RecordingRuntime) -> int:
        total_size = 0
        for run_dir in runtime.run_dirs:
            run_path = Path(run_dir)
            if not run_path.exists():
                continue
            for segment_file in run_path.glob(f"segment_*.{runtime.segment_extension}"):
                try:
                    total_size += int(segment_file.stat().st_size)
                except OSError:
                    continue
        return max(total_size, 0)

    def get_state(self, device_id: int) -> str:
        return self._state_by_device.get(device_id, "Offline")

    def get_last_stop_info(self, device_id: int) -> Optional[Dict[str, Any]]:
        return self._last_stop_info.get(device_id)

    def get_recording_transfer_rate_bps(self, device_id: int) -> Optional[float]:
        runtime = self._recording_runtime.get(device_id)
        process = self._active_recordings.get(device_id)
        if runtime is None or not self._process_alive(process):
            return None

        now_ts = time.monotonic()
        current_size = self._runtime_recorded_size_bytes(runtime)

        if runtime.last_measurement_ts <= 0:
            runtime.last_measurement_ts = now_ts
            runtime.last_measurement_bytes = current_size
            elapsed = max((datetime.datetime.utcnow() - runtime.started_at).total_seconds(), 0.001)
            runtime.transfer_rate_bps = max(current_size / elapsed, 0.0)
            return round(runtime.transfer_rate_bps, 2)

        elapsed_since_last = max(now_ts - runtime.last_measurement_ts, 0.001)
        delta_size = max(current_size - runtime.last_measurement_bytes, 0)
        runtime.transfer_rate_bps = max(delta_size / elapsed_since_last, 0.0)
        runtime.last_measurement_ts = now_ts
        runtime.last_measurement_bytes = current_size
        return round(runtime.transfer_rate_bps, 2)

    def get_output_path(
        self,
        record_id: int,
        output_format: str = "mp4",
        *,
        owner_id: Optional[int] = None,
        stream_key: Optional[str] = None,
        started_at: Optional[datetime.datetime] = None,
    ) -> str:
        extension = "mkv" if (output_format or "").strip().lower() == "mkv" else "mp4"
        date_token = (started_at or datetime.datetime.utcnow()).strftime("%Y_%m_%d")
        
        # Format: <date>_<user_id>_<record_id>.<ext>
        # If owner_id is missing, fallback to record_id only to avoid crashing, 
        # but the plan requires strict format so we should ensure owner_id is passed.
        user_part = str(owner_id) if owner_id is not None else "unknown"
        filename = f"{date_token}_{user_part}_{record_id}.{extension}"
        
        # Subdirectory strategy: keep using stream_key or date to avoid massive single folder?
        # User asked for specific filename format, didn't specify folder structure change 
        # but keeping inside recordings_dir is safer.
        # Let's keep the existing folder organization by key/date to not break browsing, 
        # or flat? The request specific filename usually implies they want to find it easily.
        # "Ingest grava na pasta que recordings? Está com o nome que eu pedi..."
        # I will keep utilizing the subdirectory structure for organization but use the requested filename.
        
        normalized_key = self._normalize_stream_key(stream_key)
        if normalized_key:
            dir_date_token = (started_at or datetime.datetime.utcnow()).strftime("%Y%m%d")
            target_dir = os.path.join(self.recordings_dir, normalized_key, dir_date_token)
        else:
            target_dir = self.recordings_dir
            
        os.makedirs(target_dir, exist_ok=True)
        return os.path.join(target_dir, filename)

    def _get_work_dir(
        self,
        record_id: int,
        *,
        stream_key: Optional[str] = None,
        started_at: Optional[datetime.datetime] = None,
    ) -> str:
        normalized_key = self._normalize_stream_key(stream_key)
        if normalized_key:
            date_token = (started_at or datetime.datetime.utcnow()).strftime("%Y%m%d")
            return os.path.join(self.recordings_dir, normalized_key, date_token, f"record_{record_id}_segments")
        return os.path.join(self.recordings_dir, f"record_{record_id}_segments")

    async def _spawn_ffmpeg_process(
        self,
        runtime: RecordingRuntime,
        source_url: str,
        profile: str,
    ) -> Optional[asyncio.subprocess.Process]:
        runtime.attempts += 1
        run_dir = os.path.join(runtime.work_dir, f"run_{runtime.attempts:04d}")
        os.makedirs(run_dir, exist_ok=True)
        runtime.run_dirs.append(run_dir)
        segment_pattern = os.path.join(run_dir, f"segment_%06d.{runtime.segment_extension}")

        ffmpeg_args: List[str] = ["ffmpeg"]
        ffmpeg_args.extend(ffmpeg_input_args_for_url(source_url))

        ffmpeg_args.extend(["-i", source_url])

        if profile == "compressed":
            ffmpeg_args.extend(
                [
                    "-c:v",
                    "libx264",
                    "-crf",
                    "23",
                    "-preset",
                    "ultrafast",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                ]
            )
        else:
            ffmpeg_args.extend(["-c", "copy"])

        if runtime.output_format == "mp4":
            ffmpeg_args.extend(["-movflags", "+faststart"])

        segment_format = "matroska" if runtime.output_format == "mkv" else "mp4"
        ffmpeg_args.extend(
            [
                "-f",
                "segment",
                "-segment_time",
                str(self.segment_seconds),
                "-reset_timestamps",
                "1",
                "-segment_format",
                segment_format,
                "-y",
                segment_pattern,
            ]
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            # Fast-fail if source URL is unreachable/invalid.
            await asyncio.sleep(0.8)
            if process.returncode is not None:
                return None
            return process
        except Exception as e:
            print(f"Error starting ffmpeg: {e}")
            return None

    async def _watch_and_restart(
        self,
        device_id: int,
        source_url: str,
        profile: str,
    ) -> None:
        while True:
            stop_event = self._stop_events.get(device_id)
            runtime = self._recording_runtime.get(device_id)
            process = self._active_recordings.get(device_id)
            if stop_event is None or runtime is None or process is None:
                return

            try:
                await process.wait()
            except Exception:
                pass

            if stop_event.is_set():
                return

            await asyncio.sleep(self.restart_delay_seconds)

            self._set_state(device_id, "Starting")
            restarted = await self._spawn_ffmpeg_process(runtime, source_url, profile)
            if restarted is not None:
                self._active_recordings[device_id] = restarted
                self._set_state(device_id, "Recording")
                continue

            # If restart fails, mark runtime as failed and stop watchdog loop.
            self._set_state(device_id, "Offline")
            await self._finalize_segmented_recording(runtime)
            shutil.rmtree(runtime.work_dir, ignore_errors=True)
            self._last_stop_info[device_id] = {
                "record_id": runtime.record_id,
                "reason": "error_connection",
                "final_status": "error_connection",
                "started_at": runtime.started_at.isoformat(timespec="seconds"),
                "ended_at": datetime.datetime.utcnow().isoformat(timespec="seconds"),
                "output_path": runtime.output_path,
                "file_size_bytes": os.path.getsize(runtime.output_path) if os.path.exists(runtime.output_path) else 0,
            }
            self._clear_runtime_tracking(device_id)
            return

    async def _finalize_segmented_recording(self, runtime: RecordingRuntime) -> None:
        segment_files: List[str] = []
        for run_dir in runtime.run_dirs:
            run_path = Path(run_dir)
            if not run_path.exists():
                continue
            for segment_file in sorted(run_path.glob(f"segment_*.{runtime.segment_extension}")):
                segment_files.append(str(segment_file.resolve()))

        if not segment_files:
            return

        if len(segment_files) == 1:
            if runtime.output_format == "mp4":
                try:
                    faststart_proc = await asyncio.create_subprocess_exec(
                        "ffmpeg", "-i", segment_files[0],
                        "-c", "copy", "-movflags", "+faststart",
                        "-y", runtime.output_path,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    await faststart_proc.wait()
                    if faststart_proc.returncode != 0:
                        shutil.copyfile(segment_files[0], runtime.output_path)
                except Exception:
                    shutil.copyfile(segment_files[0], runtime.output_path)
            else:
                shutil.copyfile(segment_files[0], runtime.output_path)
            return

        concat_file = os.path.join(runtime.work_dir, "concat_list.txt")
        with open(concat_file, "w", encoding="utf-8") as concat_handle:
            for segment_file in segment_files:
                safe_path = segment_file.replace("'", "'\\''")
                concat_handle.write(f"file '{safe_path}'\n")

        try:
            concat_args = [
                "ffmpeg",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                concat_file,
                "-c",
                "copy",
            ]
            if runtime.output_format == "mp4":
                concat_args.extend(["-movflags", "+faststart"])
            concat_args.extend(["-y", runtime.output_path])
            concat_process = await asyncio.create_subprocess_exec(
                *concat_args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await concat_process.wait()
            if concat_process.returncode != 0:
                shutil.copyfile(segment_files[0], runtime.output_path)
        except Exception:
            shutil.copyfile(segment_files[0], runtime.output_path)

    async def start_recording(
        self,
        device_id: int,
        record_id: int,
        source_url: str,
        owner_id: int,
        profile: str = "passthrough",
        output_format: str = "mp4",
    ) -> Optional[str]:
        """
        Starts an FFmpeg process to record the stream.
        Includes segmented capture + watchdog restart for unstable links.
        """
        # 0. Disk Space Check
        try:
            total, used, free = shutil.disk_usage(self.recordings_dir)
            if free < self.min_free_space_bytes:
                print(f"Disk space too low: {free} bytes free, need {self.min_free_space_bytes}")
                return None
        except Exception as e:
            print(f"Error checking disk space: {e}")
            # Proceed with caution if check fails? Or block?
            # Safer to block if critical.
            return None

        if device_id in self._recording_map:
            return None  # Already recording

        self._set_state(device_id, "Starting")
        recording_started_at = datetime.datetime.utcnow()
        normalized_output_format = "mkv" if (output_format or "").strip().lower() == "mkv" else "mp4"
        stream_key = self._extract_stream_key(source_url)
        output_path = self.get_output_path(
            record_id,
            normalized_output_format,
            owner_id=owner_id,
            stream_key=stream_key,
            started_at=recording_started_at,
        )
        work_dir = self._get_work_dir(
            record_id,
            stream_key=stream_key,
            started_at=recording_started_at,
        )
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        os.makedirs(work_dir, exist_ok=True)
        if os.path.exists(output_path):
            os.remove(output_path)

        runtime = RecordingRuntime(
            record_id=record_id,
            output_path=output_path,
            work_dir=work_dir,
            output_format=normalized_output_format,
            segment_extension=normalized_output_format,
            started_at=recording_started_at,
        )
        self._recording_runtime[device_id] = runtime
        self._recording_map[device_id] = record_id

        if not self._ffmpeg_available:
            self._clear_runtime_tracking(device_id)
            self._set_state(device_id, "Offline")
            self._last_stop_info[device_id] = {
                "record_id": runtime.record_id,
                "reason": "error_ffmpeg_unavailable",
                "final_status": "error_ffmpeg_unavailable",
                "started_at": runtime.started_at.isoformat(timespec="seconds"),
                "ended_at": datetime.datetime.utcnow().isoformat(timespec="seconds"),
                "output_path": output_path,
                "file_size_bytes": 0,
            }
            return None

        process: Optional[asyncio.subprocess.Process] = None
        for attempt in range(self.start_attempts):
            process = await self._spawn_ffmpeg_process(runtime, source_url, profile)
            if process is not None:
                break
            if attempt < self.start_attempts - 1:
                await asyncio.sleep(min(self.restart_delay_seconds, 1.0))

        if process is None:
            self._clear_runtime_tracking(device_id)
            self._set_state(device_id, "Offline")
            shutil.rmtree(runtime.work_dir, ignore_errors=True)
            self._last_stop_info[device_id] = {
                "record_id": runtime.record_id,
                "reason": "error_connection",
                "final_status": "error_connection",
                "started_at": runtime.started_at.isoformat(timespec="seconds"),
                "ended_at": datetime.datetime.utcnow().isoformat(timespec="seconds"),
                "output_path": output_path,
                "file_size_bytes": 0,
                "attempts": runtime.attempts,
            }
            return None

        self._active_recordings[device_id] = process
        stop_event = asyncio.Event()
        self._stop_events[device_id] = stop_event
        self._recording_watchdog[device_id] = asyncio.create_task(
            self._watch_and_restart(device_id, source_url, profile)
        )
        self._set_state(device_id, "Recording")
        return output_path

    async def stop_recording(
        self,
        device_id: int,
        *,
        reason: str = "user",
        final_status: Optional[str] = None,
    ) -> bool:
        """
        Stops the recording process for a device and finalizes segmented output.
        """
        if device_id not in self._recording_map:
            return False

        status_value = final_status or f"stopped_{reason}"
        self._set_state(device_id, "Stopping")
        stop_event = self._stop_events.get(device_id)
        if stop_event is not None:
            stop_event.set()

        process = self._active_recordings.get(device_id)
        if process is not None:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5)
            except Exception:
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass

        watchdog = self._recording_watchdog.get(device_id)
        if watchdog is not None:
            try:
                await watchdog
            except Exception:
                pass

        runtime = self._recording_runtime.get(device_id)
        if self._ffmpeg_available and runtime is not None:
            await self._finalize_segmented_recording(runtime)
            shutil.rmtree(runtime.work_dir, ignore_errors=True)

        ended_at = datetime.datetime.utcnow()
        started_at = runtime.started_at if runtime is not None else ended_at
        output_path = runtime.output_path if runtime is not None else self.get_output_path(self._recording_map[device_id])
        file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        self._last_stop_info[device_id] = {
            "record_id": runtime.record_id if runtime is not None else self._recording_map[device_id],
            "reason": reason,
            "final_status": status_value,
            "started_at": started_at.isoformat(timespec="seconds"),
            "ended_at": ended_at.isoformat(timespec="seconds"),
            "output_path": output_path,
            "file_size_bytes": file_size,
        }

        self._clear_runtime_tracking(device_id)
        self._set_state(device_id, "Offline")
        return True

    def is_recording(self, device_id: int) -> bool:
        process = self._active_recordings.get(device_id)
        if process is None:
            return False
        return self._process_alive(process)

    def active_count(self) -> int:
        count = 0
        for process in self._active_recordings.values():
            if process is None:
                count += 1
                continue
            if process.returncode is None:
                count += 1
        return count


recorder_service = RecorderService()
