# Ops-User Migration

Stand: 2026-06-19 · Status: **Plan, nicht umgesetzt** · Ziel: sauberer Automation-Pfad für Ansible/Hermes ohne `root`- oder `daniel`-Login als Ziel.

> Dieser Plan ist **Deskription, kein Apply**. Keine Host-Umstellung, kein Playbook-Run ohne
> explizite Freigabe. Erste Schritte sind nur Variablen + Refactor + `--check --diff`.

---

## 1. TL;DR

`ops` als generischer Unix-User ist eine **gute Idee**, weil zwei konkrete Probleme im Repo
adressiert werden:

- `homelab-nuc` nutzt aktuell `ansible_user=root` → root als SSH-Ziel ist ein Anti-Pattern.
- `daniel` ist der persönliche Account; Automation über denselben Account vermischt in Logs
  "Daniel war da" mit "ein Agent war da".

`ops` ist dabei **kein** Service-/Config-/Application-User. Es ist ein **Login-Gefäß**:
SSH-Ziel + `sudo`-Recht + besseres Audit-Label für Automation. Configs und Daten bleiben Eigentum
von `username`/`username_personal` (`daniel`/`nuc`).

**Wichtig:** `dashserv` ist im aktuellen Inventory bereits auf `ansible_user=daniel` umgestellt,
ist von hier aber noch nicht per SSH erreichbar. Dashserv ist daher erst Pilot-Kandidat, wenn der
Zugang über `daniel` funktioniert oder ein Console-/Root-Bootstrap verfügbar ist.

---

## 2. Kernentscheidung: `ops` ist **zwei** Dinge — nur eines zwingend

| | Bedeutung | Empfehlung |
|---|---|---|
| **ops A — Target-User** | `ops` als SSH-Ziel & `become`-User **auf Zielhosts** | ✅ **jetzt planen / per Pilot einführen** |
| **ops B — Control-User** | `ops` als lokaler User **auf der Control-Maschine** (ailab, Hetzner), von der aus Ansible läuft | ⏸️ **später / optional** |

### Warum die Trennung wichtig ist
`ops B` ist ein Henne-Ei: damit Ansible lokal als `ops` läuft, muss `ops` lokal existieren, die
privaten SSH-Keys, die Repo-Working-Copy und `.vault_pass` besitzen. Das ist ein lokaler Bootstrap,
den Ansible nicht sinnvoll selbst erledigt. Das Kernziel erreichst du bereits mit **ops A**: der
Hermes-Prozess kann weiterhin als `daniel` laufen und `ansible_user=ops` für Zielhosts verwenden.

---

## 3. Was `ops` tut — und was nicht

Ein Ansible-Run via `ops`:

1. Jemand (du, oder der Hermes-Prozess als `daniel`) startet lokal `ansible-playbook`.
2. Ansible ssh-t als `ops@target` ein (Public Key, kein Passwort).
3. `/etc/sudoers.d/ops` erlaubt `become`.
4. Ansible wird per `sudo` zu **`root`** — **root** macht die eigentliche Arbeit
   (Pakete, Docker, Dateien).
5. Entstehende Dateien gehören weiter **`daniel`/`nuc`** — gesteuert über
   `username`/`username_personal`, **nicht** über `ansible_user`.
6. `ops` loggt sich aus. Auf dem Host "gehört" `ops` nichts außer `~/.ssh/` und ggf.
   `.ansible_*`-Tmp-Dateien.

**Drei Rollen, eine Trennung:** `ops` = Login-Gefäß · `root` = Ausführung · `daniel/nuc` = Besitz.

### Audit-Grenzen
`ops` verbessert die Auditierbarkeit des **SSH-Einstiegs**: welcher Key/Fingerprint hat sich als
`ops` angemeldet. Nach `sudo` zeigen viele System-/Datei-/Prozessspuren aber nur `root` oder `ops`,
nicht den konkreten menschlichen/agentischen Akteur. Wenn stärkere Nachvollziehbarkeit nötig ist,
braucht es zusätzlich sudo-Logging (`log_input`/`log_output` o. ä.) und sauber kommentierte Keys.

### Anti-Patterns (was `ops` NICHT sein darf)
- ❌ `ops` als Config-/Service-Owner (`/home/ops/config` …).
- ❌ `ops` in breite Gruppen mit pauschalem NOPASSWD, das gezielte sudoers-Regeln aushebelt.
- ❌ `ops A` und `ops B` gleichzeitig einführen.
- ❌ Globales `ansible_user=ops`-Umschreiben, bevor `ansible_user`-Missbräuche in Rollen
  behoben sind (siehe §4).
- ❌ Alte Root-/Daniel-Zugänge sperren, bevor `ops` mehrfach verifiziert wurde und ein
  Console-/Recovery-Pfad bestätigt ist.

---

