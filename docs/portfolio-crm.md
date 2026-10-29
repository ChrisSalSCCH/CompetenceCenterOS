# Projektportfolio und CRM

Stand: Phase 1–2 (Portfolio-Grundlage, CRM-Grundlage). Chancen, Angebote, NDAs und Verträge sind **nicht** umgesetzt (siehe `roadmap.md`).

## Leitprinzipien

- **Eine Projekt-Entität.** Das bestehende `projects` wurde erweitert (kein zweites Projektmodell). Aufgaben, Meilensteine, OKRs und Spannungen hängen weiter am selben Projekt.
- **Strukturiert statt Freitext.** Technologien, Branchen, Forschungsgebiete, Kompetenzen, Methoden, Anwendungsbereiche, Lösungstypen und wiederverwendbare Komponenten kommen aus einem kontrollierten Katalog (`catalog_entries`) mit Aliasen. Dieselben Einträge nutzen Projekte, Rollen und Kunden.
- **Eine Organisations-Entität im CRM.** Kunde, Interessent, Partner, Forschungspartner, Fördergeber, Lieferant und Wettbewerber sind Beziehungsarten (`relation_types`) derselben `crm_organizations`, nicht getrennte Tabellen.
- **Verantwortung über Rollen.** Eine Rollenbesetzung kann einem Kunden oder Projekt zugeordnet werden (`crm_role_scopes`, z. B. Key Account). Der Geltungsbereich liefert Kontext, verleiht aber **keine** Entscheidungsbefugnis.
- **Berechnet ist gekennzeichnet.** Förderquote, Restbudget, Budgetverbrauch, überfälliger Bericht und der Wissensstand werden berechnet und in der Oberfläche als „Berechnet“ markiert; erfasste Werte als „Erfasst“.

## Datenmodell

| Tabelle | Zweck |
|---------|-------|
| `projects` (erweitert) | `classification` (customer/internal), `category`, `phase` (idea … archived), `short_name`, `project_no` (eindeutig je Organisation), `org_unit`, `manager_id`, Forschungs- und Förderfelder, `ai_relevant`. Der bisherige `status` bleibt unverändert; die feinere Lebensphase steht in `phase`. |
| `project_finance`, `project_finance_viewers` | Budget, Förderung, Eigenanteil, Kosten, Erlöse, Berichtszyklus; getrennt gespeichert, damit sie als Einheit verborgen werden können. |
| `catalog_entries`, `catalog_aliases` | Kontrolliertes Vokabular. Eindeutig je Organisation, Art und normalisiertem Namen (Groß-/Kleinschreibung, Satzzeichen ignoriert; `Node.js` = `NodeJS`). Aliase zählen als Namen. |
| `project_catalog_links`, `role_catalog_links` | Verknüpfung von Projekten und Rollen mit Katalogeinträgen. |
| `project_work_packages`, `project_results` | Arbeitspakete und Ergebnisse mit Soll/Ist-Wert, Einheit, Status und Nachweis-Link. |
| `project_knowledge` | Wissensabschnitte (Geschäftskontext, Lösung, Herausforderungen, Ergebnisse, Wiederverwendung, Architektur, KI-Einsatz) mit Prüfstatus `unverified / verified / ai_draft / approved`, Prüfer und Zeitpunkt. |
| `project_relations` | Nachfolge, Vorgänger, Wiederverwendung, Verwandtschaft. |
| `project_communication` | Referenzfreigabe und welche Inhalte (Name, Logo, Bilder, Beschreibung, Ergebnisse) genutzt werden dürfen. |
| `crm_organizations`, `crm_contacts`, `crm_contact_orgs` | Organisationen mit Hierarchie, Kontakte mit mehreren Organisationen und Kontaktrolle. |
| `project_orgs`, `project_contacts` | Kunden, Partner, Fördergeber und Ansprechpartner je Projekt. |
| `crm_activities` | Gesprächs- und Besuchsprotokolle; ein Follow-up erzeugt eine normale Aufgabe (`tasks`). |
| `crm_role_scopes` | Rollenbesetzung → Kunde oder Projekt. |

Alle Tabellen tragen `organization_id`; Geschäftstabellen haben Audit-Felder und Soft-Delete (`deleted_at`). Dokumente an Projekten sind in dieser Version **Links** (`attachments`).

