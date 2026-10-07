"""Single-instance support: route files from extra launches into the running window.

Windows Explorer runs a context-menu command once *per selected file*, so
selecting three PDFs and choosing "Convert with Any2MD > Markdown" starts
three processes at the same moment. The first process to grab a lock file
becomes the primary instance and listens on a local socket; every later
process forwards its arguments there and exits without opening a window.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QDir, QLockFile, QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket


def _instance_key() -> str:
    try:
        user = getpass.getuser()
    except Exception:
        user = "user"
    digest = hashlib.sha1(user.encode("utf-8", "replace")).hexdigest()[:12]
    return f"any2md-{digest}"


class SingleInstance(QObject):
    """
    Lock-file + QLocalServer guard.

    Emits:
        message_received(dict) — payload sent by a secondary instance
    """

    message_received = pyqtSignal(dict)

    def __init__(self, key: Optional[str] = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._key = key or _instance_key()
        self._lock = QLockFile(str(Path(QDir.tempPath()) / f"{self._key}.lock"))
        # A crashed primary leaves its lock behind; QLockFile treats a lock
        # whose owning process is gone as stale automatically.
        self._lock.setStaleLockTime(0)
        self._server: Optional[QLocalServer] = None
        self._buffers: dict[QLocalSocket, bytearray] = {}

    @property
    def key(self) -> str:
        return self._key

    def try_become_primary(self) -> bool:
        """Take the lock and start listening. False means another instance owns it."""
        if not self._lock.tryLock(0):
            return False
        QLocalServer.removeServer(self._key)  # clear a stale Unix socket file
        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not server.listen(self._key):
            self._lock.unlock()
            return False
        server.newConnection.connect(self._on_new_connection)
        self._server = server
        return True

    def send_to_primary(self, payload: dict, timeout_s: float = 8.0) -> bool:
        """Deliver payload to the primary, retrying while it is still starting up."""
        if sys.platform == "win32":
            # Let the primary bring its window to the foreground.
            try:
                import ctypes

                ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
            except Exception:
                pass

        data = (json.dumps(payload) + "\n").encode("utf-8")
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            socket = QLocalSocket()
            socket.connectToServer(self._key)
            if socket.waitForConnected(500):
                socket.write(data)
                ok = socket.waitForBytesWritten(2000)
                socket.disconnectFromServer()
                if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
                    socket.waitForDisconnected(1000)
                return ok
            time.sleep(0.1)
        return False

    def close(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
        if self._lock.isLocked():
            self._lock.unlock()

    # ──────────────────────────────────────────────────
    # Server side
    # ──────────────────────────────────────────────────

    def _on_new_connection(self) -> None:
        while self._server is not None and self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            self._buffers[socket] = bytearray()
            socket.readyRead.connect(lambda s=socket: self._on_ready_read(s))
            socket.disconnected.connect(lambda s=socket: self._on_disconnected(s))

    def _on_ready_read(self, socket: QLocalSocket) -> None:
        buf = self._buffers.setdefault(socket, bytearray())
        buf.extend(bytes(socket.readAll()))
        while b"\n" in buf:
            line, _, rest = bytes(buf).partition(b"\n")
            buf[:] = rest
            self._dispatch(line)

    def _on_disconnected(self, socket: QLocalSocket) -> None:
        buf = self._buffers.pop(socket, bytearray())
        buf.extend(bytes(socket.readAll()))
        if buf.strip():
            self._dispatch(bytes(buf))
        socket.deleteLater()

    def _dispatch(self, raw: bytes) -> None:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if isinstance(payload, dict):
            self.message_received.emit(payload)
