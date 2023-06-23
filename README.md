# README

This is my pi config. Time machine and Home Assistant

## Pi from scratch

1. Follow https://www.raspberrypi.org/documentation/installation/installing-images/
2. `touch /Volumes/boot/ssh`
3. `ssh pi@raspberrypi.local "mkdir -p ~/.ssh; chmod 700 ~/.ssh"`
4. `scp ~/.ssh/id_rsa.pub pi@raspberrypi.local:~/.ssh/authorized_keys`
5. `ssh pi@raspberrypi.local`
6. `sudo raspi-config` then change host to pi4 and password
7. reboot

## Setup

    pipenv install
    pipenv shell # optional
    pipenv run ansible-galaxy install --force-with-deps -r requirements.yml
    pipenv run ansible-playbook setup.yml

Edit secrets

    pipenv run ansible-vault edit group_vars/all/secrets.yml

Configure pihole password

    ssh pi4
    sudo docker exec -it pihole pihole -a -p

Copy the `root.cert` from `{{caddy_folder}}` to all the devices and trust it
- https://support.apple.com/en-us/HT204477
- https://httptoolkit.tech/blog/android-11-trust-ca-certificates/

## Pihole whitelist

    ssh nuc
    cd /home/nuc
    git clone https://github.com/anudeepND/whitelist.git
    sudo python3 whitelist/scripts/whitelist.py --dir /home/nuc/config/pihole/ --docker
    sudo whitelist/scripts/referral.sh --dir /home/nuc/config/pihole/ --docker

## Migrate

    ssh -A pi@192.168.50.5 sudo rsync -e "ssh" -vuar /media/Medien/{pihole,home-assistant,caddy,mosquitto,vscode,z2m} root@192.168.50.3:/home/nuc/config/
    ssh root@192.168.50.3 sudo chown -R nuc:nuc /home/nuc/config
    ssh root@192.168.50.3 .cargo/bin/exa -l --tree --level=2 /home/nuc/config/