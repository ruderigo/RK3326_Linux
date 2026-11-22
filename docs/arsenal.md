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
- **Wi-Fi**: aircrack-ng, reaver, bully, mdk4, wifite, hcxdumptool,
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

## kismet

kismet is not in the Debian archive and needs its own repository, so it is
not baked in. To add it, follow the instructions at
[kismetwireless.net](https://www.kismetwireless.net/packages/), then it
appears on the Terminal like the rest.

## Wi-Fi monitor mode and a USB adapter

The onboard radio connects to networks but cannot audit them: it has no
monitor mode and no packet injection. That is a property of the chip's
firmware, not of the kernel, and it is the same on every RK3326 handheld,
Kali included on hardware with a client-only card. So Wi-Fi testing is done
through a USB adapter whose chipset supports those modes, exactly as it is on
a laptop whose built-in card cannot.

Both kernels here already carry the common adapter drivers (ath9k_htc, mt76,
the rt2x00 family, rtl8xxxu, and the out-of-tree Realtek set that covers
8812au / 8814au / 8188eu), so a supported adapter works without building
anything. The **Arsenal** window shows a readiness line above the Wi-Fi
group:

- *Onboard radio is client-only* — no adapter plugged in. Client Wi-Fi works;
  auditing does not.
- *<driver> is plugged in but does not report monitor mode* — the adapter was
  seen but its driver advertises no monitor mode. Try a different adapter or
  driver.
- *Ready: <driver> reports monitor mode* — the adapter can enter monitor mode.
  Monitor mode is what `iw` reports; **injection is separate and only a real
  test confirms it**, so verify injection on your own networks before relying
  on it.

Known-good chipsets for monitor mode and injection on these kernels include
the Atheros AR9271 (ath9k_htc), Ralink RT3070 / RT5370 (rt2800usb), MediaTek
MT7601U / MT7612U (mt76), and the Realtek RTL8812AU. Check readiness on the
device rather than trusting a label: the Arsenal line reads the adapter that
is actually plugged in.

## Running them

Everything runs from the **Terminal**. A USB keyboard helps with the big
keyboard-driven tools. Reports you save elsewhere in the desktop land in
`/data/ark`, which the **Files** window shows.
