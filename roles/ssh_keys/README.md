# SSH Keys Role

This Ansible role generates an SSH key pair on a designated source host and distributes the public key to all hosts in the inventory. The public key is automatically added to the user specified as `ansible_user` in the inventory file for each host.

## Overview

The role performs the following operations:

1. **Key Generation**: Generates an RSA 4096-bit SSH key pair on the source host for the specified source user
2. **Key Distribution**: Reads the public key and distributes it to all target hosts
3. **Authorization**: Adds the public key to the `authorized_keys` file for each host's `ansible_user`
4. **Permissions**: Sets proper permissions on SSH directories and files

## Role Variables

### Required Variables

These variables should be set when including the role:

- **`source_host`**: The host where the SSH key pair should be generated
- **`source_user`**: The user on the source host for whom the SSH key will be generated

### Default Variables (in `defaults/main.yml`)

```yaml
source_host: ailab-ubuntu
source_user: daniel
```

## Usage

### In setup.yml

Add the role to your playbook:

```yaml
- name: Setup SSH key distribution
  hosts: ailab_ubuntus,homelab,nameserver,proxmox,mic_satellites
  ignore_unreachable: true
  vars:
    source_host: ailab-ubuntu
    source_user: daniel
  roles:
    - { role: ssh_keys, become: true, tags: [ssh-keys] }
```

### Running the Role

```bash
# Run the full playbook
uv run ansible-playbook setup.yml --tags ssh-keys

# Dry run to see what would happen
uv run ansible-playbook setup.yml --tags ssh-keys --check --diff

# Run on specific hosts
uv run ansible-playbook setup.yml --tags ssh-keys --limit homelab
```

## How It Works

1. The role generates an SSH key pair (if it doesn't already exist) on the `source_host` for the `source_user`
2. The public key is read from the source host
3. For each target host in the play, the public key is added to the `authorized_keys` file of the user specified as `ansible_user` in the inventory
4. Proper permissions are set on SSH directories and files (700 for `.ssh`, 600 for `authorized_keys`)

## Inventory Example

The role works with any inventory configuration. Here's an example from the project's inventory:

```ini
[nameserver]
nameserver-pi ansible_host=192.168.50.4 ansible_user=pi

[homelab]
homelab-nuc ansible_host=192.168.50.5 ansible_user=root

[ailab_ubuntus]
ailab-ubuntu ansible_host=192.168.50.10 ansible_user=daniel
```

The role will:
- Generate the key on `ailab-ubuntu` for user `daniel`
- Add the public key to:
  - User `pi` on `nameserver-pi`
  - User `root` on `homelab-nuc`
  - User `daniel` on `ailab-ubuntu` (self)

## Verification

After running the role, you can verify the SSH key distribution by:

1. SSH to the source host:
   ```bash
   ssh {{ source_user }}@{{ source_host }}
   ```

2. From there, SSH to any target host (no password required):
   ```bash
   ssh {{ ansible_user }}@<target-host>
   ```

3. View the authorized keys on any host:
   ```bash
   cat ~/.ssh/authorized_keys
   ```

## Requirements

- Ansible 2.0 or higher
- The `openssh_keypair` module (included in Ansible core)
- `become: true` for file operations and SSH key management

## Security Notes

- The role generates RSA 4096-bit SSH keys (strong encryption)
- Private keys are never transmitted or logged
- Proper file permissions are enforced (700 for `.ssh`, 600 for `authorized_keys`)
- Only the public key is distributed to remote hosts

## Customization

You can customize the role by:

1. **Changing key type/size**: Edit `roles/ssh_keys/tasks/main.yml` and modify the `openssh_keypair` parameters
2. **Adding to multiple users**: Modify the tasks to add keys to additional users on each host
3. **Restricting hosts**: Change the `hosts:` directive in the playbook to limit which hosts receive the key

## Troubleshooting

### Key already exists

The role checks if the key exists before generating a new one. If you want to force regeneration, manually delete the key files on the source host:

```bash
rm -f /home/{{ source_user }}/.ssh/id_rsa*
```

### Permission denied after deployment

Ensure that:
1. The `ansible_user` exists on each target host
2. File permissions are correct (the role sets these automatically)
3. SELinux/AppArmor is not blocking SSH access (if applicable)

### Host unreachable

The playbook uses `ignore_unreachable: true` to continue if some hosts are offline. The SSH key will be added to all reachable hosts.
