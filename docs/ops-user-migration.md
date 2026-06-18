# Ops-User Migration

Stand: 2026-06-18 · Status: **Plan, nicht umgesetzt** · Ziel: sauberer Automation-Pfad für Ansible/Hermes ohne `root`- oder `daniel`-Login als Ziel.

> Dieser Plan ist **Deskription, kein Apply**. Keine Host-Umstellung, kein Playbook-Run ohne
> explizite Freigabe. Erste Schritte sind nur Variablen + Refactor + `--check --diff`.

---

## 1. TL;DR

`ops` als generischer Unix-User ist eine **gute Idee**, weil zwei konkrete Probleme im Repo
damit gelöst werden:

- `homelab-nuc` und `dashserv` nutzen aktuell `ansible_user=root` → root als SSH-Ziel ist ein
  Anti-Pattern.
- `daniel` ist der persönliche Account; Automation über denselben Account vermischt in Logs
  "Daniel war da" mit "ein Agent war da".

`ops` ist dabei **kein** Service-/Config-/Application-User. Es ist ein **leeres Login-Gefäß**:
SSH-Ziel + `sudo`-Recht + Audit-Label. Configs und Daten bleiben Eigentum von
`username`/`username_personal` (`daniel`/`nuc`).

---

## 2. Kernentscheidung: `ops` ist **zwei** Dinge — nur eines zwingend

| | Bedeutung | Empfehlung |
|---|---|---|
| **ops A — Target-User** | `ops` als SSH-Ziel & `become`-User **auf jedem Host** | ✅ **jetzt machen** |
| **ops B — Control-User** | `ops` als lokaler User **auf der Control-Maschine** (ailab, Hetzner), von der aus Ansible läuft | ⏸️ **später / optional** |

### Warum die Trennung wichtig ist
`ops B` ist ein Henne-Ei: damit Ansible als `ops` läuft, muss `ops` lokal existieren, die
privaten SSH-Keys, die Repo-Working-Copy und `.vault_pass` besitzen. Das ist ein **lokaler
Bootstrap**, den Ansible nicht selbst erledigen kann. Großer Aufwand, und er ist **nicht nötig**,
um das Ziel zu erreichen: der Hermes-Prozess kann weiterhin als `daniel` laufen und einfach
`ansible_user=ops` mitschicken. Die Kontrolle gewinnst du schon mit **A**.

---

## 3. Was `ops` tut — und was nicht

Ein Ansible-Run via `ops`:

1. Jemand (du, oder der Hermes-Prozess als `daniel`) startet lokal `ansible-playbook`.
2. Ansible ssh-t als `ops@target` ein (public key, kein Passwort).
3. `/etc/sudoers.d/ops` erlaubt `become`.
4. Ansible wird per `sudo` zu **`root`** — **root** macht die eigentliche Arbeit
   (Pakete, Docker, Dateien).
5. Entstehende Dateien gehören weiter **`daniel`/`nuc`** — gesteuert über
   `username`/`username_personal`, **nicht** über `ansible_user`.
6. `ops` loggt sich aus. Auf dem Host "gehört" `ops` nichts außer `~/.ssh/` und ein paar
   `.ansible_*`-Tmp-Dateien.

**Drei Rollen, eine Trennung:** `ops` = Login-Gefäß · `root` = Ausführung · `daniel/nuc` = Besitz.

### Anti-Patterns (was `ops` NICHT sein darf)
- ❌ `ops` als Config-/Service-Owner (`/home/ops/config` …).
- ❌ `ops` in breite Gruppen mit pauschalem NOPASSWD, das `ops_sudo_nopasswd` aushebelt.
- ❌ `ops A` und `ops B` gleichzeitig einführen (Henne-Ei).
- ❌ Globales `ansible_user=ops`-Umschreiben, bevor `ansible_user`-Missbräuche in Rollen
  behoben sind (siehe §4).

---

## 4. Bestandsaufnahme (Repo-Realität)

