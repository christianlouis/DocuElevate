# Configuration Guide

DocuElevate is designed to be highly configurable through environment variables. This guide explains all available configuration options and how to use them effectively.

## Environment Variables

Configuration is primarily done through environment variables specified in a `.env` file.

### Core Settings

| **Variable**           | **Description**                                          | **Example**                    |
|------------------------|----------------------------------------------------------|--------------------------------|
| `DATABASE_URL`         | Path/URL to the SQLite database (or other SQL backend). | `sqlite:///./app/database.db`  |
| `REDIS_URL`            | URL for Redis, used by Celery for broker & result store. | `redis://redis:6379/0`         |
| `WORKDIR`              | Working directory for the application.                  | `/workdir`                     |
| `GOTENBERG_URL`        | Gotenberg PDF processing URL.                           | `http://gotenberg:3000`        |
| `EXTERNAL_HOSTNAME`    | The external hostname for the application.             | `docuelevate.example.com`      |
| `ALLOW_FILE_DELETE`    | Enable file deletion in the web interface (`true`/`false`). | `true`                      |

### Batch Processing Settings

Control how the `/processall` endpoint handles large batches of files to prevent overwhelming downstream APIs.

| **Variable**                      | **Description**                                                                                    | **Default** |
|-----------------------------------|----------------------------------------------------------------------------------------------------|-------------|
| `PROCESSALL_THROTTLE_THRESHOLD`   | Number of files above which throttling is applied. Files <= threshold are processed immediately.  | `20`        |
| `PROCESSALL_THROTTLE_DELAY`       | Delay in seconds between each task submission when throttling is active.                          | `3`         |

**Example Usage**: When processing 25 files with default settings:
- Files are staggered: file 0 at 0s, file 1 at 3s, file 2 at 6s, etc.
- Total queue time: (25-1) × 3 = 72 seconds
- Prevents API rate limit issues and ensures smooth processing

### Client-Side Upload Throttling

Control how the web UI queues and paces file uploads to avoid overwhelming the backend, especially when dragging large directories (potentially thousands of files) onto the upload area.

| **Variable**               | **Description**                                                                                                               | **Default** |
|----------------------------|-------------------------------------------------------------------------------------------------------------------------------|-------------|
| `UPLOAD_CONCURRENCY`       | Maximum number of files uploaded simultaneously from the browser.                                                            | `3`         |
| `UPLOAD_QUEUE_DELAY_MS`    | Delay in milliseconds between starting each upload slot. Staggers upload starts to smooth out server load.                   | `500`       |

**Adaptive back-off**: The browser automatically slows down if the server responds with HTTP 429 (Too Many Requests). It reads the `Retry-After` header, pauses the queue for the indicated time, doubles the inter-slot delay (exponential back-off, capped at 30 s), and reduces concurrency to 1. After 5 consecutive successes it gradually recovers toward the configured values.

**Example**: With `UPLOAD_CONCURRENCY=3` and `UPLOAD_QUEUE_DELAY_MS=500`, a directory of 5,000 files is uploaded ≈ 3 at a time with 500 ms pacing – the backend processes files at its own rate while the queue drains in the background without triggering API rate limits.

### File Upload Size Limits

