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
    pipenv shell
    ansible-playbook setup.yml

Passwords generated with

    python -c "from passlib.hash import sha512_crypt; import getpass; print(sha512_crypt.using(rounds=5000).hash(getpass.getpass()))"
