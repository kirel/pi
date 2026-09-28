# Hermes Assist: abgeschlossener Rückbau

Stand: 2026-09-28. Die separate Home-Assistant-Instanz als private
Hermes-Sprachoberfläche wurde entfernt. Daniel verwendet stattdessen eine
native Android-App. Deren Repository, Endpunkte und vollständiger Sprachablauf
wurden bei diesem Rückbau nicht geprüft.

## Entfernt

- Auf `homelab-nuc`: Container/Compose-Dienst `hermes-assist`, gleichnamiges
  Docker-Netz, Konfiguration `/home/nuc/config/hermes-assist` und Download-Cache
  `/var/cache/hermes-assist`. Der bisherige Loopback-Port `8124` ist geschlossen.
- Im Repository: `roles/hermes_assist/`, Rollenaufruf in `setup.yml` und
  Service-Eintrag in `group_vars/all/services.yml`.
- Caddy-Route und Pi-hole-CNAME für `hermes-assist.kirelabs.org` sowie die
  über Container-Labels erzeugte Homepage-Kachel.
- Die über Docker-Labels von AutoKuma verwalteten Monitore
  **Hermes Assist Web** und **Hermes Assist Container**. Beide wurden gezielt
  über die Kuma-API gelöscht; ihre Label-Quelle existiert nicht mehr.
- Die Hermes-Assist-Ausnahme für Benachrichtigungen in den AutoKuma-Defaults.
  Die betroffenen Monitoring- und Pocket-ID-Dokumente wurden angepasst.

Caddy und beide Pi-holes wurden über Ansible aktualisiert. Die geänderten
AutoKuma-Defaults wurden gezielt ausgerollt und AutoKuma neu gestartet.

## Backup und verbleibende Dienste

Vor dem Entfernen wurde der Container sauber gestoppt und die vollständige
Konfiguration auf dem NUC archiviert:

`/var/backups/hermes-assist-retired/config.tar.gz`

Das Archiv gehört root und hat Modus `0600`, sein Verzeichnis `0700`.
Es enthält Zugangsdaten und darf nicht in das Repository übernommen werden.
Die Lesbarkeit des Archivs wurde mit `tar -tzf` geprüft; ein vollständiger
Restore wurde nicht durchgeführt.

`/etc/tmpfiles.d/hermes-assist-retired.conf` konfiguriert eine Altersgrenze von
14 Tagen. Der aktive `systemd-tmpfiles-clean.timer` bereinigt das Archiv nach
den Altersregeln von systemd-tmpfiles; dies ist kein Löschtermin auf die Minute.
Die Regel und das leere Verzeichnis bleiben anschließend bestehen.

Die normale Home-Assistant-Instanz, Bare-Metal-Hermes samt API und Schlüssel,
LiteLLM sowie STT/TTS und Wyoming wurden durch diesen Rückbau nicht entfernt
oder umkonfiguriert. Die normale HA-Instanz enthält weiterhin eine
Wyoming-Integration. Andere Dienste wurden nicht dekommissioniert.

## Verifizierter Stand

- Container, Netzwerk, aktive Konfiguration, Download-Cache, Port und aktive
  Caddy-Route fehlen; beide Kuma-Monitore sind entfernt. Erneut live geprüft
  bei Erstellung dieser Dokumentation.
- Beim Abschluss des Rückbaus: CNAME auf beiden DNS-Servern entfernt,
  Homepage-Serviceantwort ohne Hermes Assist, normale HA-Oberfläche und
  Hermes-API-Health jeweils HTTP `200`.
- Ansible-Deployments ohne Fehler; Syntaxprüfung, sieben bestehende Tests und
  `git diff --check` erfolgreich. Die Syntaxprüfung meldete lediglich die
  nicht vorhandenen Inventargruppen `virtualhere` und `mic_satellites`.
- Der alte Servereintrag in der Android-Companion-App wurde nicht durch den
  Agenten entfernt; der Zustand auf dem Telefon wurde nicht verifiziert.
