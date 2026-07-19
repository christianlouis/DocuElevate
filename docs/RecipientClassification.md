# Recipient classification

DocuElevate can identify the person or household a document addresses before
it is indexed. The result is an explainable **recipient set**: a joint tax
notice may belong to Christian and Julia, while a letter addressed to
"Familie Krakau" may belong to every configured household member.

## Security boundary

- Every identity profile, policy and decision belongs to exactly one tenant
  and one Tribe.
- Classification never loads candidates from another Tribe.
- Only Tribe administrators and routing managers can manage identity profiles
  or change the classifier policy.
- A decision is readable only when the requesting user may read the underlying
  document. A private document therefore does not leak its recipient or
  evidence to other Tribe members.
- The optional AI fallback can select only active profiles whose users are
  current members of that same Tribe.

## Signals and decisions

Deterministic matching runs first. Contract/customer identifiers, email
addresses and postal addresses are strongest. Names and aliases in extracted
recipient metadata are strong enough for automatic assignment; names that
appear only incidentally in document text go to review instead.

The persisted decision contains:

- `matched`, `ambiguous`, or `unmatched` status;
- all selected user and profile IDs;
- ranked candidates and the signal-level evidence;
- confidence, strategy and classifier version.

Thresholds and the optional fallback model are stored per Tribe in the
database. API and workers read them for each classification, so changes take
effect without restarting the application.

## API

All routes are below `/api/tribes/{tribe_id}/recipients`:

| Method and route | Purpose |
| --- | --- |
| `GET/POST /profiles` | List or create identities |
| `PUT /profiles/{profile_id}` | Update or pause an identity |
| `GET/PUT /policy` | Read or change thresholds and AI fallback |
| `POST /dry-run` | Preview a classification without saving a document |
| `GET /files/{file_id}/decision` | Read a permitted document's explanation |

Classification deliberately does not move or duplicate documents yet.
Per-user pipeline and destination routing is the next layer and consumes this
persisted recipient set.
