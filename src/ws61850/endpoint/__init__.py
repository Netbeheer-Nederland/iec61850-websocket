from ws61850.endpoint.active_endpoint import ActiveEndpoint
from ws61850.endpoint.base import EndpointProtocol, WebSocketInfo
from ws61850.endpoint.endpoint import WebSocketEndpoint  # deprecated shim
from ws61850.endpoint.passive_endpoint import PassiveEndpoint

__all__ = [
    "WebSocketInfo",
    "EndpointProtocol",
    "PassiveEndpoint",
    "ActiveEndpoint",
    "WebSocketEndpoint",
    "create_endpoint",
]


def create_endpoint(mode: str, **kwargs) -> PassiveEndpoint | ActiveEndpoint:
    """Factory: create_endpoint('passive', ...) or create_endpoint('active', ...)."""
    if mode == "passive":
        return PassiveEndpoint(**kwargs)
    if mode == "active":
        return ActiveEndpoint(**kwargs)
    raise ValueError(f"Unknown mode: {mode!r}")
