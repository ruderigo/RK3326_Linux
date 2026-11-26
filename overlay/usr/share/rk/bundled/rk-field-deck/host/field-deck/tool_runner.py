#!/usr/bin/env python3
"""
tool_runner.py — Safe, Allowlisted Scan & Diagnostic Arsenal Runner for RK Field Deck
Target: RK3326_Linux (v1.2.0+, R36MAX & 93 RK3326 handhelds) + Desktop Linux

Bridges RK3326_Linux's `rk-scan` (rkshell/nmapspec.py) and the defensive/diagnostic
tools from `rkshell/arsenal.py` into a unified device-card action engine:
  - Strict input validation (IPv4/IPv6 via ipaddress, MAC regex, iface regex)
  - Zero shell=True invocation (argv lists only)
  - Root privilege isolation:
      * nmap scans execute via RK3326_Linux's own `/usr/local/sbin/rk-scan run`
        (validated JSON loadout on stdin; closing stdin cancels cleanly)
      * privileged passive capture / LAN ARP discovery (`arp-scan`, `tcpdump`,
        `tshark`, `ngrep`) execute via root-owned `/usr/local/sbin/rk-field-tool`
        (same stdin-controlled protocol as `rk-scan`, writing captures only under
        `/data/ark/field-deck/captures`)
  - Offensive exploitation / attack tools from `arsenal.py` (e.g., Metasploit,
    sqlmap, ettercap, mdk4, reaver, bully, wifite, hcxdumptool, aircrack-ng)
    are intentionally excluded.

Pure Python 3 stdlib (zero pip dependencies).
"""

import argparse
import datetime
import ipaddress
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET

IFACE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,15}$")
MAC_RE = re.compile(r"^[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}$")
CIDR_RE = re.compile(r"^[0-9]{1,3}(\.[0-9]{1,3}){3}/[0-9]{1,2}$")
SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")

RK_SCAN_BIN = "/usr/local/sbin/rk-scan"
RK_FIELD_TOOL_BIN = "/usr/local/sbin/rk-field-tool"


def resolve_data_dir():
    env_dir = os.environ.get("RK_FIELD_DECK_DATA_DIR")
    if env_dir:
        return os.path.realpath(env_dir)
    if os.path.isdir("/data/ark"):
        return "/data/ark/field-deck"
    return os.path.realpath(os.path.expanduser("~/.local/share/rk-field-deck"))


def safe_capture_path(filename, base_dir=None):
    """Confine capture output strictly inside `<data_dir>/captures/`."""
    if not filename or not SLUG_RE.match(filename):
        raise ValueError("Invalid capture filename")
    root = os.path.realpath(os.path.join(base_dir or resolve_data_dir(), "captures"))
    os.makedirs(root, exist_ok=True)
    target = os.path.realpath(os.path.join(root, filename))
    if not target.startswith(root + os.sep):
        raise ValueError("Capture path escapes allowed directory")
    return target


def validate_ip(value):
    s = (value or "").strip()
    if not s:
        return ""
    try:
        ip = ipaddress.ip_address(s)
        return str(ip)
    except ValueError:
        return ""


def validate_cidr(value):
    s = (value or "").strip()
    if not s or not CIDR_RE.match(s):
        return ""
    try:
        net = ipaddress.ip_network(s, strict=False)
        if net.prefixlen < 16:
            return ""
        return str(net)
    except ValueError:
        return ""


def validate_mac(value):
    s = (value or "").strip().lower()
    return s if MAC_RE.match(s) else ""


def validate_iface(value):
    s = (value or "").strip()
    return s if IFACE_RE.match(s) else ""


