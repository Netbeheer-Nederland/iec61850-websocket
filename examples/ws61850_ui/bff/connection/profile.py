from dataclasses import dataclass
from typing import Any, Literal

TransportRole = Literal["ws_client", "ws_server"]
ApplicationRole = Literal["iec_client", "iec_server"]


@dataclass(frozen=True)
class ConnectionProfile:
    target: str
    transport_role: TransportRole
    application_role: ApplicationRole
    host: str
    port: int
    cp: str
    is_direct: bool = False
    security: dict[str, Any] | None = None

    @property
    def endpoint_mode(self) -> str:
        return "active" if self.transport_role == "ws_client" else "passive"

    @property
    def ui_state(self) -> str:
        if self.transport_role == "ws_server":
            return "listening"
        return "connecting"

    @classmethod
    def from_legacy(
        cls,
        *,
        url: str,
        port: int,
        cp: str,
        is_direct: bool,
        mode: str,
        security: dict[str, Any] | None,
        application_role: ApplicationRole | None = None,
    ) -> "ConnectionProfile":
        transport_role: TransportRole = "ws_server" if mode == "passive" else "ws_client"
        resolved_role = application_role or "iec_client"
        return cls(
            target="rti-so" if transport_role == "ws_server" and resolved_role == "iec_client" else "rti-fsp",
            transport_role=transport_role,
            application_role=resolved_role,
            host=url,
            port=port,
            cp=cp,
            is_direct=is_direct,
            security=security,
        )
