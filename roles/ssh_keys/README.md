# SSH Keys Role

This legacy Ansible role generates an SSH key pair on a designated source host and distributes the public key to the `ansible_user` on each target host in the play.

> Status: legacy single-actor helper. For new automation-user work, prefer the `ops`/managed-users plan in `docs/ops-user-migration.md` instead of adding more behavior here.

## What it does

1. Generates `/home/{{ source_user }}/.ssh/id_rsa` on `source_host` if it does not exist.
2. Reads the public key from `source_host`.
3. Adds that public key to `authorized_keys` for each target host's current `ansible_user`.
4. Ensures `.ssh` and `authorized_keys` permissions for that user.
5. Optionally creates and authorizes additional source keys listed in
   `ssh_keys_additional_sources`; private keys remain on their source hosts.

## Defaults

```yaml
source_host: ailab-ubuntu
source_user: daniel
ssh_keys_additional_sources: []
```

The backup NAS also accepts a dedicated NUC key through this role:

```yaml
ssh_keys_additional_sources:
  - host: homelab-nuc
    user: root
    home: /root
    key: /root/.ssh/backupnas_ed25519
```

Additional keys default to Ed25519 and existing keys are never regenerated.
Additional entries can set `target_user` and `key_options` for an existing
service account. For example, the offsite backup entry targets OMV's `borg`
account with `restrict,command="/usr/local/sbin/borg-offsite-serve"`. Account
creation belongs to the OMV repository role; this role only manages keys.
Without `target_user`, access goes to the inventory user.
The NAS role separately configures SSH aliases and pins
the NAS host key, but does not generate or authorize client keys.

## Current playbook usage

`setup.yml` contains a dedicated SSH key distribution play:

```yaml
- name: Setup SSH key distribution
  hosts: ailab_ubuntus,homelab,nameserver,hetzner,mic_satellites,backup_nas
  ignore_unreachable: true
  vars:
    source_host: ailab-ubuntu
    source_user: daniel
  roles:
    - { role: ssh_keys, become: true, tags: [ssh-keys] }
```

`mic_satellites` is still referenced by the play, but the current checked-in `inventory` does not define that group, so Ansible warns and ignores it.

## Current inventory users

From the checked-in inventory, the relevant targets resolve to:

```ini
[nameserver]
nameserver-pi ansible_host=192.168.50.4 ansible_user=daniel

[homelab]
homelab-nuc ansible_host=192.168.50.5 ansible_user=root

[ailab_ubuntus]
ailab-ubuntu ansible_host=192.168.50.10 ansible_user=daniel

[hetzner]
ubuntu-8gb-fsn1-1 ansible_host=100.82.91.51 ansible_user=daniel
```

So the default run generates the key for `daniel@ailab-ubuntu` and installs it for `daniel` on `nameserver-pi`, `ailab-ubuntu`, and `ubuntu-8gb-fsn1-1`, plus `root` on `homelab-nuc`.

## Running

```bash
uv run ansible-playbook setup.yml --tags ssh-keys
uv run ansible-playbook setup.yml --tags ssh-keys --check --diff
uv run ansible-playbook setup.yml --tags ssh-keys --limit homelab
```

## Verification

From the source host:

```bash
ssh daniel@ailab-ubuntu
ssh <ansible_user>@<target-host>
```

On a target host, inspect the target user's keys:

```bash
sudo -u <ansible_user> cat ~/.ssh/authorized_keys
```

## Caveats

- The role adds keys with `exclusive: false`; it does not prune stale keys.
- The primary source key targets `ansible_user`; optional additional keys can target an existing service account. This role does not manage account lifecycle.
- Private keys are generated only on `source_host` and are not copied by this role.