# ---------------------------------------------------------------------------
# Device-card -> Scan & Diagnostic Arsenal Tool Registry
# Every entry maps directly to RK3326_Linux's `rk-scan` or `rkshell/arsenal.py`
# ---------------------------------------------------------------------------
TOOL_CATALOGUE = [
    # --- RK3326_Linux Scan (rkshell/nmapspec.py via /usr/local/sbin/rk-scan) ---
    {
        "id": "scan_quick",
        "label": "Scan: Quick Look (Top 100)",
        "group": "Scan (rk-scan)",
        "binary": "nmap",
        "runner": "rk-scan",
        "requires_root": True,
        "target_kind": "ip",
        "description": "RK3326_Linux rk-scan Quick Look preset (SYN top-100 ports, T4) for the selected host.",
        "nmap_preset": {"mode": "ports", "ports": "top100", "technique": "syn", "versions": False, "os": False, "scripts": "none", "timing": 4, "noping": False},
    },
    {
        "id": "scan_identify",
        "label": "Scan: Identify (Versions + OS)",
        "group": "Scan (rk-scan)",
        "binary": "nmap",
        "runner": "rk-scan",
        "requires_root": True,
        "target_kind": "ip",
        "description": "RK3326_Linux rk-scan Identify preset (top-1000 ports, service versions -sV, OS guess -O).",
        "nmap_preset": {"mode": "ports", "ports": "top1000", "technique": "syn", "versions": True, "os": True, "scripts": "none", "timing": 4, "noping": False},
    },
    {
        "id": "scan_quiet",
        "label": "Scan: Quiet (T2 Polite)",
        "group": "Scan (rk-scan)",
        "binary": "nmap",
        "runner": "rk-scan",
        "requires_root": True,
        "target_kind": "ip",
        "description": "RK3326_Linux rk-scan Quiet preset (low-rate T2 polite top-100 port inventory).",
        "nmap_preset": {"mode": "ports", "ports": "top100", "technique": "syn", "versions": False, "os": False, "scripts": "none", "timing": 2, "noping": False},
    },
    {
        "id": "scan_sweep",
        "label": "Scan: Host Sweep (-sn)",
        "group": "Scan (rk-scan)",
        "binary": "nmap",
        "runner": "rk-scan",
        "requires_root": True,
        "target_kind": "ip_or_cidr",
        "description": "RK3326_Linux rk-scan Sweep preset (-sn ping/ARP host discovery).",
        "nmap_preset": {"mode": "sweep", "ports": "top100", "technique": "syn", "versions": False, "os": False, "scripts": "none", "timing": 4, "noping": False},
    },

    # --- Arsenal: Seeing the traffic (100% passive packet inspection) ---
    {
        "id": "tcpdump_host",
        "label": "tcpdump: Capture 100 Pkts (.pcap)",
        "group": "Traffic Capture",
        "binary": "tcpdump",
        "runner": "rk-field-tool",
        "requires_root": True,
        "target_kind": "ip_or_mac",
        "description": "Passively capture up to 100 packets matching this device IP or MAC and save .pcap to /data/ark.",
    },
    {
        "id": "tshark_host",
        "label": "tshark: Live Protocol Decode",
        "group": "Traffic Capture",
        "binary": "tshark",
        "runner": "rk-field-tool",
        "requires_root": True,
        "target_kind": "ip_or_mac",
        "description": "Wireshark CLI passive protocol decode (60 packets) filtered strictly to this device IP or MAC.",
    },
    {
        "id": "ngrep_host",
        "label": "ngrep: Inspect ASCII Headers",
        "group": "Traffic Capture",
        "binary": "ngrep",
        "runner": "rk-field-tool",
        "requires_root": True,
        "target_kind": "ip",
        "description": "Passively display readable packet headers/payloads (40 packets) involving this device IP.",
    },

    # --- Arsenal: The network around you (read-only diagnostics & inventory) ---
    {
        "id": "arp_scan_lan",
        "label": "arp-scan: Refresh Local LAN Cards",
        "group": "Network Diagnostics",
        "binary": "arp-scan",
        "runner": "rk-field-tool",
        "requires_root": True,
        "target_kind": "iface",
        "description": "Query the local link via ARP to discover live LAN devices (IP, MAC, vendor) for Device Cards.",
    },
    {
        "id": "fping_host",
        "label": "fping: Reachability & RTT (5x)",
        "group": "Network Diagnostics",
        "binary": "fping",
        "runner": "direct",
        "requires_root": False,
        "target_kind": "ip",
        "description": "Measure ICMP reachability, packet loss, and round-trip latency (5 probes) to this host.",
    },
    {
        "id": "nbtscan_host",
        "label": "nbtscan: NetBIOS Name Query",
        "group": "Network Diagnostics",
        "binary": "nbtscan",
        "runner": "direct",
        "requires_root": False,
        "target_kind": "ip",
        "description": "Query Windows/Samba NetBIOS host name and workgroup metadata for this IP.",
    },
    {
        "id": "sslscan_host",
        "label": "sslscan: TLS Cert & Ciphers",
        "group": "Network Diagnostics",
        "binary": "sslscan",
        "runner": "direct",
        "requires_root": False,
        "target_kind": "ip",
        "description": "Audit TLS protocol versions, cipher suites, and certificate details on port 443.",
    },
    {
        "id": "dig_ptr",
        "label": "dig: Reverse DNS (PTR)",
        "group": "Network Diagnostics",
        "binary": "dig",
        "runner": "direct",
        "requires_root": False,
        "target_kind": "ip",
        "description": "Perform reverse PTR DNS lookup for this IP address.",
    },
    {
        "id": "whois_host",
        "label": "whois: ASN & Netblock Lookup",
        "group": "Network Diagnostics",
        "binary": "whois",
        "runner": "direct",
        "requires_root": False,
        "target_kind": "ip",
        "description": "Query WHOIS registration and netblock ownership for this IP address.",
    },
    {
        "id": "snmpwalk_sys",
        "label": "snmpwalk: Read System MIB",
        "group": "Network Diagnostics",
        "binary": "snmpwalk",
        "runner": "direct",
        "requires_root": False,
        "target_kind": "ip",
        "description": "Read-only SNMPv2c system subtree (1.3.6.1.2.1.1) inventory if SNMP is enabled.",
    },

    # --- Arsenal: Web servers and apps (passive / read-only inspection) ---
    {
        "id": "httpie_head",
        "label": "httpie: HTTP HEAD Inspection",
        "group": "Web Inspection",
        "binary": "http",
        "runner": "direct",
        "requires_root": False,
        "target_kind": "ip",
        "description": "Send a read-only HTTP HEAD request to inspect status code, server banner, and headers.",
    },
    {
        "id": "whatweb_host",
        "label": "whatweb: Stack Fingerprint",
        "group": "Web Inspection",
        "binary": "whatweb",
        "runner": "direct",
        "requires_root": False,
        "target_kind": "ip",
        "description": "Passively identify web server software, frameworks, and titles on HTTP.",
    },
    {
        "id": "wafw00f_host",
        "label": "wafw00f: WAF Detection",
        "group": "Web Inspection",
        "binary": "wafw00f",
        "runner": "direct",
        "requires_root": False,
        "target_kind": "ip",
        "description": "Check whether a web application firewall sits in front of this host's HTTP service.",
    },
]

