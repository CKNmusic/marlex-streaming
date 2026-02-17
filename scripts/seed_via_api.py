#!/usr/bin/env python3
"""
Populate test baseline data through API calls (no direct DB inserts).

Usage:
  PYTHONPATH=. .venv/bin/python3 scripts/seed_via_api.py \
    --base-url http://127.0.0.1:8001/surgwaze/v1
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Dict, List, Optional, Tuple

import httpx


DEFAULT_BASE_URL = "http://127.0.0.1:8001/surgwaze/v1"


def norm(value: str) -> str:
    return value.strip().lower()


class ApiSeeder:
    def __init__(self, base_url: str, admin_user: str, admin_pass: str, app_host: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.admin_user = admin_user
        self.admin_pass = admin_pass
        self.app_host = app_host
        self.client = httpx.Client(timeout=15.0)
        self.token: Optional[str] = None

    def close(self) -> None:
        self.client.close()

    def _url(self, path: str) -> str:
        if path.startswith("/"):
            return f"{self.base_url}{path}"
        return f"{self.base_url}/{path}"

    def _headers(self, auth: bool = True) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = True,
        expected_status: Tuple[int, ...] = (200,),
        **kwargs: Any,
    ) -> httpx.Response:
        response = self.client.request(
            method=method,
            url=self._url(path),
            headers=self._headers(auth=auth),
            **kwargs,
        )
        if response.status_code not in expected_status:
            raise RuntimeError(
                f"{method} {path} -> {response.status_code}\n{response.text}"
            )
        return response

    def login(self) -> bool:
        response = self.client.post(
            self._url("/login/access-token"),
            data={"username": self.admin_user, "password": self.admin_pass},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code != 200:
            return False
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            return False
        self.token = token
        return True

    def bootstrap_first_admin_if_needed(self) -> None:
        if self.login():
            print("[seed] admin login: ok")
            return

        print("[seed] admin login failed; trying /users/bootstrap ...")
        payload = {
            "username": self.admin_user,
            "full_name": "Manager Agent",
            "password": self.admin_pass,
            "is_superuser": True,
            "is_active": True,
        }
        response = self.request(
            "POST",
            "/users/bootstrap",
            auth=False,
            json=payload,
            expected_status=(201, 409),
        )
        if response.status_code == 201:
            print("[seed] bootstrap: created first admin user")
        else:
            print("[seed] bootstrap: already initialized")

        if not self.login():
            raise RuntimeError(
                "Unable to login as admin after bootstrap. "
                "Check credentials or clean DB state."
            )
        print("[seed] admin login after bootstrap: ok")

    def ensure_app_settings(self) -> None:
        payload = {
            "name": "Projeto SurgWaze",
            "description": "Streaming M\u00e9dico",
            "host": self.app_host,
            "output_format": "mkv",
        }
        self.request("PATCH", "/app-settings/", json=payload, expected_status=(200,))
        print("[seed] app-settings: ok")

    def ensure_protocols(self) -> None:
        target = [
            {"protocol": "srt", "port": 9000, "is_active": True},
            {"protocol": "rtmp", "port": 8554, "is_active": True},
        ]
        existing = self.request("GET", "/protocols/").json()
        by_protocol = {norm(item["protocol"]): item for item in existing}

        for protocol in target:
            key = norm(protocol["protocol"])
            current = by_protocol.get(key)
            if not current:
                self.request("POST", "/protocols/", json=protocol, expected_status=(200,))
                print(f"[seed] protocol created: {protocol['protocol']}")
                continue

            patch: Dict[str, Any] = {}
            if int(current.get("port") or 0) != protocol["port"]:
                patch["port"] = protocol["port"]
            if bool(current.get("is_active")) != protocol["is_active"]:
                patch["is_active"] = protocol["is_active"]
            if patch:
                self.request(
                    "PATCH",
                    f"/protocols/{current['id']}",
                    json=patch,
                    expected_status=(200,),
                )
                print(f"[seed] protocol updated: {protocol['protocol']}")

    def ensure_marks(self) -> Dict[str, int]:
        target = [
            {"name": "ZowieTek", "is_active": True},
            {"name": "NEOiD", "is_active": True},
        ]
        existing = self.request("GET", "/marks/").json()
        by_name = {norm(item["name"]): item for item in existing}

        for mark in target:
            key = norm(mark["name"])
            current = by_name.get(key)
            if not current:
                created = self.request("POST", "/marks/", json=mark, expected_status=(200,)).json()
                by_name[key] = created
                print(f"[seed] mark created: {mark['name']}")
                continue

            patch: Dict[str, Any] = {}
            if bool(current.get("is_active")) != mark["is_active"]:
                patch["is_active"] = mark["is_active"]
            if patch:
                updated = self.request(
                    "PATCH",
                    f"/marks/{current['id']}",
                    json=patch,
                    expected_status=(200,),
                ).json()
                by_name[key] = updated
                print(f"[seed] mark updated: {mark['name']}")

        return {k: int(v["id"]) for k, v in by_name.items()}

    def ensure_users(self) -> None:
        target = [
            {"username": "admin", "full_name": "Manager Agent", "password": "123", "is_superuser": True, "is_active": True},
            {"username": "user", "full_name": "Dr. Tester", "password": "123", "is_superuser": False, "is_active": True},
            {"username": "dra", "full_name": "Dra. Base", "password": "123", "is_superuser": False, "is_active": True},
            {"username": "user1", "full_name": "User Inativo 01", "password": "123", "is_superuser": False, "is_active": False},
            {"username": "user2", "full_name": "User Inativo 02", "password": "123", "is_superuser": False, "is_active": True},
        ]

        existing = self.request("GET", "/users/").json()
        by_username = {norm(item["username"]): item for item in existing}

        for user in target:
            key = norm(user["username"])
            current = by_username.get(key)
            if not current:
                self.request("POST", "/users/", json=user, expected_status=(200,))
                print(f"[seed] user created: {user['username']}")
                continue

            patch: Dict[str, Any] = {}
            if (current.get("full_name") or "") != user["full_name"]:
                patch["full_name"] = user["full_name"]
            if bool(current.get("is_active")) != user["is_active"]:
                patch["is_active"] = user["is_active"]
            if bool(current.get("is_superuser")) != user["is_superuser"]:
                patch["is_superuser"] = user["is_superuser"]
            # Keep passwords deterministic for test baseline.
            patch["password"] = user["password"]
            self.request(
                "PATCH",
                f"/users/{current['id']}",
                json=patch,
                expected_status=(200,),
            )
            print(f"[seed] user updated: {user['username']}")

    def ensure_cities(self) -> Dict[Tuple[str, str], int]:
        target = [
            {"name": "S\u00e3o Paulo", "uf": "SP", "is_active": True},
            {"name": "Campinas", "uf": "SP", "is_active": True},
            {"name": "Curitiba", "uf": "PR", "is_active": True},
            {"name": "Cunha Por\u00e3", "uf": "SC", "is_active": True},
        ]

        existing = self.request("GET", "/cities/").json()
        by_key = {(norm(item["name"]), item["uf"].upper()): item for item in existing}

        for city in target:
            key = (norm(city["name"]), city["uf"].upper())
            current = by_key.get(key)
            if not current:
                created = self.request("POST", "/cities/", json=city, expected_status=(200,)).json()
                by_key[key] = created
                print(f"[seed] city created: {city['name']}/{city['uf']}")
                continue

            patch: Dict[str, Any] = {}
            if bool(current.get("is_active")) != city["is_active"]:
                patch["is_active"] = city["is_active"]
            if patch:
                updated = self.request(
                    "PATCH",
                    f"/cities/{current['id']}",
                    json=patch,
                    expected_status=(200,),
                ).json()
                by_key[key] = updated
                print(f"[seed] city updated: {city['name']}/{city['uf']}")

        return {k: int(v["id"]) for k, v in by_key.items()}

    def ensure_places(self, city_id_map: Dict[Tuple[str, str], int]) -> Dict[str, int]:
        target = [
            {"name": "Centro Cir\u00fargico", "description": "Sala principal", "city_key": ("s\u00e3o paulo", "SP"), "is_active": True},
            {"name": "Ambulat\u00f3rio", "description": "Sala ambulatorial", "city_key": ("campinas", "SP"), "is_active": True},
            {"name": "UTI", "description": "Unidade intensiva", "city_key": ("curitiba", "PR"), "is_active": True},
            {"name": "Santa Casa", "description": "Centro de grava\u00e7\u00e3o", "city_key": ("cunha por\u00e3", "SC"), "is_active": True},
        ]

        existing = self.request("GET", "/places/").json()
        by_name = {norm(item["name"]): item for item in existing}

        for place in target:
            city_key = (place["city_key"][0], place["city_key"][1])
            city_id = city_id_map.get(city_key)
            if not city_id:
                raise RuntimeError(f"City not found for place {place['name']}: {city_key}")

            current = by_name.get(norm(place["name"]))
            payload = {
                "name": place["name"],
                "description": place["description"],
                "city_id": city_id,
                "is_active": place["is_active"],
            }

            if not current:
                created = self.request("POST", "/places/", json=payload, expected_status=(200,)).json()
                by_name[norm(place["name"])] = created
                print(f"[seed] place created: {place['name']}")
                continue

            patch: Dict[str, Any] = {}
            if int(current.get("city_id")) != city_id:
                patch["city_id"] = city_id
            if (current.get("description") or "") != place["description"]:
                patch["description"] = place["description"]
            if bool(current.get("is_active")) != place["is_active"]:
                patch["is_active"] = place["is_active"]
            if patch:
                updated = self.request(
                    "PATCH",
                    f"/places/{current['id']}",
                    json=patch,
                    expected_status=(200,),
                ).json()
                by_name[norm(place["name"])] = updated
                print(f"[seed] place updated: {place['name']}")

        return {k: int(v["id"]) for k, v in by_name.items()}

    def ensure_procedures(self) -> None:
        target = [
            {"name": "Bariatrica", "description": "Cirurgia bari\u00e1trica", "is_active": True},
            {"name": "Hernia", "description": "Cirurgia de h\u00e9rnia", "is_active": True},
            {"name": "Cora\u00e7\u00e3o", "description": "Cirurgia card\u00edaca", "is_active": True},
        ]

        existing = self.request("GET", "/procedures/").json()
        by_name = {norm(item["name"]): item for item in existing}

        for procedure in target:
            key = norm(procedure["name"])
            current = by_name.get(key)
            if not current:
                self.request("POST", "/procedures/", json=procedure, expected_status=(200,))
                print(f"[seed] procedure created: {procedure['name']}")
                continue

            patch: Dict[str, Any] = {}
            if (current.get("description") or "") != procedure["description"]:
                patch["description"] = procedure["description"]
            if bool(current.get("is_active")) != procedure["is_active"]:
                patch["is_active"] = procedure["is_active"]
            if patch:
                self.request(
                    "PATCH",
                    f"/procedures/{current['id']}",
                    json=patch,
                    expected_status=(200,),
                )
                print(f"[seed] procedure updated: {procedure['name']}")

    def ensure_devices(self, place_id_by_name: Dict[str, int], mark_id_by_name: Dict[str, int]) -> None:
        target = [
            {
                "mark_name": "ZowieTek",
                "model": "ZowieREC-131",
                "sn": "29252",
                "place_name": "Centro Cir\u00fargico",
                "protocol": "srt",
                "is_active": True,
            },
            {
                "mark_name": "NEOiD",
                "model": "EDeN",
                "sn": "iD25250431536",
                "place_name": "Ambulat\u00f3rio",
                "protocol": "rtmp",
                "is_active": True,
            },
        ]

        existing = self.request("GET", "/devices/").json()
        by_key = {
            (str(item.get("sn") or ""), norm(str(item.get("mark_name") or ""))): item
            for item in existing
        }
        target_keys = {(item["sn"], norm(item["mark_name"])) for item in target}

        for device in target:
            place_id = place_id_by_name.get(norm(device["place_name"]))
            if not place_id:
                raise RuntimeError(f"Place not found for device SN {device['sn']}: {device['place_name']}")
            mark_id = mark_id_by_name.get(norm(device["mark_name"]))
            if not mark_id:
                raise RuntimeError(f"Mark not found for device SN {device['sn']}: {device['mark_name']}")

            payload = {
                "mark_id": mark_id,
                "model": device["model"],
                "sn": device["sn"],
                "protocol": device["protocol"],
                "place_id": place_id,
                "is_active": device["is_active"],
            }
            current = by_key.get((device["sn"], norm(device["mark_name"])))

            if not current:
                self.request("POST", "/devices/", json=payload, expected_status=(200,))
                print(f"[seed] device created: sn={device['sn']}")
                continue

            patch: Dict[str, Any] = {}
            if int(current.get("mark_id") or 0) != mark_id:
                patch["mark_id"] = mark_id
            if (current.get("model") or "") != device["model"]:
                patch["model"] = device["model"]
            if int(current.get("place_id")) != place_id:
                patch["place_id"] = place_id
            if norm(current.get("protocol") or "") != norm(device["protocol"]):
                patch["protocol"] = device["protocol"]
            if bool(current.get("is_active")) != device["is_active"]:
                patch["is_active"] = device["is_active"]
            if patch:
                self.request(
                    "PATCH",
                    f"/devices/{current['id']}",
                    json=patch,
                    expected_status=(200,),
                )
                print(f"[seed] device updated: sn={device['sn']}")

        for current in existing:
            current_key = (str(current.get("sn") or ""), norm(str(current.get("mark_name") or "")))
            if current_key in target_keys:
                continue
            device_id = int(current["id"])
            try:
                self.request("DELETE", f"/devices/{device_id}", expected_status=(200,))
                print(f"[seed] device deleted (out of baseline): id={device_id}")
            except Exception:
                self.request(
                    "PATCH",
                    f"/devices/{device_id}",
                    json={"is_active": False},
                    expected_status=(200,),
                )
                print(f"[seed] device deactivated (out of baseline): id={device_id}")

    def run(self) -> None:
        self.bootstrap_first_admin_if_needed()
        self.ensure_app_settings()
        self.ensure_protocols()
        mark_id_map = self.ensure_marks()
        self.ensure_users()
        city_id_map = self.ensure_cities()
        place_id_map = self.ensure_places(city_id_map)
        self.ensure_procedures()
        self.ensure_devices(place_id_map, mark_id_map)

        users = self.request("GET", "/users/").json()
        marks = self.request("GET", "/marks/").json()
        devices = self.request("GET", "/devices/").json()
        protocols = self.request("GET", "/protocols/").json()
        procedures = self.request("GET", "/procedures/").json()
        cities = self.request("GET", "/cities/").json()
        places = self.request("GET", "/places/").json()
        app_settings = self.request("GET", "/app-settings/").json()
        print(
            "[seed] done: "
            f"users={len(users)} marks={len(marks)} devices={len(devices)} protocols={len(protocols)} "
            f"procedures={len(procedures)} cities={len(cities)} places={len(places)} "
            f"app_settings_id={app_settings.get('id')}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed baseline data through API calls.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL, e.g. http://127.0.0.1:8001/surgwaze/v1")
    parser.add_argument("--admin-user", default="admin", help="Admin username for login/bootstrap.")
    parser.add_argument("--admin-pass", default="123", help="Admin password for login/bootstrap.")
    parser.add_argument("--app-host", default="http://192.168.10.19", help="Public app host to save in app-settings.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    seeder = ApiSeeder(
        base_url=args.base_url,
        admin_user=args.admin_user,
        admin_pass=args.admin_pass,
        app_host=args.app_host,
    )
    try:
        seeder.run()
        return 0
    except Exception as exc:
        print(f"[seed] error: {exc}", file=sys.stderr)
        return 1
    finally:
        seeder.close()


if __name__ == "__main__":
    raise SystemExit(main())