## 4. Bestandsaufnahme (Repo-Realität)

### Login-User vs. Service-Owner ist **bereits** getrennt — nur inkonsequent
| Stelle | Bedeutung |
|---|---|
| `group_vars/all/config.yml` `username_personal: daniel` | persönlicher/config-owner, vorhanden |
| `group_vars/all/config.yml` `config_root: /home/{{ username }}/config` | service-root aus `username`, **nicht** aus `ansible_user` ✅ |
| `group_vars/homelab.yml` `username: nuc` | service-owner pro Hostgruppe |
| `group_vars/ailab_ubuntus.yml` `config_root: /home/{{ username_personal }}/config` | sauberes Muster |

→ Aufgabe ist **Härten & Dokumentieren**, nicht Neu-Erfinden.

### Aktuelle Login-Lage
- `homelab-nuc`: weiterhin `ansible_user=root` → Hauptmotiv für `ops`.
- `dashserv-m-1`: im Inventory bereits `ansible_user=daniel`, aber SSH-Zugang von hier ist aktuell
  noch nicht funktionsfähig.
- `hetzner`: `ansible_user=daniel`, `cloud_security` aktiv.
- interne Hosts (`nameserver`, `ailab_ubuntus`): nutzen `daniel`; `cloud_security` läuft dort nicht.

### `ansible_user`-Missbräuche — **harte Blocker** vor jeder Host-Umstellung
| Stelle | Problem bei `ansible_user=ops` |
|---|---|
| `roles/comfyui/tasks/main.yml` | restricted OpenClaw-SSH-Key (`command="docker exec …"`) wird auf `ops` statt `daniel` gelegt → bricht Funktion **oder** gibt `ops` unerwartet Container-Exec-Rechte |
| `roles/wan2gp/tasks/main.yml` | dito (Wan2GP/OpenClaw) |
| `roles/ssh_keys/tasks/main.yml` | Legacy-Ein-Actor-Verteilung an `ansible_user` |

→ Vor jeder Umstellung auf **explizite Variablen** umstellen, z. B.
`comfyui_restricted_ssh_user` und `wan2gp_restricted_ssh_user`, mit sicherem Default
`{{ username_personal }}`.

### Bereits existierende User-/sudo-Logik (nicht duplizieren!)
- `roles/basic/tasks/main.yml`: installiert `mosh`, setzt aber auch global
  `%sudo ALL=(ALL) NOPASSWD: ALL` in `/etc/sudoers`. Auf Hosts ohne `cloud_security` bleibt das
  ein Blocker für kontrolliertes sudo.
- `roles/cloud_security/tasks/main.yml`: kann User + SSH-Keys + `/etc/sudoers.d/<user>` verwalten
  und entfernt standardmäßig die breite `%sudo … NOPASSWD`-Regel. Das hilft auf Hetzner/Dashserv,
  aber **nicht** auf Homelab/Nameserver/Ailab, solange `cloud_security` dort nicht läuft.
- `roles/hetzner/tasks/main.yml`: parallele `hetzner_users`-Logik mit `sudoers.d`.

### Legacy-Duplikate (deprecated / umbauen)
- `distribute_ssh_key.yml`, `get_ssh_key.yml`, `roles/ssh_keys`: Varianten des Ein-Actor-Modells.

---

## 5. Variablenstruktur

Neu in `group_vars/all/config.yml` (Platzhalter, **keine** echten Keys im Repo):

```yaml
# --- ops automation user (login vessel only, not a service owner) ---
ops_user: ops
ops_shell: /bin/bash              # Ansible/SSH/mosh brauchen eine echte Shell; kein nologin
ops_authorized_keys: []           # public keys, pro Actor dokumentiert (s. §8)
ops_sudo: true                    # falls bestehende managed-user/cloud_security-Schema genutzt wird
ops_passwordless_sudo: true       # Ansible braucht sudo -n/become ohne Passwort
ops_groups: []                    # keine docker-Gruppe außer nach expliziter Begründung
ops_authorized_keys_exclusive: true # Zielzustand: stale ops-Keys aktiv entfernen
```

Bestehend **bleiben getrennt** (nicht aus `ansible_user` ableiten):

```yaml
username_personal: daniel         # persönlicher/config-owner
username: nuc                     # service-owner pro Hostgruppe (homelab etc.)
config_root: /home/{{ username }}/config
```

### Mapping auf bestehende Rollen
Wenn `cloud_security_users` genutzt wird, müssen die `ops_*`-Variablen sauber in dessen Schema
übersetzt werden:

```yaml
cloud_security_users:
  - name: "{{ ops_user }}"
    shell: "{{ ops_shell }}"
    sudo: "{{ ops_sudo }}"
    passwordless_sudo: "{{ ops_passwordless_sudo }}"
    authorized_keys: "{{ ops_authorized_keys | map(attribute='key') | list }}"
```