TOOL_BY_ID = {t["id"]: t for t in TOOL_CATALOGUE}


def tool_available(tool):
    return bool(shutil.which(tool["binary"]))


def tools_for_device(device):
    """
    Return the ordered list of Scan & diagnostic Arsenal tools applicable to a
    detected device card, annotated with live `installed` availability.
    """
    ip = validate_ip(device.get("ip", ""))
    mac = validate_mac(device.get("mac", ""))
    iface = validate_iface(device.get("iface", ""))
    band = device.get("band", "")

    matched = []
    for tool in TOOL_CATALOGUE:
        kind = tool["target_kind"]
        ok = False
        if kind == "ip" and ip:
            ok = True
        elif kind == "ip_or_cidr" and (ip or validate_cidr(device.get("cidr", ""))):
            ok = True
        elif kind == "ip_or_mac" and (ip or mac):
            ok = True
        elif kind == "iface" and (iface or band == "LAN"):
            ok = True
        if ok:
            item = dict(tool)
            item["installed"] = tool_available(tool)
            matched.append(item)
    return matched


def build_tool_command(tool_id, target_ip="", target_mac="", target_cidr="", iface="", pcap_name=""):
    """
    Build a strictly validated, shell-free argv list (or rk-scan JSON loadout)
    for any allowlisted tool in TOOL_CATALOGUE. Raises ValueError on bad input.
    """
    tool = TOOL_BY_ID.get(tool_id)
    if not tool:
        raise ValueError(f"Unknown or non-allowlisted tool: {tool_id}")

    ip = validate_ip(target_ip)
    mac = validate_mac(target_mac)
    cidr = validate_cidr(target_cidr)
    ifc = validate_iface(iface)

    if tool["runner"] == "rk-scan":
        tgt = ip or cidr
        if not tgt:
            raise ValueError("Selected device has no valid IPv4/IPv6 address or CIDR for rk-scan")
        spec = dict(tool["nmap_preset"], target=tgt)
        return {"mode": "rk-scan", "spec": spec, "preview": _preview_nmap(spec)}

    if tool_id == "tcpdump_host":
        if not (ip or mac):
            raise ValueError("tcpdump requires a valid device IP or MAC address")
        args = ["tcpdump", "-nn", "-c", "100", "-l"]
        if ifc:
            args += ["-i", ifc]
        if pcap_name:
            out_path = safe_capture_path(pcap_name)
            args += ["-w", out_path]
        if ip:
            args += ["host", ip]
        else:
            args += ["ether", "host", mac]
        return {"mode": "argv", "argv": args, "privileged": True, "preview": " ".join(args)}

    if tool_id == "tshark_host":
        if not (ip or mac):
            raise ValueError("tshark requires a valid device IP or MAC address")
        args = ["tshark", "-n", "-c", "60", "-l"]
        if ifc:
            args += ["-i", ifc]
        flt = f"host {ip}" if ip else f"ether host {mac}"
        args += ["-f", flt]
        return {"mode": "argv", "argv": args, "privileged": True, "preview": " ".join(args)}

    if tool_id == "ngrep_host":
        if not ip:
            raise ValueError("ngrep requires a valid device IP address")
        args = ["ngrep", "-q", "-n", "40", "-W", "byline"]
        if ifc:
            args += ["-d", ifc]
        args += ["", "host", ip]
        return {"mode": "argv", "argv": args, "privileged": True, "preview": " ".join(args)}

    if tool_id == "arp_scan_lan":
        args = ["arp-scan", "--localnet", "--plain", "--retry=2"]
        if ifc:
            args += ["-I", ifc]
        return {"mode": "argv", "argv": args, "privileged": True, "preview": " ".join(args)}

    if tool_id == "fping_host":
        if not ip:
            raise ValueError("fping requires a valid device IP")
        args = ["fping", "-c", "5", "-q", ip]
        return {"mode": "argv", "argv": args, "privileged": False, "preview": " ".join(args)}

    if tool_id == "nbtscan_host":
        if not ip:
            raise ValueError("nbtscan requires a valid device IP")
        args = ["nbtscan", "-v", ip]
        return {"mode": "argv", "argv": args, "privileged": False, "preview": " ".join(args)}

    if tool_id == "sslscan_host":
        if not ip:
            raise ValueError("sslscan requires a valid device IP")
        args = ["sslscan", "--no-colour", f"{ip}:443"]
        return {"mode": "argv", "argv": args, "privileged": False, "preview": " ".join(args)}

    if tool_id == "dig_ptr":
        if not ip:
            raise ValueError("dig requires a valid device IP")
        args = ["dig", "+noall", "+answer", "-x", ip]
        return {"mode": "argv", "argv": args, "privileged": False, "preview": " ".join(args)}

    if tool_id == "whois_host":
        if not ip:
            raise ValueError("whois requires a valid device IP")
        args = ["whois", ip]
        return {"mode": "argv", "argv": args, "privileged": False, "preview": " ".join(args)}

    if tool_id == "snmpwalk_sys":
        if not ip:
            raise ValueError("snmpwalk requires a valid device IP")
        args = ["snmpwalk", "-v2c", "-c", "public", "-t", "2", "-r", "1", ip, "1.3.6.1.2.1.1"]
        return {"mode": "argv", "argv": args, "privileged": False, "preview": " ".join(args)}

    if tool_id == "httpie_head":
        if not ip:
            raise ValueError("httpie requires a valid device IP")
        args = ["http", "--check-status", "--timeout=5", "--print=h", "HEAD", f"http://{ip}/"]
        return {"mode": "argv", "argv": args, "privileged": False, "preview": " ".join(args)}

    if tool_id == "whatweb_host":
        if not ip:
            raise ValueError("whatweb requires a valid device IP")
        args = ["whatweb", "--color=never", "--aggression=1", f"http://{ip}"]
        return {"mode": "argv", "argv": args, "privileged": False, "preview": " ".join(args)}

    if tool_id == "wafw00f_host":
        if not ip:
            raise ValueError("wafw00f requires a valid device IP")
        args = ["wafw00f", f"http://{ip}"]
        return {"mode": "argv", "argv": args, "privileged": False, "preview": " ".join(args)}

    raise ValueError(f"Unsupported tool: {tool_id}")


