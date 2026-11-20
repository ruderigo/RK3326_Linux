# The Arsenal

A Kali-style toolset on the handheld, for testing machines that are yours or
that you have been asked to test. It comes in two parts.

## Light tools — in the image

Installed when the card is built (`build/packages-tools.txt`), so they are
there the moment you boot. A tool the Debian arm64 archive does not carry is
skipped at build time; the build log lists any that were skipped.

- **Seeing the traffic**: tcpdump, tshark, termshark, ngrep, iftop,
  iptraf-ng, tcpflow
- **The network around you**: arp-scan, netdiscover, masscan, nbtscan,
  fping, hping3, netcat, socat, sslscan, whois, dnsutils, dnsrecon, dnsenum,
  fierce, snmp, smbclient
- **Web servers and apps**: nikto, whatweb, wafw00f, dirb, gobuster, ffuf,
  wfuzz, sqlmap, httpie
- **Wi-Fi**: aircrack-ng, reaver, bully, mdk4, wifite, kismet, hcxdumptool,
  macchanger
- **In the middle**: ettercap, proxychains

## Heavy tools — fetched on first online boot

Metasploit (about a gigabyte with its Ruby stack) and a local copy of
Exploit-DB are too big to flash, so they are pulled when you ask. In
**Arsenal**, press **X** while on Wi-Fi; `rk-tools install-heavy` does it:
Metasploit into the system, Exploit-DB into `/data/opt/exploitdb` with
`searchsploit` on the path.

### If the automatic fetch has no build for this CPU

`rk-tools` uses Rapid7's package repository. If it has no `arm64` build, the
fetch stops cleanly and nothing is left half-installed. You can then install
Metasploit from the Kali repository by hand, in the Terminal:

    curl -fsSL https://archive.kali.org/archive-key.asc | sudo gpg --dearmor -o /usr/share/keyrings/kali.gpg
    echo "deb [signed-by=/usr/share/keyrings/kali.gpg] http://http.kali.org/kali kali-rolling main" | sudo tee /etc/apt/sources.list.d/kali.list
    sudo apt-get update
    sudo apt-get install -y metasploit-framework
    sudo rm /etc/apt/sources.list.d/kali.list && sudo apt-get update

Removing the Kali list afterwards keeps the rest of the system on Debian.

## Wi-Fi monitor mode

The Wi-Fi tools need a dongle that can enter monitor mode and, for some,
inject packets. The Blueway RT3070 dongle lists monitor mode; injection has
not been confirmed on this hardware yet. Until that is tested, treat the
Wi-Fi group as present but unproven on the handheld.

## Running them

Everything runs from the **Terminal**. A USB keyboard helps with the big
keyboard-driven tools. Reports you save elsewhere in the desktop land in
`/data/ark`, which the **Files** window shows.
