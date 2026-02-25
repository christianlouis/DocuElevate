# Licensing & Compliance

DocuElevate is released under the **Apache License 2.0**.  This document explains the project's own license, the obligations associated with third-party dependencies, and how compliance is maintained.

## Table of Contents

- [DocuElevate License](#docuelevate-license)
- [LGPL Dependencies](#lgpl-dependencies)
- [Third-Party Dependency Summary](#third-party-dependency-summary)
- [Compliance Checklist](#compliance-checklist)
- [Maintaining Compliance](#maintaining-compliance)

---

## DocuElevate License

DocuElevate is copyright © 2025 Christian Krakau-Louis and is distributed under the **Apache License, Version 2.0**.

```
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

The full license text is in [`LICENSE`](../LICENSE) at the root of the repository.

---

## LGPL Dependencies

One dependency requires special handling under its license:

### Paramiko (LGPL 2.1)

[Paramiko](https://github.com/paramiko/paramiko) is a Python implementation of the SSH protocol and is licensed under the **GNU Lesser General Public License (LGPL) v2.1**.

**Compliance obligations:**

1. **Source availability** — The source code for Paramiko is publicly available at `https://github.com/paramiko/paramiko`.  Users of DocuElevate have the right to obtain, modify, and redistribute Paramiko under the terms of the LGPL.

2. **License text** — A copy of the LGPL v2.1 is bundled with DocuElevate at `frontend/static/licenses/lgpl.txt` and is accessible at runtime via `/static/licenses/lgpl.txt`.

3. **Attribution** — DocuElevate's attribution page (`/attribution`) prominently credits Paramiko and links to its source repository and the LGPL license text.  The `NOTICE` file at the root of the repository also includes a formal LGPL attribution notice.

4. **No modification** — DocuElevate does not modify Paramiko's source code.  It is used as an unmodified library dependency installed via pip.  This means the "dynamic linking" exception applies, and DocuElevate's own Apache 2.0 license is not affected.

**In-app compliance endpoints:**

| URL | Description |
|-----|-------------|
| `/attribution` | Third-party attribution page listing all major dependencies |
| `/static/licenses/lgpl.txt` | Full LGPL v2.1 license text |
| `/licenses/lgpl.txt` | Alias served via the API |

---

## Third-Party Dependency Summary

The table below summarizes the licenses of DocuElevate's key runtime dependencies.  See `/attribution` in the application or the `NOTICE` file for the complete list.

| Package | License | Repository |
|---------|---------|------------|
| FastAPI | MIT | https://github.com/tiangolo/fastapi |
| Celery | BSD | https://github.com/celery/celery |
| Uvicorn | BSD | https://github.com/encode/uvicorn |
| SQLAlchemy | MIT | https://github.com/sqlalchemy/sqlalchemy |
| Pydantic | MIT | https://github.com/pydantic/pydantic |
| Alembic | MIT | https://github.com/sqlalchemy/alembic |
| OpenAI Python | MIT | https://github.com/openai/openai-python |
| pypdf | BSD | https://github.com/py-pdf/pypdf |
| Requests | Apache 2.0 | https://github.com/psf/requests |
| **Paramiko** | **LGPL 2.1** | https://github.com/paramiko/paramiko |
| Dropbox SDK | MIT | https://github.com/dropbox/dropbox-sdk-python |
| google-auth | Apache 2.0 | https://github.com/googleapis/google-auth-library-python |
| msal | MIT | https://github.com/AzureAD/microsoft-authentication-library-for-python |
| boto3 (AWS) | Apache 2.0 | https://github.com/boto/boto3 |
| Jinja2 | BSD | https://github.com/pallets/jinja |
| Tailwind CSS | MIT | https://github.com/tailwindlabs/tailwindcss |
| Redis (redis-py) | MIT | https://github.com/redis/redis-py |

> The canonical list is maintained in `requirements.txt` (runtime dependencies) and `requirements-dev.txt` (development tools).

---

## Compliance Checklist

Use this checklist when preparing a release or auditing the project:

- [ ] `LICENSE` file is present and contains the Apache 2.0 text.
- [ ] `NOTICE` file is present and includes the LGPL attribution notice for Paramiko.
- [ ] `frontend/static/licenses/lgpl.txt` contains the full LGPL v2.1 text.
- [ ] The `/attribution` page is accessible and lists Paramiko with a link to its source repository and the LGPL license.
- [ ] No new LGPL, GPL, or proprietary dependencies have been introduced without review.
- [ ] `safety check` passes with no known CVEs in runtime dependencies.
- [ ] `pip-licenses` output reviewed for any unexpected license changes after dependency updates.

### Checking Dependency Licenses

Install `pip-licenses` and generate a report:

```bash
pip install pip-licenses
pip-licenses --format=markdown --order=license
```

Flag any license that is:
- **GPL (not LGPL)** — Copyleft; may require open-sourcing DocuElevate itself if statically linked.
- **AGPL** — Network copyleft; distribution over a network triggers copyleft obligations.
- **Proprietary / commercial** — Requires a separate commercial agreement.

---

## Maintaining Compliance

### When Adding a New Dependency

1. Identify the license from `pip-licenses` or the package's PyPI page / README.
2. If the license is LGPL, GPL, AGPL, or proprietary, raise a discussion before merging.
3. If LGPL is approved:
   - Add an entry to `frontend/templates/attribution.html`.
   - Add an entry to the `NOTICE` file.
   - Bundle the license text in `frontend/static/licenses/` if not already present.
4. For all new dependencies, verify with `safety check` that the package has no known CVEs.

### Automated CVE Scanning

The CI pipeline runs `safety check` on every pull request.  Any newly introduced CVE will block the PR from merging.

```bash
# Run locally before submitting a PR
safety check
```

### Attribution Page

The application's built-in attribution page (`/attribution`) is defined in:
- Template: `frontend/templates/attribution.html`
- Route: `app/views/license_routes.py`

Keep this page up to date whenever dependencies change.