Für interne Hosts braucht es entweder eine extrahierte generische `managed_users`-Rolle oder eine
kleine `ops_user`/`managed_users`-Bootstrap-Rolle mit denselben Semantiken. Nur `cloud_security` zu
erweitern reicht nicht.

Pro-Actor-Keylisten (Beispielstruktur; echte Keys via lookup/secret):

```yaml
ops_authorized_keys:
  - comment: "daniel@ailab-ubuntu (personal)"
    fingerprint: "SHA256:..."
    key: "{{ lookup('file', lookup('env', 'HOME') + '/.ssh/id_rsa.pub') }}"
  - comment: "hermes@hetzner (automation)"
    fingerprint: "SHA256:..."
    key: "{{ vault_hermes_ops_pubkey }}"
  - comment: "coding-agent@ailab (automation)"
    fingerprint: "SHA256:..."
    key: "{{ vault_ailab_ops_pubkey }}"
```

Für `ops` sollten Keys langfristig **managed/exclusive** sein oder explizit gepruned werden; das
aktuelle `authorized_key exclusive: false`-Muster akkumuliert stale Keys.

---

## 6. Migrationsplan (Schritte)

> Reihenfolge ist verbindlich. Jeder Schritt = eigener, reviewbarer Commit.

1. **Variablen + Dokumentation** anlegen (§5) — keine Host-Umstellung. `--syntax-check`.
2. **`basic`/sudo-Modell klären**, bevor interne Hosts pilotiert werden:
   - breite `%sudo ALL=(ALL) NOPASSWD: ALL` aus `basic` entfernen, optionalisieren oder in eine
     explizite Variable überführen;
   - sicherstellen, dass `cloud_security`/managed-user-Läufe diese Regel nicht später wieder
     verlieren oder wiederherstellen.
3. **`ansible_user`-Missbräuche** in `comfyui`/`wan2gp` auf explizite
   `*_restricted_ssh_user`-Variablen refactor, Default `{{ username_personal }}`.
4. **User-Management-Pfad wählen**:
   - Für Hetzner/Dashserv: vorhandenes `cloud_security_users` nutzen.
   - Für Homelab/Nameserver/Ailab: generische `managed_users`-Rolle oder minimale `ops_user`-Rolle
     einführen; nicht voraussetzen, dass `cloud_security` dort läuft.
5. **Ops-Tag real machen**: neue User/Bootstrap-Tasks mit Tag `ops` versehen. Bis dahin keine
   Befehle dokumentieren, die `--tags ops` als existierend voraussetzen.
6. **Legacy** `distribute_ssh_key.yml`/`get_ssh_key.yml`/`roles/ssh_keys` als deprecated markieren
   bzw. auf Multi-Actor-Keylisten umbauen.
7. **Pilot per Opt-in** (`[ops_pilot]`-Gruppe oder per-host `ansible_user=ops`), **kein** dauerhaft
   divergierendes `inventory.ops`. Bei Gruppen darauf achten, dass Inventory-Variable-Precedence
   eindeutig ist; per-host Override ist für Piloten am klarsten.
8. Pro Pilot-Host: Bootstrap mit altem Zugang → Verifikation → `--check --diff` → begrenzter Apply
   → zweiter Check → Root/Daniel-Zugang einschränken (§7/§8).

---

## 7. Pilot-Auswahl und konkrete Befehle

### Pilot-Kriterien
Ein Pilot-Host braucht:

- funktionierenden alten Zugang (`root` oder `daniel`) **und** bestätigten Console-/Recovery-Zugang;
- möglichst geringe Service-Kritikalität;
- keine ungeklärten Firewall-/SSH-Hardening-Änderungen im selben Schritt;
- klare Rollback-Möglichkeit auf alten `ansible_user`.

Empfehlung:

- **Dashserv** kann ein guter erster echter Pilot sein, weil `cloud_security` dort bereits im Play
  hängt und der Zielzustand `daniel` statt root schon begonnen wurde — **aber erst**, wenn SSH-Zugang
  repariert ist.
- **Homelab-nuc** ist kein guter erster Pilot: service-kritisch, root-basiert und aktuell ohne
  `cloud_security`-User-Pfad.
- **Nameserver/Ailab** erst nach generischem internen User-Pfad.

### Befehle pro Pilot-Host

