# Roadmap Projektportfolio und CRM

Dieses Dokument trennt **umgesetzt** von **geplant**. Geplantes ist in der Oberfläche als „Geplant“ gekennzeichnet und enthält keine Scheindaten.

## Umgesetzt (Phase 1–2)

- Projektportfolio mit Klassifizierung, Phase, Forschung/Förderung, Arbeitspaketen und Ergebnissen (Soll/Ist)
- Strukturiertes Projektwissen mit Prüfstatus
- Technologie- und Kompetenzkatalog mit Aliasen, Duplikaterkennung und Zusammenführen
- Finanz- und Reportingdaten mit eingeschränkter Sichtbarkeit
- Referenzfreigaben je Inhaltsart und Referenzansicht
- CRM: Organisationen (mehrere Beziehungsarten, Hierarchie), Kontakte, Aktivitäten, Follow-up-Aufgaben, 360°-Sicht, Dashboard
- Kundenbezogene Rollenzuordnung (z. B. Key Account)
- Globale Suche über Projekte, Kunden, Kontakte und Katalog

## Geplant

| Phase | Inhalt | Stand |
|-------|--------|-------|
| 3 | Chancen und Pipeline, Angebote mit Positionen und Versionen, NDAs und Verträge mit Laufzeiten und Erinnerungen | nicht umgesetzt; Seiten zeigen „Geplant“ |
| 4 | Auswertungen und Prognosen über Pipeline und Portfolio | nicht umgesetzt |
| 5 | Dokumentenablage mit Datei-Upload, Dokumenten-Indexierung, KI-gestützte Suche und Antworten über Projektwissen (Retrieval) | nicht umgesetzt; Dokumente sind Links |

Das Datenmodell ist darauf vorbereitet: `project_knowledge` trägt Prüfstatus und `ai_draft`, `attachments` kann um Dateien erweitert werden, und alle Tabellen sind mandantenbezogen.
