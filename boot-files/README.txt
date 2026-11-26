RK3326 Linux - boot partition

Before the first start
  1. Open wifi.txt, fill in SSID and PASSWORD, save.
     Open it again to check that your two lines are there: a text editor
     that saves in another format leaves the file as it was.
  2. Optional: put your SSH public key(s) in a file named authorized_keys here.
  3. Eject the card, put it in the handheld, switch on.

First start
  The first start takes a minute longer: the card gets its own SSH keys, a
  data partition, and RKSHARE, a partition your computer can read.

Games and apps
  Not here. After the first start, put the card back in the computer: a
  second disk named RKSHARE shows up beside this one. Games go in its
  roms folder, BIOS files in roms/bios, app packages (.zip) in packages.
  Only BOOT shows up? The card was set up before RKSHARE existed. On the
  handheld: Settings, "Show the card on a computer".

Log in over SSH
  ssh ark@HOSTNAME.local        (HOSTNAME is in hostname.txt on this partition)
  If SSH says the host identification has changed (the same name was used
  by another card), run:  ssh-keygen -R HOSTNAME.local
  No answer at all: the login screen shows the Wi-Fi address; empty means
  the handheld did not join. With a USB keyboard, log in on the handheld:
    nmcli dev wifi list
    sudo nmcli dev wifi connect "Network name" password "the password"
  The first password is: ark    You are asked to change it at the first login.

If it does not start (black screen, or it stops)
  This card starts the 5.10 kernel. The older 4.4 kernel is in the folder
  fallback-4.4. Copy the three files in that folder to the top of this
  partition, replacing the ones there, and start again.
  To go back, do the same with the folder default-5.10.

Another handheld (any RK3326 handheld arkos4clone supports)
  This card starts on the handheld named in rk-device.txt. The boot files of
  all the others are in consoles/, one folder each.
  Mac or Linux: run "Choose handheld.command" on this partition and pick
  yours from the list.
  Windows, or by hand: copy three files to the top of this partition,
  replacing the ones there (delete the old .dtb file):
    consoles/<your handheld>/boot.ini
    consoles/<your handheld>/5.10/<name>.dtb      and  consoles/kernel/5.10/Image
  or, for the 4.4 kernel:
    consoles/<your handheld>/<name>.dtb           and  consoles/kernel/original/Image
  Not sure which folder is yours: arkos4clone's DTB Analysis Tool tells you
  (https://github.com/lcdyk0517/arkos4clone). The wrong one usually gives a
  black or sideways screen, or buttons that do nothing; choose again.
  On the handheld itself:  sudo rk-boot-select list   and   set "<name>" 5.10
  Screen sideways or upside down: put a file rotate.txt here holding one
  number, 0, 1, 2 or 3 (quarter turns), and start again.

Your own picture at switch-on
  Replace logo.bmp here. Only one kind of file is shown: a BMP, 24 bits,
  not compressed, exactly the size of the screen in pixels (720 x 720 on an
  R36MAX, 640 x 480 on an R36S). A JPG or PNG, or another size, shows
  nothing. Choosing another handheld puts the stock picture back.

Files here
  boot.ini, Image, *.dtb, logo.bmp   what the handheld starts
  consoles/                          boot files for every supported handheld
  Choose handheld.command            picks one of them (Mac, Linux)
  rk-device.txt                      the handheld and kernel selected
  wifi.txt, authorized_keys          settings read at every start
