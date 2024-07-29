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

    pipenv run ansible-playbook prep_pi.yml

## Bootstrap the Homelab Server

TODO https://github.com/coreprocess/linux-unattended-installation

## Setup

    pipenv install
    pipenv shell # optional
    pipenv run ansible-galaxy install --force-with-deps -r requirements.yml
    pipenv run ansible-playbook setup.yml # Update everything
    pipenv run ansible-playbook setup.yml --tags ha # Update smart home
    pipenv run ansible-playbook setup.yml --tags ollama # Update smart home 
    pipenv run ansible-playbook setup.yml --tags caddy,pihole,homepage --limit homelab,nameserver # update dhcp, domains etc.
    pipenv run ansible-playbook setup.yml --limit virtualhere

Edit secrets

    pipenv run ansible-vault edit group_vars/all/secrets.yml

Configure pihole password

    ssh pi4
    sudo docker exec -it pihole pihole -a -p

Copy the `root.cert` from `{{caddy_folder}}` to all the devices and trust it
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

    pipenv run ansible-playbook fix_hass_bluetooth.yml

### Ring breaks:

Probably the token has expired. Regenerate it with:
```
ssh nuc
HOST_PATH=/home/nuc/config/ring-mqtt/
docker run -it --rm --mount type=bind,source=$HOST_PATH,target=/data --entrypoint /app/ring-mqtt/init-ring-mqtt.js tsightler/ring-mqtt
docker restart ring-mqtt
```
TODO: create ansible script