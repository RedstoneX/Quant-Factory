"""Provider-neutral, least-privilege research gateway."""

from agent_gateway.contracts import (
    GATEWAY_PROTOCOL,
    GatewayError,
    GatewayIdentity,
    GatewayRequest,
    GatewayResponse,
)
__all__ = [
    "GATEWAY_PROTOCOL",
    "GatewayError",
    "GatewayIdentity",
    "GatewayRequest",
    "GatewayResponse",
]
