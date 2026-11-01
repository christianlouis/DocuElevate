# OAuth- und App-Store-Vorbereitung

Stand: 1. November 2026. Dieses Dokument ist eine Arbeitsgrundlage für die Einreichung der **gehosteten DocuElevate-Instanz**. Es bescheinigt keine Freigabe durch Apple, Google, Dropbox oder Microsoft. Statuswerte in dieser Anleitung bedeuten: **PREPARED** = im Repository dokumentiert, **BLOCKED** = technische Arbeit oder Nachweis fehlt, **CONSOLE NOT INSPECTED** = kein Zugriff auf das jeweilige Entwicklerkonto. Jede selbst gehostete Instanz benötigt eigene Provider-Anwendungen und eigene Rücksprungadressen.

## Aktueller Bestand

| Bereich | Im Code vorhanden | Vor Einreichung nachzuweisen |
|---|---|---|
| Benutzer-SSO | Authentik sowie optionale Google-, Microsoft-, Apple- und Dropbox-Clients | Produktions-Clients, sichtbare Anmeldeknöpfe, Fehler- und Widerrufstests |
| Google Drive | `/google-drive-auth-start` → `/google-drive-callback` | Scope-Begründung, OAuth-Consent, Verifikation für eingeschränkte Drive-Scopes |
| Dropbox-Dateien | OAuth-Codeaustausch über `/dropbox-callback`; Social-Login unter `/social-callback/dropbox` | App Folder oder Full Dropbox begründen, minimale Berechtigungen, Production-Review |
| Microsoft OneDrive | `/onedrive-auth-start` → `/onedrive-callback`; verwendet `.default offline_access` | Tatsächliche Graph-Berechtigungen prüfen, Publisher Verification und Admin-Consent testen |
| Apple-Login | `/social-callback/apple` ist vorgesehen | Services ID, App ID, signiertes Client-Secret, Relay-Absender, native iOS-Anmeldung; **BLOCKED** bis getestet |
| iCloud Drive | Inoffizieller `pyicloud`-Zugang mit Apple-ID/App-Passwort | Entfernen oder durch nativen iCloud-Dokumentenfluss ersetzen; kein allgemeiner Apple-OAuth-Connector |

## Callback-Inventar der gehosteten Instanz

Diese Werte sind die Zielwerte für die Produktionsinstanz. Sie müssen im jeweiligen Portal exakt mit HTTPS eingetragen und anschließend gegen den tatsächlich ausgerollten Build getestet werden. Es wurden keine separaten Test-Redirect-URIs als konfiguriert bestätigt.

| Zweck | Produktions-Callback |
|---|---|
| Google Drive-Dateiverbindung | `https://app.docuelevate.org/google-drive-callback` |
| Microsoft OneDrive-Dateiverbindung | `https://app.docuelevate.org/onedrive-callback` |
| Dropbox-Dateiverbindung | `https://app.docuelevate.org/dropbox-callback` |
| Google/Microsoft/Apple/Dropbox Social Login | `https://app.docuelevate.org/social-callback/{provider}` (`{provider}` exakt durch `google`, `microsoft`, `apple` oder `dropbox` ersetzen) |
| Authentik/SSO | `https://app.docuelevate.org/oauth-callback` |

Bei selbst gehosteten Installationen werden diese Hostnamen vollständig durch die eigene öffentliche Basis-URL ersetzt. Callback-URLs dürfen nicht aus einem frei übergebenen Host-Header abgeleitet werden.

## Berechtigungen und Zweck

