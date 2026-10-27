# Agentgateway-Spielwiese

Separater Agentgateway-1.6.0-Container auf `homelab-nuc`, direkt vor CPA und
LlamaSwap. LiteLLM bleibt unverändert. Diese Rolle wird nur über das eigene
Playbook gestartet und ist nicht Teil von `setup.yml`.

## Öffnen

- Oberfläche: <https://agentgateway.kirelabs.org/ui/>
- OpenAI-kompatible Base URL: `https://agentgateway.kirelabs.org/v1`
- API-Key: für diesen internen Testzugang nicht erforderlich. Falls ein
  Client einen Wert verlangt, `unused` eintragen.

Die URL wird über `services.yml`, Caddy und Pi-hole bereitgestellt. Caddys
`internal_only`-Regel beschränkt den Zugriff auf interne Netze und Tailscale;
`public: false` ist explizit gesetzt. Der Zugang umfasst auch die schreibende
Admin-Oberfläche und ist innerhalb dieser Netze ohne Anmeldung nutzbar.

Alternativ bleibt der SSH-Tunnel möglich:

```bash
ssh -N -L 127.0.0.1:4010:127.0.0.1:4010 -o ExitOnForwardFailure=yes root@homelab-nuc.lan
```

Dann ist die Oberfläche unter <http://localhost:4010/ui/> erreichbar.
Port 4010 bleibt auf dem NUC an `127.0.0.1` gebunden; Caddy erreicht ihn über
sein Host-Netzwerk.

## Konfigurieren

In der UI unter **LLM → Providers / Models** die beiden vorbereiteten Provider
`cpa` und `llamaswap` bearbeiten oder weitere Modelle hinzufügen. Die vier
Startmodelle sind:

- `gpt-6.1-sol-cpa`: CPA, Chat Completions und Responses.
- `gemini-3.8-flash-high-cpa`: CPA.
- `home-hermes`: beim ersten Deploy aus `model_group_alias` übernommen,
  Reasoning-Default `low`.
- `home-embed`: lokales Embedding-Modell aus `model_group_alias`.

Änderungen speichert Agentgateway direkt in
`/home/nuc/config/agentgateway/config.yaml`. Ansible legt diese Datei nur beim
ersten Deploy an; spätere Deploys überschreiben keine UI-Änderungen. Das gilt
auch für spätere Änderungen an den Modell-Aliasen im Repository: diese werden
nicht automatisch in die bereits angelegte Spielwiese übernommen.

Die SQLite-Datei `data.db` liegt im selben persistenten Verzeichnis. Das
CPA-Credential wird aus dem vorhandenen Ansible Vault als `CPA_API_KEY`
bereitgestellt. Der Provider referenziert `$CPA_API_KEY`; kein Schlüssel muss
in den Browser kopiert werden.

MCP ist vorbereitet, hat aber noch keine Targets. Unter **MCP → Servers**
können HTTP-MCP-Targets für manuelle Tests hinzugefügt werden. Die bestehenden
LiteLLM-Gruppen und Tool-Rechte werden nicht automatisch übernommen. Das
Standardimage enthält nicht die Node-/Python-MCP-Pakete aus unserem
LiteLLM-Image.

## Manuelle API-Tests

Modellliste:

```bash
curl -fsS https://agentgateway.kirelabs.org/v1/models
```

Chat:

```bash
curl -fsS --max-time 60 https://agentgateway.kirelabs.org/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"gpt-6.1-sol-cpa","messages":[{"role":"user","content":"Antworte kurz mit Hallo."}],"reasoning_effort":"low","max_completion_tokens":128}'
```

Für Streaming `"stream":true` ergänzen und `curl -N` benutzen.

Responses:

```bash
curl -fsS --max-time 60 https://agentgateway.kirelabs.org/v1/responses \
  -H 'Content-Type: application/json' \
  -d '{"model":"gpt-6.1-sol-cpa","input":"Antworte kurz mit Hallo.","reasoning":{"effort":"low"},"max_output_tokens":128}'
```

Lokale Embeddings:

```bash
curl -fsS --max-time 120 https://agentgateway.kirelabs.org/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{"model":"home-embed","input":"Ein kurzer Testsatz.","encoding_format":"float"}'
```

Für lokalen Chat im Chat-Beispiel `home-hermes` als Modell einsetzen. Diese
lokalen Requests benutzen die produktive LlamaSwap-/GPU-Instanz und können
Modelle laden. Der Gateway-Container selbst benötigt keine GPU.

Audio-/Bild-/Video-Routen, weitere Provider, Fallbacks und Familienrechte sind
nicht Teil dieser kleinen Startkonfiguration.

## Deployment und Stoppen

```bash
uv run ansible-playbook agentgateway.yml --limit homelab-nuc
```

Nach Änderungen am Service-Eintrag zusätzlich Proxy und DNS deployen:

```bash
uv run ansible-playbook setup.yml --tags caddy --limit homelab
uv run ansible-playbook setup.yml --tags pihole --limit nameserver,homelab -e pihole_pull_policy=never
```

Container stoppen und entfernen, persistente Konfiguration behalten:

```bash
ssh root@homelab-nuc.lan 'docker compose -p agentgateway -f /home/nuc/config/agentgateway/compose.yaml down'
```

Die Compose-Datei setzt 512 MiB RAM und eine CPU als Obergrenze. Das explizite
Docker-Subnetz `10.206.0.0/24` vermeidet die Kollision zwischen Dockers
automatischer Adressvergabe und einer bestehenden Tailscale-Route.

## Geprüft am 2026-10-10

- Native Konfigurationsvalidierung, UI-HTML und JS-/CSS-Assets: erfolgreich.
- `/v1/models`: vier konfigurierte Modelle.
- CPA Chat Completions: HTTP 200, Antwort `AGENTGATEWAY_OK`.
- CPA Responses: HTTP 200, Antwort `RESPONSES_OK`.
- Speichern über die UI-Konfigurations-API: HTTP 200, Konfiguration unverändert.
- Container-Neustart: Modellkonfiguration erhalten; erneuter Ansible-Deploy
  meldet `changed=0`.
- Ansible-Syntaxcheck und rollenbezogenes Ansible-Lint ohne Fehler/Warnungen.
- Lokaler Zugriff über SSH-Tunnel funktioniert; kein direkter LAN-Zugriff.
- HTTPS über Caddy: UI, Modellliste und Konfigurations-API erfolgreich.
- Beide Pi-holes lösen `agentgateway.kirelabs.org` auf `192.168.50.5` auf.
- Lokale Inferenz, Gemini, MCP, Streaming und Toolcalls noch nicht getestet.
- Visueller Browser-Test nicht erfolgt: dem T3-Browser fehlen Systembibliotheken.

Upstream: [Docker](https://agentgateway.dev/docs/standalone/latest/documentation/setup/install/docker/),
[UI-Konfigurationsspeicher](https://agentgateway.dev/docs/standalone/latest/documentation/setup/storage/).
