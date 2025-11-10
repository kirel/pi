# README

This is my homelab config. The repo is called `pi` because it started as a single pi. It's now:

- 192.168.50.4 is a pihole that acts as DHCP and DNS Server (and Adblocker)
- 192.168.50.5 is a mini PC (right now an intel NUC) running Ubuntu as a Docker Host - all services are run as Containers (inc a pihole backup)
- 192.168.50.6 tbd another mini PC

## Bootstrap the Pi

1. Download the pi imager at https://www.raspberrypi.com/software/
2. Select Pi OS Lite 64 bit
3. Set hostname to pihole.local
4. activate ssh, and paste `cat ~/.ssh/id_rsa.pub | pbcopy` into the public key field
5. ~Set username and password~
6. Set language settings to Berlin timezone and us keyboard
7. Write the image
8. Eject and reinsert the memory card

    uv run ansible-playbook prep_pi.yml

## Bootstrap the Homelab Server

TODO https://github.com/coreprocess/linux-unattended-installation

## Setup

### Basic Setup

    # Install dependencies using uv
    uv pip sync
    # Install Ansible Galaxy roles
    uv run ansible-galaxy install --force-with-deps -r requirements.yml

### Everything

    uv run ansible-playbook setup.yml # Update everything

### DNS etc

    uv run ansible-playbook setup.yml --tags caddy,pihole,homepage --limit homelab,nameserver # update dhcp, domains etc.

### Home Assistant

    uv run ansible-playbook setup.yml --tags ha # Update smart home
    uv run ansible-playbook setup.yml --tags ollama # Update ollama

    uv run ansible-playbook setup.yml --limit mic-satellites -t satellite-audio
    uv run ansible-playbook setup.yml --limit mic-satellites -t wyoming --start-at-task="Start wyoming stack"

### Virtualhere

    uv run ansible-playbook setup.yml --limit virtualhere

### Ailab

    ansible-playbook setup.yml --limit ailab

### AI Lab - LlamaSwap (llama.cpp)

**LlamaSwap** - A lightweight llama.cpp server running Qwen3-VL-8B-Instruct-GGUF with GPU acceleration
- **Context Size:** 92,375 tokens (maximum that fits in RTX 3090 24GB VRAM)
- **Model:** Qwen3-VL-8B-Instruct-GGUF Q8_K_XL from Unsloth
- **URL:** http://ailab-ubuntu.lan:9292 or https://llama-swap.lan
- **WebUI:** http://ailab-ubuntu.lan:9292/ui
- **Context Testing:** 92,000-92,375 tokens work, 92,500+ causes OOM

Deploy/update:
```bash
uv run ansible-playbook setup.yml --tags llm-inference --limit ailab-ubuntu
```

Note: After adding services, remember to redeploy Caddy and Pi-hole:
```bash
uv run ansible-playbook setup.yml --tags caddy --limit homelab
uv run ansible-playbook setup.yml --tags pihole --limit nameserver
```

## Secrets

Edit secrets

    uv run ansible-vault edit group_vars/all/secrets.yml

Configure pihole password

    ssh pi4
    sudo docker exec -it pihole pihole -a -p

Copy the `root.cert` from `{{ caddy_folder }}` to all the devices and trust it
- https://support.apple.com/en-us/HT204477
- https://httptoolkit.tech/blog/android-11-trust-ca-certificates/

    scp nuc:/home/nuc/config/caddy/root.crt tmp/

## Manual router setup

1. Turn DHCP off. Pihole and pihole-homelab take over.
2. ...
3. Profit

## Pihole whitelist

    ssh nuc
    cd /home/nuc
    git clone https://github.com/anudeepND/whitelist.git
    sudo python3 whitelist/scripts/whitelist.py --dir /home/pi/config/pihole/ --docker
    sudo whitelist/scripts/referral.sh --dir /home/pi/config/pihole/ --docker

## Migrate

    ssh -A pi@192.168.50.5 sudo rsync -e "ssh" -vuar /media/Medien/{pihole,home-assistant,caddy,mosquitto,vscode,z2m} root@192.168.50.3:/home/nuc/config/
    ssh root@192.168.50.3 sudo chown -R nuc:nuc /home/nuc/config
    ssh root@192.168.50.3 .cargo/bin/exa -l --tree --level=2 /home/nuc/config/

TODO create ansible script and make it work for both pihole and homelab.

## Open items

1. advertise both DNS servers!

## Troubleshooting

### Fix bluetooth

    uv run ansible-playbook fix_hass_bluetooth.yml

### Ring breaks:

Probably the token has expired. Regenerate it with:
```
ssh nuc
HOST_PATH=/home/nuc/config/ring-mqtt/
docker run -it --rm --mount type=bind,source=$HOST_PATH,target=/data --entrypoint /app/ring-mqtt/init-ring-mqtt.js tsightler/ring-mqtt
docker restart ring-mqtt
```
TODO: create ansible script

## Satellites

    uv run ansible-playbook setup.yml -l mic-satellites -t alsa,pulse
    uv run ansible-playbook setup.yml -l mic-satellites -t stack
    uv run ansible-playbook setup.yml -l mic-satellites -t vis

### Test audio

    ssh micpi pactl set-sink-volume @DEFAULT_SINK@ 80%
    ssh micpi amixer set Master 90%
    ssh micpi dmesg


    ssh micpi 'TERM=xterm vis'
    ssh micpi "aplay -D plughw:0,0 /usr/share/sounds/alsa/Front_Center.wav"
    ssh micpi "paplay /usr/share/sounds/alsa/Front_Center.wav"
    ssh micpi sudo docker exec wyoming-snd-external-alexa aplay /usr/share/sounds/alsa/Front_Center.wav

    ssh micpi "sudo systemctl status pulseaudio"
    ssh micpi "sudo systemctl restart pulseaudio"
    ssh micpi "sudo systemctl stop pulseaudio"
    ssh micpi "journalctl -xeu pulseaudio.service"
    ssh micpi "pactl info"
    ssh micpi "pactl list short sinks"
    ssh micpi "pactl list short sources"


## Debug wyoming

    osascript <<EOF
    tell application "iTerm2"
         create window with default profile
         tell current session of current window
              delay 1
              write text "zellij"
          end tell
    end tell
EOF

    zellij run -- ssh micpi sudo docker logs -f wyoming-snd-external-alexa
    zellij run -- ssh micpi sudo docker logs -f wyoming-mic-external-alexa
    zellij run -- ssh root@homelab-nuc.lan sudo docker logs -f wyoming-satellite-alexa
    zellij run -- ssh root@homelab-nuc.lan sudo docker logs -f wyoming-porcupine1
    zellij run -- ssh micpi tail -f /var/log/jabra_connected.log

## Reset some things

    ssh micpi "sudo wget -O /boot/firmware/config.txt https://raw.githubusercontent.com/RPi-Distro/pi-gen/refs/heads/master/stage1/00-boot-files/files/config.txt"

    ssh micpi "sudo rm -rf /etc/pulse && sudo apt -y purge pulseaudio pulseaudio-utils && sudo apt -y autoremove"