```bash
# 0. Syntax-/Dry checks lokal
uv run ansible-playbook setup.yml --syntax-check
# uv run ansible-lint   # falls im Projekt verfügbar

# 1. Bootstrap mit bisherigem Zugang: ops anlegen + authorized_keys + sudoers.d
#    Nur gültig, nachdem ein echter ops/managed-users Tag existiert.
uv run ansible-playbook setup.yml --tags ops --limit <pilot-host>

# Bei cloud_security-Piloten alternativ/zusätzlich nur wenn SSH/UFW-Auswirkungen geprüft sind:
uv run ansible-playbook setup.yml --tags security --limit <pilot-host>

# 2. SSH- und sudo-Verifikation (manuell, noch nicht über Ansible)
ssh ops@<pilot-host> 'id && sudo -n true'

# 3. Ansible als ops prüfen
uv run ansible <pilot-host> -u ops -b -m ping

# 4. Dry-run mit echtem Setup-Play als ops
uv run ansible-playbook setup.yml --limit <pilot-host> -u ops -b --check --diff

# 5. Begrenzter Apply (nur nach Freigabe)
uv run ansible-playbook setup.yml --limit <pilot-host> -u ops -b

# 6. Zweiter Check und Service-/SSH-Validierung
uv run ansible-playbook setup.yml --limit <pilot-host> -u ops -b --check --diff
ssh ops@<pilot-host> 'sudo -n true'

# 7. Inventory erst nach erfolgreicher Verifikation auf ansible_user=ops ändern.

# 8. Root/Daniel-Zugang einschränken — erst nach erfolgreicher ops-Verifikation
#    und bestätigtem Console-/Emergency-Zugang.
```

### Rollback

Wenn etwas fehlschlägt:

1. Inventory/per-host Override zurück auf den alten `ansible_user` setzen.
2. Mit altem Zugang prüfen: `uv run ansible <host> -m ping`.
3. Falls SSH kaputt ist: Console/Provider-Rescue nutzen; Root/Daniel-Zugang wieder aktivieren.
4. `ops` nicht entfernen, bevor verstanden ist, ob der Fehler in SSH, sudo, UFW oder Ansible liegt.
5. Root-/Daniel-Zugang erst nach mindestens einem erfolgreichen Apply **und** einem späteren
   erfolgreichen Check/Drift-Run einschränken.

---

## 8. Sicherheitsnotizen

- **Keine Secrets loggen, keine Vault-Werte ausgeben.** Public keys ja, private keys **nie** ins
  Repo.
- **Pro-Actor-Keys mit Kommentaren/Fingerprints sind Pflicht** — der gemeinsame `ops`-User
  verschleiert sonst den Akteur in Audit-Logs. Key-Fingerprints sind die primäre Zuordnung.
- **Revocation ist Pflicht:** `ops`-Keys dürfen nicht nur mit `exclusive: false` anwachsen. Für
  `ops` managed/exclusive Keylisten oder explizites Pruning verwenden.
- **Inventory und Git-Historie auf Klartext-Secrets prüfen:** Zugangsdaten gehören in den Vault,
  nicht ins Inventory. Nicht ops-spezifisch, aber sicherheitsrelevant.
- **Root-/Daniel-Zugang** erst einschränken, **nachdem** `ops` auf dem Host verifiziert funktioniert
  und ein Recovery-Pfad bestätigt ist.
- **`cloud_security_ssh_allow_users` beachten:** falls gesetzt, muss `ops` enthalten sein, sonst
  kann SSH-Hardening den neuen Zugang aussperren.
- **Firewall-/sshd-Änderungen trennen:** besonders auf öffentlichen VPS nicht gleichzeitig User-
  Migration, UFW-Policy und Root-Login-Sperre in einem ungetesteten Schritt bündeln.
- **Keine pauschale Docker-Gruppe für `ops`:** Ansible soll per `sudo` zu root werden. Direkte
  `docker`-Gruppenmitgliedschaft nur nach expliziter Begründung.
- **Mosh-Kompatibilität:** `ops` braucht eine echte Shell; `nologin` bricht SSH-Kommandos, Ansible
  und mosh.

---

## 9. Nächste Schritte (ohne Host-Umstellung, ohne Apply)

Reviewbarer erster PR-Inhalt:

- [ ] Variablen-Block `ops_*` in `group_vars/all/config.yml` (Platzhalter, keine Secrets).
- [ ] `basic`-sudo-Regel optionalisieren/entschärfen oder dokumentiert auf cloud-only Entfernung
      durch `cloud_security` begrenzen.
- [ ] Refactor `comfyui`/`wan2gp` auf `*_restricted_ssh_user`-Variablen mit Default
      `{{ username_personal }}`.
- [ ] Entscheidung: `cloud_security_users` nur für Cloud-Piloten oder generische `managed_users` /
      `ops_user`-Rolle für interne Hosts.
- [ ] Echten `ops`-Tag definieren, bevor Befehle mit `--tags ops` verwendet werden.
- [ ] `roles/ssh_keys`/Legacy-Playbooks als deprecated markieren oder Multi-Actor-Keylisten planen.
- [ ] Pilot-Host erst benennen, nachdem Zugang + Recovery + Rollback klar sind.
- [ ] `--syntax-check` + ggf. `ansible-lint` vor Commit.
