/** German translations for the sign-in screen (English source strings as keys). */
const PAIRS: [string, string][] = [
  ['Welcome to kernel', 'Willkommen bei kernel'],
  ['The operating system for your organization.', 'Das Betriebssystem für Ihre Organisation.'],
  ['Connecting people, projects, knowledge and intelligence.', 'Menschen, Projekte, Wissen und Intelligenz verbinden.'],
  ['Sign in with your account to continue.', 'Melden Sie sich mit Ihrem Konto an, um fortzufahren.'],
  ['Enter your email address.', 'Geben Sie Ihre E-Mail-Adresse ein.'],
  ['Enter a valid email address.', 'Geben Sie eine gültige E-Mail-Adresse ein.'],
  ['Enter your password.', 'Geben Sie Ihr Passwort ein.'],
  ['Show password', 'Passwort anzeigen'],
  ['Hide password', 'Passwort verbergen'],
]

export const DE_LOGIN: Record<string, string> = Object.fromEntries(PAIRS)
