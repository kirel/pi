# Authentifizierung mit Authelia

Authelia ist der zentrale Identity Provider für die Webdienste im Homelab. Es
stellt zwei unterschiedliche Integrationen bereit:

1. **Caddy Forward Auth** schützt einen kompletten Webdienst vor dem Backend.
2. **OpenID Connect (OIDC)** meldet Benutzer direkt in einer Anwendung an.

Passkeys werden zentral bei Authelia registriert und können anschließend für
beide Varianten verwendet werden. TOTP ist deaktiviert. E-Mail-Benachrichtigungen
und Identitätsprüfungen werden per SMTP über Brevo versendet; die frühere
`notification.txt` wird nicht mehr verwendet.

## Aktueller Stand

| Dienst | Integration | Authelia-Richtlinie | Lokaler Fallback |
| --- | --- | --- | --- |
| Homepage | Caddy Forward Auth | `two_factor`, Gruppe `admins` | Anwendung hat keine eigene SSO-Sitzung |
| PruneMate | Caddy Forward Auth | `two_factor`, Gruppe `admins` | Anwendung hat keine eigene SSO-Sitzung |
| DHCP Leases Homelab | Caddy Forward Auth | `two_factor`, Gruppe `admins` | Anwendung hat keine eigene SSO-Sitzung |
| Linkding | natives OIDC | `two_factor` | Passwort-Login bleibt während der Pilotphase aktiv |
| Beszel | natives OIDC | `two_factor` | Passwort-Login bleibt bis zum bestätigten OIDC-Test aktiv |

Der aktuelle Authelia-Backend-Entwurf rendert genau einen Benutzer (`daniel`)
mit der Gruppe `admins`. Bevor weitere Personen aufgenommen werden, muss die
Benutzerdefinition von den einzelnen Variablen auf eine Benutzerliste
umgestellt werden.

Die Authentifizierung ändert nicht die Netzwerkfreigabe eines Dienstes. Ohne
`public: true` bleibt ein Eintrag durch Caddys `internal_only`-Regel auf LAN und
Tailnet beschränkt.

### Wer darf sich wo anmelden?

Bei Forward Auth sind Authentifizierungsstufe und erlaubte Gruppen direkt im
jeweiligen `services.yml`-Eintrag festgelegt. Die drei aktuellen Dienste sind
auf `two_factor` und `admins` begrenzt.

Die aktuellen OIDC-Clients verwenden dagegen nur
`authorization_policy: two_factor`. Damit darf jeder in Authelia vorhandene
Benutzer den OIDC-Login starten; Benutzeranlage und Rollen werden anschließend
von Linkding beziehungsweise Beszel entschieden. Solange Authelia nur `daniel`
enthält, ergibt sich daraus kein zusätzlicher Zugriff.

Wenn mehrere Benutzer hinzukommen, gibt es für OIDC zwei Ebenen:

1. Bevorzugt verwaltet die Anwendung ihre eigenen Rollen anhand des
   angemeldeten Benutzers oder über geeignete Claims.
2. Falls bereits der Login zu einem Client eingeschränkt werden soll, kann in
   Authelia eine benannte OIDC-`authorization_policy` verwendet werden:

```yaml
identity_providers:
  oidc:
    authorization_policies:
      admins_only:
        default_policy: deny
        rules:
          - policy: two_factor
            subject: "group:admins"
    clients:
      - client_id: example
        authorization_policy: admins_only
```

Diese Policy entscheidet nur über die OIDC-Autorisierungsanfrage. Sie ersetzt
nicht die Rollen- und Rechteverwaltung innerhalb der Anwendung.

## Passkeys

Die Authelia-Konfiguration verwendet WebAuthn als bevorzugte
Zwei-Faktor-Methode:

- Passkey-Anmeldung ist aktiviert.
- Discoverable Credentials und Benutzerverifikation sind erforderlich.
- TOTP ist deaktiviert.
- Dienste und OIDC-Clients verwenden derzeit `two_factor`.

Einen neuen Passkey registrieren:

1. Einen mit `two_factor` geschützten Dienst oder einen OIDC-Login öffnen.
2. Bei Authelia zunächst die bestehende Identität bestätigen.
3. Im Authelia-Portal unter **Zwei-Faktor-Authentifizierung** einen WebAuthn-
   Passkey hinzufügen.
4. Die Registrierung am Gerät beziehungsweise im Passwortmanager bestätigen.
5. Mindestens einen zweiten Passkey auf einem unabhängigen Gerät als Recovery-
   Weg registrieren.