def _preview_nmap(spec):
    cmd = ["nmap", f"-T{spec['timing']}"]
    if spec.get("noping"):
        cmd.append("-Pn")
    if spec.get("mode") == "sweep":
        cmd.append("-sn")
    else:
        cmd.append({"syn": "-sS", "connect": "-sT", "udp": "-sU"}[spec["technique"]])
        if spec["ports"] == "top100":
            cmd.append("-F")
        elif spec["ports"] == "all":
            cmd.append("-p-")
        if spec.get("versions"):
            cmd.append("-sV")
        if spec.get("os"):
            cmd.append("-O")
    cmd.append(spec["target"])
    return " ".join(cmd)


# ---------------------------------------------------------------------------
# Live LAN Device Discovery Parsers (ip neigh, arp-scan, rk-scan nmap XML)
# ---------------------------------------------------------------------------
def list_own_networks():
    """Return [(iface, cidr, ip), ...] from `ip -j -4 addr show scope global`."""
    try:
        out = subprocess.run(
            ["ip", "-j", "-4", "addr", "show", "scope", "global"],
            capture_output=True, text=True, timeout=4,
        ).stdout
        result = []
        for dev in json.loads(out or "[]"):
            ifname = dev.get("ifname", "")
            for a in dev.get("addr_info", []):
                if a.get("family") == "inet":
                    iface_obj = ipaddress.ip_interface(f"{a['local']}/{a['prefixlen']}")
                    result.append((ifname, str(iface_obj.network), str(iface_obj.ip)))
        return result
    except Exception:
        return []


