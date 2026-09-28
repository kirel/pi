# Ponytail-Review des Migrationsplans

Stand: 2026-09-28. Geprüft: [Migrationsplan](service-topology-migration-plan.md).
Umfang: unnötige Komplexität; beide Empfehlungen sind in den Plan eingearbeitet.

- [x] `yagni:` Separate Gateway-Zuordnung entfernt. Endpunkte werden aus `services.litellm` und `services['litellm-local']` abgeleitet; Modellzuordnung bleibt in `llms.yml`, Standortauswahl in bestehenden Hostgruppen. Keine neue `group_vars/all/litellm.yml`.
- [x] `shrink:` Jeder MCP erhält `site: local` oder `site: cloud`. Die Auswahl erfolgt mit `site == litellm_site`; Listen für Mehrfachplatzierung entfallen.

Die beiden Review-Änderungen verkürzten die damalige Planfassung um eine Zeile; zusätzlich entfiel eine geplante Konfigurationsdatei. Spätere Ergänzungen zur Datensicherung sind in dieser Zeilenzahl nicht enthalten. Die Infrastruktur ist weiterhin unverändert.

net: -1 lines.
