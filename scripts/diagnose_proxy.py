#!/usr/bin/env python3
"""
mihomo 代理连接诊断工具

用法：
  python scripts/diagnose_proxy.py
  python scripts/diagnose_proxy.py --config config.yaml
  python scripts/diagnose_proxy.py --sub sub_raw.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import re
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import yaml

IS_WINDOWS = platform.system() == "Windows"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="mihomo 代理连接诊断工具")
    parser.add_argument("--config", default="config.yaml", help="config.yaml 路径")
    parser.add_argument("--sub", default="sub_raw.yaml", help="订阅文件路径")
    parser.add_argument("--mihomo", default="", help="mihomo 二进制路径")
    parser.add_argument("--node", default="", help="指定测试的节点名")
    parser.add_argument("--skip-runtime", action="store_true", help="跳过后运行时测试")
    parser.add_argument("--verbose", action="store_true", help="显示详细输出")
    return parser.parse_args()


@dataclass
class DiagnoseResult:
    section: str
    items: list[dict[str, Any]] = field(default_factory=list)

    def add(self, status: str, name: str, detail: str = "") -> None:
        self.items.append({"status": status, "name": name, "detail": detail})

    def pass_(self, name: str, detail: str = "") -> None:
        self.add("PASS", name, detail)

    def fail(self, name: str, detail: str = "") -> None:
        self.add("FAIL", name, detail)

    def warn(self, name: str, detail: str = "") -> None:
        self.add("WARN", name, detail)

    def info(self, name: str, detail: str = "") -> None:
        self.add("INFO", name, detail)


def run_cmd(cmd: list[str] | str, timeout: int = 10, check: bool = False) -> tuple[int, str, str]:
    """运行命令并返回结果"""
    try:
        if isinstance(cmd, list):
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        else:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -2, "", str(e)


def check_environment(args: argparse.Namespace) -> DiagnoseResult:
    """[1] 环境检查"""
    result = DiagnoseResult("环境检查")

    # [1.1] Python 版本
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    result.pass_(f"Python {py_ver}")

    # [1.2] 操作系统
    os_info = f"{platform.system()} {platform.release()}"
    result.pass_(os_info)

    # [1.3] 当前工作目录
    cwd = Path.cwd()
    result.pass_(f"工作目录: {cwd}")

    # [1.4] mihomo 二进制
    mihomo_path = args.mihomo or os.environ.get("MIHOMO_PATH", "")
    if not mihomo_path:
        # 尝试常见位置
        for candidate in ["mihomo-windows-amd64-v3.exe", "./mihomo-windows-amd64-v3.exe", "./mihomo.exe"]:
            if Path(candidate).exists():
                mihomo_path = str(Path(candidate).resolve())
                break

    if mihomo_path and Path(mihomo_path).exists():
        rc, stdout, _ = run_cmd([mihomo_path, "-v"], timeout=5)
        if rc == 0:
            ver = stdout.strip().split()[0] if stdout else "unknown"
            result.pass_(f"mihomo: {ver}", f"路径: {mihomo_path}")
        else:
            result.warn("mihomo 存在但无法获取版本", mihomo_path)
    else:
        result.fail("mihomo 二进制未找到", f"尝试路径: {mihomo_path or '默认位置'}")

    # [1.5] config.yaml
    config_path = Path(args.config)
    if config_path.exists():
        size = config_path.stat().st_size
        result.pass_(f"config.yaml 存在", f"大小: {size} bytes")
    else:
        result.warn("config.yaml 不存在", str(config_path))

    # [1.6] sub_raw.yaml
    sub_path = Path(args.sub)
    if sub_path.exists():
        size = sub_path.stat().st_size
        result.pass_(f"sub_raw.yaml 存在", f"大小: {size} bytes")
    else:
        result.warn("sub_raw.yaml 不存在", str(sub_path))

    # [1.7] 其他代理进程检查
    if IS_WINDOWS:
        rc, stdout, _ = run_cmd(["tasklist", "/FO", "CSV"], timeout=5)
        if rc == 0:
            processes = []
            suspicious = ["farmer", "ziyoumao", "clash", "v2ray", "sing-box", "hiddify", "nekoray"]
            for line in stdout.splitlines():
                for name in suspicious:
                    if name.lower() in line.lower():
                        match = re.search(r'"([^"]+)"', line)
                        if match:
                            processes.append(match.group(1))
            if processes:
                result.warn("发现其他代理进程", ", ".join(set(processes)))
            else:
                result.pass_("未发现其他代理进程")
    else:
        # Linux: use ps to check for suspicious processes
        rc, stdout, _ = run_cmd("ps aux | grep -E 'farmer|ziyoumao|clash|v2ray|sing-box|hiddify|nekoray' | grep -v grep", timeout=5)
        if rc == 0 and stdout.strip():
            processes = [line.split()[1] for line in stdout.splitlines() if line.strip()]
            if processes:
                result.warn("发现其他代理进程", f"PIDs: {', '.join(set(processes))}")
            else:
                result.pass_("未发现其他代理进程")
        else:
            result.pass_("未发现其他代理进程")

    # [1.7b] 端口占用检查
    if IS_WINDOWS:
        rc, stdout, _ = run_cmd("netstat -ano | findstr LISTENING", timeout=5)
        if rc == 0:
            ports_7890 = [line for line in stdout.splitlines() if ":7890" in line]
            ports_9090 = [line for line in stdout.splitlines() if ":9090" in line]
            if ports_7890:
                result.warn("端口 7890 被占用", ports_7890[0][:80])
            if ports_9090:
                result.warn("端口 9090 被占用", ports_9090[0][:80])
            if not ports_7890 and not ports_9090:
                result.pass_("端口 7890/9090 未被占用")
    else:
        # Linux: use netstat or ss to check ports
        rc, stdout, _ = run_cmd("netstat -tlnp 2>/dev/null || ss -tlnp", timeout=5)
        if rc == 0:
            ports_7890 = [line for line in stdout.splitlines() if ":7890" in line]
            ports_9090 = [line for line in stdout.splitlines() if ":9090" in line]
            if ports_7890:
                result.warn("端口 7890 被占用", ports_7890[0][:80])
            if ports_9090:
                result.warn("端口 9090 被占用", ports_9090[0][:80])
            if not ports_7890 and not ports_9090:
                result.pass_("端口 7890/9090 未被占用")

    return result


def check_network() -> DiagnoseResult:
    """[2] 网络环境检查"""
    result = DiagnoseResult("网络环境")

    # [2.1] 系统 DNS 服务器
    rc, stdout, _ = run_cmd("ipconfig /all", timeout=5)
    if rc == 0:
        dns_servers = []
        for line in stdout.splitlines():
            if "DNS Servers" in line or "DNS 服务器" in line:
                match = re.search(r":\s*(\d+\.\d+\.\d+\.\d+)", line)
                if match:
                    dns_servers.append(match.group(1))
            elif dns_servers and line.strip().startswith("."):
                match = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
                if match:
                    dns_servers.append(match.group(1))
        if dns_servers:
            result.pass_(f"系统 DNS: {', '.join(dns_servers[:2])}")
        else:
            result.warn("未能解析系统 DNS")

    # [2.2] 系统代理设置
    if IS_WINDOWS:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                               r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as key:
                proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
                proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
                if proxy_enable:
                    result.warn(f"系统代理: 已启用", f"服务器: {proxy_server}")
                else:
                    result.pass_("系统代理: 未设置")
        except Exception as e:
            result.info("系统代理: 读取失败", str(e))
    else:
        # Linux: check environment variables
        http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        if http_proxy or https_proxy:
            proxies = []
            if http_proxy:
                proxies.append(f"HTTP: {http_proxy}")
            if https_proxy:
                proxies.append(f"HTTPS: {https_proxy}")
            result.warn(f"系统代理: 已启用", ", ".join(proxies))
        else:
            result.pass_("系统代理: 未设置")

    # [2.3] 虚拟网卡检查
    if IS_WINDOWS:
        rc, stdout, _ = run_cmd("ipconfig /all", timeout=5)
    else:
        rc, stdout, _ = run_cmd("ip addr show", timeout=5)
    if rc == 0:
        virtual_nics = []
        for nic in ["tun", "wintun", "utun", "farmer", "ziyoumao", "clash", "meta"]:
            if nic.lower() in stdout.lower():
                virtual_nics.append(nic)
        if virtual_nics:
            result.warn("发现虚拟网卡", ", ".join(set(virtual_nics)))
        else:
            result.pass_("未发现虚拟网卡")

    # [2.4] 基础网络连通性
    rc, _, _ = run_cmd("ping -n 1 -w 3000 223.5.5.5", timeout=5)
    if rc == 0:
        result.pass_("国内 DNS (223.5.5.5) 可连通")
    else:
        result.fail("国内 DNS (223.5.5.5) 不通")

    rc, _, _ = run_cmd("ping -n 1 -w 3000 baidu.com", timeout=5)
    if rc == 0:
        result.pass_("baidu.com 可解析")
    else:
        result.warn("baidu.com 解析失败")

    return result


def test_dns_resolution() -> DiagnoseResult:
    """[3] DNS 解析对比测试"""
    result = DiagnoseResult("DNS 解析")
    test_domain = "freevipa1.freecatnodles.com"

    # [3.1] 系统默认 DNS
    rc, stdout, _ = run_cmd(f"nslookup {test_domain}", timeout=5)
    if rc == 0 and "Address:" in stdout:
        ips = re.findall(r"Address:\s*(\d+\.\d+\.\d+\.\d+)", stdout)
        if ips:
            result.pass_(f"系统 DNS: {ips[0]}")
        else:
            result.fail("系统 DNS: 无结果")
    else:
        result.fail("系统 DNS: 解析失败")

    # [3.2] 国内 DNS
    for dns in ["223.5.5.5", "119.29.29.29", "114.114.114.114"]:
        rc, stdout, _ = run_cmd(f"nslookup {test_domain} {dns}", timeout=5)
        if rc == 0 and "Address:" in stdout:
            ips = re.findall(r"Address:\s*(\d+\.\d+\.\d+\.\d+)", stdout)
            ips = [ip for ip in ips if ip != dns]
            if ips:
                result.pass_(f"国内 DNS {dns}: {ips[0]}")
            else:
                result.fail(f"国内 DNS {dns}: 无结果")
        else:
            result.fail(f"国内 DNS {dns}: 解析失败")

    # [3.3] 国外 DNS
    for dns in ["8.8.8.8", "1.1.1.1"]:
        rc, stdout, _ = run_cmd(f"nslookup {test_domain} {dns}", timeout=5)
        if rc == 0 and "Address:" in stdout:
            ips = re.findall(r"Address:\s*(\d+\.\d+\.\d+\.\d+)", stdout)
            ips = [ip for ip in ips if ip != dns]
            if ips:
                result.pass_(f"国外 DNS {dns}: {ips[0]}")
            else:
                result.fail(f"国外 DNS {dns}: 无结果")
        else:
            result.fail(f"国外 DNS {dns}: 解析失败")

    # [3.4] DoH 解析测试
    doh_results = {}
    for name, url, params, headers in [
        ("doh.pub", "https://doh.pub/dns-query",
         {"name": test_domain, "type": "A"}, {"Accept": "application/dns-json"}),
        ("dns.google", "https://dns.google/resolve",
         {"name": test_domain, "type": "A"}, {"Accept": "application/dns-json"}),
        ("cloudflare", "https://cloudflare-dns.com/dns-query",
         {"name": test_domain, "type": "A"}, {"Accept": "application/dns-json"}),
    ]:
        try:
            resp = httpx.get(url, params=params, headers=headers, timeout=10)
            data = resp.json()
            answers = data.get("Answer", [])
            if answers:
                ip = answers[0].get("data", "")
                doh_results[name] = ip
                result.pass_(f"DoH {name}: {ip}")
            else:
                result.fail(f"DoH {name}: 无结果")
        except Exception as e:
            result.fail(f"DoH {name}: 失败", str(e)[:50])

    # [3.5] Python socket 直接解析
    try:
        addrinfo = socket.getaddrinfo(test_domain, 29833, socket.AF_INET, socket.SOCK_STREAM)
        if addrinfo:
            ip = addrinfo[0][4][0]
            result.pass_(f"Python socket: {ip}")
        else:
            result.fail("Python socket: 无结果")
    except Exception as e:
        result.fail("Python socket: 解析失败", str(e)[:50])

    return result


def test_tcp_connectivity() -> DiagnoseResult:
    """[4] TCP 连通性测试"""
    result = DiagnoseResult("TCP 连通性")

    # 已知 IP 列表
    test_ips = [
        ("85.211.195.146", "已知IP-1"),
        ("85.211.177.2", "已知IP-2"),
        ("85.211.176.179", "已知IP-3"),
    ]

    for ip, name in test_ips:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            start = time.time()
            rc = sock.connect_ex((ip, 29833))
            elapsed = int((time.time() - start) * 1000)
            if rc == 0:
                result.pass_(f"{name} ({ip}:29833)", f"连接成功 ({elapsed}ms)")
            else:
                result.fail(f"{name} ({ip}:29833)", f"连接失败 (code={rc})")
            sock.close()
        except Exception as e:
            result.fail(f"{name} ({ip}:29833)", str(e)[:50])

    return result


def load_yaml_safe(path: str) -> dict[str, Any]:
    """安全加载 YAML"""
    try:
        return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def check_config(args: argparse.Namespace) -> DiagnoseResult:
    """[5] mihomo 配置对比分析"""
    result = DiagnoseResult("配置分析")

    # [5.1] 我们的 config.yaml 关键配置
    config = load_yaml_safe(args.config)
    if not config:
        result.fail("无法加载 config.yaml")
        return result

    dns = config.get("dns", {})
    result.info(f"mixed-port: {config.get('mixed-port', 'N/A')}")
    result.info(f"external-controller: {config.get('external-controller', 'N/A')}")
    result.info(f"dns.enable: {dns.get('enable', 'N/A')}")
    result.info(f"dns.enhanced-mode: {dns.get('enhanced-mode', 'N/A')}")
    result.info(f"dns.default-nameserver: {dns.get('default-nameserver', 'N/A')}")
    result.info(f"dns.proxy-server-nameserver: {dns.get('proxy-server-nameserver', 'N/A')}")
    result.info(f"dns.nameserver: {dns.get('nameserver', 'N/A')[:2] if dns.get('nameserver') else 'N/A'}...")

    proxies = config.get("proxies", [])
    if proxies:
        first = proxies[0]
        result.info(f"第一个节点: {first.get('name', 'N/A')}",
                   f"server={first.get('server', 'N/A')}, port={first.get('port', 'N/A')}")

    # [5.2] 原始订阅配置
    sub_config = load_yaml_safe(args.sub)
    if sub_config:
        sub_dns = sub_config.get("dns", {})
        if sub_dns:
            result.info("原始订阅 DNS 配置:")
            result.info(f"  enhanced-mode: {sub_dns.get('enhanced-mode', 'N/A')}")
            result.info(f"  proxy-server-nameserver: {sub_dns.get('proxy-server-nameserver', 'N/A')}")
        else:
            result.info("原始订阅: 无 DNS 配置")

        # 对比差异
        our_pss = dns.get("proxy-server-nameserver", [])
        sub_pss = sub_dns.get("proxy-server-nameserver", []) if sub_dns else []
        if our_pss != sub_pss:
            result.warn("proxy-server-nameserver 与原始订阅不同",
                       f"我们: {our_pss[:1]}..., 原始: {sub_pss[:1]}...")

    return result


async def test_mihomo_runtime(args: argparse.Namespace) -> DiagnoseResult:
    """[6] mihomo 运行时测试"""
    result = DiagnoseResult("运行时测试")

    if args.skip_runtime:
        result.info("跳过", "--skip-runtime 已指定")
        return result

    mihomo_path = args.mihomo or os.environ.get("MIHOMO_PATH", "")
    if not mihomo_path or not Path(mihomo_path).exists():
        for candidate in ["mihomo-windows-amd64-v3.exe", "./mihomo-windows-amd64-v3.exe"]:
            if Path(candidate).exists():
                mihomo_path = str(Path(candidate).resolve())
                break

    if not mihomo_path or not Path(mihomo_path).exists():
        result.fail("mihomo 未找到，跳过后续测试")
        return result

    # 先停止可能运行的 mihomo
    if IS_WINDOWS:
        run_cmd("taskkill /f /im mihomo-windows-amd64-v3.exe 2>nul", timeout=3)
    else:
        # Linux: use pkill to stop mihomo processes
        run_cmd("pkill -f mihomo 2>/dev/null || true", timeout=3)
    await asyncio.sleep(1)

    sub_config = load_yaml_safe(args.sub)
    proxies = sub_config.get("proxies", [])
    test_node = args.node

    # 找到第一个真实代理节点
    if not test_node and proxies:
        for p in proxies:
            name = p.get("name", "")
            if "流量" not in name and "重置" not in name and "到期" not in name and "网址" not in name:
                test_node = name
                break

    if not test_node:
        result.fail("未找到可测试的节点")
        return result

    result.info("测试节点", test_node)

    # 加载原始订阅
    sub_data = Path(args.sub).read_text(encoding="utf-8") if Path(args.sub).exists() else ""

    tests = [
        ("A", "DNS 关闭", {"dns": {"enable": False}}),
        ("B", "redir-host", {"dns": {"enable": True, "enhanced-mode": "redir-host",
                                     "nameserver": ["https://doh.pub/dns-query"]}}),
        ("C", "fake-ip+DoH", {"dns": {"enable": True, "enhanced-mode": "fake-ip",
                                        "proxy-server-nameserver": ["https://dns.google/dns-query",
                                                                    "https://doh.pub/dns-query"]}}),
    ]

    for test_id, test_name, dns_override in tests:
        config_path = Path(f"config_diag_{test_id}.yaml")
        try:
            # 生成测试配置
            if test_id == "D":
                # 测试 D: 原始订阅
                if sub_data:
                    config_path.write_text(sub_data, encoding="utf-8")
                else:
                    result.fail(f"[TEST {test_id}] 原始订阅", "无法加载")
                    continue
            elif test_id == "E":
                # 测试 E: 最小配置
                minimal = {
                    "mixed-port": 7890,
                    "external-controller": "127.0.0.1:9090",
                    "proxies": proxies[:1] if proxies else [],
                    "proxy-groups": [{"name": "GLOBAL", "type": "select",
                                      "proxies": [proxies[0].get("name")] if proxies else []}],
                    "rules": ["MATCH,GLOBAL"],
                }
                config_path.write_text(
                    yaml.dump(
                        minimal,
                        allow_unicode=True,
                        default_flow_style=False,
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )
            else:
                # 基于原始订阅修改
                test_config = yaml.safe_load(sub_data) if sub_data else {"proxies": [], "proxy-groups": []}
                if not isinstance(test_config, dict):
                    test_config = {}
                # 合并 DNS 配置
                test_config["dns"] = dns_override.get("dns", {})
                # 确保有基本配置
                test_config.setdefault("mixed-port", 7890)
                test_config.setdefault("external-controller", "127.0.0.1:9090")
                config_path.write_text(
                    yaml.dump(
                        test_config,
                        allow_unicode=True,
                        default_flow_style=False,
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )

            # 启动 mihomo
            proc = await asyncio.create_subprocess_exec(
                mihomo_path, "-d", ".", "-f", str(config_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )

            # 等待 API 就绪
            await asyncio.sleep(2)
            delay_result = None
            error_msg = ""

            for _ in range(8):  # 最多 8 秒
                try:
                    async with httpx.AsyncClient(timeout=3) as client:
                        # 先检查版本
                        ver_resp = await client.get("http://127.0.0.1:9090/version")
                        if ver_resp.status_code == 200:
                            # 测试延迟
                            encoded_node = quote(test_node, safe="")
                            delay_resp = await client.get(
                                f"http://127.0.0.1:9090/proxies/{encoded_node}/delay",
                                params={"url": "http://www.gstatic.com/generate_204", "timeout": 5000},
                                timeout=10,
                            )
                            if delay_resp.status_code == 200:
                                data = delay_resp.json()
                                delay_result = data.get("delay", 0)
                                break
                            else:
                                error_msg = f"API error {delay_resp.status_code}"
                except Exception as e:
                    error_msg = str(e)[:30]
                await asyncio.sleep(1)

            # 停止 mihomo
            proc.terminate()
            await proc.wait()
            if IS_WINDOWS:
                run_cmd("taskkill /f /im mihomo-windows-amd64-v3.exe 2>nul", timeout=2)
            else:
                run_cmd("pkill -f mihomo 2>/dev/null || true", timeout=2)

            if delay_result and delay_result > 0:
                result.pass_(f"[TEST {test_id}] {test_name}", f"延迟 {delay_result}ms")
            else:
                result.fail(f"[TEST {test_id}] {test_name}", error_msg or "超时或失败")

            # 清理
            config_path.unlink(missing_ok=True)
            await asyncio.sleep(0.5)

        except Exception as e:
            result.fail(f"[TEST {test_id}] {test_name}", str(e)[:50])
            run_cmd("taskkill /f /im mihomo-windows-amd64-v3.exe 2>nul", timeout=2)

    # 最后清理
    for f in ["config_diag_A.yaml", "config_diag_B.yaml", "config_diag_C.yaml"]:
        Path(f).unlink(missing_ok=True)

    return result


def check_ziyoumao() -> DiagnoseResult:
    """[7] 自由猫进程分析（仅限 Windows）"""
    result = DiagnoseResult("自由猫分析")

    if not IS_WINDOWS:
        result.info("自由猫分析", "仅支持 Windows 系统")
        return result

    # [7.1] 检查进程
    rc, stdout, _ = run_cmd("tasklist /FI \"IMAGENAME eq ziyoumaoCore.exe\" /FO CSV", timeout=3)
    if rc == 0 and "ziyoumaoCore" in stdout:
        result.info("ziyoumaoCore.exe 正在运行")
    else:
        rc, stdout, _ = run_cmd("tasklist /FI \"IMAGENAME eq ziyoumao.exe\" /FO CSV", timeout=3)
        if rc == 0 and "ziyoumao" in stdout:
            result.info("ziyoumao.exe 正在运行")
        else:
            result.info("自由猫未运行", "无法分析其配置")
            return result

    # [7.2] 检查端口
    rc, stdout, _ = run_cmd("netstat -ano | findstr LISTENING", timeout=5)
    if rc == 0:
        ziyoumao_ports = []
        for line in stdout.splitlines():
            if any(p in line for p in ["7890", "9090", "9091", "19090"]):
                ziyoumao_ports.append(line.strip()[:60])
        if ziyoumao_ports:
            result.info("自由猫监听端口", ziyoumao_ports[0])

    # [7.3] 尝试获取配置
    for port in [9090, 9091, 19090]:
        try:
            resp = httpx.get(f"http://127.0.0.1:{port}/configs", timeout=3)
            if resp.status_code == 200:
                result.pass_(f"自由猫 API 端口 {port} 可访问")
                break
        except Exception:
            pass
    else:
        result.info("无法访问自由猫 API", "可能使用了 secret 或未开启外部控制")

    return result


def print_report(results: list[DiagnoseResult], args: argparse.Namespace) -> None:
    """打印诊断报告"""
    print("=" * 60)
    print("  mihomo 代理连接诊断报告")
    print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    for r in results:
        print(f"[{r.section}]")
        for item in r.items:
            status = item["status"]
            name = item["name"]
            detail = item["detail"]
            if detail:
                print(f"  [{status}] {name} - {detail}")
            else:
                print(f"  [{status}] {name}")
        print()

    # 诊断结论
    print("=" * 60)
    print("  诊断结论")
    print("=" * 60)
    print()

    # 自动分析
    analysis = []

    # 检查 DNS 情况
    dns_result = next((r for r in results if r.section == "DNS 解析"), None)
    if dns_result:
        doh_pass = any("DoH" in i["name"] and i["status"] == "PASS" for i in dns_result.items)
        system_fail = any("系统 DNS" in i["name"] and i["status"] == "FAIL" for i in dns_result.items)
        if doh_pass and system_fail:
            analysis.append("DNS 污染确认: 系统 DNS 失败但 DoH 成功，节点域名被污染")

    # 检查 TCP
    tcp_result = next((r for r in results if r.section == "TCP 连通性"), None)
    if tcp_result:
        tcp_pass = any(i["status"] == "PASS" for i in tcp_result.items)
        if not tcp_pass:
            analysis.append("TCP 连接失败: 所有 IP 的 29833 端口都不通，可能被封锁")
        else:
            analysis.append("TCP 连接正常: 端口未被封锁")

    # 检查运行时测试
    runtime_result = next((r for r in results if r.section == "运行时测试"), None)
    if runtime_result and not args.skip_runtime:
        test_results = {i["name"]: i["status"] for i in runtime_result.items}
        if "[TEST C] fake-ip+DoH" in test_results:
            if test_results["[TEST C] fake-ip+DoH"] == "PASS":
                analysis.append("当前配置可正常工作: fake-ip + DoH 模式测试通过")
            else:
                analysis.append("当前配置可能有问题: fake-ip + DoH 测试失败")

    # 检查虚拟网卡
    net_result = next((r for r in results if r.section == "网络环境"), None)
    if net_result:
        has_tun = any("虚拟网卡" in i["name"] and i["status"] == "WARN" for i in net_result.items)
        if has_tun:
            analysis.append("警告: 发现 TUN 虚拟网卡，可能干扰 mihomo 网络连接")

    if analysis:
        for line in analysis:
            print(f"- {line}")
    else:
        print("- 未能自动分析根因，请查看详细测试结果")

    print()
    print("建议:")
    print("- 如果 DoH 能解析但系统 DNS 不能，确认 config.yaml 中 proxy-server-nameserver 使用 DoH")
    print("- 如果所有运行时测试都失败，检查是否有其他代理软件冲突")
    print("- 如果 TCP 连接失败，可能需要更换机场或使用 TUN 模式")
    print()


async def main() -> int:
    args = parse_args()

    results: list[DiagnoseResult] = []

    # 执行各项检查
    results.append(check_environment(args))
    results.append(check_network())
    results.append(test_dns_resolution())
    results.append(test_tcp_connectivity())
    results.append(check_config(args))
    results.append(await test_mihomo_runtime(args))
    results.append(check_ziyoumao())

    # 打印报告
    print_report(results, args)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