def parse_ip_neigh(text):
    """Parse `ip neigh show` into real LAN device dicts."""
    hosts = []
    for raw in (text or "").splitlines():
        parts = raw.split()
        if len(parts) < 5:
            continue
        ip = validate_ip(parts[0])
        if not ip:
            continue
        iface = ""
        mac = ""
        state = parts[-1]
        if state in ("FAILED", "INCOMPLETE"):
            continue
        for i, tok in enumerate(parts):
            if tok == "dev" and i + 1 < len(parts):
                iface = validate_iface(parts[i + 1])
            elif tok == "lladdr" and i + 1 < len(parts):
                mac = validate_mac(parts[i + 1])
        if mac:
            hosts.append({"ip": ip, "mac": mac, "iface": iface, "state": state, "vendor": ""})
    return hosts


def parse_arp_scan_output(text):
    """Parse `arp-scan --localnet --plain` output lines (`<ip>\t<mac>\t<vendor>`)."""
    hosts = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        cols = line.split("\t")
        if len(cols) < 2:
            cols = line.split(None, 2)
        if len(cols) < 2:
            continue
        ip = validate_ip(cols[0])
        mac = validate_mac(cols[1])
        if not ip or not mac:
            continue
        vendor = cols[2].strip() if len(cols) >= 3 else ""
        hosts.append({"ip": ip, "mac": mac, "vendor": vendor})
    return hosts


