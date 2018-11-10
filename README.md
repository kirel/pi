# README

    pipenv install
    pipenv shell
    ansible-playbook setup.yml

Passwords generated with

    python -c "from passlib.hash import sha512_crypt; import getpass; print(sha512_crypt.using(rounds=5000).hash(getpass.getpass()))"
