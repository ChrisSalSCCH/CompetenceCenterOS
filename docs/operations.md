# Betrieb

## Lokal mit Docker Compose

```bash
export JWT_SECRET=$(openssl rand -hex 32)
export POSTGRES_PASSWORD=$(openssl rand -hex 16)
docker compose up --build
```

Frontend: http://localhost:8080 · API-Dokumentation: http://localhost:8080/api/docs (nur außerhalb von `ENVIRONMENT=prod`).

## Umgebungsvariablen (Namen, keine Werte)

| Variable | Zweck |
|----------|-------|
| `DATABASE_URL` | PostgreSQL-Verbindung des Backends |
| `JWT_SECRET` | Signatur der Sitzungstoken (Pflicht) |
| `APP_ENCRYPTION_KEY` | optional, Schlüssel für gespeicherte KI-Zugangsdaten |
| `REGISTRATION_MODE` | `closed` – Benutzer legt nur der Administrator an |
| `DEMO_LOGIN_ENABLED` | `false` schaltet den Demo-Schnellzugang ab |
| `CORS_ORIGINS` | erlaubte Browser-Ursprünge |
| `ENVIRONMENT` | `local`, `dev`, `staging`, `prod` |

## Gesundheitsprüfungen

`GET /health` (Liveness) und `GET /ready` (prüft die Datenbank).

## Sicherung und Wiederherstellung

Alle Daten liegen in PostgreSQL.

- Sicherung: `pg_dump --format=custom --file circleos.dump "$DATABASE_URL"` (täglich, Aufbewahrung nach Bedarf).
- Wiederherstellung: leere Datenbank anlegen, `pg_restore --clean --if-exists -d "$DATABASE_URL" circleos.dump`, Backend starten (Migrationen sind versioniert und wiederholbar).
- Zusätzlich: Administration, Daten, JSON-Export für fachliche Exporte einer Organisation.

## Demonstrationsdaten

Beim ersten Start ohne Organisation entsteht die klar gekennzeichnete Demoorganisation (12 Personen, 18 Rollen). Administratoren setzen sie unter Administration zurück. Alle Demokonten teilen ein dokumentiertes Demopasswort; für echte Installationen `DEMO_LOGIN_ENABLED=false` setzen und die Organisation nicht verwenden.

## Tests

- `pytest -m "not integration"` – Domänenregeln (Zyklen, Workflows, Suche, Ziele) und ein Lese-Smoke-Test über alle Endpunkte.
- Mit `TEST_DATABASE_URL`: Integrationstests für Transaktionen, Autorisierung und Mandantentrennung.
- `CIRCLEOS_WRITE_SMOKE=1` – optionaler Schreib-Smoke-Test, setzt die Demoorganisation danach zurück.
- `vitest` – Hilfsfunktionen, Diff-Darstellung und ein Rendertest der gesamten App.

## Bekannte Einschränkungen

- Rollenbesetzungen sind nicht versioniert; die historische Ansicht zeigt Kreise und Rollen, nicht die damalige Besetzung.
- Dokumente an Rollen und Aufgaben sind Links; Datei-Upload ist geplant.
- OIDC/Microsoft Entra ID, MCP, KI-Agenten, semantische Suche und Importe aus anderen Tools sind geplant und nicht umgesetzt.
- Sitzungen sind zustandslose JWTs; eine serverseitige Sperrliste ist noch nicht vorhanden.