def parse_nmap_xml_hosts(xml_text):
    """Parse `nmap -oX -` XML output from `/usr/local/sbin/rk-scan run` into host records."""
    hosts = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return hosts
    for h in root.findall("host"):
        st = h.find("status")
        if st is not None and st.attrib.get("state") != "up":
            continue
        ip = ""
        mac = ""
        vendor = ""
        for addr in h.findall("address"):
            atype = addr.attrib.get("addrtype", "")
            if atype in ("ipv4", "ipv6") and not ip:
                ip = validate_ip(addr.attrib.get("addr", ""))
            elif atype == "mac":
                mac = validate_mac(addr.attrib.get("addr", ""))
                vendor = addr.attrib.get("vendor", "")
        hostname = ""
        hn = h.find("hostnames/hostname")
        if hn is not None:
            hostname = hn.attrib.get("name", "")
        os_name = ""
        osm = h.find("os/osmatch")
        if osm is not None:
            os_name = osm.attrib.get("name", "")
        ports = []
        for p in h.findall("ports/port"):
            pst = p.find("state")
            if pst is None or pst.attrib.get("state") != "open":
                continue
            svc = p.find("service")
            svc_name = svc.attrib.get("name", "") if svc is not None else ""
            prod = svc.attrib.get("product", "") if svc is not None else ""
            ver = svc.attrib.get("version", "") if svc is not None else ""
            ports.append({
                "port": int(p.attrib.get("portid", 0)),
                "proto": p.attrib.get("protocol", "tcp"),
                "service": svc_name,
                "banner": f"{prod} {ver}".strip(),
            })
        if ip:
            hosts.append({
                "ip": ip, "mac": mac, "vendor": vendor,
                "hostname": hostname, "os": os_name, "ports": ports,
            })
    return hosts


def read_local_arp_neighbors():
    try:
        out = subprocess.run(["ip", "neigh", "show"], capture_output=True, text=True, timeout=3).stdout
        return parse_ip_neigh(out)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Streaming Job Runner (UI side)
