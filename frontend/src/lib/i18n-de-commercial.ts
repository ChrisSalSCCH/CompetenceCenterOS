/** German translations for proposals, NDAs, contracts, documents and sales settings (English source strings as keys). */
const PAIRS: [string, string][] = [
  // proposals
  ['Proposals', 'Angebote'], ['Proposal not found', 'Angebot nicht gefunden'], ['Every proposal keeps all its versions. Approved versions are locked.', 'Jedes Angebot behält alle seine Versionen. Freigegebene Versionen sind gesperrt.'],
  ['Status', 'Status'], ['Version', 'Version'], ['Total price', 'Gesamtpreis'], ['Valid until', 'Gültig bis'], ['No proposals yet', 'Noch keine Angebote'],
  ['Create proposals from an opportunity after a Bid decision.', 'Legen Sie Angebote nach einer Bid-Entscheidung aus einer Chance an.'], ['A Bid decision is required before a proposal can be created.', 'Für ein Angebot ist zuerst eine Bid-Entscheidung nötig.'],
  ['New proposal', 'Neues Angebot'], ['Create', 'Anlegen'], ['Versions', 'Versionen'], ['New revision', 'Neue Revision'], ['New alternative', 'Neue Alternative'], ['Compare versions', 'Versionen vergleichen'],
  ['locked', 'gesperrt'], ['This version is approved and locked since', 'Diese Version ist freigegeben und gesperrt seit'], ['Changes always create a new version.', 'Änderungen erzeugen immer eine neue Version.'],
  ['Request approval', 'Freigabe anfordern'], ['Mark as sent to customer', 'Als an den Kunden gesendet markieren'], ['Customer accepted', 'Kunde hat angenommen'], ['Customer declined', 'Kunde hat abgelehnt'], ['Withdraw proposal', 'Angebot zurückziehen'],
  ['draft', 'Entwurf'], ['in approval', 'in Freigabe'], ['approved', 'freigegeben'], ['submitted', 'gesendet'], ['accepted', 'angenommen'], ['rejected', 'abgelehnt'], ['withdrawn', 'zurückgezogen'], ['expired', 'abgelaufen'], ['superseded', 'ersetzt'],
  ['revision', 'Revision'], ['alternative', 'Alternative'],
  // approval
  ['Approval', 'Freigabe'], ['Approve', 'Freigeben'], ['Reject', 'Ablehnen'], ['Note', 'Vermerk'], ['Note (required when rejecting)', 'Vermerk (Pflicht beim Ablehnen)'],
  // version editor
  ['Content', 'Inhalt'], ['Label', 'Bezeichnung'], ['Summary', 'Zusammenfassung'], ['Scope of work', 'Leistungsumfang'], ['Assumptions', 'Annahmen'], ['Exclusions', 'Ausschlüsse'], ['Commercial terms', 'Kommerzielle Bedingungen'],
  ['Work packages and milestones', 'Arbeitspakete und Meilensteine'], ['Add work package', 'Arbeitspaket hinzufügen'], ['No work packages yet', 'Noch keine Arbeitspakete'], ['Code', 'Kürzel'], ['Milestone', 'Meilenstein'], ['Milestone due', 'Meilenstein fällig'],
  ['Calculation', 'Kalkulation'], ['Locked versions cannot be edited', 'Gesperrte Versionen sind nicht bearbeitbar'], ['Add line', 'Zeile hinzufügen'], ['Type', 'Art'], ['Price list', 'Preistabelle'], ['Work package', 'Arbeitspaket'],
  ['Qty', 'Menge'], ['Unit', 'Einheit'], ['Unit cost', 'Stückkosten'], ['Unit price', 'Stückpreis'], ['Curr.', 'Währ.'], ['Total', 'Summe'], ['Exchange rate', 'Wechselkurs'], ['Source of the rate', 'Quelle des Kurses'],
  ['1 unit of a foreign currency equals this many units of the version currency. The source is documented with the version.', '1 Einheit der Fremdwährung entspricht so vielen Einheiten der Versionswährung. Die Quelle wird mit der Version dokumentiert.'],
  ['Effort', 'Aufwand'], ['days', 'Tage'], ['Cost', 'Kosten'], ['labor', 'Personal'], ['material', 'Material'], ['travel', 'Reise'], ['external', 'Extern'], ['day', 'Tag'], ['hour', 'Stunde'], ['piece', 'Stück'], ['flat', 'Pauschale'], ['Remove', 'Entfernen'],
  // compare
  ['From version', 'Von Version'], ['To version', 'Auf Version'], ['Changed text fields', 'Geänderte Textfelder'], ['Work packages added', 'Arbeitspakete hinzugefügt'], ['Work packages removed', 'Arbeitspakete entfernt'], ['Lines added', 'Zeilen hinzugefügt'], ['Lines removed', 'Zeilen entfernt'],
  ['summary', 'Zusammenfassung'], ['scope text', 'Leistungsumfang'], ['assumptions', 'Annahmen'], ['exclusions', 'Ausschlüsse'], ['terms', 'Bedingungen'], ['currency', 'Währung'], ['label', 'Bezeichnung'],
  // NDAs
  ['NDAs', 'NDAs'], ['NDA', 'NDA'], ['New NDA', 'Neues NDA'], ['Confidentiality agreements per customer, with validity and coverage.', 'Geheimhaltungsvereinbarungen je Kunde, mit Laufzeit und Abdeckung.'],
  ['A signed NDA proves confidentiality. It does not release anything for publication or as a reference.', 'Ein unterzeichnetes NDA belegt die Vertraulichkeit. Es gibt nichts zur Veröffentlichung oder als Referenz frei.'],
  ['No NDAs yet', 'Noch keine NDAs'], ['Coverage', 'Abdeckung'], ['Valid from', 'Gültig ab'], ['NDA not found', 'NDA nicht gefunden'], ['Back to NDAs', 'Zurück zu den NDAs'], ['Terminate', 'Beenden'], ['Terms', 'Bedingungen'],
  ['Signed on', 'Unterzeichnet am'], ['Recipients', 'Empfänger'], ['Purpose', 'Zweck'], ['Covers', 'Gilt für'], ['Applies to the customer in general.', 'Gilt für den Kunden allgemein.'], ['Covers opportunities', 'Gilt für Chancen'], ['Choose opportunities', 'Chancen wählen'],
  ['Mutual', 'Gegenseitig'], ['One-way (we receive)', 'Einseitig (wir empfangen)'], ['One-way (we disclose)', 'Einseitig (wir offenbaren)'], ['not started', 'noch nicht gültig'], ['active', 'aktiv'], ['expiring', 'läuft bald ab'], ['terminated', 'beendet'], ['none', 'keines'],
  ['Record signature', 'Unterzeichnung erfassen'], ['Signatory', 'Unterzeichner'], ['Only needed if you do not hold a role that may sign. Only administrators can sign without such a role.', 'Nur nötig, wenn Sie keine unterzeichnungsberechtigte Rolle haben. Ohne eine solche Rolle können nur Administratoren unterzeichnen.'],
  ['No NDA for this customer yet', 'Noch kein NDA für diesen Kunden'], ['Manage NDAs', 'NDAs verwalten'], ['Manage contracts', 'Verträge verwalten'],
  // contracts
  ['Contracts', 'Verträge'], ['New contract', 'Neuer Vertrag'], ['Framework agreements, call-offs and project contracts.', 'Rahmenverträge, Abrufe und Projektverträge.'], ['No contracts yet', 'Noch keine Verträge'], ['Contract', 'Vertrag'], ['Projects', 'Projekte'],
  ['restricted', 'eingeschränkt'], ['Reminders', 'Erinnerungen'], ['Contract not found', 'Vertrag nicht gefunden'], ['Back to contracts', 'Zurück zu den Verträgen'],
  ['The conditions of this contract are only visible to its owner, the opportunity team and signing roles.', 'Die Konditionen dieses Vertrags sind nur für die verantwortliche Person, das Chancen-Team und Unterzeichnungsrollen sichtbar.'],
  ['Notice period (days)', 'Kündigungsfrist (Tage)'], ['renews automatically', 'verlängert sich automatisch'], ['Framework agreement', 'Rahmenvertrag'], ['Opportunity', 'Chance'], ['Projects covered', 'Erfasste Projekte'], ['No projects linked', 'Keine Projekte verknüpft'],
  ['Call-offs', 'Abrufe'], ['Payment milestones', 'Zahlungsmeilensteine'], ['Add', 'Hinzufügen'], ['No milestones yet', 'Noch keine Meilensteine'], ['Payment milestone', 'Zahlungsmeilenstein'], ['Amount', 'Betrag'],
  ['Amendment', 'Nachtrag'], ['Amendments', 'Nachträge'], ['No amendments', 'Keine Nachträge'], ['Change of value', 'Wertänderung'], ['New end date', 'Neues Enddatum'], ['Signed - apply value and term now', 'Unterzeichnet – Wert und Laufzeit jetzt anwenden'],
  ['signed', 'unterzeichnet'], ['until', 'bis'], ['None', 'Keine'], ['framework', 'Rahmenvertrag'], ['project', 'Projektvertrag'], ['service', 'Dienstleistung'], ['license', 'Lizenz'], ['planned', 'geplant'], ['invoiced', 'fakturiert'], ['paid', 'bezahlt'],
  ['expires soon', 'läuft bald ab'], ['notice deadline', 'Kündigungsfrist'], ['due soon', 'bald fällig'], ['in review', 'in Prüfung'],
  // settings
  ['Sales settings', 'Vertriebseinstellungen'], ['Probabilities, who may decide what, and the price list.', 'Wahrscheinlichkeiten, wer was entscheiden darf, und die Preistabelle.'], ['Read-only: only administrators change these settings.', 'Nur lesen: Diese Einstellungen ändern nur Administratoren.'],
  ['Probability per stage', 'Wahrscheinlichkeit je Phase'], ['Used for the weighted pipeline unless an opportunity has its own probability. Won is always 100%, lost 0%.', 'Wird für die gewichtete Pipeline verwendet, sofern eine Chance keine eigene Wahrscheinlichkeit hat. Gewonnen ist immer 100 %, verloren 0 %.'],
  ['Decision rules', 'Entscheidungsregeln'], ['Authority comes from the role a person holds, never from a job title. Without a matching rule, only an administrator can decide - with a recorded note.', 'Befugnis kommt aus der Rolle, die eine Person innehat, nie aus dem Jobtitel. Ohne passende Regel kann nur ein Administrator entscheiden – mit Vermerk.'],
  ['No decision rules yet', 'Noch keine Entscheidungsregeln'], ['Until rules exist, every decision is marked as needing clarification.', 'Solange keine Regeln existieren, ist jede Entscheidung als klärungsbedürftig markiert.'],
  ['Role', 'Rolle'], ['Step', 'Schritt'], ['New rule', 'Neue Regel'], ['New decision rule', 'Neue Entscheidungsregel'], ['Proposal approval', 'Angebotsfreigabe'], ['Contract signature', 'Vertragsunterzeichnung'], ['NDA signature', 'NDA-Unterzeichnung'],
  ['Role that decides', 'Entscheidende Rolle'], ['Choose role', 'Rolle wählen'], ['Value from', 'Wert ab'], ['Value up to', 'Wert bis'], ['Everything', 'Alles'], ['Applies to', 'Gilt für'], ['New entry', 'Neuer Eintrag'], ['New price list entry', 'Neuer Preistabelleneintrag'],
  ['No price list entries yet', 'Noch keine Preistabelleneinträge'], ['Entries have a validity period; a proposal only accepts entries that are valid today.', 'Einträge haben einen Gültigkeitszeitraum; ein Angebot akzeptiert nur heute gültige Einträge.'],
  ['Valid', 'Gültig'], ['open', 'offen'], ['Cost rate', 'Kostensatz'], ['Sell rate', 'Verkaufssatz'], ['Role label', 'Rollenbezeichnung'],
  // documents
  ['Documents', 'Dokumente'], ['New version', 'Neue Version'], ['Add document', 'Dokument hinzufügen'], ['Upload file', 'Datei hochladen'], ['Link', 'Link'], ['File', 'Datei'],
  ['The file goes straight to secure storage. Size and type are checked by the server.', 'Die Datei geht direkt in den geschützten Speicher. Größe und Typ prüft der Server.'], ['Confidentiality', 'Vertraulichkeit'], ['People with access', 'Personen mit Zugriff'],
  ['Restricted: the team of this record, administrators and the people listed.', 'Eingeschränkt: das Team dieses Datensatzes, Administratoren und die genannten Personen.'], ['Confidential: administrators, you and the people listed.', 'Vertraulich: Administratoren, Sie und die genannten Personen.'],
  ['Uploading ...', 'Wird hochgeladen …'], ['Upload failed', 'Upload fehlgeschlagen'], ['What changed?', 'Was hat sich geändert?'], ['No documents yet', 'Noch keine Dokumente'], ['Upload a file or link a document.', 'Laden Sie eine Datei hoch oder verknüpfen Sie ein Dokument.'],
  ['documents are hidden because you have no access', 'Dokumente sind ausgeblendet, weil Sie keinen Zugriff haben'], ['internal', 'intern'], ['confidential', 'vertraulich'], ['report', 'Bericht'], ['technical', 'Technisch'], ['contract', 'Vertrag'], ['nda', 'NDA'],
]

export const DE_COMMERCIAL: Record<string, string> = Object.fromEntries(PAIRS)
