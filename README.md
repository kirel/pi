# README

## Pi from scratch

1. Follow https://www.raspberrypi.org/documentation/installation/installing-images/
2. `touch /Volumes/boot/ssh`
3. `scp ~/.ssh/id_rsa.pub pi@pi:~/.ssh/authorized_keys`
4. `ssh pi@pi`

## Setup

    pipenv install
    pipenv shell
    ansible-playbook setup.yml

Passwords generated with

    python -c "from passlib.hash import sha512_crypt; import getpass; print(sha512_crypt.using(rounds=5000).hash(getpass.getpass()))"
