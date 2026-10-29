/** German translations for the sales and management modules (English source strings as keys). */
export const DE_SALES: Record<string, string> = {
  // navigation and stages
  'Sales': 'Vertrieb', 'Pipeline': 'Pipeline', 'Lead': 'Anfrage', 'Qualification': 'Qualifizierung', 'Bid / No-Bid': 'Bid / No-Bid', 'Proposal': 'Angebot', 'Negotiation': 'Verhandlung',
  'Won': 'Gewonnen', 'Lost': 'Verloren', 'Contract': 'Vertrag', 'Process': 'Prozess', 'done': 'erledigt', 'current': 'aktuell', 'pending': 'offen',
  // pipeline page
  'Sales pipeline': 'Vertriebspipeline', 'Opportunities from first contact to a won project. Drag a card to another column to change its stage.': 'Chancen vom ersten Kontakt bis zum gewonnenen Projekt. Ziehen Sie eine Karte in eine andere Spalte, um die Phase zu ändern.',
  'New opportunity': 'Neue Chance', 'Open opportunities': 'Offene Chancen', 'Overdue': 'Überfällig', 'Next action or decision date passed': 'Nächste Aktion oder Entscheidungstermin überschritten',
  'Weighted pipeline': 'Gewichtete Pipeline', 'Calculated: value x probability': 'Berechnet: Wert × Wahrscheinlichkeit', 'Win rate': 'Gewinnquote', 'Won / (won + lost)': 'Gewonnen / (gewonnen + verloren)',
  'Search title, number, customer ...': 'Titel, Nummer, Kunde suchen …', 'Overdue only': 'Nur überfällige', 'Board': 'Board', 'List': 'Liste', 'Pipeline board': 'Pipeline-Board',
  'Drop a card here': 'Karte hier ablegen', 'Nothing yet': 'Noch nichts', 'Move': 'Verschieben', 'Probability': 'Wahrscheinlichkeit', 'high risk': 'hohes Risiko', 'Project': 'Projekt',
  'Action overdue': 'Aktion überfällig', 'Decision overdue': 'Entscheidung überfällig', 'Opportunity': 'Chance', 'Customer': 'Kunde', 'Stage': 'Phase', 'Value': 'Wert', 'Decision': 'Entscheidung',
  'Owner': 'Verantwortlich', 'Next action': 'Nächste Aktion', 'overdue': 'überfällig', 'Calculated': 'Berechnet', 'Weighted value': 'Gewichteter Wert', 'manual': 'manuell', 'stage default': 'Phasenstandard',
  // opportunity form
  'Edit opportunity': 'Chance bearbeiten', 'Title': 'Titel', 'Choose customer': 'Kunde wählen', 'Risk': 'Risiko', 'low': 'niedrig', 'medium': 'mittel', 'high': 'hoch', 'Circle': 'Kreis',
  'Expected value': 'Erwarteter Wert', 'Currency': 'Währung', 'Probability %': 'Wahrscheinlichkeit %', 'Stage default': 'Phasenstandard', 'Effort (days)': 'Aufwand (Tage)', 'Expected decision': 'Erwartete Entscheidung',
  'Due': 'Fällig', 'Source': 'Quelle', 'Description': 'Beschreibung', 'Edit': 'Bearbeiten', 'Category': 'Kategorie', 'Any': 'Beliebig', 'Start': 'Beginn', 'End': 'Ende', 'Save': 'Speichern', 'Cancel': 'Abbrechen',
  // lost dialog
  'Mark as lost': 'Als verloren markieren', 'Reason': 'Grund',
  // detail
  'Back to pipeline': 'Zurück zur Pipeline', 'Opportunity not found': 'Chance nicht gefunden', 'Create project': 'Projekt anlegen', 'Open project': 'Projekt öffnen', 'Delete opportunity': 'Chance löschen',
  'Overview': 'Überblick', 'Activities': 'Aktivitäten', 'History': 'Verlauf', 'No history yet': 'Noch kein Verlauf', 'Facts': 'Eckdaten', 'Team and roles': 'Team und Rollen', 'No team assigned': 'Kein Team zugeordnet',
  'Responsible roles': 'Zuständige Rollen', 'A responsibility for a customer gives context. It does not grant decision authority.': 'Eine Zuständigkeit für einen Kunden liefert Kontext. Sie verleiht keine Entscheidungsbefugnis.',
  'Customer contacts': 'Kundenkontakte', 'No contacts linked': 'Keine Kontakte verknüpft', 'Technologies and references': 'Technologien und Referenzen', 'Nothing linked yet': 'Noch nichts verknüpft',
  'Contacts, team and references': 'Kontakte, Team und Referenzen', 'Our team': 'Unser Team', 'Choose contacts': 'Kontakte wählen', 'Choose people': 'Personen wählen', 'Technologies and topics': 'Technologien und Themen',
  'Choose entries': 'Einträge wählen', 'Reference projects': 'Referenzprojekte', 'Choose projects': 'Projekte wählen',
  // bid panel
  'Assessment': 'Bewertung', 'The score is guidance only. It never decides anything by itself.': 'Der Score dient nur der Orientierung. Er entscheidet nichts von allein.',
  'Strategic fit': 'Strategische Passung', 'Customer potential': 'Kundenpotenzial', 'Technical feasibility': 'Technische Machbarkeit', 'Capacity': 'Kapazität', 'Competence': 'Kompetenz', 'Margin': 'Marge',
  'Funding': 'Förderung', 'Reference value': 'Referenzwert', 'Reuse potential': 'Wiederverwendungspotenzial', 'Chance to win': 'Gewinnchance',
  '5 = fits our strategy very well': '5 = passt sehr gut zu unserer Strategie', '5 = high long-term potential': '5 = hohes langfristiges Potenzial', '5 = clearly feasible': '5 = klar machbar',
  '5 = people are available': '5 = Personen sind verfügbar', '5 = we have the skills': '5 = wir haben die Kompetenz', '5 = very low risk': '5 = sehr geringes Risiko', '5 = very attractive margin': '5 = sehr attraktive Marge',
  '5 = funding is secured': '5 = Förderung ist gesichert', '5 = strong reference': '5 = starke Referenz', '5 = results are reusable': '5 = Ergebnisse sind wiederverwendbar', '5 = very likely': '5 = sehr wahrscheinlich',
  'Rating': 'Bewertung', 'Weight': 'Gewicht', 'Comment': 'Kommentar', 'Comment or evidence': 'Kommentar oder Nachweis', 'Save assessment': 'Bewertung speichern', 'Who may decide': 'Wer darf entscheiden',
  'Clarification required: no decision rule applies. Only an administrator can decide, with a note.': 'Klärung erforderlich: Es gilt keine Entscheidungsregel. Nur Administratoren können mit Vermerk entscheiden.',
  'holders': 'Rolleninhaber', 'unfilled': 'unbesetzt', 'The responsible role is not filled. Clarification required.': 'Die zuständige Rolle ist nicht besetzt. Klärung erforderlich.', 'You hold a deciding role.': 'Sie haben eine entscheidungsberechtigte Rolle.',
  'administrator override': 'Administrator-Entscheidung', 'Rationale': 'Begründung', 'Conditions': 'Bedingungen', 'Administrator note': 'Administrator-Vermerk', 'Only the holders of the roles above can decide.': 'Nur die Inhaber der oben genannten Rollen können entscheiden.',
  'Bid': 'Bid', 'No-Bid': 'No-Bid', 'Needs clarification': 'Klärung erforderlich', 'bid': 'Bid', 'no bid': 'No-Bid', 'clarify': 'Klärung',
  // convert dialog
  'Create project from opportunity': 'Projekt aus Chance anlegen', 'Create a new customer project': 'Neues Kundenprojekt anlegen', 'Fill an existing project': 'Bestehendes Projekt ergänzen', 'Choose project': 'Projekt wählen',
  'Choose circle': 'Kreis wählen', 'Only a won opportunity can be turned into a project.': 'Nur eine gewonnene Chance kann in ein Projekt umgewandelt werden.', 'This opportunity was already turned into a project.': 'Diese Chance wurde bereits in ein Projekt umgewandelt.',
  'There is no approved proposal. Work packages and budget cannot be taken over.': 'Es gibt kein freigegebenes Angebot. Arbeitspakete und Budget können nicht übernommen werden.', 'Choose the circle that will own the new project.': 'Wählen Sie den Kreis, dem das neue Projekt gehört.',
  'This project already originates from another opportunity.': 'Dieses Projekt stammt bereits aus einer anderen Chance.', 'Field': 'Feld', 'Current': 'Aktuell', 'From opportunity': 'Aus der Chance', 'Overwrite': 'Überschreiben',
  'will be set': 'wird gesetzt', 'fills an empty field': 'füllt ein leeres Feld', 'differs': 'weicht ab', 'Will be linked': 'Wird verknüpft', 'work packages': 'Arbeitspakete', 'milestones': 'Meilensteine',
  'catalog entries': 'Katalogeinträge', 'contacts': 'Kontakte', 'team': 'Team', 'contracts': 'Verträge', 'Fill project': 'Projekt ergänzen',
  'Classification': 'Klassifizierung', 'Budget': 'Budget', 'Name': 'Name',
  // activities
  'Log activity': 'Aktivität erfassen', 'Kind': 'Art', 'Subject': 'Betreff', 'Notes': 'Notizen', 'Create a follow-up task': 'Folgeaufgabe anlegen', 'Task': 'Aufgabe', 'No activities yet': 'Noch keine Aktivitäten',
  'Workshops, presentations and negotiations show up here.': 'Workshops, Präsentationen und Verhandlungen erscheinen hier.', 'Follow-up': 'Folgeaufgabe', 'workshop': 'Workshop', 'presentation': 'Präsentation', 'negotiation': 'Verhandlung',
  'call': 'Anruf', 'meeting': 'Termin', 'email': 'E-Mail', 'visit': 'Besuch', 'note': 'Notiz', 'todo': 'offen',
}
