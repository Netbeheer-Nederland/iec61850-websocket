import asyncio
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuntimeState:
    endpoint: Any = None
    client: Any = None
    server: Any = None
    loop: asyncio.AbstractEventLoop | None = None
    invoke_lock: asyncio.Lock | None = None
    connection_thread: threading.Thread | None = None
    endpoint_task: Any = None
    token_refresh_task: Any = None
    connection_profile: Any = None
    application_role: str = "iec_client"
    connect_aid: int | None = None
    status: str = "not-connected"
    mode: str = "active"
    is_direct: bool = False
    cancel_connect: bool = False
    manual_disconnect: bool = False
    security_files: list[str] = field(default_factory=list)

    actions: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=200))
    action_seq: int = 0

    messages: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=500))
    message_seq: int = 0
    messages_max: int = 500

    model_status: str = "idle"
    model_data: dict[str, Any] | None = None
    model_error: str | None = None
    model_task: Any = None
    model_started_at: float | None = None
    model_progress: dict[str, Any] | None = None

    report_updates: list[dict[str, Any]] = field(default_factory=list)

    state_lock: threading.Lock = field(default_factory=threading.Lock)
    actions_lock: threading.Lock = field(default_factory=threading.Lock)
    messages_lock: threading.Lock = field(default_factory=threading.Lock)
    model_lock: threading.Lock = field(default_factory=threading.Lock)
    report_lock: threading.Lock = field(default_factory=threading.Lock)
