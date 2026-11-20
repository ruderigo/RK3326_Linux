"""A scan, described as a loadout, and the nmap command it stands for.

The desktop builds the description (a small dict) with the gamepad, shows the
command it stands for, and hands it to rk-scan, which runs nmap as root.
rk-scan imports this same module, so the command shown is the command run,
and nothing reaches nmap that this module did not put there: no option of
nmap's own can be passed in a target (one could make root write a file or
run a script).

  target     addresses, names, ranges or networks, separated by spaces
  mode       "sweep" (who is there)  or  "ports" (what they offer)
  ports      "top100" | "top1000" | "all" | a list such as "22,80,8000-8100"
  technique  "syn" | "connect" | "udp"
  versions   True: ask each open port what it is running
  os         True: guess the operating system
  scripts    "none" | "default" | "safe" | "discovery"
  timing     2 (slow and quiet) to 5 (as fast as it goes)
  noping     True: treat every target as up, without asking first
"""
import re

DEFAULT = {"target": "", "mode": "ports", "ports": "top100", "technique": "syn", "versions": False, "os": False,
           "scripts": "none", "timing": 4, "noping": False}

# what the gamepad cycles through, with a short name for the screen
ABILITIES = [
    ("mode", "Mission", [("sweep", "Sweep: who is there"), ("ports", "Probe: what they offer")]),
    ("ports", "Ports", [("top100", "Top 100"), ("top1000", "Top 1000"), ("all", "All 65535")]),
    ("technique", "Technique", [("syn", "SYN (half-open)"), ("connect", "Connect (full)"), ("udp", "UDP")]),
    ("versions", "Versions", [(False, "Off"), (True, "On")]),
    ("os", "OS guess", [(False, "Off"), (True, "On")]),
    ("scripts", "Scripts", [("none", "None"), ("default", "Default"), ("safe", "Safe"), ("discovery", "Discovery")]),
    ("timing", "Speed", [(2, "T2 Polite"), (3, "T3 Normal"), (4, "T4 Fast"), (5, "T5 Insane")]),
    ("noping", "Skip the ping", [(False, "Off"), (True, "On")]),
]
PRESETS = [
    ("Quick look", {"mode": "ports", "ports": "top100", "technique": "syn", "timing": 4}),
    ("Sweep", {"mode": "sweep", "timing": 4}),
    ("Identify", {"mode": "ports", "ports": "top1000", "technique": "syn", "versions": True, "os": True, "timing": 4}),
    ("Quiet", {"mode": "ports", "ports": "top100", "technique": "syn", "timing": 2}),
    ("Everything", {"mode": "ports", "ports": "all", "technique": "syn", "versions": True, "os": True,
                    "scripts": "default", "timing": 4}),
]
# rough guides for the two gauges: (time, noise) each option adds
COST = {("mode", "sweep"): (1, 1), ("ports", "top100"): (1, 1), ("ports", "top1000"): (2, 2), ("ports", "all"): (5, 3),
        ("technique", "connect"): (0, 1), ("technique", "udp"): (4, 0), ("versions", True): (2, 1), ("os", True): (1, 1),
        ("scripts", "default"): (2, 2), ("scripts", "safe"): (3, 2), ("scripts", "discovery"): (2, 2),
        ("timing", 2): (4, -2), ("timing", 3): (1, -1), ("timing", 5): (-1, 2), ("noping", True): (1, 0)}

TARGET_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.:/_-]*$")
PORTS_OK = re.compile(r"^[0-9]{1,5}(-[0-9]{1,5})?(,[0-9]{1,5}(-[0-9]{1,5})?)*$")


def preset(name, target=""):
    spec = dict(DEFAULT, target=target)
    spec.update(dict(PRESETS)[name])
    return spec


def problem(spec):
    """Why this spec cannot be run, in words for the screen; "" when it can."""
    targets = str(spec.get("target", "")).split()
    if not targets:
        return "Choose a target first"
    if len(targets) > 16:
        return "Too many targets"
    for t in targets:
        if len(t) > 100 or not TARGET_OK.match(t):
            return f"Not a valid target: {t[:40]}"
    if spec.get("mode") not in ("sweep", "ports"):
        return "Unknown mission"
    p = spec.get("ports")
    if p not in ("top100", "top1000", "all") and not (isinstance(p, str) and len(p) <= 200 and PORTS_OK.match(p)):
        return "Not a valid list of ports"
    if spec.get("technique") not in ("syn", "connect", "udp"):
        return "Unknown technique"
    if spec.get("scripts") not in ("none", "default", "safe", "discovery"):
        return "Unknown script pack"
    if spec.get("timing") not in (2, 3, 4, 5):
        return "Unknown speed"
    for k in ("versions", "os", "noping"):
        if not isinstance(spec.get(k), bool):
            return f"Bad value for {k}"
    return ""


def command(spec):
    """The nmap command for a valid spec, as a list. Output options are added by rk-scan."""
    if problem(spec):
        raise ValueError(problem(spec))
    cmd = ["nmap", f"-T{spec['timing']}"]
    if spec["noping"]:
        cmd.append("-Pn")
    if spec["mode"] == "sweep":
        cmd.append("-sn")
    else:
        cmd.append({"syn": "-sS", "connect": "-sT", "udp": "-sU"}[spec["technique"]])
        if spec["ports"] == "top100":
            cmd.append("-F")
        elif spec["ports"] == "all":
            cmd.append("-p-")
        elif spec["ports"] != "top1000":
            cmd += ["-p", spec["ports"]]
        if spec["versions"]:
            cmd.append("-sV")
        if spec["scripts"] != "none":
            cmd.append(f"--script={spec['scripts']}")
    if spec["os"] and spec["mode"] == "ports":
        cmd.append("-O")
    return cmd + spec["target"].split()


def applies(key, spec):
    """False for an ability that does nothing in this mission (shown dimmed)."""
    return spec["mode"] == "ports" or key in ("mode", "timing", "noping")


def cost(spec):
    """(time, noise), each 0..1, as rough guides for the gauges."""
    t = n = 0
    for key, _, _ in ABILITIES:
        if applies(key, spec):
            dt, dn = COST.get((key, spec[key]), (0, 0))
            t, n = t + dt, n + dn
    hosts = 1
    for target in spec["target"].split():
        m = re.search(r"/(\d+)$", target)
        if m and int(m.group(1)) < 32:
            hosts = max(hosts, 2 ** (32 - int(m.group(1))))
    if hosts > 1:
        t += 1 if hosts <= 256 else 3
        n += 1
    return max(0.05, min(1.0, t / 12)), max(0.05, min(1.0, n / 9))
