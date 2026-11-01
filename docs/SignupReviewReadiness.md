# Signup- und Provider-Review-Readiness

Dieses Dokument beschreibt den derzeit implementierten Vertrag für öffentliche
Registrierung und die verbleibenden Freigaben für App-Store- und OAuth-Provider-
Prüfungen. Eine erfolgreiche technische Registrierung ist keine Zusage, dass ein
Provider die Anwendung bereits akzeptiert.

## Implementierter Vertrag

`GET /api/auth/capabilities` ist unauthentifiziert und liefert:

```json
{
  "local_signup": true,
  "smtp_configured": true,
  "csrf_token": "session-bound-token",
  "email_verification_required": true,
  "terms_version": "2026-11-01",
  "privacy_version": "2026-11-01",
  "terms_url": "/terms",
  "privacy_url": "/privacy",
  "account_deletion_url": "/account/delete"
}
```

Die Versionswerte sind Beispiele des in diesem Änderungsstand implementierten Legal-Stands und müssen
bei jeder Änderung der Texte gemeinsam mit den veröffentlichten Seiten erhöht
werden. `POST /api/auth/signup` akzeptiert nur Requests mit
`accept_terms=true`, `accept_privacy=true` und exakt den aktuell gemeldeten
Versionswerten. Version und UTC-Zeitpunkt werden am `LocalUser` gespeichert.

Cookie-basierte Clients laden zunächst die Capabilities mit `credentials: include` und senden den erhaltenen `csrf_token` im Header `X-CSRF-Token` zusammen mit demselben Session-Cookie. Die Antwort darf nicht zwischengespeichert werden. Native Geräte müssen die Cookie-Persistenz im Abnahmetest bestätigen.

SMTP ist für öffentliche Registrierung zwingend. Fehlt die Konfiguration oder
schlägt der Versand fehl, antwortet die API mit `503`; es wird kein aktivierter
Account angelegt. Nach erfolgreicher Registrierung bleibt der Account bis zum
Klick auf den Verifikationslink inaktiv. Mobile Clients können denselben
Endpoint nutzen, anschließend die Mail-Verifikation abwarten und sich mit dem
bestehenden Login anmelden.

Auch Social-Login-Konten müssen vor dem Abschluss des Onboardings
`POST /api/onboarding/complete` mit den vier Feldern `accept_terms`,
`accept_privacy`, `terms_version` und `privacy_version` bestätigen. Die
Versionen und Zeitpunkte werden in `UserProfile` gespeichert; veraltete oder
fehlende Zustimmungen führen zu `422` und setzen das Onboarding nicht auf
abgeschlossen.

Alle `/api/onboarding/*`-Endpunkte akzeptieren weiterhin Browser-Sessions und nun
auch einen gültigen `Authorization: Bearer ...`-Token. Die Identität wird durch
die zentrale Authentifizierung aufgelöst; ein fehlender oder ungültiger Token
bleibt `401`, und Daten werden immer auf diese Identität begrenzt.

## Freigaben vor Einreichung

- HTTPS, produktive Terms-/Privacy-Seiten, Supportkontakt und eine erreichbare
  Account-Löschung inklusive Bestätigung der Datenbereinigung prüfen.
- SMTP-Absender, SPF/DKIM/DMARC, Verifikationslink unter Produktions-Domain und
  Rate-Limits in der Zielumgebung konfigurieren; Testmail und abgelaufener Token
  müssen nachweisbar funktionieren.
- Apple Developer: App-ID, Sign in with Apple Service ID/Redirect-URLs,
  Return-URLs und Key/Team-Konfiguration eintragen; den privaten Relay-Mailfluss
  testen. Die iOS-App muss die Account-Löschung aus der App erreichbar machen.
- Google Cloud: OAuth consent screen, verifizierte Domain, Support-/Privacy-/Terms-
  URLs, iOS client und die exakten Redirect-URIs registrieren. Nur tatsächlich
  benötigte Scopes beantragen.
- Dropbox: App-Konsole, Redirect-URIs, minimale Scopes und Datenschutzerklärung
  hinterlegen; Zugriffsentzug und erneute Autorisierung testen.
- Weitere Provider (Microsoft/GitHub etc.) jeweils mit produktiver Redirect-URI,
  Supportkontakt, Datenschutzerklärung und Scope-Begründung konfigurieren.
- Für jeden Provider einen Testnutzer, Erstlogin, Abbruch, Logout,
  Kontoverknüpfung und Kontolöschung dokumentieren. Keine Client-Secrets in App,
  Repository oder Dokumentation ausliefern.

Die Provider-Konfiguration und Store-Einreichung bleiben umgebungs- und
kontospezifische Schritte; dieses Dokument ersetzt keine Prüfung in den
jeweiligen Konsolen.