Die Passkey-Metadaten liegen in Authelias SQLite-Datenbank. Die Datenbank und
die verschlüsselten Ansible-Vault-Werte gehören daher gemeinsam in das Backup.

## Forward Auth

Forward Auth ist richtig, wenn eine Weboberfläche selbst kein OIDC unterstützt
und vollständig vor unberechtigtem Zugriff verborgen werden soll. Caddy fragt
Authelia vor jeder Weiterleitung über `/api/authz/forward-auth`. Bei Erfolg
werden `Remote-User`, `Remote-Groups`, `Remote-Email` und `Remote-Name` an das
Backend weitergegeben.

Vorteile:

- funktioniert auch bei Anwendungen ohne SSO-Unterstützung;
- zentrale Richtlinien nach Domain und Authelia-Gruppe;
- sehr kleine Änderung pro Dienst.

Grenzen:

- die Anwendung erhält dadurch nicht automatisch ein eigenes Benutzerkonto;
- eine vorhandene Anwendungsauthentifizierung kann als zweiter Login sichtbar
  bleiben;
- APIs, Webhooks, native Apps und WebSockets müssen separat getestet werden;
- ein pauschaler Schutz kann nicht-interaktive Clients aussperren.

Die Source of Truth ist `group_vars/all/services.yml`:

```yaml
services:
  example:
    name: Example
    target: homelab-nuc.lan
    http_port: 8080
    domain: example.kirelabs.org
    group: Productivity
    auth:
      provider: authelia
      policy: two_factor
      groups: [admins]
```

Aus diesem Block werden sowohl Caddys `forward_auth`-Direktive als auch die
Authelia-Zugriffsregel generiert. Nach einer Änderung müssen deshalb beide
Komponenten neu ausgerollt werden; bei einer neuen Domain zusätzlich Pi-hole:

```bash
uv run ansible-playbook setup.yml --tags authelia,caddy --limit homelab
uv run ansible-playbook setup.yml --tags pihole --limit nameserver,homelab
```

## Natives OIDC

OIDC ist die bevorzugte Variante, wenn die Anwendung es sauber unterstützt.
Die Anwendung leitet den Browser zu Authelia um, erhält nach erfolgreicher
Anmeldung einen Authorization Code und legt anschließend ihre eigene Sitzung
an. Benutzername, Name und E-Mail kommen aus den Scopes `openid`, `profile` und
`email`.

Vorteile:

- echtes Single Sign-on statt einer zusätzlichen Schutzschicht;
- die Anwendung kennt den angemeldeten Benutzer;
- anwendungseigene Rollen, Freigaben und Audit-Logs bleiben nutzbar;
- normale API-Tokens der Anwendung können unabhängig vom Browser-Login
  weiterverwendet werden.

Grenzen:

- jeder Dienst braucht einen eigenen Client und eine exakte Callback-URL;
- Benutzerzuordnung und Rollen bleiben Aufgabe der Anwendung;
- Abmeldung aus einer Anwendung beendet nicht zwingend jede Authelia-Sitzung;
- Implementierungsdetails wie PKCE und Client-Authentifizierung müssen zur
  jeweiligen Anwendung passen.

Für OIDC werden keine `auth:`-Blöcke in `services.yml` gesetzt. Andernfalls
entsteht unnötig ein Forward-Auth-Login vor dem eigentlichen OIDC-Login.

### Neuen OIDC-Client hinzufügen

1. Callback-URL und unterstützte OIDC-Optionen in der Dokumentation der
   Anwendung ermitteln.
2. Ein zufälliges Client-Secret und den von Authelia erwarteten Digest
   erzeugen.
3. Klartext-Secret und Digest ausschließlich verschlüsselt in
   `group_vars/all/authelia_secrets.yml` ablegen.
4. Variablen in `roles/authelia/defaults/main.yml` referenzieren.
5. Den Client in
   `roles/authelia/templates/configuration.yml.j2` mit mindestens
   `authorization_policy: two_factor`, exakter `redirect_uri` und den wirklich
   benötigten Scopes ergänzen.
6. Das Klartext-Secret über die Rolle der Anwendung injizieren. Secrets weder
   in Compose-Dateien einchecken noch in Task-Ausgaben schreiben; betroffene
   Tasks verwenden `no_log: true`.
7. Authelia und nur die betroffene Anwendung ausrollen.

Beispiel:

```bash
uv run ansible-playbook setup.yml --tags authelia,linkding --limit homelab
```