### Login-User vs. Service-Owner ist **bereits** getrennt — nur inkonsequent
| Stelle | Bedeutung |
|---|---|
| `group_vars/all/config.yml:97` `username_personal: daniel` | persönlicher/config-owner, vorhanden |
| `group_vars/all/config.yml:111` `config_root: /home/{{ username }}/config` | service-root aus `username`, **nicht** aus `ansible_user` ✅ |
| `group_vars/homelab.yml:2` `username: nuc` | service-owner pro Hostgruppe |
| `group_vars/ailab_ubuntus.yml:7` `config_root: /home/{{ username_personal }}/config` | sauberes Muster |

→ Aufgabe ist **Härten & Dokumentieren**, nicht Neu-Erfinden.

### `ansible_user`-Missbräuche — **harte Blocker** vor jeder Host-Umstellung
| Stelle | Problem bei `ansible_user=ops` |
|---|---|
| `roles/comfyui/tasks/main.yml:61` | restricted OpenClaw-SSH-Key (`command="docker exec …"`) wird auf `ops` statt `daniel` gelegt → bricht Funktion **oder** gibt `ops` unerwartet `docker exec`-Recht |
| `roles/wan2gp/tasks/main.yml:162` | dito (Wan2GP/OpenClaw) |
| `roles/ssh_keys/tasks/main.yml` | Legacy-Ein-Actor-Verteilung an `ansible_user` |

→ Vor jeder Umstellung auf **explizite Variablen** (`comfyui_restricted_ssh_user`,
`wan2gp_restricted_ssh_user`) umstellen.

### Bereits existierende User-/sudo-Logik (nicht duplizieren!)
- `roles/basic/tasks/main.yml:2–6`: global `%sudo ALL=(ALL) NOPASSWD: ALL` in `/etc/sudoers`.
  **Kollidiert** mit kontrolliertem `ops_sudo_nopasswd` — sobald `ops` in der `sudo`-Gruppe ist,
  hat es automatisch pauschales NOPASSWD. Für Pilot-Hosts zuerst restrukturieren.
- `roles/cloud_security/tasks/main.yml` + `roles/cloud_security/defaults/main.yml:21`
  (`cloud_security_users: "{{ hetzner_users | default([]) }}"`): User + sshd + `sudoers.d`, bereits
  mit `hetzner` verkoppelt. **Hier** `ops` einbinden, statt eine vierte User-Rolle bauen.
- `roles/hetzner/tasks/main.yml`: parallele `hetzner_users`-Logik mit `sudoers.d`.

### Legacy-Duplikate (deprecated / umbauen)
- `distribute_ssh_key.yml`, `get_ssh_key.yml`, `roles/ssh_keys`: alles Varianten des
  Ein-Actor-Modells.

---

## 5. Variablenstruktur

Neu in `group_vars/all/config.yml` (Platzhalter, **keine** echten Keys im Repo):

```yaml
# --- ops automation user (login vessel only, not a service owner) ---
ops_user: ops
ops_shell: /usr/sbin/nologin      # kein interaktiver Shell-Bedarf; ggf. /bin/bash
ops_authorized_keys: []           # public keys, pro Actor dokumentiert (s. §6)
ops_sudo_nopasswd: true           # Ansible braucht passwordless become
ops_groups: []                    # nur wenn wirklich nötig
```

Bestehend **bleiben getrennt** (nicht aus `ansible_user` ableiten):

```yaml
username_personal: daniel         # persönlicher/config-owner
username: nuc                     # service-owner pro Hostgruppe (homelab etc.)
config_root: /home/{{ username }}/config
```

Pro-Actor-Keylisten (Beispielstruktur; echte Keys via lookup/secret):

```yaml
ops_authorized_keys:
  - comment: "daniel@ailab-ubuntu (personal)"
    key: "{{ lookup('file', ...) }}"
  - comment: "hermes@hetzner (automation)"
    key: "{{ vault_hermes_ops_pubkey }}"
  - comment: "coding-agent@ailab (automation)"
    key: "{{ vault_ailab_ops_pubkey }}"
```

