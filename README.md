# scch/kernel

Das Betriebssystem für Ihre Organisation. Entwickelt vom Software Competence Center Hagenberg (SCCH).

Dieses README beschreibt, wie die Anwendung bereitgestellt (deployt) wird. Fachliche und technische Details stehen im Ordner [`docs/`](docs/README.md).

## Inhalt

1. [Architektur im Überblick](#architektur-im-überblick)
2. [Voraussetzungen](#voraussetzungen)
3. [Schnellstart mit Docker Compose](#schnellstart-mit-docker-compose)
4. [Konfiguration](#konfiguration)
5. [Produktivbetrieb hinter einem Reverse Proxy (HTTPS)](#produktivbetrieb-hinter-einem-reverse-proxy-https)
6. [Datenbank und Migrationen](#datenbank-und-migrationen)
7. [Updates einspielen](#updates-einspielen)
8. [Sicherung und Wiederherstellung](#sicherung-und-wiederherstellung)
9. [Überwachung](#überwachung)
10. [Sicherheits-Checkliste](#sicherheits-checkliste)
11. [Fehlersuche](#fehlersuche)
12. [Lokale Entwicklung](#lokale-entwicklung)

## Architektur im Überblick

Drei Container, gestartet über `docker-compose.yml`:

| Dienst | Image / Build | Aufgabe | Port |
|--------|---------------|---------|------|
| `frontend` | `./frontend` (Node 22 Build, danach nginx 1.27) | liefert die React-Anwendung aus und leitet `/api/` und `/health` an das Backend weiter | 80 im Container, 8080 am Host |
| `backend` | `./backend` (Python 3.12, FastAPI mit uvicorn) | REST-API, Anmeldung, Geschäftslogik, Migrationen beim Start | 8080 (nur im Compose-Netz) |
| `db` | `postgres:16-alpine` | persistente Daten im Volume `pgdata` | 5432 (nur im Compose-Netz) |

Nach außen ist nur das Frontend erreichbar. Browser und API teilen sich dieselbe Adresse: Das Frontend wird mit `VITE_API_URL=/api` gebaut, nginx reicht alle Anfragen unter `/api/` an `http://backend:8080` weiter. Dadurch braucht die Anwendung keine zweite öffentliche Adresse.

```
Browser --> frontend (nginx) --/api/--> backend (FastAPI) --> db (PostgreSQL)
```

## Voraussetzungen

- Docker Engine 24 oder neuer mit dem Compose-Plugin (`docker compose`)
- 2 GB freier Arbeitsspeicher und rund 2 GB Plattenplatz für Images und Datenbank
- Internetzugang beim ersten Build (Basis-Images, npm- und pip-Pakete)
- Für den Produktivbetrieb: eine Domain und ein Reverse Proxy, der HTTPS terminiert

## Schnellstart mit Docker Compose

```bash
# 1. Repository holen und hineinwechseln
git clone <repository-url> kernel
cd kernel

# 2. Geheimnisse erzeugen (Pflicht, ohne sie startet Compose nicht)
export JWT_SECRET=$(openssl rand -hex 32)
export POSTGRES_PASSWORD=$(openssl rand -hex 16)

# 3. Bauen und starten
docker compose up --build -d

# 4. Status prüfen
docker compose ps
curl -f http://localhost:8080/health
```

Danach ist die Anwendung unter <http://localhost:8080> erreichbar.

**Wichtig:** `JWT_SECRET` und `POSTGRES_PASSWORD` müssen bei jedem `docker compose`-Aufruf gesetzt sein, auch bei `down`, `logs` oder `up` nach einem Neustart des Servers. Am einfachsten legen Sie beide in eine `.env`-Datei neben `docker-compose.yml`; Compose liest sie automatisch. Diese Datei gehört nicht ins Repository.

```dotenv
# .env (Werte selbst erzeugen, nicht kopieren)
JWT_SECRET=<zufällige Zeichenfolge, mindestens 32 Bytes>
POSTGRES_PASSWORD=<zufälliges Passwort>
```

Wird `JWT_SECRET` nach dem ersten Start geändert, werden alle bestehenden Sitzungen ungültig. Wird `POSTGRES_PASSWORD` nach der ersten Initialisierung des Volumes geändert, muss das Passwort auch in der Datenbank geändert werden (`ALTER USER`), sonst kann das Backend nicht mehr verbinden.

## Konfiguration

Alle Einstellungen kommen aus Umgebungsvariablen des Backend-Containers. Die in `docker-compose.yml` gesetzten Werte sind für den lokalen Test gedacht; für den Produktivbetrieb passen Sie sie an.

| Variable | Pflicht | Standard | Bedeutung |
|----------|---------|----------|-----------|
| `DATABASE_URL` | ja | in Compose gesetzt | PostgreSQL-Verbindung, Format `postgresql://benutzer:passwort@host:5432/datenbank` |
| `JWT_SECRET` | ja | keiner | Schlüssel zum Signieren der Sitzungstoken |
| `ENVIRONMENT` | nein | `local` | `local`, `dev`, `staging` oder `prod`. Bei `prod` ist die API-Dokumentation (`/api/docs`) abgeschaltet; außerhalb von `local` sendet das Backend den HSTS-Header |
| `CORS_ORIGINS` | ja im Betrieb | `http://localhost:5173,http://localhost:3000` | Erlaubte Browser-Ursprünge, kommagetrennt. Muss die öffentliche Adresse enthalten, z. B. `https://kernel.example.org` |
| `REGISTRATION_MODE` | empfohlen | `open` | `closed` sperrt die Selbstregistrierung. In Compose ist `closed` gesetzt |
| `DEMO_LOGIN_ENABLED` | empfohlen | `true` | `false` schaltet den Demo-Schnellzugang ab |
| `APP_ENCRYPTION_KEY` | nein | `JWT_SECRET` | Schlüssel für gespeicherte KI-Zugangsdaten. Ohne Angabe wird `JWT_SECRET` verwendet; wer ihn trennt, kann `JWT_SECRET` rotieren, ohne gespeicherte Zugangsdaten zu verlieren |
| `APP_NAME` | nein | `scch/kernel` | Anzeigename in API-Titel und Meldungen |
| `DEBUG` | nein | `false` | `true` erhöht die Log-Ausführlichkeit |
| `DATABASE_SCHEMA` | nein | Standard-Schema | Schema für die Migrationen, falls nicht `public` |
| `TRUSTED_PROXY_HOPS` | nein | `0` | Anzahl vertrauenswürdiger Reverse Proxies vor dem Backend (für die Erkennung der Client-Adresse bei der Anfragebegrenzung) |
| `RATE_LIMIT_STORAGE_URI` | nein | `memory://` | Speicher der Anfragebegrenzung. Bei mehr als einer Backend-Instanz einen gemeinsamen Speicher (z. B. Redis) angeben |
| `HOST`, `PORT` | nein | `0.0.0.0`, `8080` | Bindung des Backends im Container |

Geheimnisse gehören in eine `.env`-Datei, in ein Secret-Management oder in die Umgebung der Laufzeitplattform, nie in Git.

## Produktivbetrieb hinter einem Reverse Proxy (HTTPS)

Der mitgelieferte nginx im Frontend-Container spricht nur HTTP. Für den Produktivbetrieb stellen Sie einen Reverse Proxy (nginx, Traefik, Caddy, Load Balancer) davor, der HTTPS terminiert und an Port 8080 des Hosts weiterreicht.

1. In `docker-compose.yml` den Port auf die lokale Schnittstelle begrenzen, damit nur der Proxy zugreifen kann:
   ```yaml
   frontend:
     ports:
       - "127.0.0.1:8080:80"
   ```
2. Im Backend die öffentliche Adresse eintragen:
   ```yaml
   backend:
     environment:
       CORS_ORIGINS: https://kernel.example.org
       TRUSTED_PROXY_HOPS: "1"
   ```
3. Der Proxy muss `Host`, `X-Forwarded-For` und `X-Forwarded-Proto` weitergeben.

Beispiel für nginx als vorgeschalteter Proxy:

```nginx
server {
  listen 443 ssl http2;
  server_name kernel.example.org;

  ssl_certificate     /etc/ssl/kernel/fullchain.pem;
  ssl_certificate_key /etc/ssl/kernel/privkey.pem;

  client_max_body_size 25m;

  location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}

server {
  listen 80;
  server_name kernel.example.org;
  return 301 https://$host$request_uri;
}
```

## Datenbank und Migrationen

- Das Schema liegt als versionierte SQL-Dateien in `backend/migrations/` (`V001__...sql` und folgende).
- Das Backend wendet beim Start alle noch nicht angewendeten Migrationen an. Schlägt eine Migration fehl, startet das Backend nicht; der Fehler steht in `docker compose logs backend`.
- Migrationen sind additiv und gelten für jede Installation, auch für bestehende Daten.
- Bei mehreren Backend-Instanzen starten Sie zuerst eine Instanz, warten auf `/ready` und skalieren erst dann.
- Die Daten liegen im benannten Volume `pgdata`. `docker compose down` behält es, `docker compose down -v` löscht es unwiderruflich.

### Erster Start und Demodaten

Ist die Datenbank beim Start leer (keine Organisation vorhanden), legt das Backend eine klar gekennzeichnete Demoorganisation mit 12 Personen und 18 Rollen an. Die Demokonten teilen ein in der Anwendung dokumentiertes Passwort.

Für eine echte Installation gilt:

- `DEMO_LOGIN_ENABLED=false` setzen, damit die Schnellanmeldung auf der Startseite verschwindet.
- `REGISTRATION_MODE=closed` beibehalten.
- Die Demoorganisation nicht für echte Daten verwenden. Einen eigenen Weg, beim ersten Start statt der Demodaten ein leeres Administratorkonto anzulegen, gibt es derzeit nicht. Das ist eine bekannte Einschränkung (siehe [`docs/operations.md`](docs/operations.md)).

## Updates einspielen

```bash
git pull
docker compose up --build -d
docker compose logs -f backend   # Migrationen und Start beobachten
curl -f http://localhost:8080/ready
```

Vor jedem Update eine Sicherung ziehen (siehe nächster Abschnitt). Für ein Rücksetzen auf die vorige Version: Code auf den früheren Stand bringen, neu bauen und die Datenbank aus der Sicherung wiederherstellen, da Migrationen nicht automatisch zurückgenommen werden.

## Sicherung und Wiederherstellung

Alle Daten liegen in PostgreSQL.

```bash
# Sicherung (täglich empfohlen)
docker compose exec -T db pg_dump -U circleos -d circleos --format=custom > kernel-$(date +%F).dump

# Wiederherstellung in eine leere Datenbank
docker compose stop backend
docker compose exec -T db pg_restore -U circleos -d circleos --clean --if-exists < kernel-2026-01-31.dump
docker compose start backend
```

Benutzer und Datenbank heißen in `docker-compose.yml` weiterhin `circleos`; das ist ein technischer Bezeichner und verändert die Anwendung nicht. Bewahren Sie Sicherungen getrennt vom Server auf und testen Sie die Wiederherstellung regelmäßig. Zusätzlich bietet die Administration einen JSON-Export der Organisationsdaten.

## Überwachung

| Endpunkt | Zweck | Prüft die Datenbank |
|----------|-------|---------------------|
| `GET /health` | Liveness: der Prozess läuft | nein |
| `GET /ready` | Readiness: bereit für Anfragen | ja |

- `/health` ist auch über das Frontend erreichbar (`http://<host>:8080/health`); `/ready` und alle anderen Endpunkte erreichen Sie unter `/api/...` oder direkt am Backend-Container.
- Compose prüft das Backend selbst per Healthcheck; das Frontend startet erst, wenn das Backend gesund ist.
- Jede Antwort trägt einen `X-Request-ID`-Header. Dieselbe Kennung steht in den Backend-Logs und erlaubt, einen Fehler von der Fehlermeldung bis zur Log-Zeile zu verfolgen.
- Logs: `docker compose logs -f backend`.
- Fehlerantworten haben immer die Form `{ "error": { "code", "message", "field", "details" } }`.

## Sicherheits-Checkliste

- [ ] `JWT_SECRET` und `POSTGRES_PASSWORD` sind zufällig, lang und nicht im Repository
- [ ] `ENVIRONMENT=prod`
- [ ] HTTPS am Reverse Proxy, Port 8080 nur lokal gebunden
- [ ] `CORS_ORIGINS` enthält nur die echte Adresse
- [ ] `REGISTRATION_MODE=closed`
- [ ] `DEMO_LOGIN_ENABLED=false`
- [ ] Datenbank-Port 5432 ist nicht veröffentlicht (im mitgelieferten Compose-File ist er es nicht)
- [ ] `TRUSTED_PROXY_HOPS` passt zur Anzahl der Proxies
- [ ] Sicherungen laufen und eine Wiederherstellung wurde getestet
- [ ] Images werden regelmäßig neu gebaut, um Sicherheitsupdates der Basis-Images zu erhalten

Das Backend setzt von sich aus Sicherheits-Header (u. a. `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, HSTS außerhalb von `local`) und begrenzt Anfragen pro Client. Die Sitzungen sind zustandslose JWTs; eine serverseitige Sperrliste gibt es noch nicht, ein Widerruf erfolgt daher durch Wechsel von `JWT_SECRET`.

## Fehlersuche

| Symptom | Ursache und Lösung |
|---------|-------------------|
| `set JWT_SECRET` oder `set POSTGRES_PASSWORD` beim Start | Variable nicht gesetzt. In der Shell exportieren oder in `.env` eintragen |
| Backend startet nicht, Log zeigt Migrationsfehler | Fehlermeldung in `docker compose logs backend` lesen; Datenbank nicht von Hand ändern |
| Backend kann die Datenbank nicht erreichen | `POSTGRES_PASSWORD` passt nicht zum bestehenden Volume, oder `db` ist noch nicht gesund (`docker compose ps`) |
| Anmeldung im Browser schlägt mit CORS-Fehler fehl | `CORS_ORIGINS` enthält nicht exakt die Adresse in der Browserzeile (Schema, Host, Port) |
| Nach Update bei allen Nutzern abgemeldet | `JWT_SECRET` wurde geändert |
| `/api/docs` liefert 404 | gewollt bei `ENVIRONMENT=prod` |
| Fehler 429 | Anfragebegrenzung; bei Proxy-Betrieb `TRUSTED_PROXY_HOPS` prüfen, sonst zählen alle Nutzer unter der Proxy-Adresse zusammen |
| 502 vom Frontend | Backend läuft nicht oder ist nicht gesund: `docker compose logs backend` |

## Lokale Entwicklung

Ohne Docker, mit zwei Terminals und einer lokalen PostgreSQL-Datenbank:

```bash
# Backend (Port 8080)
cd backend
pip install -r requirements.txt
export DATABASE_URL=postgresql://<benutzer>:<passwort>@localhost:5432/<datenbank>
export JWT_SECRET=$(openssl rand -hex 32)
PYTHONPATH=src uvicorn main:app --app-dir src --port 8080 --reload

# Frontend (Vite-Entwicklungsserver)
cd frontend
npm install
npm run dev
```

Tests:

```bash
cd backend && pytest -m "not integration"      # ohne Datenbank
cd frontend && npx vitest run
```

Weitere Hinweise zu Tests und bekannten Einschränkungen: [`docs/operations.md`](docs/operations.md).