Linkding ist die Referenzimplementierung. Der existierende Benutzer `daniel`
wird anhand seiner E-Mail dem OIDC-Login zugeordnet, damit Bookmarks und
Administratorrechte erhalten bleiben. Beszel hat eine eigene Bootstrap- und
Recovery-Anleitung unter
[`docs/beszel-oidc-one-time-setup.md`](beszel-oidc-one-time-setup.md).

## Auswahlhilfe

| Situation | Empfehlung |
| --- | --- |
| Anwendung unterstützt OIDC zuverlässig | Natives OIDC |
| Reine Weboberfläche ohne OIDC | Caddy Forward Auth |
| API, Webhook oder native Mobile-App | Anwendungseigene Auth bevorzugen; Forward Auth nur nach Client-Test |
| Dienst hat eigene Rollen oder mehrere Benutzer | Natives OIDC |
| Kurzfristiger zusätzlicher Schutz vor einer Admin-Oberfläche | Forward Auth |
| Maschinenzugriff mit `Authorization`-Header | Kein pauschales Forward Auth ohne getrennte Route oder bestätigte Kompatibilität |

Das vorhandene Caddy-`basic_auth` bleibt für eng begrenzte Legacy-Fälle
verfügbar. Es bietet weder Passkeys noch SSO und ist für neue interaktive
Dienste nicht die bevorzugte Lösung.

## Zuständigkeiten und Source of Truth

| Bereich | Datei |
| --- | --- |
| Domains, Forward-Auth-Auswahl und Gruppen | `group_vars/all/services.yml` |
| Authelia-Benutzer, Passkeys, Policies und OIDC-Clients | `roles/authelia/` |
| Verschlüsselte Authelia- und OIDC-Secrets | `group_vars/all/authelia_secrets.yml` |
| Generierte Caddy-Integration | `roles/caddy/templates/Caddyfile.j2` |
| Linkding OIDC und Benutzerzuordnung | `roles/linkding/` |
| Beszel OIDC-Bootstrap | `roles/beszel/` |

Authelias OIDC-HMAC-Secret und Issuer-Key werden von allen Clients gemeinsam
verwendet und dürfen nicht beiläufig rotiert werden. Pro Anwendung gibt es
dagegen ein eigenes Client-Secret.

## Verifikation und Recovery

Nach jedem Auth-Änderungssatz sind mindestens diese Ebenen zu prüfen:

1. Authelia-Container läuft ohne Neustartschleife und `/api/health` antwortet.
2. OIDC Discovery und JWKS sind erreichbar.
3. Der Dienst startet den erwarteten Redirect mit korrektem `client_id`, Scope
   und Callback.
4. Ein echter Browser-Login mit Passkey endet wieder in der Anwendung.
5. Benutzeridentität, Rollen und bestehende Daten sind in der Anwendung
   unverändert.
6. Der vorgesehene lokale Notfallzugang funktioniert, solange er aktiviert ist.

Read-only Smoke Tests:

```bash
curl -fsS https://auth.kirelabs.org/api/health
curl -fsS https://auth.kirelabs.org/.well-known/openid-configuration | jq '.issuer, .jwks_uri'
curl -fsS https://auth.kirelabs.org/jwks.json | jq '.keys | length'
curl -sS -o /dev/null -D - https://linkding.kirelabs.org/oidc/authenticate/
curl -sSI https://homepage.kirelabs.org/
```

Ein HTTP-Erfolg allein beweist den Login nicht. Der letzte Test bleibt immer
eine Anmeldung im Browser mit Prüfung des tatsächlich zugeordneten Benutzers.

Recovery-Grundsätze:

- Passwort-Fallbacks erst nach bestätigtem OIDC-Login abschalten.
- Vor der Änderung bestehende Admin-Konten nicht löschen.
- Bei OIDC-Fehlern zuerst Discovery, Callback-URL, Client-ID, Secret-Methode,
  PKCE und Authelia-Logs prüfen.
- Bei Forward-Auth-Fehlern sowohl Caddys gerenderte Konfiguration als auch die
  gerenderten Authelia-Access-Control-Regeln prüfen.
- Keine Secrets aus Vault, gerenderten Konfigurationen oder
  Container-Umgebungen in Logs oder Tickets kopieren.

## Referenzen

- [Authelia: Caddy-Integration](https://www.authelia.com/integration/proxies/caddy/)
- [Authelia: Access Control](https://www.authelia.com/configuration/security/access-control/)
- [Authelia: OpenID Connect Provider](https://www.authelia.com/configuration/identity-providers/openid-connect/provider/)
- [Authelia: WebAuthn](https://www.authelia.com/configuration/second-factor/webauthn/)
- [Linkding: OIDC-Optionen](https://linkding.link/options/)
