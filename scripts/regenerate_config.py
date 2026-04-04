from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from backend.core.s02_tools.builtin.proxy_config import ProxyConfigGenerator


class RegenerateConfigError(Exception):
    """Raised when regenerating the mihomo config fails."""


@dataclass(frozen=True)
class CliArgs:
    sub_path: Path
    out_path: Path
    smux: bool


def parse_args() -> CliArgs:
    parser = argparse.ArgumentParser(description="Regenerate mihomo config from a subscription file.")
    parser.add_argument("--sub", default="sub_raw.yaml", help="Path to the UTF-8 subscription YAML.")
    parser.add_argument("--out", default="config.yaml", help="Path to the generated config YAML.")
    parser.add_argument("--smux", action="store_true", help="Inject smux. Disabled by default.")
    args = parser.parse_args()
    return CliArgs(sub_path=Path(args.sub), out_path=Path(args.out), smux=bool(args.smux))


def load_subscription_data(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RegenerateConfigError(f"Failed to read subscription file: {exc}") from exc
    except yaml.YAMLError as exc:
        raise RegenerateConfigError(f"Failed to parse subscription YAML: {exc}") from exc
    if isinstance(payload, list):
        payload = {"proxies": payload}
    if not isinstance(payload, dict) or not isinstance(payload.get("proxies"), list):
        raise RegenerateConfigError("Subscription YAML must contain a proxies list.")
    return payload


def build_config(args: CliArgs) -> dict[str, Any]:
    generator = ProxyConfigGenerator(str(args.out_path), backup=False)
    return generator.generate_from_subscription(
        load_subscription_data(args.sub_path),
        smux_config={} if args.smux else None,
        dns_config=ProxyConfigGenerator.default_dns_config(),
        global_opts=ProxyConfigGenerator.default_global_opts(),
    )


def main() -> int:
    try:
        args = parse_args()
        generator = ProxyConfigGenerator(str(args.out_path), backup=False)
        output_path = generator.save(build_config(args))
    except RegenerateConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
