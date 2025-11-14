#!/usr/bin/env python3
"""Extract follower positions from lerobot stdout and broadcast via UNIX socket."""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import time
from pathlib import Path
from typing import Dict

SOCKET_PATH = os.environ.get("TELEOP_TELEMETRY_SOCKET", "/tmp/teleop_positions.sock")
POSITION_REGEX = re.compile(r"teleop_positions=(\{.+\})")


class TeleopTelemetryServer:
    def __init__(self, socket_path: str = SOCKET_PATH):
        self.socket_path = socket_path
        self.server = None
        self.clients: list[socket.socket] = []

    def start(self) -> None:
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            print(f"[teleop-telemetry] ⚠️ Could not unlink socket: {exc}", file=sys.stderr)

        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.socket_path)
        self.server.listen(5)
        self.server.setblocking(False)
        print(f"[teleop-telemetry] Listening on {self.socket_path}", file=sys.stderr)

    def accept_clients(self) -> None:
        if not self.server:
            return
        try:
            conn, _ = self.server.accept()
            conn.setblocking(False)
            self.clients.append(conn)
            print(f"[teleop-telemetry] Client connected ({len(self.clients)} total)", file=sys.stderr)
        except BlockingIOError:
            pass

    def broadcast(self, payload: Dict) -> None:
        if not self.clients:
            return

        data = (json.dumps(payload) + "\n").encode("utf-8")
        dead = []
        for client in self.clients:
            try:
                client.sendall(data)
            except (BrokenPipeError, ConnectionResetError):
                dead.append(client)
        for client in dead:
            self.clients.remove(client)

    def close(self) -> None:
        for client in self.clients:
            try:
                client.close()
            except OSError:
                pass
        self.clients.clear()
        if self.server:
            try:
                self.server.close()
            except OSError:
                pass
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass


def parse_positions(line: str) -> Dict | None:
    # Expect JSON chunk after "teleop_positions="
    match = POSITION_REGEX.search(line)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
        if isinstance(payload, dict):
            payload.setdefault("timestamp", time.time())
            return payload
    except json.JSONDecodeError:
        return None
    return None


def main() -> int:
    server = TeleopTelemetryServer()
    server.start()
    try:
        while True:
            server.accept_clients()
            line = sys.stdin.readline()
            if not line:
                break
            payload = parse_positions(line)
            if payload:
                server.broadcast(payload)
    finally:
        server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