# ---------------------------------------------------------------------------
class ToolJob:
    """Runs one allowlisted Scan or diagnostic Arsenal action asynchronously."""

    def __init__(self, tool_id, device, on_line=None, on_done=None):
        self.tool_id = tool_id
        self.tool = TOOL_BY_ID[tool_id]
        self.device = dict(device)
        self.on_line = on_line
        self.on_done = on_done
        self.lines = []
        self.raw_chunks = []
        self.started_at = time.time()
        self.finished_at = None
        self.returncode = None
        self.cancelled = False
        self.preview = ""
        self.pcap_path = ""
        self.parsed_hosts = []
        self._proc = None
        self._lock = threading.Lock()

    @property
    def running(self):
        return self.finished_at is None

    def _emit_line(self, line):
        with self._lock:
            self.lines.append(line)
            if len(self.lines) > 1500:
                self.lines = self.lines[-1500:]
        if self.on_line:
            self.on_line(line)

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def cancel(self):
        self.cancelled = True
        proc = self._proc
        if proc and proc.poll() is None:
            try:
                if proc.stdin:
                    proc.stdin.close()
            except Exception:
                pass
            try:
                proc.terminate()
            except Exception:
                pass

    def _run(self):
        try:
            pcap_name = ""
            if self.tool_id == "tcpdump_host":
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                tag = (self.device.get("ip") or self.device.get("mac") or "host").replace(":", "").replace(".", "_")
                pcap_name = f"field_{tag}_{ts}.pcap"
                self.pcap_path = safe_capture_path(pcap_name)

            plan = build_tool_command(
                self.tool_id,
                target_ip=self.device.get("ip", ""),
                target_mac=self.device.get("mac", ""),
                target_cidr=self.device.get("cidr", ""),
                iface=self.device.get("iface", ""),
                pcap_name=pcap_name,
            )
            self.preview = plan["preview"]
            self._emit_line(f"$ {self.preview}")
            if self.pcap_path:
                self._emit_line(f"[capture] saving to {self.pcap_path}")

            if plan["mode"] == "rk-scan":
                self._exec_rk_scan(plan["spec"])
            else:
                self._exec_tool(plan)
        except Exception as exc:
            self._emit_line(f"[error] {exc}")
            self.returncode = 2
        finally:
            self.finished_at = time.time()
            if self.on_done:
                self.on_done(self)

    def _exec_rk_scan(self, spec):
        if os.path.exists(RK_SCAN_BIN):
            cmd = [RK_SCAN_BIN, "run"] if os.geteuid() == 0 else ["sudo", "-n", RK_SCAN_BIN, "run"]
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self._proc = proc
            proc.stdin.write(json.dumps(spec) + "\n")
            proc.stdin.flush()
            # Keep stdin open so closing stdin cancels rk-scan per RK3326_Linux contract
            xml_buf = []
            for line in proc.stdout:
                xml_buf.append(line)
                s = line.strip()
                if s.startswith("<taskprogress "):
                    m_pct = re.search(r'percent="([^"]+)"', s)
                    m_task = re.search(r'task="([^"]+)"', s)
                    if m_pct:
                        self._emit_line(f"[rk-scan] {m_task.group(1) if m_task else 'scan'}: {m_pct.group(1)}%")
                elif "<port protocol=" in s or "<address addr=" in s or "<osmatch " in s:
                    self._emit_line(s[:140])
            proc.wait()
            self.returncode = proc.returncode
            xml_text = "".join(xml_buf)
            self.parsed_hosts = parse_nmap_xml_hosts(xml_text)
            if self.parsed_hosts:
                self._emit_line(f"[rk-scan] parsed {len(self.parsed_hosts)} live host(s):")
                for h in self.parsed_hosts:
                    ports_str = ", ".join(f"{p['port']}/{p['proto']}({p['service']})" for p in h["ports"]) or "no open ports"
                    self._emit_line(f"  {h['ip']}  {h['mac'] or '-'}  {h['os'] or h['vendor'] or ''}  [{ports_str}]")
        else:
            # Desktop Linux fallback when rk-scan is not installed (uses non-root connect scan if unprivileged)
            if not shutil.which("nmap"):
                self._emit_line("[error] nmap is not installed on this host")
                self.returncode = 127
                return
            argv = ["nmap", f"-T{spec['timing']}", "-oX", "-"]
            if spec["mode"] == "sweep":
                argv.append("-sn")
            else:
                argv.append("-sS" if os.geteuid() == 0 else "-sT")
                if spec["ports"] == "top100":
                    argv.append("-F")
                if spec.get("versions"):
                    argv.append("-sV")
            argv.append(spec["target"])
            proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            self._proc = proc
            xml_text = proc.stdout.read()
            proc.wait()
            self.returncode = proc.returncode
            self.parsed_hosts = parse_nmap_xml_hosts(xml_text)
            for h in self.parsed_hosts:
                ports_str = ", ".join(f"{p['port']}/{p['proto']}({p['service']})" for p in h["ports"]) or "no open ports"
                self._emit_line(f"  {h['ip']}  {h['mac'] or '-'}  [{ports_str}]")

    def _exec_tool(self, plan):
        if plan["privileged"] and os.geteuid() != 0 and os.path.exists(RK_FIELD_TOOL_BIN):
            req = {
                "tool_id": self.tool_id,
                "ip": self.device.get("ip", ""),
                "mac": self.device.get("mac", ""),
                "cidr": self.device.get("cidr", ""),
                "iface": self.device.get("iface", ""),
                "pcap_name": os.path.basename(self.pcap_path) if self.pcap_path else "",
            }
            proc = subprocess.Popen(
                ["sudo", "-n", RK_FIELD_TOOL_BIN, "run"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self._proc = proc
            proc.stdin.write(json.dumps(req) + "\n")
            proc.stdin.flush()
        else:
            binary = plan["argv"][0]
            if not shutil.which(binary):
                self._emit_line(f"[error] binary `{binary}` is not installed (check Arsenal / PATH)")
                self.returncode = 127
                return
            proc = subprocess.Popen(
                plan["argv"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self._proc = proc

        for raw in proc.stdout:
            line = raw.rstrip("\r\n")
            self.raw_chunks.append(line)
            if line:
                self._emit_line(line)
        proc.wait()
        self.returncode = proc.returncode
        if self.tool_id == "arp_scan_lan":
            self.parsed_hosts = parse_arp_scan_output("\n".join(self.raw_chunks))


# ---------------------------------------------------------------------------
# Root-isolated Helper Mode (`/usr/local/sbin/rk-field-tool run`)
# Mirrors RK3326_Linux's `/usr/local/sbin/rk-scan` security model exactly.
# ---------------------------------------------------------------------------
PRIVILEGED_HELPER_IDS = {"tcpdump_host", "tshark_host", "ngrep_host", "arp_scan_lan"}


def run_helper_from_stdin():
    try:
        req = json.loads(sys.stdin.readline() or "")
    except ValueError:
        print("rk-field-tool: invalid JSON request", file=sys.stderr)
        return 2
    if not isinstance(req, dict):
        print("rk-field-tool: request must be a JSON object", file=sys.stderr)
        return 2

    tool_id = str(req.get("tool_id", ""))
    if tool_id not in PRIVILEGED_HELPER_IDS:
        print(f"rk-field-tool: tool `{tool_id}` is not permitted via privileged helper", file=sys.stderr)
        return 2

    try:
        plan = build_tool_command(
            tool_id,
            target_ip=str(req.get("ip", "")),
            target_mac=str(req.get("mac", "")),
            target_cidr=str(req.get("cidr", "")),
            iface=str(req.get("iface", "")),
            pcap_name=str(req.get("pcap_name", "")),
        )
    except ValueError as exc:
        print(f"rk-field-tool: {exc}", file=sys.stderr)
        return 2

    if not shutil.which(plan["argv"][0]):
        print(f"rk-field-tool: binary `{plan['argv'][0]}` not installed", file=sys.stderr)
        return 127

    child = subprocess.Popen(plan["argv"], stdin=subprocess.DEVNULL)

    def watch_stdin():
        try:
            sys.stdin.read()
        except Exception:
            pass
        if child.poll() is None:
            child.terminate()

    threading.Thread(target=watch_stdin, daemon=True).start()
    return child.wait()


def probe_environment():
    tools = [
        {
            "id": t["id"],
            "label": t["label"],
            "group": t["group"],
            "binary": t["binary"],
            "runner": t["runner"],
            "installed": tool_available(t),
        }
        for t in TOOL_CATALOGUE
    ]
    return {
        "data_dir": resolve_data_dir(),
        "rk_scan_present": os.path.exists(RK_SCAN_BIN),
        "rk_field_tool_present": os.path.exists(RK_FIELD_TOOL_BIN),
        "networks": [{"iface": i, "cidr": c, "ip": ip} for i, c, ip in list_own_networks()],
        "arp_neighbors": read_local_arp_neighbors(),
        "tools": tools,
        "installed_count": sum(1 for t in tools if t["installed"]),
        "total_count": len(tools),
    }


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "run":
        return run_helper_from_stdin()

    parser = argparse.ArgumentParser(
        description="RK Field Deck safe Scan & diagnostic Arsenal tool runner"
    )
    parser.add_argument("--probe", action="store_true", help="Print installed tools, networks, and neighbors as JSON")
    args = parser.parse_args()
    if args.probe:
        print(json.dumps(probe_environment(), indent=2))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *_: sys.exit(130))
    sys.exit(main())
