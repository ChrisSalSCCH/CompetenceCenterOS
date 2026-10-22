# Architektur von CircleOS

## Technologie

Die gewünschte Kombination Angular, .NET und PrimeNG ist in dieser Umgebung nicht zuverlässig erzeugbar. CircleOS nutzt deshalb den unterstützten Stack und behält die Architektur, die Domänengrenzen und die Containerisierung bei:

| Schicht | Umsetzung |
|---------|-----------|
| Frontend | React 19, TypeScript, Tailwind v4, shadcn/ui, TanStack Query, d3-hierarchy (Kartenlayout), Recharts |
| Backend | FastAPI (modulare Router + Service-Schicht), OpenAPI unter `/api/docs` |
| Datenbank | PostgreSQL, versionierte SQL-Migrationen (`backend/migrations/V*.sql`) |
| Deployment | `docker-compose.yml`, je ein Dockerfile für Backend und Frontend, Health-Checks, Volume für die Datenbank |

## Backend-Module (`backend/src`)

- `routes/` – dünne HTTP-Schicht: `session`, `structure`, `governance`, `meetings`, `work`, `goals`, `people`, `search`, `ai`, `admin`.
- `services/ctx.py` – Mandant, Rolle des Aufrufers und Berechtigungsregeln. Jede Abfrage trägt `organization_id`.
- `services/governance.py` – Governance-Engine: Änderungsoperationen, Workflow-Regeln, Snapshots.
- `services/orgdata.py` – Lesemodelle der Struktur (aktuell und zu einem Stichtag).
- `services/search.py`, `services/analysis.py` – deterministische Suche, Überschneidungserkennung.
- `services/assistant.py`, `services/llm.py`, `services/secrets.py` – Circle Intelligence und anbieterunabhängige LLM-Schicht.
- `services/seed.py` – Demonstrationsorganisation (nur bei leerer Datenbank; per Admin zurücksetzbar).

## Berechtigungsmodell

| Stufe | Bedeutung |
|-------|-----------|
| `org_admin` | Benutzer, Einstellungen, Audit-Log, Export; darf jeden Kreis governen |
| `member` | arbeitet mit Aufgaben, Spannungen, Anträgen; liest die gesamte Organisation |
| `observer` | nur lesen |

Governance-Befugnis entsteht **nicht** durch irgendeine Rolle, sondern nur durch Rollen mit dem Merkmal `can_govern` im Kreis oder einem übergeordneten Kreis. Eine Rolle zu halten gibt nie Administratorrechte. Aufgaben und Projekte unterscheiden Ausführung (Person) und Verantwortung (Rolle).

## Governance

Strukturänderungen sind **Änderungsoperationen** (`create_/update_/delete_` für Kreise und Rollen). Der wirksame Workflow eines Kreises wird vom nächsten Vorfahren mit eigener Einstellung geerbt, sonst gilt die Organisationsvorgabe (`direct`, `approval`, `consent`, `holacracy`).

- Im Modus `direct` und mit Governance-Befugnis wird sofort geändert; sonst entsteht automatisch ein Antrag.
- Anträge durchlaufen die Stufen ihres Workflows (Holacracy: Antrag, klärende Fragen, Reaktionen, Einwände, Integration, Entscheidung).
- Die Annahme wendet alle Operationen in **einer** Transaktion an. Schlägt eine fehl, bleibt die Struktur unverändert. Abgelehnte Anträge ändern nichts.
- Jede angewendete Operation schreibt einen versionierten Vorher/Nachher-Snapshot nach `governance_changes` (inkl. Akteur, Antrag, Begründung). Daraus entsteht die Historie und die Strukturansicht zu einem beliebigen Datum (`GET /api/structure?as_of=`).
- Zyklen in verschachtelten Kreisen werden serverseitig verhindert (`would_create_cycle`).

## KI-Schicht

- Ohne LLM-Anbieter bleibt alles nutzbar: Suche und Antworten sind deterministisch und stammen aus den Organisationsdaten.
- Ein OpenAI-kompatibler Endpunkt (Hosted oder On-Premise) wird unter Administration konfiguriert. Der Schlüssel wird verschlüsselt gespeichert (`APP_ENCRYPTION_KEY`, sonst abgeleitet aus `JWT_SECRET`) und nie an den Browser geliefert.
- Die KI ändert nie selbst Governance-Daten. Rollenvorschläge sind Entwürfe, die der Nutzer als normalen Antrag einreicht.
- `GET /api/ai/capabilities` beschreibt die Werkzeuge; MCP, KI-Agenten mit Rollen und semantische Suche sind **geplant**.