Google Drive wird abhängig von der Integration angefordert: `drive.file` für Exporte, `drive.readonly` für Quellen und `drive` nur dann, wenn eingehende Dateien nach Verarbeitung gelöscht werden sollen. Der umfassende Scope ist zu vermeiden, wenn die Funktion mit `drive.file` oder einem ausdrücklich ausgewählten Dateizugriff auskommt. Google führt `drive.readonly` und `drive` als eingeschränkte Scopes; serverseitige Speicherung oder Übertragung solcher Daten kann eine zusätzliche Sicherheitsprüfung erfordern. Siehe [Drive-Berechtigungen](https://developers.google.com/workspace/drive/api/guides/api-specific-auth) und [Google-Verifikation eingeschränkter Scopes](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification).

DocuElevate verwendet für Gmail derzeit IMAP. Es gibt im geprüften Anwendungscode keinen Gmail-API-OAuth-Scope. Ein künftiger Gmail-API-Connector darf deshalb erst beworben werden, wenn eigene Scopes, Datenflüsse und eine separate Google-Prüfung dokumentiert sind.

Für Dropbox muss vor dem Antrag festgehalten werden, ob die Anwendung nur einen App-Ordner oder das gesamte Dropbox-Konto benötigt. Ein Export in den App-Ordner ist der bevorzugte Minimalfall. Ein Watch Folder mit frei wählbaren bestehenden Ordnern kann Full Dropbox erfordern und braucht eine konkrete Begründung. Der [Dropbox Developer Guide](https://www.dropbox.com/developers/reference/developer-guide) verlangt außerdem eine nachvollziehbare Produktbeschreibung und Testanleitung.

Bei OneDrive ist `.default` kein ausreichender Berechtigungsnachweis. Die effektiven delegierten Graph-Rechte der App-Registrierung müssen mit den tatsächlich benötigten Dateioperationen abgeglichen werden. Für eine öffentliche Multi-Tenant-Anwendung sollte die Herausgeberverifikation vor dem Antrag abgeschlossen sein: [Microsoft Publisher Verification](https://learn.microsoft.com/en-us/entra/identity-platform/publisher-verification-overview). Der Status des Microsoft-Portals ist **CONSOLE NOT INSPECTED**.

## Portal-Checkliste

### Google Cloud

- Für Entwicklung, Test und Produktion getrennte OAuth-Clients beziehungsweise Projekte festlegen.
- Verifizierte Eigentümerschaft an `docuelevate.org`, Produktname, Logo, Startseite, Datenschutz- und Nutzungsbedingungen im OAuth-Consent-Screen hinterlegen.
- Die oben genannten Redirect-URIs exakt registrieren; keine lokalen oder unverschlüsselten Produktions-Callbacks verwenden.
- Nur die tatsächlich benötigten Drive-Scopes veröffentlichen und jede Quelle-/Ziel-/Löschoperation im Consent-Text erklären.
- OAuth-Verifikation für eingeschränkte Scopes beantragen. Wenn eingeschränkte Daten serverseitig gespeichert oder übertragen werden, die erforderliche jährliche Sicherheitsprüfung beziehungsweise CASA-Anforderung einplanen: [Restricted Scope Verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification).

### Dropbox

- App-Namen, Publisher, Website, Logo, Support-Kontakt und exakte Produktions-Callback-URL hinterlegen.
- App Folder bevorzugen; Full Dropbox nur für den nachgewiesenen Watch-Folder-Zweck beantragen.
- Die im Portal aktivierten Berechtigungen aus den tatsächlich ausgeführten Dateioperationen ableiten. Im Code ist kein zentraler, abschließend geprüfter Scope-Katalog dokumentiert; deshalb werden hier keine nicht verifizierten Scope-Namen behauptet.
- Die Testvorführung mit einem sauberen Testordner und einer Ablehnung der Zustimmung vorbereiten.
- Neue Apps bleiben im Development-Status. Sobald 50 verbundene Nutzer erreicht sind, muss innerhalb von zwei Wochen der Production-Review beantragt werden; andernfalls kann weiteres Verbinden eingefroren werden. Siehe [Dropbox Developer Guide](https://www.dropbox.com/developers/reference/developer-guide).

### Apple Developer

- App ID, Services ID, Domain und exakte Web-Callback-URL einrichten; für die iOS-App die Sign in with Apple Capability erst nach vorhandenem nativen Flow aktivieren.
- Client-Secret mit ES256 aus Team ID, Key ID und privatem Schlüssel erzeugen. `exp` maximal sechs Monate setzen und Rotation vor Ablauf automatisiert testen.
- Erstlogin (Name nur beim ersten Mal), erneute Anmeldung, „E-Mail-Adresse verbergen“ und Private-Relay-Zustellung testen.
- Account-Löschung mit Apple-Token-Widerruf sowie Verarbeitung von Account-Änderungs-/Löschbenachrichtigungen planen. Für in Korea registrierte Entwickler ist der Benachrichtigungsendpunkt verpflichtend; für alle anderen sollte er für robuste Kontolöschung ebenfalls vorgesehen werden.

### Microsoft Entra

- Verifizierte Herausgeberdomain und Publisher Verification einrichten.
- Delegierte Graph-Berechtigungen auflisten und mit den konkreten OneDrive-Operationen vergleichen; `.default` im Code darf keine unkontrolliert breite Berechtigungsmenge verbergen.
- Multi-Tenant-/Single-Tenant-Entscheidung, Admin-Consent, Testkonto und Widerruf dokumentieren.

## Apple: Login und iCloud getrennt behandeln

Für den Web-Login werden eine aktivierte App ID, eine zugeordnete Services ID, die registrierte Domain und exakt eingetragene HTTPS-Rücksprungadressen benötigt: [Apple Web-Konfiguration](https://developer.apple.com/help/account/capabilities/configure-sign-in-with-apple-for-the-web/). Das Server-Secret muss aus Team ID, Key ID und dem privaten Sign-in-with-Apple-Schlüssel als kurzlebiges signiertes JWT erzeugt und vor Ablauf erneuert werden. Private Schlüssel gehören ausschließlich in den geschützten Secret-Speicher; sie werden nicht in Dokumentation, Container-Images oder Client-Bundles aufgenommen. Apple-Portalstatus: **CONSOLE NOT INSPECTED**.

Der mobile Client besitzt derzeit keinen nachgewiesenen nativen Sign-in-with-Apple-Button und keine Apple-Capability. Vor einer App-Store-Einreichung ist deshalb entweder der native Flow mit Nonce- und Callback-Prüfung zu ergänzen oder die beworbene Anmeldung entsprechend zurückzunehmen. Kontolöschung muss aus der App initiiert werden; Apple-Tokens und Provider-Verknüpfungen sind dabei zu widerrufen: [Apple Account Deletion](https://developer.apple.com/help/app-review/guideline-reference/5-1-1-account-deletion).

„Apple Drive“ ist kein allgemeiner OAuth2-Dateispeicher wie Dropbox. Apple stellt für persönliche iCloud-Drive-Dateien keine öffentliche serverseitige REST-OAuth-Schnittstelle bereit. Der aktuelle `pyicloud`-Zugang mit Apple-ID/App-Passwort ist daher kein Einreichungsweg. Unterstützte Zielvarianten sind ein nativer iOS-Dokumenten-Picker für den vom Nutzer ausgewählten Import/Export oder ein eigener iCloud-Container für App-Daten: [iCloud Services](https://developer.apple.com/documentation/xcode/configuring-icloud-services/). Bis dahin darf die Produktseite keine allgemeine iCloud-Drive-Synchronisierung versprechen.

## Zugangsdatenmodell (Zielkontrollen vor Produktion)

Die gehostete Instanz soll eigene, zentral verwaltete Produktions-Clients verwenden. Als Zielkontrollen sind festzulegen: Client-Secrets, Apple-Schlüssel und Refresh-Tokens ausschließlich serverseitig verschlüsselt speichern; Rotation und Widerruf nachweisbar testen; bei Deinstallation oder Kontolöschung lokale Tokens löschen und Provider-Widerruf ausführen. Diese Kontrollen sind im aktuellen Status noch nicht als vollständig abgenommen markiert. Selbst gehostete Installationen konfigurieren eigene Client IDs, Secrets, Domains und Redirect-URIs; sie teilen keine zentralen Geheimnisse der gehosteten Instanz. Jede Redirect-URI wird als feste HTTPS-Adresse konfiguriert, nicht aus einem frei übermittelten Host-Header abgeleitet.

## Reviewer-Paket und Abnahmetests

### Evidence sheet (je Provider ausfüllen)

```text
Provider / App-ID:
Environment and public base URL:
Exact redirect URI(s):
Requested scopes / app permission type:
User-facing purpose and consent text:
Test account and clean test folder:
Successful flow evidence (link or capture):
Denied-consent and token-revocation evidence:
Disconnect and account-deletion evidence:
Console status: PREPARED / BLOCKED / CONSOLE NOT INSPECTED
Owner and date:
```

Für jeden Anbieter wird ein unveränderlicher Testdatensatz vorbereitet:

1. Testkonto und Testordner ohne echte personenbezogene Dokumente.
2. Screenshot oder Bildschirmaufzeichnung des Zustimmungsdialogs mit Zweck und angeforderten Scopes.
3. Erfolgreicher Login beziehungsweise Verbindung, anschließender Export/Import und sichtbare Fehlerbehandlung bei Ablehnung.
4. Prüfung von Tokenablauf, erneuter Zustimmung, Provider-Widerruf und „Verbindung trennen“.
5. Kontolöschung mit Nachweis, dass lokale Integrationen, Refresh-Tokens und Warteschlangen entfernt wurden.
6. Liste der exakten Produktions-Redirect-URIs, Domains, Bundle ID, Team ID sowie der verantwortlichen Kontaktadresse.
7. Öffentliche URLs für Datenschutz, Nutzungsbedingungen, Support und Kontolöschung; die Kontolöschungsseite ist derzeit nur eine Informations-/Übergangsanzeige, solange kein vollständiger automatisierter Löschablauf nachgewiesen ist.

Ein Antrag wird erst als bereit markiert, wenn diese Nachweise, die öffentlichen Datenschutz-/Nutzungsbedingungen und die Support- sowie Kontolöschungsseite auf der tatsächlich eingereichten Domain erreichbar sind. Offene Punkte bleiben als **BLOCKED** im Review-Tracker stehen; Dokumentation allein ersetzt keine technische Umsetzung oder Anbieterfreigabe.

## Offizielle Leitfäden

- [Google OAuth-Richtlinien](https://developers.google.com/identity/protocols/oauth2/policies)
- [Google Workspace User Data Policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy)
- [Apple Review Guidelines](https://developer.apple.com/app-store/review/guidelines/)
- [Apple Private Email Relay](https://developer.apple.com/documentation/signinwithapple/communicating-using-the-private-email-relay-service)
- [Dropbox Developer Guide](https://www.dropbox.com/developers/reference/developer-guide)

## Registrierung und Kontolebenszyklus im aktuellen Änderungsstand

Web und Mobile enthalten eine Registrierung mit aktuellen Zustimmungen, verpflichtender E-Mail-Verifikation und anschließender Einrichtung. SMTP und öffentliche Registrierung müssen auf dem Zielserver aktiviert sein. Social-Login-Konten bestätigen die aktuellen Bedingungen beim Abschluss der Einrichtung. Kontolöschung ist über Profil und `/account/delete` erreichbar; sie bereinigt verwaltete Daten und widerruft gespeicherte Apple-Grants. Details und Grenzen: [SignupReviewReadiness.md](SignupReviewReadiness.md), [AccountDeletion.md](AccountDeletion.md). Diese Implementierung ist erst nach Deployment und Geräteabnahme ein Produktionsnachweis. Die oben genannten Provider-Konsolen, nativen Apple-Freigaben und iCloud-Grenzen bleiben getrennte Prüfpunkte.