---

## 6. Migrationsplan (Schritte)

> Reihenfolge ist verbindlich. Jeder Schritt = eigener, reviewbarer Commit.

1. **Variablen** anlegen (§5) — keine Rolle, kein Host. `--syntax-check` + `ansible-lint`.
2. **`ansible_user`-Missbräuche** in `comfyui`/`wan2gp` auf explizite
   `*_restricted_ssh_user`-Variablen refactor.
3. **`ops` einbinden** via bestehender `cloud_security_users`-Struktur (bzw. minimal
   extrahierte generische `managed_users`-Rolle), **keine** vierte User-Rolle. Optional:
   `roles/ops_user` **nur** als Bootstrap-Minimal-Playbook für noch nackte Neu-Hosts.
4. **`basic` für Pilot-Hosts** restrukturieren, sodass `%sudo … NOPASSWD: ALL` nicht mehr
   pauschal greift (sonst ist `ops_sudo_nopasswd` wirkungslos).
5. **Legacy** `distribute_ssh_key.yml`/`get_ssh_key.yml`/`roles/ssh_keys` als deprecated
   markieren bzw. auf Multi-Actor-Keylisten umbauen.
6. **Pilot per Opt-in** (`[ops_pilot]`-Gruppe oder per-host `ansible_user=ops`),
   **kein** dauerhaft divergierendes `inventory.ops`.
7. Pro Pilot-Host: Bootstrap (alter Zugang) → Verifikation → `--check --diff` → Apply →
   Root/Daniel-Zugang einschränken (§7).

---

## 7. Konkrete Befehle pro Pilot-Host

```bash
# 0. Bootstrap mit bisherigem Zugang: ops anlegen + authorized_keys + sudoers.d
uv run ansible-playbook setup.yml --tags ops,security --limit <pilot-host>

# 1. SSH- und sudo-Verifikation (manuell, noch nicht über Ansible)
ssh ops@<pilot-host> 'id && sudo -n true'

# 2. Ansible als ops prüfen
uv run ansible <pilot-host> -u ops -b -m ping

# 3. Dry-run mit echtem Setup-Play
uv run ansible-playbook setup.yml --limit <pilot-host> --check --diff

# 4. Apply (nur nach Freigabe)
uv run ansible-playbook setup.yml --limit <pilot-host>

# 5. Root/Daniel-Zugang einschränken — erst nach erfolgreicher ops-Verifikation
#    z.B. cloud_security_ssh_permit_root_login: "no"
```

---

## 8. Sicherheitsnotizen

- **Keine Secrets loggen, keine Vault-Werte ausgeben.** Public keys ja, private keys **nie** ins
  Repo.
- **Pro-Actor-Keys mit Kommentaren/Fingerprints sind Pflicht** — der gemeinsame `ops`-User
  verschleiert sonst den Akteur in Audit-Logs. Keys sind die einzige Zuordnungsmöglichkeit.
- **Inventory-Platzhalter/Plaintext prüfen:** `inventory` enthält z. B. `winhost1 …
  ansible_password=…` im Klartext → Vault. Nicht ops-relevant, aber aufräumen.
- **Root-/Daniel-Zugang** erst einschränken, **nachdem** `ops` auf dem Host verifiziert
  funktioniert.
- Keine pauschale Root-SSH-Abhängigkeit langfristig.

---

## 9. Nächste Schritte (ohne Host-Umstellung, ohne Apply)

Reviewbarer erster PR-Inhalt:

- [ ] Variablen-Block `ops_*` in `group_vars/all/config.yml` (Platzhalter)
- [ ] `ops`-Eintrag in `cloud_security_users` (oder `managed_users`-Extrakt)
- [ ] Refactor `comfyui`/`wan2gp` auf `*_restricted_ssh_user`-Variablen
- [ ] `--syntax-check` + `ansible-lint` vor Commit
- [ ] Pilot-Host benennen (Vorschlag: ein ungefährlicher interner Host oder nur `--check --diff`)
