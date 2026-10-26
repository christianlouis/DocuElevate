# Evernote integration

DocuElevate supports Evernote as a per-user destination. Each integration stores
its developer token in the encrypted credentials field; notebook GUID, default
tags, metadata inclusion, and sandbox mode are ordinary per-user configuration.
The token is never taken from the operator's global settings for this path.

Create an Evernote developer token, choose the target notebook GUID, and use
**Test connection** before saving. The test only reads the account's notebook
list and does not create or modify notes. Uploaded PDFs are attached as an
Evernote resource and the note body retains escaped DocuElevate metadata in
ENML. Tags are normalized, deduplicated, and bounded to Evernote's limits.

The classic Evernote EDAM API and SDKs are deprecated and no longer developed,
but remain available for maintaining existing integrations. This connector is
therefore maintenance for existing valid credentials, not a new OAuth rollout.
See the [official legacy API notice](https://dev.evernote.com/legacy). ENEX
import is not part of this integration.
