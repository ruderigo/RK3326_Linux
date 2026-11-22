"""The security toolset, grouped, with the command each one provides and a
line on what it is for. The Arsenal window reads this to show what is on the
handheld; the names line up with build/packages-tools.txt (light tools, baked
in) and rk-tools (the heavy ones, fetched on first online boot).

Each tool is (command, label, about). "command" is what must be on PATH for
the tool to count as installed. Keep the "about" lines plain: what the tool
is, not how to attack with it.
"""

# (title, heavy, [ (command, label, about) ])
CATALOGUE = [
    ("Seeing the traffic", False, [
        ("tcpdump", "tcpdump", "Record and read the packets on a link."),
        ("tshark", "tshark", "Wireshark's engine, on the command line."),
        ("termshark", "termshark", "A Wireshark-like view of a capture, in the terminal."),
        ("ngrep", "ngrep", "grep for network traffic: find packets by their contents."),
        ("iftop", "iftop", "Live list of who is using the bandwidth."),
        ("iptraf-ng", "iptraf-ng", "Live network statistics by connection and interface."),
        ("tcpflow", "tcpflow", "Reassemble a TCP conversation back into its stream."),
    ]),
    ("The network around you", False, [
        ("arp-scan", "arp-scan", "List the machines on the local link from their ARP replies."),
        ("netdiscover", "netdiscover", "Find hosts on a network, passively or by asking."),
        ("masscan", "masscan", "A very fast port scanner for large ranges."),
        ("nbtscan", "nbtscan", "Find Windows names and shares over NetBIOS."),
        ("fping", "fping", "Ping many hosts at once to see who is up."),
        ("hping3", "hping3", "Craft and send custom TCP/IP packets."),
        ("nc", "netcat", "Read and write raw network connections."),
        ("socat", "socat", "Connect, relay and tunnel between sockets and files."),
        ("sslscan", "sslscan", "List the ciphers and certificate of a TLS service."),
        ("whois", "whois", "Who a domain or address is registered to."),
        ("dig", "dnsutils", "Ask the DNS directly (dig, nslookup, host)."),
        ("dnsrecon", "dnsrecon", "Enumerate a domain's DNS records and subdomains."),
        ("dnsenum", "dnsenum", "Gather a domain's DNS information."),
        ("fierce", "fierce", "Find the hosts that belong to a domain."),
        ("snmpwalk", "snmp", "Read a device's SNMP information (snmpwalk, snmpget)."),
        ("smbclient", "smbclient", "Browse Windows and Samba file shares."),
    ]),
    ("Web servers and apps", False, [
        ("nikto", "nikto", "Check a web server for known problems and files."),
        ("whatweb", "whatweb", "Identify what a website is built with."),
        ("wafw00f", "wafw00f", "Detect a web application firewall in front of a site."),
        ("dirb", "dirb", "Look for pages and folders a site does not link to."),
        ("gobuster", "gobuster", "Fast search for hidden paths, subdomains and buckets."),
        ("ffuf", "ffuf", "Fuzz a web app to find parameters and paths."),
        ("wfuzz", "wfuzz", "Another web fuzzer, for parameters and forms."),
        ("sqlmap", "sqlmap", "Test a web app for SQL-injection weaknesses."),
        ("http", "httpie", "A friendly command-line HTTP client."),
    ]),
    ("Wi-Fi (needs a USB adapter; see the line below)", False, [
        ("aircrack-ng", "aircrack-ng", "The classic Wi-Fi assessment suite."),
        ("reaver", "reaver", "Test a router's WPS for the known weakness."),
        ("bully", "bully", "Another WPS testing tool."),
        ("mdk4", "mdk4", "Stress-test and probe Wi-Fi networks."),
        ("wifite", "wifite", "Automate common Wi-Fi assessments."),
        ("hcxdumptool", "hcxdumptool", "Capture material from Wi-Fi for offline analysis."),
        ("macchanger", "macchanger", "Change a network interface's hardware address."),
    ]),
    ("In the middle", False, [
        ("ettercap", "ettercap", "Inspect and intercept traffic on a LAN you control."),
        ("proxychains4", "proxychains", "Send another tool's traffic through a proxy."),
    ]),
    ("Exploitation (heavy; uses a keyboard)", True, [
        ("msfconsole", "Metasploit", "The exploitation framework. Fetched on first online boot."),
        ("searchsploit", "exploitdb", "Search a local copy of Exploit-DB. Fetched with Metasploit."),
    ]),
]

COMMANDS = [(cmd, label, about, heavy) for _, heavy, tools in CATALOGUE for cmd, label, about in tools]


def heavy_commands():
    return [cmd for cmd, _, _, heavy in COMMANDS if heavy]
