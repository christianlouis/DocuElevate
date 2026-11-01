# Account deletion

## User journey

From **Profile → Delete account** in the web or mobile application, review the consequences and enter `DELETE MY ACCOUNT`. The public `/account/delete` page is also the external entry point for store listings; authentication is required to execute the operation. Cookie requests require CSRF protection and mobile requests use the existing bearer authentication.

`DELETE /api/account` accepts `{"confirmation":"DELETE MY ACCOUNT"}`. `GET /api/account` reports the authenticated account's lifecycle state. The server derives ownership from the authenticated canonical subject; it never accepts a target account in the request body.

## Removed data and safeguards

The service removes the account's managed document files, database documents and dependent processing records, profiles, integration credentials, tokens and sharing records. It removes document entries from configured search/vector indexes and revokes saved Apple refresh grants before completing deletion. Indirect pipeline and import records are included. Records belonging to another account are preserved; shared physical paths remain while another record references them.

Legal holds and unsafe filesystem paths block deletion. A durable deletion marker blocks normal authenticated use and queued processing. Background workers share an account lock; deletion waits for active work before cleaning data. PostgreSQL uses advisory locks; SQLite uses locks in the shared work directory. Other database engines require an explicit locking implementation before this feature is used.

If cleanup fails, the server returns an error, retains the cleanup manifest and keeps the account blocked. The original authenticated account can retry the deletion endpoint. A repeated completed request is idempotent. Failed deletion is never presented as success. Operators must monitor failures and complete retries rather than treating a blocked account as erased.

After completion, the retained marker contains a SHA-256 digest of the canonical account identifier, lifecycle state and timestamps. This is a pseudonymous prevention record, not an active profile; hashing does not make a predictable email identifier anonymous. The digest prevents old sessions and queued tasks from recreating the same account. Re-registration with that same canonical identity remains blocked.

## Boundaries and release evidence

Independent copies already exported to a user's Google Drive, Dropbox, OneDrive, email recipient or another destination are outside this operation. Their owners control their retention. Infrastructure backups and external provider logs follow separately configured retention policies. Operators must publish their actual backup expiry schedule and ensure restores reapply completed deletion markers before reopening access. Do not promise immediate erasure from backups.

Index cleanup currently requires reachable Meilisearch and Qdrant endpoints for accounts with documents, including when indexing has subsequently been disabled. A missing or unreachable endpoint keeps deletion in a failed, retryable state; operators must provide the historical index services before enabling this release.

Before release, test the deployed server and signed mobile build with a dedicated account: signup, email verification, first-run setup, upload and processing, sharing, deletion, failed-cleanup retry, denied access with old tokens and absence from configured indexes. Verify Apple revocation with a real test grant. Verify SQLite locks across workers sharing a work directory or PostgreSQL locks across worker processes. Confirm mobile cookie persistence during signup on an actual iOS device.

This implementation does not certify provider approval or attest production deployment. Developer-console credentials, domain verification, provider review evidence and store declarations are tracked in [OAuthProviderSubmissionGuide.md](OAuthProviderSubmissionGuide.md) and [SignupReviewReadiness.md](SignupReviewReadiness.md).
