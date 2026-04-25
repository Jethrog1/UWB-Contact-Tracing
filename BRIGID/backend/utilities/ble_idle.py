"""
ble_idle.py - Global "Active BLE Idle" service.

Runs a single BLE listener stack that stays up across the entire
application lifetime whenever the user enables it from the hotbar.
Each profiled tag's MAC gets one dedicated bleak client task.

Other backend runtimes (RTLSRuntime, CalibrationRuntime) subscribe as
listeners; incoming measurement strings and status changes are fanned
out to all of them. When a UI module (RTLS Dashboard, Calibration Tool)
asks to connect while idle is active, the backend skips spinning up
its own BLE stack and just bridges the runtime to this service.
"""

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
except ImportError:  # pragma: no cover - optional dependency
    BleakClient = None
    HAS_BLEAK = False


CHAR_UUID = "deadbeef-0000-0000-0000-000000000001"

logger = logging.getLogger("ble_idle")


def _normalize_mac(value: str) -> str:
    return str(value or "").strip().replace("-", ":").upper()


class BleIdleService:
    """Runs global BLE listeners for all profiled MACs.

    Subscribers are callables ``(event_type, tag_id, payload)`` where
    event_type is ``"data"`` (payload is the raw measurement string) or
    ``"status"`` (payload is ``Connecting.../Connected/Disconnected``).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._enabled = False
        self._thread: threading.Optional[Thread] = None
        self._loop: asyncio.Optional[AbstractEventLoop] = None
        self._stop = threading.Event()

        # tag_id -> mac (normalized)
        self._tag_macs: dict[str, str] = {}
        # tag_id -> current status string
        self._tag_status: dict[str, str] = {}
        # tag_id -> asyncio Task running the per-tag BLE loop
        self._tasks: dict[str, Any] = {}

        # Active consumers (ref-counted lifetime). The service runs while
        # any consumer holds a slot; releasing the last one stops it.
        # IDs: "hotbar", "rtls", "calibration:<workspace_key>".
        self._consumers: set[str] = set()

        self._subscribers: list[Callable[[str, str, str], None]] = []

    # ── Subscription ──────────────────────────────────────────────────────

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
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("ble_idle subscriber raised: %s", exc)

    # ── Public API ────────────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        """True while the BLE service is actually running."""
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
        """Register a consumer. Starts the service if it isn't already running.

        Returns (ok, detail). When called for an already-active service the
        result is immediate — the consumer just hooks into the existing
        connections.
        """
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
        # Refresh MAC set to whatever the latest caller knows about.
        self.sync_profiles(profiles)
        with self._lock:
            tag_count = len(self._tag_macs)
        if was_running:
            detail = f"Joined Active BLE Idle ({tag_count} tag(s))."
        else:
            detail = f"Active BLE Idle running for {tag_count} tag(s)."
        return True, detail

    def release(self, consumer_id: str) -> bool:
        """Drop a consumer. Stops the service when the last one leaves.

        Returns True if the service was stopped as a result of this call.
        """
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
        """Force-stop: drop every consumer and tear down the service."""
        with self._lock:
            self._consumers.clear()
        self._stop_service()

    # Backward-compat alias for HotBar-only enable/disable (singleton consumer).
    def enable(self, profiles: list[dict]) -> tuple[bool, str]:
        return self.acquire("hotbar", profiles)

    def disable(self) -> None:
        self.release("hotbar")

    def _stop_service(self) -> None:
        """Tear down the BLE thread + loop. Idempotent; safe with no consumers."""
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
        """Update the MAC set from the latest profile list.

        Called whenever tag profiles may have changed. Adds new MACs,
        cancels tasks for removed MACs, and restarts any MAC whose tag_id
        was remapped to a new address.
        """
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

            # Prune status for tags that no longer exist at all.
            for tag_id in list(self._tag_status.keys()):
                if tag_id not in next_macs:
                    self._tag_status.pop(tag_id, None)

        if not was_enabled or loop is None:
            return

        # Schedule task mutations on the BLE loop.
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
            # `enabled` tracks the HotBar toggle specifically: True when the
            # user has Active BLE Idle switched on from the HotBar BLE menu.
            # `service_running` reports the global service state, which may
            # be True via RTLS / Calibration even when HotBar is off.
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

    # ── Internals ─────────────────────────────────────────────────────────

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

        # Spawn tasks for any MACs already registered via sync_profiles().
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
        # Runs inside the BLE loop thread (scheduled via call_soon_threadsafe).
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
            # Small cool-down before retrying.
            deadline = time.time() + 3.0
            while not self._stop.is_set() and time.time() < deadline:
                await asyncio.sleep(0.25)


# Module-level singleton used by cad_server.
ble_idle_service = BleIdleService()
