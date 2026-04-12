from __future__ import annotations

from backend.common.types import ToolParameterSchema


def build_tool_parameters() -> ToolParameterSchema:
    return ToolParameterSchema(
        properties={
            "action": {"type": "string", "description": "add_exit | remove_exit | set | remove | list"},
            "name": {"type": "string", "description": "Exit node name"},
            "type": {"type": "string", "description": "Proxy type. Defaults to trojan"},
            "server": {"type": "string", "description": "Server address"},
            "port": {"type": "integer", "description": "Server port"},
            "password": {"type": "string", "description": "Password for password-based nodes"},
            "sni": {"type": "string", "description": "TLS SNI or VLESS servername"},
            "skip_cert_verify": {"type": "boolean", "description": "Skip certificate verification"},
            "extra": {"type": "object", "description": "Additional protocol-specific fields"},
            "uuid": {"type": "string", "description": "UUID for VLESS or VMess"},
            "network": {"type": "string", "description": "Transport protocol such as tcp, ws, grpc, or h2"},
            "flow": {"type": "string", "description": "VLESS flow such as xtls-rprx-vision"},
            "reality_public_key": {"type": "string", "description": "Reality public key"},
            "reality_short_id": {"type": "string", "description": "Reality short id"},
            "fingerprint": {"type": "string", "description": "Client fingerprint such as chrome"},
            "exit_node": {"type": "string", "description": "Exit node name"},
            "transit_pattern": {"type": "string", "description": "Keyword used to match transit nodes"},
            "transit_nodes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Explicit transit node list",
            },
        },
        required=["action"],
    )
