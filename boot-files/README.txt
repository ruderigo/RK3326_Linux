RK3326 Linux - boot partition

Before the first start
  1. Open wifi.txt, fill in SSID and PASSWORD, save.
     Open it again to check that your two lines are there: a text editor
     that saves in another format leaves the file as it was.
  2. Optional: put your SSH public key(s) in a file named authorized_keys here.
  3. Eject the card, put it in the handheld, switch on.

First start
  The first start takes a minute longer: the card gets its own SSH keys and
  a data partition that fills the rest of the card.

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

Files here
  boot.ini, Image, *.dtb, logo.bmp   what the handheld starts
  consoles/                          boot files for every supported handheld
  rk-device.txt                      the handheld and kernel selected
  wifi.txt, authorized_keys          settings read at every start
