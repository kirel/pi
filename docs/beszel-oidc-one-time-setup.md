# Beszel: einmalige Authelia-OIDC-Konfiguration

Der Beszel Hub, alle drei Agents und der generische OpenID-Connect-Provider
werden durch Ansible verwaltet. Die Rolle legt den Provider über die
PocketBase-Admin-API an und gleicht ihn bei späteren Deploys erneut ab. Existiert
bereits ein anderer OAuth2-Provider, bricht sie bewusst ab, damit sie ihn nicht
überschreibt.
Die Authelia-Clientseite und beide Secrets liegen verschlüsselt in Ansible
Vault.

## Vorbedingungen

- `https://beszel.kirelabs.org/api/health` antwortet erfolgreich.
- `https://auth.kirelabs.org/.well-known/openid-configuration` ist erreichbar.
- Der Ansible-Deploy für `authelia`, `beszel`, `caddy` und `pihole` ist erfolgt.

## Automatischer Bootstrap

Die Rolle legt zuerst einen PocketBase-Superuser und den normalen Beszel-
Bootstrap-Benutzer an. Anschließend konfiguriert sie `users.oauth2` mit
Authelia und prüft über `/api/collections/users/auth-methods`, dass Beszel den
Provider öffentlich anbietet. Alle Tasks mit Kennwörtern oder Client-Secrets
verwenden `no_log: true`. Der Klartextwert aus Ansible Vault wird vor der
Übergabe an PocketBase getrimmt; ein von `encrypt_string` übernommener
Zeilenumbruch würde sonst den OIDC-Tokenaustausch ungültig machen.

## Manueller Recovery-Weg

Die folgenden Schritte sind nur nötig, wenn ein bestehender Hub bereits einen
anderen OAuth2-Provider enthält oder die PocketBase-Einstellungen manuell
wiederhergestellt werden müssen.

### Zugangsdaten lokal aus Ansible Vault lesen

Die folgenden Befehle nur in einem lokalen Terminal ausführen. Werte weder in
Git noch in Tickets, Chats oder Shell-Skripte kopieren.

```bash
uv run ansible localhost -i localhost, -c local \
  -m ansible.builtin.debug \
  -a 'msg={{ vault_beszel_superuser_password }}' \
  -e @group_vars/all/authelia_secrets.yml \
  --vault-password-file .vault_pass

uv run ansible localhost -i localhost, -c local \
  -m ansible.builtin.debug \
  -a 'msg={{ vault_authelia_oidc_beszel_client_secret }}' \
  -e @group_vars/all/authelia_secrets.yml \
  --vault-password-file .vault_pass
```

Der erste Wert ist das Beszel-Superuser-Passwort, der zweite das Klartext-OIDC-
Client-Secret. Der in Authelia konfigurierte Digest ist ein separater
Vault-Wert.

### OpenID Connect in Beszel aktivieren

1. `https://beszel.kirelabs.org/_/#/settings` öffnen.
2. Mit `danishkirel@gmail.com` und dem Beszel-Superuser-Passwort anmelden.
3. `Hide collection create and edit controls` vorübergehend deaktivieren.
4. Bei der Collection `users` das Zahnrad öffnen und `Options` wählen.
5. Unter `OAuth2` die Funktion aktivieren und `Add Provider` →
   `OpenID Connect` wählen.
6. Folgende Werte eintragen:

   | Feld | Wert |
   | --- | --- |
   | Client ID | `beszel-kirelabs` |
   | Client secret | Klartextwert `vault_authelia_oidc_beszel_client_secret` |
   | Display name | `Authelia` |
   | Auth URL | `https://auth.kirelabs.org/api/oidc/authorization` |
   | Token URL | `https://auth.kirelabs.org/api/oidc/token` |
   | Fetch user info from | `User info URL` |
   | User info URL | `https://auth.kirelabs.org/api/oidc/userinfo` |

7. Speichern und `Hide collection create and edit controls` wieder aktivieren.
8. In einem privaten Browserfenster über `Authelia` anmelden. Der Callback ist
   `https://beszel.kirelabs.org/api/oauth2-redirect`.

### Weißer Bildschirm nach dem Callback

Authelia und Beszel verwenden für diesen Client `client_secret_basic`. Wenn
Authelia im Token-Endpunkt `invalid character` für das Client-Secret meldet,
enthielt der an Beszel übergebene Vault-Wert wahrscheinlich einen abschließenden
Zeilenumbruch. Ein erneuter `--tags beszel`-Deploy korrigiert den in PocketBase
gespeicherten Provider deklarativ.

## Passwort-Login nach erfolgreichem Test deaktivieren

Nach einem bestätigten OIDC-Login in `roles/beszel/defaults/main.yml` setzen:

```yaml
beszel_disable_password_auth: true
```

Danach nur Beszel neu ausrollen:

```bash
uv run ansible-playbook setup.yml --tags beszel --limit homelab-nuc
```

Der PocketBase-Superuser-Zugang unter `/_/` bleibt davon getrennt und dient als
lokaler Notfallzugang.

## Ablösung von Glances

Glances wurde erst nach der Live-Verifikation entfernt: `homelab-nuc`,
`nameserver-pi` und `ailab-ubuntu` waren gleichzeitig online; Beszel hatte
Systemzeitreihen, Container, SMART-Geräte, zusätzliche Dateisysteme und drei
NVIDIA-GPUs erfasst. Die alten Glances-Config-Verzeichnisse dürfen als kleiner
Rollback-Pfad auf den Hosts verbleiben, werden aber nicht mehr gestartet oder
über Caddy/Pi-hole veröffentlicht.
