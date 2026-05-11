
from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
from typing import Any, Callable

try:
    from bleak import BleakClient

    HAS_BLEAK = True
except ImportError:                                          
    BleakClient = None
    HAS_BLEAK = False

CHAR_UUID = "deadbeef-0000-0000-0000-000000000001"

logger = logging.getLogger("ble_idle")

def _normalize_mac(value: str) -> str:
    return str(value or "").strip().replace("-", ":").upper()

class BleIdleService:

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._enabled = False
        self._thread: threading.Optional[Thread] = None
        self._loop: asyncio.Optional[AbstractEventLoop] = None
        self._stop = threading.Event()

        self._tag_macs: dict[str, str] = {}

        self._tag_status: dict[str, str] = {}

        self._tasks: dict[str, Any] = {}

        self._consumers: set[str] = set()

        self._subscribers: list[Callable[[str, str, str], None]] = []

    def subscribe(self, callback: Callable[[str, str, str], None]) -> None:
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[str, str, str], None]) -> None:
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def _emit(self, event_type: str, tag_id: str, payload: str) -> None:
        with self._lock:
            subs = list(self._subscribers)
            if event_type == "status":
                self._tag_status[tag_id] = payload
        for cb in subs:
            try:
                cb(event_type, tag_id, payload)
            except Exception as exc:                                
                logger.debug("ble_idle subscriber raised: %s", exc)

    def is_enabled(self) -> bool:
        return self._enabled

    def is_available(self) -> bool:
        return HAS_BLEAK

    def has_consumer(self, consumer_id: str) -> bool:
        with self._lock:
            return consumer_id in self._consumers

    def consumer_list(self) -> list[str]:
        with self._lock:
            return sorted(self._consumers)

    def acquire(self, consumer_id: str, profiles: list[dict]) -> tuple[bool, str]:
        if not HAS_BLEAK:
            return False, "bleak is not installed on the backend."
        if not consumer_id:
            return False, "Consumer id required."
        with self._lock:
            was_running = self._enabled
            self._consumers.add(consumer_id)
            if not was_running:
                self._enabled = True
                self._stop.clear()
                self._thread = threading.Thread(
                    target=self._thread_main, name="BleIdleThread", daemon=True,
                )
                self._thread.start()

        self.sync_profiles(profiles)
        with self._lock:
            tag_count = len(self._tag_macs)
        if was_running:
            detail = f"Joined Active BLE Idle ({tag_count} tag(s))."
        else:
            detail = f"Active BLE Idle running for {tag_count} tag(s)."
        return True, detail

    def release(self, consumer_id: str) -> bool:
        with self._lock:
            if consumer_id not in self._consumers:
                return False
            self._consumers.discard(consumer_id)
            still_held = bool(self._consumers)
        if still_held:
            return False
        self._stop_service()
        return True

    def shutdown(self) -> None:
        with self._lock:
            self._consumers.clear()
        self._stop_service()

    def enable(self, profiles: list[dict]) -> tuple[bool, str]:
        return self.acquire("hotbar", profiles)

    def disable(self) -> None:
        self.release("hotbar")

    def _stop_service(self) -> None:
        thread: threading.Optional[Thread] = None
        loop: asyncio.Optional[AbstractEventLoop] = None
        with self._lock:
            if not self._enabled:
                return
            self._enabled = False
            self._stop.set()
            thread = self._thread
            loop = self._loop
            self._thread = None
            self._loop = None
            for tag_id in list(self._tag_status):
                self._tag_status[tag_id] = "Disconnected"

        if loop is not None:
            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception:
                pass
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

        with self._lock:
            self._tasks.clear()

        for tag_id in list(self._tag_status.keys()):
            self._emit("status", tag_id, "Disconnected")

    def sync_profiles(self, profiles: list[dict]) -> None:
        next_macs: dict[str, str] = {}
        for profile in profiles:
            tag_id = str(profile.get("tag_id", "") or "").strip()
            if not tag_id:
                continue
            mac = _normalize_mac(profile.get("device", {}).get("mac_address", ""))
            if mac:
                next_macs[tag_id] = mac

        with self._lock:
            was_enabled = self._enabled
            loop = self._loop
            prev = dict(self._tag_macs)
            self._tag_macs = next_macs

            removed = [tag_id for tag_id in prev if tag_id not in next_macs or next_macs[tag_id] != prev[tag_id]]
            added = [tag_id for tag_id in next_macs if tag_id not in prev or next_macs[tag_id] != prev[tag_id]]

            for tag_id in list(self._tag_status.keys()):
                if tag_id not in next_macs:
                    self._tag_status.pop(tag_id, None)

        if not was_enabled or loop is None:
            return

        for tag_id in removed:
            loop.call_soon_threadsafe(self._cancel_task_locked, tag_id)

        for tag_id in added:
            mac = next_macs.get(tag_id, "")
            if mac:
                loop.call_soon_threadsafe(self._spawn_task_locked, tag_id, mac)

    def status(self) -> dict:
        with self._lock:
            tags = [
                {
                    "tag_id": tag_id,
                    "mac_address": self._tag_macs[tag_id],
                    "status": self._tag_status.get(tag_id, "Disconnected"),
                }
                for tag_id in self._tag_macs
            ]
            consumers = sorted(self._consumers)

            return {
                "enabled": "hotbar" in self._consumers,
                "service_running": self._enabled,
                "available": HAS_BLEAK,
                "consumers": consumers,
                "tags": tags,
            }

    def get_tag_status(self, tag_id: str) -> str:
        with self._lock:
            return self._tag_status.get(tag_id, "Disconnected")

    def _thread_main(self) -> None:
        if sys.platform.startswith("win"):
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            except Exception:
                pass
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with self._lock:
            self._loop = loop

        with self._lock:
            initial = dict(self._tag_macs)
        for tag_id, mac in initial.items():
            self._spawn_task_locked(tag_id, mac)

        try:
            loop.run_forever()
        finally:
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                try:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except Exception:
                    pass
            loop.close()
            with self._lock:
                self._loop = None
                self._tasks.clear()

    def _spawn_task_locked(self, tag_id: str, mac: str) -> None:

        existing = self._tasks.get(tag_id)
        if existing is not None and not existing.done():
            return
        task = asyncio.ensure_future(self._listen(tag_id, mac))
        self._tasks[tag_id] = task

    def _cancel_task_locked(self, tag_id: str) -> None:
        task = self._tasks.pop(tag_id, None)
        if task is not None and not task.done():
            task.cancel()
        self._emit("status", tag_id, "Disconnected")

    async def _listen(self, tag_id: str, mac: str) -> None:
        if not HAS_BLEAK:
            return
        while not self._stop.is_set():
            with self._lock:
                if not self._enabled or self._tag_macs.get(tag_id, "") != mac:
                    return
            self._emit("status", tag_id, "Connecting...")
            try:
                async with BleakClient(mac) as client:
                    self._emit("status", tag_id, "Connected")
                    await client.start_notify(
                        CHAR_UUID,
                        lambda _sender, data, tid=tag_id: self._emit(
                            "data",
                            tid,
                            data.decode("utf-8", errors="replace").strip(),
                        ),
                    )
                    while client.is_connected and not self._stop.is_set():
                        with self._lock:
                            if not self._enabled or self._tag_macs.get(tag_id, "") != mac:
                                break
                        await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                self._emit("status", tag_id, "Disconnected")
                raise
            except Exception:
                self._emit("status", tag_id, "Disconnected")

            deadline = time.time() + 3.0
            while not self._stop.is_set() and time.time() < deadline:
                await asyncio.sleep(0.25)

ble_idle_service = BleIdleService()
