# Ansible Homelab TODO List

This list tracks suggested improvements and refactoring tasks for the Ansible configuration based on recent analysis.

## High Priority

1.  **Refactor Variable Scoping (`group_vars`)**
    *   [ ] Move service-specific ports and filesystem paths (most of `Service Ports` and `Filesystem Paths` sections, including `config_root`) from `group_vars/all/config.yml` to `group_vars/homelab.yml`.
    *   [ ] Define `pihole_config_folder` and `dnsmasq_config_folder` explicitly in both `group_vars/homelab.yml` and `group_vars/nameserver.yml` using the appropriate `username` for each group.
    *   [ ] Correct `mosquitto_address` in `group_vars/all/config.yml` to point to the actual broker IP (likely `{{ hostvars['homelab-nuc'].ansible_host }}`) instead of `{{ ansible_default_ipv4.address }}`.
    *   [ ] Move `username_personal` and `uid_personal` from `group_vars/all/config.yml` to a more specific scope (relevant group/host vars or role vars) where the "daniel" user is actually managed.
    *   [ ] Review `username` definition and usage. Ensure it's defined where needed (e.g., `group_vars/nameserver.yml`, `group_vars/homelab.yml`) and that variables like `config_root` resolve correctly on all relevant hosts. Consider using `ansible_user` if appropriate.
    *   [ ] Replace hardcoded `sunshine_address` in `group_vars/all/config.yml` with `hostvars` if the host is managed by Ansible.

2.  **Refactor `setup.yml` (DRY)**
    *   [ ] Reduce role repetition across different plays (homelab, nameserver, etc.). Choose one method:
        *   Create a meta-group (e.g., `[all_docker_hosts:children]`) in the `inventory` and a single play targeting this group for common roles (`basic`, `docker`, `dockerproxy`, `glances`, `trust-internal-ca`, etc.).
        *   *OR* Create a `common-setup` role that includes the common roles, and apply this `common-setup` role in each play.

3.  **Automate Manual Steps from `README.md`**
    *   [ ] Automate Pi-hole whitelist/referral script execution (`whitelist.py`, `referral.sh`) within the `pihole` role (using `git` and `command`/`script` modules).
    *   [ ] Automate Ring MQTT token refresh process (create an Ansible task or a dedicated playbook `refresh_ring_token.yml`).
    *   [ ] Investigate automating Pi-hole password setting (potentially via environment variables during container creation or `community.docker.docker_container_exec`).

## Medium Priority

4.  **Address `README.md` TODOs**
    *   [ ] Investigate unattended installation for Homelab Server.
    *   [ ] Ensure both DNS servers are advertised correctly (DHCP config?).
    *   [ ] Create `migrate.yml` playbook if migration is a recurring task.

5.  **Add Role Defaults**
    *   [ ] Review custom roles (e.g., `caddy`, `pihole`, `homeassistant`, etc.) and add `defaults/main.yml` files defining default values for variables used within the roles.

6.  **Clean Up**
    *   [ ] Remove commented-out `virtualhere` host from `inventory` and `group_vars/all/config.yml` if it's permanently unused.
    *   [ ] Remove `nextcloud_data_folder` from `group_vars/all/config.yml` if the Nextcloud service is not being used/deployed.

## Low Priority / Consider

7.  **Implement Linting/Testing**
    *   [x] Add `ansible-lint` to the project and fix reported issues (via pre-commit).
    *   [x] Add `yamllint` for consistent YAML formatting (via pre-commit).
    *   [ ] Consider `molecule` for role testing if roles are intended to be highly reusable or complex.

8.  **Review Role Granularity**
    *   [ ] Evaluate if large roles like `media`, `monitoring`, `basic`, `nuc`, `pi` could be beneficially split into smaller, more focused roles. (Requires deeper analysis of role tasks).

9.  **Review `setup.yml` Role Variables**
    *   [ ] Move `vars: { docker_install_compose: true }` from `setup.yml` into the appropriate `group_vars` file(s) if the setting applies consistently to the group(s) where the `geerlingguy.docker` role is used.