**Security Feature**: Control file upload sizes to prevent resource exhaustion attacks. See [SECURITY_AUDIT.md](../SECURITY_AUDIT.md#5-file-upload-size-limits) for security details.

| **Variable**              | **Description**                                                                                              | **Default**   |
|---------------------------|--------------------------------------------------------------------------------------------------------------|---------------|
| `MAX_UPLOAD_SIZE`         | Maximum file upload size in bytes. Files exceeding this limit are rejected.                                | `1073741824` (1GB) |
| `MAX_SINGLE_FILE_SIZE`    | Optional: Maximum size for a single file chunk in bytes. Files exceeding this are split into smaller parts. | `None` (no splitting) |
| `MAX_REQUEST_BODY_SIZE`   | Maximum request body size in bytes for non-file-upload requests (JSON, form data, etc.). File uploads use `MAX_UPLOAD_SIZE` instead. | `1048576` (1MB) |

**Configuration Examples:**

```bash
# Default: Allow up to 1GB uploads, no splitting, 1MB JSON/form body limit
MAX_UPLOAD_SIZE=1073741824
MAX_REQUEST_BODY_SIZE=1048576

# Conservative: 100MB max, split files over 50MB
MAX_UPLOAD_SIZE=104857600
MAX_SINGLE_FILE_SIZE=52428800

# Large files: 2GB max, split files over 500MB
MAX_UPLOAD_SIZE=2147483648
MAX_SINGLE_FILE_SIZE=524288000
```

**File Splitting Behavior:**
- When `MAX_SINGLE_FILE_SIZE` is configured and a PDF exceeds this size, it is automatically split into smaller chunks
- **IMPORTANT:** Splitting is done at **PAGE BOUNDARIES**, not by byte position
  - Uses pypdf to properly parse PDF structure
  - Each output file is a complete, valid PDF containing whole pages
  - No risk of corrupted or broken PDF files
  - Pages are distributed across output files to stay under size limit
- Each chunk is processed sequentially as a separate task
- Only works for PDF files (images and office documents are converted to PDF first)
- Original file is removed after successful splitting
- Useful for very large PDFs to prevent memory issues during processing

**Use Cases:**
- **Default (1GB, no splitting)**: Suitable for most deployments handling typical documents
- **With splitting**: Recommended for servers with limited memory or when processing very large scanned documents
- **Higher limits**: For environments specifically designed to handle large architectural plans, books, or scanned archives

### IMAP Configuration

DocuElevate can monitor multiple IMAP mailboxes for document attachments. Each mailbox uses a numbered prefix (e.g., `IMAP1_`, `IMAP2_`).

| **Variable**                  | **Description**                                              | **Example**       |
|-------------------------------|--------------------------------------------------------------|-------------------|
| `IMAP1_HOST`                  | Hostname for first IMAP server.                             | `mail.example.com`|
| `IMAP1_PORT`                  | Port number (usually `993`).                                | `993`             |
| `IMAP1_USERNAME`              | IMAP login (first mailbox).                                 | `user@example.com`|
| `IMAP1_PASSWORD`              | IMAP password (first mailbox).                              | `*******`         |
| `IMAP1_SSL`                   | Use SSL (`true`/`false`).                                   | `true`            |
| `IMAP1_POLL_INTERVAL_MINUTES` | Frequency in minutes to poll for new mail.                  | `5`               |

### Authentication

| **Variable**            | **Description**                                               |
|-------------------------|---------------------------------------------------------------|
| `AUTH_ENABLED`          | Enable or disable authentication (`true`/`false`).           |
| `SESSION_SECRET`        | Secret key used to encrypt sessions and cookies (at least 32 chars). |
| `ADMIN_USERNAME`        | Username for basic authentication (when not using OIDC).     |
| `ADMIN_PASSWORD`        | Password for basic authentication (when not using OIDC).     |
| `ADMIN_GROUP_NAME`      | Group name in OIDC claims that grants admin access. Default: `admin`. |
| `AUTHENTIK_CLIENT_ID`   | Client ID for Authentik OAuth2/OIDC authentication.          |
| `AUTHENTIK_CLIENT_SECRET` | Client secret for Authentik OAuth2/OIDC authentication.    |
| `AUTHENTIK_CONFIG_URL`  | Configuration URL for Authentik OpenID Connect.             |
| `OAUTH_PROVIDER_NAME`   | Display name for the OAuth provider button.                  |

### Security Headers

DocuElevate supports HTTP security headers to improve browser-side security. **These headers are disabled by default** since most deployments use a reverse proxy (Traefik, Nginx, etc.) that already adds them. Enable only if deploying directly without a reverse proxy. See [Deployment Guide - Security Headers](DeploymentGuide.md#security-headers) for detailed configuration examples.

### Rate Limiting

DocuElevate implements rate limiting to protect against DoS attacks and API abuse. **Rate limiting is enabled by default** and uses Redis for distributed rate limiting across multiple workers.

#### Master Control

| **Variable**              | **Description**                                                                    | **Default** |
|---------------------------|------------------------------------------------------------------------------------|-------------|
| `RATE_LIMITING_ENABLED`   | Enable/disable rate limiting middleware. Recommended for production.               | `true`      |

#### Rate Limit Configuration

Rate limits are specified in the format `count/period`, where:
- `count` is the maximum number of requests allowed
- `period` is one of: `second`, `minute`, `hour`, `day`

| **Variable**           | **Description**                                                      | **Default**      | **Applies To**                          |
|------------------------|----------------------------------------------------------------------|------------------|-----------------------------------------|
| `RATE_LIMIT_DEFAULT`   | Default rate limit for all API endpoints                             | `100/minute`     | Most API endpoints                      |
| `RATE_LIMIT_UPLOAD`    | Rate limit for file upload endpoints (prevents resource exhaustion)  | `600/minute`     | `/api/ui-upload` and similar            |
| `RATE_LIMIT_AUTH`      | Stricter rate limit for authentication (prevents brute force)        | `10/minute`      | Login, authentication endpoints         |

**Note**: Processing endpoints (OCR, metadata extraction) use built-in queue throttling via Celery to control processing rates and prevent upstream API overloads. No additional API-level rate limit is configured for processing endpoints.

#### How Rate Limiting Works

1. **Per-User Tracking**: For authenticated requests, limits are enforced per user ID
2. **Per-IP Tracking**: For unauthenticated requests, limits are enforced per IP address
3. **429 Response**: When limit is exceeded, API returns `429 Too Many Requests` with `Retry-After` header
4. **Redis Backend**: Uses Redis for distributed rate limiting (required for multi-worker deployments)
5. **In-Memory Fallback**: Falls back to in-memory storage if Redis is unavailable (not recommended for production)

#### Configuration Example

```bash
# Enable rate limiting (recommended for production)
RATE_LIMITING_ENABLED=true

# Configure Redis for distributed rate limiting
REDIS_URL=redis://redis:6379/0

# Customize rate limits
RATE_LIMIT_DEFAULT=100/minute     # 100 requests per minute per user/IP
RATE_LIMIT_UPLOAD=600/minute      # 600 uploads per minute
RATE_LIMIT_AUTH=10/minute         # 10 auth attempts per minute (brute force protection)
```

#### Recommended Limits by Deployment Size

**Small Deployment (1-10 users)**:
```bash
RATE_LIMIT_DEFAULT=200/minute
RATE_LIMIT_UPLOAD=1200/minute
RATE_LIMIT_AUTH=20/minute
```

**Medium Deployment (10-100 users)**:
```bash
RATE_LIMIT_DEFAULT=100/minute
RATE_LIMIT_UPLOAD=600/minute
RATE_LIMIT_AUTH=10/minute
```

**Large Deployment (100+ users)**:
```bash
RATE_LIMIT_DEFAULT=50/minute
RATE_LIMIT_UPLOAD=300/minute
RATE_LIMIT_AUTH=5/minute
```

#### Disabling Rate Limiting (Development Only)

For development or testing, you can disable rate limiting:

```bash
RATE_LIMITING_ENABLED=false
```

**Warning**: Do not disable rate limiting in production environments.

#### Monitoring Rate Limits

When rate limits are exceeded, check application logs for details:

```
2024-02-10 16:00:00 - Rate limiting by user: testuser
2024-02-10 16:00:01 - Rate limit exceeded: 100 per 1 minute
```

For more information on handling rate-limited responses in API clients, see [API Documentation - Rate Limiting](API.md#rate-limiting).

---

## Security Headers Configuration

DocuElevate supports HTTP security headers to improve browser-side security. **These headers are disabled by default** since most deployments use a reverse proxy (Traefik, Nginx, etc.) that already adds them. Enable only if deploying directly without a reverse proxy. See [Deployment Guide - Security Headers](DeploymentGuide.md#security-headers) for detailed configuration examples.

#### Master Control

| **Variable**                | **Description**                                                         | **Default** |
|-----------------------------|-------------------------------------------------------------------------|-------------|
| `SECURITY_HEADERS_ENABLED`  | Enable/disable security headers middleware. Set to `true` if deploying without reverse proxy. | `false` |

#### Strict-Transport-Security (HSTS)

Forces browsers to use HTTPS for all future requests to this domain. **Only effective over HTTPS.**

| **Variable**                   | **Description**                                              | **Default**                              |
|--------------------------------|--------------------------------------------------------------|------------------------------------------|
| `SECURITY_HEADER_HSTS_ENABLED` | Enable HSTS header.                                          | `true`                                   |
| `SECURITY_HEADER_HSTS_VALUE`   | HSTS header value (max-age in seconds, subdomain support).  | `max-age=31536000; includeSubDomains`   |

**Common Values:**
- `max-age=31536000; includeSubDomains` (1 year, recommended for production)
- `max-age=300` (5 minutes, for testing)
- `max-age=63072000; includeSubDomains; preload` (2 years with HSTS preload)

#### Content-Security-Policy (CSP)

Controls which resources browsers are allowed to load. Helps prevent XSS attacks and code injection.

| **Variable**                  | **Description**                                              | **Default**                              |
|-------------------------------|--------------------------------------------------------------|------------------------------------------|
| `SECURITY_HEADER_CSP_ENABLED` | Enable CSP header.                                           | `true`                                   |
| `SECURITY_HEADER_CSP_VALUE`   | CSP policy directives.                                       | See below                                |

**Default Policy:**
```
default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:;
```

**Common Customizations:**
```bash
# Stricter CSP (remove 'unsafe-inline', use nonces)
SECURITY_HEADER_CSP_VALUE="default-src 'self'; script-src 'self'; style-src 'self';"

# Allow specific external domains
SECURITY_HEADER_CSP_VALUE="default-src 'self'; script-src 'self' https://cdn.example.com; style-src 'self' 'unsafe-inline';"
```

**Note:** The default policy includes `'unsafe-inline'` for compatibility with Tailwind CSS and inline JavaScript. For stricter security, use nonces or hashes.

#### X-Frame-Options

Prevents the page from being loaded in frames/iframes. Protects against clickjacking attacks.

| **Variable**                             | **Description**                          | **Default** |
|------------------------------------------|------------------------------------------|-------------|
| `SECURITY_HEADER_X_FRAME_OPTIONS_ENABLED` | Enable X-Frame-Options header.          | `true`      |
| `SECURITY_HEADER_X_FRAME_OPTIONS_VALUE`   | X-Frame-Options header value.           | `DENY`      |

**Valid Values:**
- `DENY` - Page cannot be displayed in a frame (most secure)
- `SAMEORIGIN` - Page can only be displayed in a frame on the same origin
- ~~`ALLOW-FROM uri`~~ - **Deprecated**: Page can only be displayed in a frame on the specified origin. This directive is deprecated in modern browsers; use CSP `frame-ancestors` directive instead.

#### X-Content-Type-Options

Prevents browsers from MIME-sniffing responses away from the declared content-type. Helps prevent XSS attacks.

| **Variable**                                    | **Description**                          | **Default** |
|-------------------------------------------------|------------------------------------------|-------------|
| `SECURITY_HEADER_X_CONTENT_TYPE_OPTIONS_ENABLED` | Enable X-Content-Type-Options header.   | `true`      |

**Note:** This header is always set to `nosniff` when enabled (no configuration needed).

#### Configuration Examples

**Reverse Proxy Deployment (Default - Traefik, Nginx):**
```bash
# Headers disabled by default - reverse proxy handles them
# SECURITY_HEADERS_ENABLED=false  # Can be omitted
```

**Direct Deployment (No Reverse Proxy):**
```bash
# Enable all security headers
SECURITY_HEADERS_ENABLED=true
SECURITY_HEADER_HSTS_ENABLED=true
SECURITY_HEADER_CSP_ENABLED=true
SECURITY_HEADER_X_FRAME_OPTIONS_ENABLED=true
SECURITY_HEADER_X_CONTENT_TYPE_OPTIONS_ENABLED=true
```

**Custom Configuration:**
```bash
# Enable headers but customize values
SECURITY_HEADERS_ENABLED=true
SECURITY_HEADER_HSTS_VALUE="max-age=300"  # 5 minutes for testing
SECURITY_HEADER_X_FRAME_OPTIONS_VALUE="SAMEORIGIN"  # Allow same-origin framing
SECURITY_HEADER_CSP_VALUE="default-src 'self'; script-src 'self' https://trusted-cdn.com;"
```

**See Also:**
- [Deployment Guide - Security Headers](DeploymentGuide.md#security-headers) for Traefik/Nginx examples
- [SECURITY_AUDIT.md](../SECURITY_AUDIT.md#infrastructure-security) for security rationale

### AI Provider & Model Selection

DocuElevate supports multiple AI providers for metadata extraction and OCR text refinement. Select the provider via `AI_PROVIDER` and configure the matching credentials below.

| **Variable**      | **Description**                                                       | **Default**        |
|-------------------|-----------------------------------------------------------------------|--------------------|
| `AI_PROVIDER`     | Active AI provider. See supported values below.                       | `openai`           |
| `AI_MODEL`        | Model name for the selected provider. Falls back to `OPENAI_MODEL` when not set. | *(unset)* |
| `OPENAI_MODEL`    | Default model name (used when `AI_MODEL` is not set).                 | `gpt-4o-mini`      |

**Supported `AI_PROVIDER` values**: `openai`, `azure`, `anthropic`, `gemini`, `ollama`, `openrouter`, `portkey`, `litellm`

---

#### OpenAI (default)

| **Variable**          | **Description**                                  | **Default**                      |
|-----------------------|--------------------------------------------------|----------------------------------|
| `OPENAI_API_KEY`      | OpenAI API key.                                  | *(required)*                     |
| `OPENAI_BASE_URL`     | API base URL. Change for compatible proxies.     | `https://api.openai.com/v1`      |

```bash
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

#### Azure OpenAI

| **Variable**                  | **Description**                              | **Default**    |
|-------------------------------|----------------------------------------------|----------------|
| `OPENAI_API_KEY`              | Azure OpenAI API key.                        | *(required)*   |
| `OPENAI_BASE_URL`             | Azure resource endpoint URL.                 | *(required)*   |
| `AZURE_OPENAI_API_VERSION`    | Azure OpenAI API version string.             | `2024-02-01`   |

```bash
AI_PROVIDER=azure
OPENAI_API_KEY=<azure-key>
OPENAI_BASE_URL=https://my-resource.openai.azure.com
AI_MODEL=gpt-4o   # deployment name in Azure
```

#### Anthropic Claude

| **Variable**        | **Description**          |
|---------------------|--------------------------|
| `ANTHROPIC_API_KEY` | Anthropic API key.       |

```bash
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
AI_MODEL=claude-3-5-sonnet-20241022
```

#### Google Gemini

| **Variable**      | **Description**            |
|-------------------|----------------------------|
| `GEMINI_API_KEY`  | Google AI Studio API key.  |

```bash
AI_PROVIDER=gemini
GEMINI_API_KEY=AIza...
AI_MODEL=gemini-1.5-pro
```

#### Ollama (local LLMs – CPU-friendly)

Run models locally using [Ollama](https://ollama.com). Recommended for CPU-only deployments:

| **Variable**       | **Description**                         | **Default**               |
|--------------------|-----------------------------------------|---------------------------|
| `OLLAMA_BASE_URL`  | Ollama server URL.                      | `http://localhost:11434`  |

```bash
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://ollama:11434   # Docker service name
AI_MODEL=llama3.2                     # or qwen2.5, phi3, etc.
```

Recommended models for document processing on CPU:

- **`llama3.2`** (3B) – good balance of speed and JSON output quality
- **`qwen2.5`** (3B/7B) – excellent at structured extraction
- **`phi3`** (3.8B) – strong reasoning, very fast on CPU

#### OpenRouter

[OpenRouter](https://openrouter.ai) provides access to 100+ models from a single endpoint using the `provider/model` name format.

| **Variable**            | **Description**                     | **Default**                       |
|-------------------------|-------------------------------------|-----------------------------------|
| `OPENROUTER_API_KEY`    | OpenRouter API key.                 | *(required)*                      |
| `OPENROUTER_BASE_URL`   | Override the gateway URL.           | `https://openrouter.ai/api/v1`    |

```bash
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
AI_MODEL=anthropic/claude-3.5-sonnet
```

#### Portkey AI Gateway

[Portkey](https://portkey.ai) is an AI gateway that adds observability, caching, fallbacks, and load balancing across 200+ models behind a single OpenAI-compatible endpoint.

| **Variable**          | **Description**                                                                                          | **Default**                      |
|-----------------------|----------------------------------------------------------------------------------------------------------|----------------------------------|
| `PORTKEY_API_KEY`     | Portkey account API key.                                                                                 | *(required)*                     |
| `PORTKEY_VIRTUAL_KEY` | Optional Virtual Key (stores provider credentials in Portkey vault, keeping them out of your env file). | *(unset)*                        |
| `PORTKEY_CONFIG`      | Optional saved Config ID (e.g. `pc-fallback-abc123`) for routing rules, fallbacks, and load balancing. | *(unset)*                        |
| `PORTKEY_BASE_URL`    | Override the Portkey gateway URL (for self-hosted deployments).                                         | `https://api.portkey.ai/v1`      |

```bash
AI_PROVIDER=portkey
PORTKEY_API_KEY=pk-...
PORTKEY_VIRTUAL_KEY=vk-openai-abc123   # optional – routes to your OpenAI key stored in Portkey
AI_MODEL=gpt-4o
```

Using a Config for fallback routing:
```bash
AI_PROVIDER=portkey
PORTKEY_API_KEY=pk-...
PORTKEY_CONFIG=pc-fallback-config-xyz  # applies your saved routing rules
AI_MODEL=gpt-4o
```

#### LiteLLM (aggregator proxy)

[LiteLLM](https://litellm.ai) provides a unified `provider/model` interface for 100+ LLMs including OpenAI, Anthropic, Gemini, Cohere, Ollama, and many more.

| **Variable**       | **Description**                                 | **Default**                   |
|--------------------|-------------------------------------------------|-------------------------------|
| `OPENAI_API_KEY`   | API key forwarded to LiteLLM (provider-specific). | *(depends on model)*        |
| `OPENAI_BASE_URL`  | Optional proxy/gateway URL.                     | `https://api.openai.com/v1`   |

```bash
AI_PROVIDER=litellm
AI_MODEL=anthropic/claude-3-5-sonnet-20241022
OPENAI_API_KEY=sk-ant-...   # passed as the api_key to LiteLLM
```

---

### OCR Providers

DocuElevate supports multiple OCR engines that can be used individually or in combination. Configure the list of active providers with `OCR_PROVIDERS` and tune each provider with the settings below.

#### Provider Selection

| **Variable**          | **Description**                                                                                   | **Default** |
|-----------------------|---------------------------------------------------------------------------------------------------|-------------|
| `OCR_PROVIDERS`       | Comma-separated list of OCR engines to use, e.g. `azure`, `mistral`, `azure,tesseract`.         | `azure`     |
| `OCR_MERGE_STRATEGY`  | Strategy for combining results from multiple providers: `ai_merge`, `longest`, or `primary`.     | `ai_merge`  |

**Supported `OCR_PROVIDERS` values**: `azure`, `tesseract`, `easyocr`, `mistral`, `google_docai`, `aws_textract`

When multiple providers are listed, all run in parallel and their results are merged according to `OCR_MERGE_STRATEGY`.

#### Embedded Text Quality Check

DocuElevate can automatically assess whether the text already embedded in a PDF is of sufficient quality before deciding to skip OCR. This prevents poor OCR output from a previous scan being silently used for downstream processing.

| **Variable**                              | **Description**                                                                                         | **Default**                                                                               |
|-------------------------------------------|---------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------|
| `ENABLE_TEXT_QUALITY_CHECK`               | Enable AI-based quality assessment of embedded PDF text.                                                | `true`                                                                                    |
| `TEXT_QUALITY_THRESHOLD`                  | Minimum quality score (0–100) required to accept embedded text without re-OCR.                         | `85`                                                                                      |
| `TEXT_QUALITY_SIGNIFICANT_ISSUES`         | Comma-separated issue labels that force re-OCR even when the score meets the threshold.                 | `excessive_typos,garbage_characters,incoherent_text,fragmented_sentences`                 |

**How it works:**

1. When a PDF with embedded text is received, DocuElevate first examines the PDF metadata (`/Producer`, `/Creator`).
2. If the PDF was **digitally created** (e.g., exported from Word, LibreOffice, LaTeX, or any modern authoring tool), the embedded text is considered trustworthy and the quality check is skipped — digital text cannot be improved by re-OCRing.
3. If the PDF was **previously OCR'd** (Tesseract, ABBYY, ocrmypdf, etc.) or the origin is **unknown**, an AI model evaluates a sample of the extracted text for:
   - Excessive typos and character-substitution artefacts typical of OCR
   - Garbage characters or symbol soup
   - Incoherent or nonsensical sentences
   - Heavy fragmentation
4. The text is **rejected** (and re-OCR triggered) when **either** of these conditions is true:
   - The quality score is **below** `TEXT_QUALITY_THRESHOLD` (default 85), **or**
   - The AI identifies one or more issues listed in `TEXT_QUALITY_SIGNIFICANT_ISSUES` — even if the numeric score is above the threshold. This prevents edge cases such as a score of 68 with `excessive_typos` and `garbage_characters` being silently accepted.
5. After the re-OCR pass, the fresh OCR result is compared **head-to-head** against the original embedded text using an AI side-by-side review. The higher-quality text is passed to downstream processing (metadata extraction, AI analysis). This ensures re-OCR never degrades quality.
6. All quality decisions (score, source, AI feedback, comparison outcome) are recorded in the processing log for review.

> **Tip**: Set `ENABLE_TEXT_QUALITY_CHECK=false` to disable the check entirely and always use embedded text as-is. This is useful when the AI provider is unavailable or when processing speed is more important than text accuracy.

> **Tuning the threshold**: The default of `TEXT_QUALITY_THRESHOLD=85` is intentionally strict. Lower it (e.g., `70`) for environments with consistently good existing OCR. Raise it (up to `100`) for maximum quality enforcement.

#### Searchable PDF Text Layer

Not all OCR providers embed a searchable text layer in the output PDF. The table below summarises each provider's behaviour and how DocuElevate handles it:

| **Provider**      | **Embeds text layer?** | **Notes** |
|-------------------|------------------------|-----------|
| `azure`           | ✅ Yes                 | Azure Document Intelligence returns a PDF/A with an embedded text layer. |
| `tesseract`       | ❌ No (text only)      | Text is extracted but the PDF is not modified. `embed_text_layer` post-processing is applied automatically. |
| `easyocr`         | ❌ No (text only)      | Same as above. |
| `mistral`         | ❌ No (text only)      | Mistral OCR API returns plain text; `embed_text_layer` post-processing is applied automatically. |
| `google_docai`    | ❌ No (text only)      | Google Cloud Document AI returns plain text; `embed_text_layer` post-processing is applied automatically. |
| `aws_textract`    | ❌ No (text only)      | AWS Textract returns plain text; `embed_text_layer` post-processing is applied automatically. |

For providers that do **not** embed a text layer, DocuElevate automatically runs `ocrmypdf --skip-text` after OCR to add an invisible Tesseract-generated text layer to the PDF. This makes the file selectable and searchable in PDF viewers. The step is silently skipped if `ocrmypdf` is not available on `PATH` (a warning is logged).

#### Azure Document Intelligence

| **Variable**                              | **Description**                                          | **How to Obtain**                       |
|-------------------------------------------|----------------------------------------------------------|-----------------------------------------|
| `AZURE_DOCUMENT_INTELLIGENCE_KEY`         | Azure Document Intelligence API key for OCR.            | [Azure Portal](https://portal.azure.com/) |
| `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`   | Endpoint URL for Azure Document Intelligence API.        | [Azure Portal](https://portal.azure.com/) |

#### Tesseract (self-hosted)

Requires `tesseract-ocr` to be installed in the Docker image or on the host. The default Docker image ships with Tesseract (English language data only).

**Automatic language data download**: DocuElevate automatically downloads missing Tesseract `.traineddata` files at startup using `wget` from the [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast) repository. No manual installation is required — simply set `TESSERACT_LANGUAGE` to the desired language codes and the data files are fetched on first start. The container must have outbound internet access for this to work.

| **Variable**           | **Description**                                                                   | **Default** |
|------------------------|-----------------------------------------------------------------------------------|-------------|
| `TESSERACT_CMD`        | Path to the `tesseract` binary (optional; auto-detected from `PATH`).            | *(auto)*    |
| `TESSERACT_LANGUAGE`   | Tesseract language code(s), e.g. `eng`, `eng+deu`, `deu`.                       | `eng+deu`   |

```bash
OCR_PROVIDERS=tesseract
TESSERACT_LANGUAGE=eng+deu
```

> **Language codes**: Use ISO 639-2 codes separated by `+`, e.g. `eng+deu+fra` for English + German + French.
> All codes supported by Tesseract are available. See the [tessdata repository](https://github.com/tesseract-ocr/tessdata_fast) for the full list.

> **No internet access?** Set `TESSDATA_PREFIX` to a writable directory and pre-populate it with the required `.traineddata` files. Alternatively, build a custom Docker image that installs the needed language packages via `apt-get install tesseract-ocr-<lang>`.

#### EasyOCR (self-hosted)

Requires the `easyocr` Python package. Install it separately as it is not included in the base requirements.

**Automatic model download**: EasyOCR model files are downloaded automatically on first use (or at startup) to `~/.EasyOCR/model/`. The container must have outbound internet access. Model download can take several minutes depending on the language.

| **Variable**          | **Description**                                                        | **Default** |
|-----------------------|------------------------------------------------------------------------|-------------|
| `EASYOCR_LANGUAGES`   | Comma-separated EasyOCR language codes, e.g. `en,de,fr`.              | `en,de`     |
| `EASYOCR_GPU`         | Enable GPU acceleration for EasyOCR (`true`/`false`).                 | `false`     |

#### Mistral OCR

| **Variable**           | **Description**                                | **How to Obtain**                              |
|------------------------|------------------------------------------------|------------------------------------------------|
| `MISTRAL_API_KEY`      | Mistral API key.                               | [console.mistral.ai](https://console.mistral.ai) |
| `MISTRAL_OCR_MODEL`    | Mistral OCR model name.                        | `mistral-ocr-latest`                           |

#### Google Cloud Document AI

| **Variable**                     | **Description**                                                                       | **Default** |
|----------------------------------|---------------------------------------------------------------------------------------|-------------|
| `GOOGLE_DOCAI_PROJECT_ID`        | GCP project ID (required).                                                           | *(required)* |
| `GOOGLE_DOCAI_PROCESSOR_ID`      | Document AI processor ID (required).                                                 | *(required)* |
| `GOOGLE_DOCAI_LOCATION`          | Processor location, e.g. `us` or `eu`.                                              | `us`         |
| `GOOGLE_DOCAI_CREDENTIALS_JSON`  | Service account JSON (optional; falls back to `GOOGLE_DRIVE_CREDENTIALS_JSON`).      | *(optional)* |

#### AWS Textract

Reuses the AWS credentials already configured for S3 integration.

| **Variable**              | **Description**                      |
|---------------------------|--------------------------------------|
| `AWS_ACCESS_KEY_ID`       | AWS access key ID.                   |
| `AWS_SECRET_ACCESS_KEY`   | AWS secret access key.               |
| `AWS_REGION`              | AWS region, e.g. `us-east-1`.       |

#### Multi-Provider Example

```bash
# Use both Azure (for accuracy) and Tesseract (for redundancy); merge via AI
OCR_PROVIDERS=azure,tesseract
OCR_MERGE_STRATEGY=ai_merge
AZURE_AI_KEY=...
AZURE_ENDPOINT=https://...
TESSERACT_LANGUAGE=eng+deu
```

### Azure Document Intelligence (Legacy)

> **Note:** This section documents the standalone Azure Document Intelligence credentials. When using `OCR_PROVIDERS=azure` these same credentials are used automatically.

| **Variable**                     | **Description**                          | **How to Obtain**                                                        |
|---------------------------------|------------------------------------------|--------------------------------------------------------------------------|
| `AZURE_DOCUMENT_INTELLIGENCE_KEY` | Azure Document Intelligence API key for OCR. | [Azure Portal](https://portal.azure.com/) |
| `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` | Endpoint URL for Azure Doc Intelligence API. | [Azure Portal](https://portal.azure.com/) |

### Paperless NGX

| **Variable**                        | **Description**                                                                                     |
|-------------------------------------|-----------------------------------------------------------------------------------------------------|
| `PAPERLESS_NGX_API_TOKEN`           | API token for Paperless NGX.                                                                        |
| `PAPERLESS_HOST`                    | Root URL for Paperless NGX (e.g. `https://paperless.example.com`).                                 |
| `PAPERLESS_CUSTOM_FIELD_ABSENDER`   | (Optional, Legacy) Name of the custom field in Paperless-ngx to store the sender ("absender") information. If set, the extracted sender will be automatically set as a custom field after document upload. Example: `Absender` or `Sender` |
| `PAPERLESS_CUSTOM_FIELDS_MAPPING`   | (Optional, Recommended) JSON mapping of extracted metadata fields to Paperless custom field names. This allows you to map multiple fields at once. Format: `{"metadata_field": "CustomFieldName", ...}`. See examples below. |

#### Custom Fields Mapping Examples

**Single Field (Legacy Method)**:
```bash
PAPERLESS_CUSTOM_FIELD_ABSENDER=Absender
```

**Multiple Fields (Recommended Method)**:
```bash
# Map multiple metadata fields to custom fields in Paperless
PAPERLESS_CUSTOM_FIELDS_MAPPING='{"absender": "Sender", "empfaenger": "Recipient", "language": "Language"}'
```

**All Available Metadata Fields**:
DocuElevate extracts the following fields that can be mapped to Paperless custom fields:
- `absender` - Sender/author of the document
- `empfaenger` - Recipient of the document
- `correspondent` - The issuing entity/company (shortened name)
- `document_type` - Type classification (Invoice, Contract, etc.)
- `language` - Document language (ISO 639-1 code, e.g., "de", "en")
- `kommunikationsart` - Communication type (German classification)
- `kommunikationskategorie` - Communication category (German classification)
- `reference_number` - Invoice/order/reference number if found
- `title` - Human-readable document title
- `tags` - List of thematic keywords (array)

**Complete Example**:
```bash
PAPERLESS_CUSTOM_FIELDS_MAPPING='{"absender": "Sender", "empfaenger": "Recipient", "correspondent": "Correspondent", "language": "Language", "reference_number": "ReferenceNumber"}'
```

**Note**: Custom fields must be created in your Paperless-ngx instance before DocuElevate can use them. The field names in the mapping (right side of the JSON) must **exactly** match the names in Paperless (case-sensitive).

### Dropbox

| **Variable**            | **Description**                                  |
|-------------------------|--------------------------------------------------|
| `DROPBOX_APP_KEY`       | Dropbox API app key.                             |
| `DROPBOX_APP_SECRET`    | Dropbox API app secret.                          |
| `DROPBOX_REFRESH_TOKEN` | OAuth2 refresh token for Dropbox.                |
| `DROPBOX_FOLDER`        | Default folder path for Dropbox uploads.         |

For detailed setup instructions, see the [Dropbox Setup Guide](DropboxSetup.md).

### Nextcloud

| **Variable**            | **Description**                                               |
|-------------------------|---------------------------------------------------------------|
| `NEXTCLOUD_UPLOAD_URL`  | Nextcloud WebDAV URL (e.g. `https://nc.example.com/remote.php/dav/files/<USERNAME>`). |
| `NEXTCLOUD_USERNAME`    | Nextcloud login username.                                    |
| `NEXTCLOUD_PASSWORD`    | Nextcloud login password.                                    |
| `NEXTCLOUD_FOLDER`      | Destination folder in Nextcloud (e.g. `"/Documents/Uploads"`). |

### Google Drive

| **Variable**                    | **Description**                                       |
|---------------------------------|-------------------------------------------------------|
| `GOOGLE_DRIVE_USE_OAUTH`        | Set to `true` to use OAuth flow (recommended)         |
| `GOOGLE_DRIVE_CLIENT_ID`        | OAuth Client ID (required if using OAuth flow)        |
| `GOOGLE_DRIVE_CLIENT_SECRET`    | OAuth Client Secret (required if using OAuth flow)    |
| `GOOGLE_DRIVE_REFRESH_TOKEN`    | OAuth Refresh Token (required if using OAuth flow)    |
| `GOOGLE_DRIVE_FOLDER_ID`        | Google Drive folder ID for file uploads               |
| `GOOGLE_DRIVE_CREDENTIALS_JSON` | JSON string containing service account credentials (alternative method) |
| `GOOGLE_DRIVE_DELEGATE_TO`      | Email address to delegate permissions (optional for service accounts) |

**Note:** For OAuth method with non-verified apps, refresh tokens expire after 7 days. For production use, either complete the Google verification process or use the Service Account method.

For detailed setup instructions, see the [Google Drive Setup Guide](GoogleDriveSetup.md).

### WebDAV

| **Variable**            | **Description**                                               |
|-------------------------|---------------------------------------------------------------|
| `WEBDAV_URL`            | WebDAV server URL (e.g. `https://webdav.example.com/path`).   |
| `WEBDAV_USERNAME`       | WebDAV authentication username.                               |
| `WEBDAV_PASSWORD`       | WebDAV authentication password.                               |
| `WEBDAV_FOLDER`         | Destination folder on WebDAV server (e.g. `"/Documents/Uploads"`). |
| `WEBDAV_VERIFY_SSL`     | Whether to verify SSL certificates (default: `True`).         |

### FTP

| **Variable**            | **Description**                                               |
|-------------------------|---------------------------------------------------------------|
| `FTP_HOST`              | FTP server hostname or IP address.                            |
| `FTP_PORT`              | FTP port (default: `21`).                                     |
| `FTP_USERNAME`          | FTP authentication username.                                  |
| `FTP_PASSWORD`          | FTP authentication password.                                  |
| `FTP_FOLDER`            | Destination folder on FTP server (e.g. `"/Documents/Uploads"`). |
| `FTP_USE_TLS`           | Try to use FTPS with TLS encryption first (default: `True`).  |
| `FTP_ALLOW_PLAINTEXT`   | Allow fallback to plaintext FTP if TLS fails (default: `True`). |

### SFTP

| **Variable**                  | **Description**                                         |
|------------------------------|-------------------------------------------------------|
| `SFTP_HOST`                  | SFTP server hostname or IP address.                    |
| `SFTP_PORT`                  | SFTP port (default: `22`).                             |
| `SFTP_USERNAME`              | SFTP authentication username.                          |
| `SFTP_PASSWORD`              | SFTP authentication password (if not using private key). |
| `SFTP_FOLDER`                | Destination folder on SFTP server.                     |
| `SFTP_PRIVATE_KEY`           | Path to private key file for authentication (optional). |
| `SFTP_PRIVATE_KEY_PASSPHRASE`| Passphrase for private key if required (optional).     |

### Email

| **Variable**                | **Description**                                           |
|----------------------------|----------------------------------------------------------|
| `EMAIL_HOST`               | SMTP server hostname.                                     |
| `EMAIL_PORT`               | SMTP port (default: `587`).                               |
| `EMAIL_USERNAME`           | SMTP authentication username.                             |
| `EMAIL_PASSWORD`           | SMTP authentication password.                             |
| `EMAIL_USE_TLS`            | Whether to use TLS (default: `True`).                     |
| `EMAIL_SENDER`             | From address (e.g., `"DocuElevate <docuelevate@example.com>"`). |
| `EMAIL_DEFAULT_RECIPIENT`  | Default recipient email if none specified in the task.    |

### OneDrive / Microsoft Graph

| **Variable**                    | **Description**                                       |
|---------------------------------|-------------------------------------------------------|
| `ONEDRIVE_CLIENT_ID`            | Azure AD application client ID                        |
| `ONEDRIVE_CLIENT_SECRET`        | Azure AD application client secret                    |
| `ONEDRIVE_TENANT_ID`            | Azure AD tenant ID: use "common" for personal accounts or your tenant ID for corporate accounts |
| `ONEDRIVE_REFRESH_TOKEN`        | OAuth 2.0 refresh token (required for personal accounts) |
| `ONEDRIVE_FOLDER_PATH`          | Folder path in OneDrive for storing documents         |

For detailed setup instructions, see the [OneDrive Setup Guide](OneDriveSetup.md).

### Amazon S3

| **Variable**                    | **Description**                                       |
|---------------------------------|-------------------------------------------------------|
| `AWS_ACCESS_KEY_ID`             | AWS IAM access key ID                                 |
| `AWS_SECRET_ACCESS_KEY`         | AWS IAM secret access key                             |
| `AWS_REGION`                    | AWS region where your S3 bucket is located (default: `us-east-1`) |
| `S3_BUCKET_NAME`                | Name of your S3 bucket                                |
| `S3_FOLDER_PREFIX`              | Optional prefix/folder path for uploaded files        |
| `S3_STORAGE_CLASS`              | Storage class for uploaded objects (default: `STANDARD`) |
| `S3_ACL`                        | Access control for uploaded files (default: `private`) |

For detailed setup instructions, see the [Amazon S3 Setup Guide](AmazonS3Setup.md).

### Notification System

| **Variable**                | **Description**                                           |
|----------------------------|----------------------------------------------------------|
| `NOTIFICATION_URLS`        | Comma-separated list of Apprise notification URLs         |
| `NOTIFY_ON_TASK_FAILURE`   | Send notifications on task failures (`True`/`False`)     |
| `NOTIFY_ON_CREDENTIAL_FAILURE` | Send notifications on credential failures (`True`/`False`) |
| `NOTIFY_ON_STARTUP`        | Send notification when system starts (`True`/`False`)    |
| `NOTIFY_ON_SHUTDOWN`       | Send notification when system shuts down (`True`/`False`)|

For detailed setup instructions, see the [Notifications Setup Guide](NotificationsSetup.md).

### Uptime Kuma

| **Variable**                | **Description**                                                |
|-----------------------------|----------------------------------------------------------------|
| `UPTIME_KUMA_URL`           | Uptime Kuma push URL for monitoring the application's health.   |
| `UPTIME_KUMA_PING_INTERVAL` | How often to ping Uptime Kuma in minutes (default: `5`).       |

### UI / Appearance

DocuElevate supports a **dark mode** toggle in the navbar. Users can switch between light and dark themes at any time; their choice is stored in `localStorage` and persists across page reloads in the same browser.

Administrators can set the **site-wide default** colour scheme that is applied when a user has not yet made a personal choice:

| **Variable**               | **Description**                                                                                                                                  | **Default** |
|----------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|-------------|
| `UI_DEFAULT_COLOR_SCHEME`  | Default colour scheme for all users. Options: `system` (follow OS preference), `light`, `dark`. Users can always override with the navbar toggle. | `system`    |

**How it works:**

1. On page load an inline script checks the user's `localStorage` preference first.
2. If no stored preference exists, the server-supplied `UI_DEFAULT_COLOR_SCHEME` is used.
3. When the value is `system` (the default), the OS-level `prefers-color-scheme` media query is respected.
4. Clicking the 🌙 / ☀️ toggle in the navbar saves the new preference to `localStorage` immediately.

**WCAG AA compliance:** All dark-mode colour pairs have been chosen with a minimum 4.5:1 contrast ratio for normal text and 3:1 for large text.

**Example:**

```dotenv
# Force dark mode for all users by default
UI_DEFAULT_COLOR_SCHEME=dark
```

## Configuration Examples

### Minimal Configuration

This is the minimal configuration needed to run DocuElevate with local storage only:

```dotenv
DATABASE_URL=sqlite:///./app/database.db
REDIS_URL=redis://redis:6379/0
WORKDIR=/workdir
GOTENBERG_URL=http://gotenberg:3000
```

### Full Configuration with All Services

```dotenv
# Core settings
DATABASE_URL=sqlite:///./app/database.db
REDIS_URL=redis://redis:6379/0
WORKDIR=/workdir
GOTENBERG_URL=http://gotenberg:3000
EXTERNAL_HOSTNAME=docuelevate.example.com
ALLOW_FILE_DELETE=true

# IMAP settings
IMAP1_HOST=mail.example.com
IMAP1_PORT=993
IMAP1_USERNAME=user@example.com
IMAP1_PASSWORD=password
IMAP1_SSL=true
IMAP1_POLL_INTERVAL_MINUTES=5
IMAP1_DELETE_AFTER_PROCESS=false

# AI services
OPENAI_API_KEY=sk-...
AZURE_DOCUMENT_INTELLIGENCE_KEY=...
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://...

# Authentication
AUTH_ENABLED=true
SESSION_SECRET=a-very-long-and-secure-random-secret-key-string-for-session-encryption
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_password
ADMIN_GROUP_NAME=admin
AUTHENTIK_CLIENT_ID=...
AUTHENTIK_CLIENT_SECRET=...
AUTHENTIK_CONFIG_URL=https://auth.example.com/.well-known/openid-configuration
OAUTH_PROVIDER_NAME=Authentik SSO

# Storage services
PAPERLESS_NGX_API_TOKEN=...
PAPERLESS_HOST=https://paperless.example.com

DROPBOX_APP_KEY=...
DROPBOX_APP_SECRET=...
DROPBOX_REFRESH_TOKEN=...
DROPBOX_FOLDER=/Documents/Uploads

NEXTCLOUD_UPLOAD_URL=https://nc.example.com/remote.php/dav/files/username
NEXTCLOUD_USERNAME=username
NEXTCLOUD_PASSWORD=password
NEXTCLOUD_FOLDER=/Documents/Uploads

# Google Drive
GOOGLE_DRIVE_CREDENTIALS_JSON={"type":"service_account","project_id":"..."}
GOOGLE_DRIVE_FOLDER_ID=1a2b3c4d5e6f7g8h9i0j
GOOGLE_DRIVE_DELEGATE_TO=optional-user@example.com
GOOGLE_DRIVE_USE_OAUTH=true
GOOGLE_DRIVE_CLIENT_ID=your_client_id
GOOGLE_DRIVE_CLIENT_SECRET=your_client_secret
GOOGLE_DRIVE_REFRESH_TOKEN=your_refresh_token

# WebDAV
WEBDAV_URL=https://webdav.example.com/path
WEBDAV_USERNAME=username
WEBDAV_PASSWORD=password
WEBDAV_FOLDER=/Documents/Uploads
WEBDAV_VERIFY_SSL=True

# FTP
FTP_HOST=ftp.example.com
FTP_PORT=21
FTP_USERNAME=username
FTP_PASSWORD=password
FTP_FOLDER=/Documents/Uploads
FTP_USE_TLS=True
FTP_ALLOW_PLAINTEXT=True

# SFTP
SFTP_HOST=sftp.example.com
SFTP_PORT=22
SFTP_USERNAME=username
SFTP_PASSWORD=password
SFTP_FOLDER=/Documents/Uploads
# SFTP_PRIVATE_KEY=/path/to/key.pem
# SFTP_PRIVATE_KEY_PASSPHRASE=passphrase

# Email
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_USERNAME=docuelevate@example.com
EMAIL_PASSWORD=password
EMAIL_USE_TLS=True
EMAIL_SENDER=DocuElevate System <docuelevate@example.com>
EMAIL_DEFAULT_RECIPIENT=recipient@example.com

# Notification Settings
# Configure notification services using Apprise URL format
NOTIFICATION_URLS=discord://webhook_id/webhook_token,mailto://user:pass@gmail.com,tgram://bot_token/chat_id
NOTIFY_ON_TASK_FAILURE=True
NOTIFY_ON_CREDENTIAL_FAILURE=True
NOTIFY_ON_STARTUP=True
NOTIFY_ON_SHUTDOWN=False

# OneDrive (Personal Account)
ONEDRIVE_CLIENT_ID=12345678-1234-1234-1234-123456789012
ONEDRIVE_CLIENT_SECRET=your_client_secret
ONEDRIVE_TENANT_ID=common
ONEDRIVE_REFRESH_TOKEN=your_refresh_token
ONEDRIVE_FOLDER_PATH=Documents/Uploads

# Amazon S3
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AWS_REGION=us-east-1
S3_BUCKET_NAME=my-document-bucket
S3_FOLDER_PREFIX=documents/uploads/2023/  # Will place files in this subfolder
S3_STORAGE_CLASS=STANDARD
S3_ACL=private

# Uptime Kuma
UPTIME_KUMA_URL=https://kuma.example.com/api/push/abcde12345?status=up
UPTIME_KUMA_PING_INTERVAL=5
```

## Selective Service Configuration

You can choose which document storage services to use by only including the relevant environment variables. For example, if you only want to use Dropbox, include only the Dropbox variables and omit the Paperless NGX and Nextcloud variables.

## Configuration File Location

The `.env` file should be placed at the root of the project directory. When using Docker Compose, you can reference it with the `env_file` directive in your `docker-compose.yml`.