## Regeln (serverseitig erzwungen)

- Ein Kundenprojekt braucht mindestens eine verknüpfte Kundenorganisation (`CUSTOMER_REQUIRED`, 422). Das gilt beim Anlegen, beim Umstellen auf „Kunde“ und beim Ändern der Verknüpfungen.
- Katalog: Duplikate nach Name **oder Alias** werden mit 409 (`CATALOG_DUPLICATE`) abgelehnt. Verwendete Einträge werden nicht gelöscht, sondern zusammengeführt (nur Administratoren): Verknüpfungen wechseln zum Ziel, der alte Name bleibt als Alias.
- CRM: Duplikate nach Name oder UID, Kontakte nach E-Mail (409 `CRM_DUPLICATE`). Eine Organisation, die Kunde bestehender Kundenprojekte ist, kann nicht gelöscht oder von „Kunde“ umgestellt werden.
- Wird der Text eines verifizierten Abschnitts geändert, fällt er auf „ungeprüft“ zurück. „Verifiziert“ setzen Administratoren oder die Projektleitung, „Freigegeben“ ebenso; „KI-Entwurf“ und „ungeprüft“ darf jeder Schreibberechtigte setzen.
- Referenzfreigaben: Ohne `reference_allowed` werden alle Einzelfreigaben auf „nein“ gesetzt. Die Referenzansicht liefert nur freigegebene Inhalte; ohne Namensfreigabe erscheint „Vertrauliches Projekt (Branche)“.

## Berechtigungen

| Funktion | Administrator | Projektleitung | Projektteam / Rolleninhaber | Mitglied | Beobachter |
|----------|:---:|:---:|:---:|:---:|:---:|
| Projekt ansehen | ja | ja | ja | ja | ja |
| Projekt, Wissen, Katalogzuordnung ändern | ja | ja | ja | nein | nein |
| Finanzdaten sehen | ja | ja | nur wenn benannt | nur wenn benannt | nur wenn benannt |
| Finanzdaten ändern, Zugriff vergeben | ja | ja | nein | nein | nein |
| Katalog anlegen / Alias | ja | ja | ja | ja | nein |
| Katalog zusammenführen / löschen | ja | nein | nein | nein | nein |
| CRM-Organisationen, Kontakte, Aktivitäten schreiben | ja | ja | ja | ja | nein |
| Kontaktdaten (E-Mail, Telefon) sehen | ja | ja | ja | ja | **nein** (ausgeblendet) |

## Programmierschnittstelle

- `GET/POST /api/portfolio`, `GET/PATCH/DELETE /api/portfolio/{id}`, `GET /api/portfolio/references`, `GET /api/portfolio/{id}/history`
- Unterressourcen: `orgs`, `contacts`, `entries`, `knowledge/{section}`, `work-packages`, `results`, `finance`, `finance-viewers`, `communication`, `relations`, `documents`
- `GET/POST/PATCH/DELETE /api/catalog`, `GET /api/catalog/suggest`, `POST /api/catalog/{id}/aliases`, `POST /api/catalog/{id}/merge`, `GET/PUT /api/roles/{id}/competencies`
- `/api/crm/organizations`, `/api/crm/contacts`, `/api/crm/activities`, `/api/crm/role-scopes`, `/api/crm/dashboard`
- Die globale Suche (`GET /api/search`) liefert zusätzlich Projekte (inkl. Katalogeinträgen, Aliasen, Kunden, Wissen), Kunden, Kontakte und Katalogeinträge.

## Demonstrationsdaten

`services/seed_portfolio.py` legt – nur für die Demo-Organisation und nur, solange sie noch keine Katalogeinträge hat – fiktive Daten an: sieben Organisationen (Kunden, Forschungspartner, Fördergeber, Interessent), sechs Kontakte, drei Kundenprojekte und fünf interne Projekte, rund 28 Katalogeinträge mit Aliasen, Arbeitspakete, Ergebnisse, Finanzdaten, Referenzfreigaben, Aktivitäten und die Rolle „Key Account Manager“ mit Kundenzuordnung. Vorhandene Daten werden nie überschrieben.
