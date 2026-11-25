# Handhelds

One image, every RK3326 handheld [arkos4clone](https://github.com/lcdyk0517/arkos4clone) supports: 93 of them. The card holds the boot files of all of them; which one it starts on is chosen on the boot partition (`Choose handheld.command`, or three files copied by hand: see `README.txt` there), or on the handheld with `sudo rk-boot-select set "<folder>" 5.10`.

This table is written by `build/check-consoles.py` from the device trees at the pinned arkos4clone commit (`c462a40`). The build runs the same check on every push: each handheld's boot files, screen, pad and power chip are read and held against what the system expects, and the desktop is drawn at every screen size in the list (1280×720, 1024×768, 720×720, 854×480, 720×540, 800×480, 480×640, 640×480, 480×320).

**Checked is not the same as started.** "On hardware" says where a person has started the image and used it. Everywhere else the files have been checked and nothing more: expect to be the first, and please report.

| Folder | Handheld | Screen | Panel turned | Direction pad | Power chip | Kernels | On hardware |
|---|---|---|---|---|---|---|---|
| `a10mini` | YMC A10Mini | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `a10miniv4` | YMC A10Mini V4 | 720×540 | 180° (720×540 panel) | keys | RK817 | 5.10, 4.4 | not yet |
| `clone type1 panel1` | R36S Clone Type1 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `clone type1 panel1 amp` | R36S Clone Type1 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `clone type1 panel1 invert` | R36S Clone Type1 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `clone type1 panel2` | R36S Clone Type1 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `clone type1 panel3` | R36S Clone Type1 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `clone type1 panel4` | R36S Clone Type1 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `clone type1 panel5` | R36S Clone Type1 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `clone type1 panel5 invert` | R36S Clone Type1 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `clone type1 panel6` | R36S Clone Type1 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `clone type1 panel7` | R36S Clone Type1 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `clone type2 panel1` | R36S Clone Type2 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `clone type2 panel1 amp` | R36S Clone Type2 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `clone type2 panel1 rk809` | R36S Clone Type2 | 640×480 | no | keys | RK809 | 5.10, 4.4 | not yet |
| `clone type2 panel2` | R36S Clone Type2 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `d007` | SZDiiER D007 Plus | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `dc35v` | XiFan DC35V | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `dc40v` | XiFan DC40V | 720×720 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `dc45v` | XiFan DC45V | 1024×768 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `dr28s` | Diium Dr28s | 640×480 | 270° (480×640 panel) | keys | RK817 | 5.10, 4.4 | not yet |
| `g350` | BatleXP G350 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `go2` | Lenovo GO2 | 1024×768 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `h7` | GUSGU H7 | 1024×768 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `hg36` | GameConsole HG36 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `k36` | Kinhank K36 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `k36s` | AISLPC K36S | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `mini40` | XiFan Mini40 | 720×720 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `mymini` | XiFan MyMini | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `o30s` | GameConsole O30S | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `origin panel0` | GameConsole R36S | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `origin panel1` | GameConsole R36S | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `origin panel2` | GameConsole R36S | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `origin panel3` | GameConsole R36S | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `origin panel4 type1` | GameConsole R36S | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `origin panel4 type2` | GameConsole R36S | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `r33s` | GameConsole R33S | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `r36h` | GameConsole R36H | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `r36hpromax` | GameConsole R36H ProMax | 1024×768 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `r36max type1` | XiFan R36Max | 720×720 | no | keys | RK817 | 5.10, 4.4 | yes (R36MAX) |
| `r36max type2` | XiFan R36Max | 720×720 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `r36max type3` | XiFan R36Max | 720×720 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `r36max2` | XiFan R36Max2 | 1024×768 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `r36pro` | XiFan R36Pro | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `r36splus` | GameConsole R36sPlus | 720×720 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `r36t` | AISLPC R36T | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `r36tmax` | AISLPC R36TMax | 720×720 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `r36ultra` | UDT R36Ultra | 720×720 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `r36ultrax` | UDT R36UltraX | 1024×768 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `r36xx` | GameConsole R36XX | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `r40s` | GameConsole R40S | 800×480 | 270° (480×800 panel) | keys | RK817 | 5.10, 4.4 | not yet |
| `r40xx` | GameConsole R40xx | 1024×768 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `r40xxpromax` | GameConsole R40XX ProMax | 1024×768 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `r45h` | GameConsole R45H | 1024×768 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `r46h` | GameConsole R46H | 1024×768 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `r50h` | GameConsole R50H | 1280×720 | 270° (720×1280 panel) | keys | RK817 | 5.10, 4.4 | not yet |
| `r50s` | GameConsole R50S | 854×480 | 270° (480×854 panel) | keys | RK817 | 5.10, 4.4 | not yet |
| `rf35h` | XiFan RF35H | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `rf40h` | XiFan RF40H | 720×720 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `rf45h` | XiFan RF45H | 1024×768 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `rf45v` | XiFan RF45V | 1024×768 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `rf55h` | XiFan RF55H | 1280×720 | 90° (720×1280 panel) | keys | RK817 | 5.10, 4.4 | not yet |
| `rg351mp` | Anbernic RG351MP | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `rg351p` | Anbernic RG351P | 480×320 | 270° (320×480 panel) | hat | RK817 | 5.10, 4.4 | not yet |
| `rg351v panel1` | Anbernic RG351V | 640×480 | no | hat | RK817 | 5.10, 4.4 | not yet |
| `rg351v panel2` | Anbernic RG351V | 640×480 | no | hat | RK817 | 5.10, 4.4 | not yet |
| `rg36` | GameConsole RG36 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `rg36pro` | GameConsole RG36Pro | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `rgb10` | Powkiddy RGB10 | 480×320 | 270° (320×480 panel) | keys | RK817 | 5.10, 4.4 | not yet |
| `rgb10max1` | Powkiddy RGB10MAX1 | 854×480 | 270° (480×854 panel) | keys | RK817 | 5.10, 4.4 | not yet |
| `rgb10max2` | Powkiddy RGB10MAX2 | 854×480 | 270° (480×854 panel) | keys | RK817 | 5.10, 4.4 | not yet |
| `rgb10x` | Powkiddy RGB10X | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `rgb20s` | Powkiddy RGB20S  | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `rgbv10` | Powkiddy RGBV10 | 480×320 | 270° (320×480 panel) | keys | RK817 | 5.10, 4.4 | not yet |
| `rp1` | RetroBox P1 | 480×640 | 270° (640×480 panel) | keys | RK817 | 5.10, 4.4 | not yet |
| `rs16` | CoolBoy RS-16 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `rx6h` | GameConsole RX6H | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `sauce panel1` | GameConsole R36S Soy Sauce Panel 1 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `sauce panel2` | GameConsole R36S Soy Sauce Panel 2 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `sauce panel3` | GameConsole R36S Soy Sauce Panel 3 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `sauce panel4` | GameConsole R36S Soy Sauce Panel 4 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `sauce panel5` | GameConsole R36S Soy Sauce Panel 5 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `t16max` | GameConsole T16Max | 720×720 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `u8 panel1` | GameConsole U8 | 800×480 | 270° (480×800 panel) | keys | RK817 | 5.10, 4.4 | not yet |
| `u8 panel2` | GameConsole U8 | 800×480 | 270° (480×800 panel) | keys | RK817 | 5.10, 4.4 | not yet |
| `v21 panel4 rumble test` | GameConsole R36S | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `xf28` | XiFan XF28 | 640×480 | 90° (480×640 panel) | keys | RK817 | 5.10, 4.4 | not yet |
| `xf35h` | XiFan XF35H | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `xf40h` | XiFan XF40H | 720×720 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `xf40v` | XiFan XF40V | 720×720 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `xf45v` | XiFan XF45V | 1024×768 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `xgb36` | GameConsole XGB36 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |
| `xu10` | MagicX Xu10 | 640×480 | no | keys | RK817 | 5.10, 4.4 | not yet |

## What is the same on all of them, and what is not

- **Desktop, tools, Terminal, Wi-Fi, updates**: one system, laid out for the screen it finds. A panel mounted on its side is turned the way the kernel is told to turn the text console; if a picture still comes out sideways, a file `rotate.txt` on the boot partition holding 0, 1, 2 or 3 sets it by hand.
- **Buttons**: every handheld in the list reports the same pad with the same button codes. The RG351P and RG351V send their direction pad as a hat; the desktop reads both.
- **Dock apps, Video and Games** draw through the GPU, not through the desktop, and are turned there, the way arkos4clone and dArkOS do it: SDL programs (the dock apps, Video's player) load the SDL2 built for the panel's turn, and Games uses RetroArch's driver for turned RK3326 panels. Both turn the picture with the Rockchip 2D chip (librga). `rotate.txt` sets these too.
- **Sound, charging, brightness**: the fixes in `build/dtb-fixes.txt` are for the R36MAX (type 1) only, found on one. Other handhelds run arkos4clone's device tree as it is.
- **Left-stick pointer**: needs a left stick. Without one the direction pad does everything.
- **Boards on USB serial (ESP32 and the like)**: on kernel 5.10, the chips these boards use all get a serial port (`/dev/ttyUSB0`, or `/dev/ttyACM0`): CP210x, FTDI, PL2303, and the CH340/CH341 of most ESP32 boards (a Freenove ESP32-WROVER, for one). arkos4clone's 5.10 kernel is built without the CH340 driver (`ch341`), so the image adds it, built from that kernel's source (`build/kernel-modules.env`). A flashed image has it; a card that is updated takes it from the release after **Update this handheld** (or `sudo rk-tools kernel-modules`), which adds the module and replaces none of the kernel's files. On the 4.4 fallback kernel a CH340 board gets no serial port; the Provisioner still reaches it there, driving the chip itself.
