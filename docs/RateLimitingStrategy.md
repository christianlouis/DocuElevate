# Rate Limiting Strategy for DocuElevate API Endpoints

This document outlines the rate limiting strategy for DocuElevate API endpoints to protect against abuse and DoS attacks.

## Overview

DocuElevate implements rate limiting using [SlowAPI](https://github.com/laurents/slowapi), a FastAPI-compatible rate limiting library based on Flask-Limiter. Rate limits are enforced per IP address for unauthenticated requests and per user ID for authenticated requests.

## Default Configuration

All API endpoints are protected with a default rate limit unless explicitly exempted or configured otherwise:

- **Default**: 100 requests per minute per IP/user
- **File Upload**: 600 requests per minute per IP/user
- **Authentication**: 10 requests per minute (brute force protection)

**Note**: Document processing endpoints use built-in queue throttling via Celery to control processing rates and prevent upstream API overloads. No additional API-level rate limit is configured for processing endpoints.

## Endpoint Categories

### 1. Authentication Endpoints (Stricter Limits)

**Rate Limit**: 10 requests per minute

**Endpoints**:
- `POST /auth` - Local username/password authentication
- `GET /login` - Login page
- `GET /oauth-login` - OAuth login initiation
- `GET /oauth-callback` - OAuth callback handler

**Rationale**: These endpoints are vulnerable to brute force attacks and credential stuffing. A strict rate limit of 10 requests per minute per IP prevents automated attacks while allowing legitimate users to retry failed login attempts.

**Implementation Status**: Applied via `RATE_LIMIT_AUTH` configuration (default: `10/minute`)

---

### 2. File Upload Endpoints (Resource Protection)

**Rate Limit**: 600 requests per minute

**Endpoints**:
- `POST /api/ui-upload` - Web UI file upload
- `POST /api/upload` - API file upload

**Rationale**: File uploads consume network bandwidth, disk I/O, and storage space. A limit of 600 uploads per minute allows fast batch uploads while preventing resource exhaustion and abuse.

**Implementation Status**: Configured via `RATE_LIMIT_UPLOAD` (default: `600/minute`)

**Implementation Status**: Configured via `RATE_LIMIT_UPLOAD` (default: `20/minute`)

---

### 3. Read-Only API Endpoints (Default Limits)

**Rate Limit**: 100 requests per minute

**Endpoints**:
- `GET /api/files` - List files
- `GET /api/files/{file_id}` - Get file details
- `GET /api/files/{file_id}/metadata` - Get file metadata
- `GET /api/files/{file_id}/preview` - Get file preview
- `GET /api/files/{file_id}/download` - Download file
- `GET /api/logs` - Get logs

**Rationale**: Read-only operations are less resource-intensive but still need protection against scraping and excessive polling. The default limit of 100 requests per minute allows legitimate applications while preventing abuse.

**Implementation Status**: Uses default rate limit (`RATE_LIMIT_DEFAULT`)

---

### 4. Frontend Routes (Default Limits)

**Rate Limit**: 100 requests per minute

**Endpoints**:
- `GET /` - Home page
- `GET /about` - About page
- `GET /upload` - Upload page
- `GET /status` - Status page
- `GET /settings` - Settings page

**Rationale**: Frontend routes serve HTML pages and are less resource-intensive than API endpoints. The default limit prevents excessive requests while ensuring a smooth user experience.

**Implementation Status**: Uses default rate limit

---

### 5. Webhook/Callback Endpoints (Higher Limits)

**Rate Limit**: Consider exemption or very high limits

**Endpoints**:
- `GET /oauth-callback` - OAuth callback (authentication, stricter limit applies)

**Rationale**: Webhook endpoints receive requests from external services and should not be rate-limited in most cases, as the external service controls the request rate. However, OAuth callbacks have stricter limits for security.

**Implementation Status**: OAuth callbacks use `RATE_LIMIT_AUTH` (10/minute)

---

### 6. Health/Diagnostic Endpoints (Exempt or High Limits)

**Rate Limit**: Potentially exempt for monitoring

**Endpoints**:
- `GET /health` (if implemented)
- `GET /metrics` (if implemented)

**Rationale**: Health checks and metrics endpoints are typically called by monitoring systems at regular intervals. These should either be exempted from rate limiting or have very high limits to avoid false positives in monitoring.

**Implementation Status**: Not yet implemented (future consideration)

---

## Rate Limiting Mechanism

### Per-User vs Per-IP

- **Authenticated Requests**: Rate limits are enforced per user ID from the session
- **Unauthenticated Requests**: Rate limits are enforced per IP address

This prevents authenticated users from bypassing rate limits by switching IP addresses and ensures fair usage across all users.

### Storage Backend

- **Production**: Uses Redis for distributed rate limiting across multiple workers
- **Development**: Falls back to in-memory storage if Redis is unavailable

### Response Format

When a rate limit is exceeded, the API returns:

```json
{
  "detail": "Rate limit exceeded: 100 per 1 minute"
}
```

**HTTP Status Code**: `429 Too Many Requests`
**Headers**: `Retry-After` (seconds until limit resets)

---

## Configuration

Rate limits are configured via environment variables:

```bash
# Enable/disable rate limiting
RATE_LIMITING_ENABLED=true

# Configure Redis for distributed rate limiting
REDIS_URL=redis://redis:6379/0

# Configure limits
RATE_LIMIT_DEFAULT=100/minute
RATE_LIMIT_UPLOAD=20/minute
RATE_LIMIT_PROCESS=30/minute
RATE_LIMIT_AUTH=10/minute
```

---

## Future Enhancements

### 1. Per-Endpoint Custom Limits

Apply specific rate limits to individual endpoints using the `@limiter.limit()` decorator:

```python
from app.main import app

@router.post("/expensive-operation")
@app.state.limiter.limit("5/minute")  # Custom strict limit
async def expensive_operation(request: Request):
    ...
```

### 2. User Tier-Based Limits

Implement different rate limits based on user subscription tier:

```python
def get_rate_limit_for_user(user):
    """Get rate limit based on user tier."""
    if user.tier == "premium":
        return "500/minute"
    elif user.tier == "standard":
        return "100/minute"
    else:
        return "50/minute"
```

### 3. Burst Allowances

Use token bucket algorithm for bursty traffic:

```python
# Allow bursts of 20 requests, but enforce 100/minute average
RATE_LIMIT_DEFAULT=100/minute burst=20
```

### 4. Geographic Rate Limiting

Apply different limits based on request origin for abuse prevention.

### 5. Endpoint Exemptions

Exempt specific endpoints from rate limiting:

```python
from app.main import app

@router.get("/public-data")
@app.state.limiter.exempt
async def public_data():
    ...
```

---

## Monitoring and Alerts

### Logs

Rate limit violations are logged:

```
2024-02-10 16:00:00 - Rate limit exceeded: 100 per 1 minute (IP: 192.168.1.1)
```

### Metrics (Future)

Consider tracking:
- Number of rate limit violations per endpoint
- Most frequently rate-limited IPs/users
- Average request rates per endpoint

### Alerts (Future)

Set up alerts for:
- Excessive rate limit violations (potential attack)
- Specific IPs repeatedly hitting limits (block consideration)
- Unusual traffic patterns

---

## Testing Rate Limits

### Manual Testing

```bash
# Test rate limit on upload endpoint
for i in {1..25}; do
  curl -X POST "http://localhost:8000/api/ui-upload" \
    -H "Cookie: session=..." \
    -F "file=@test.pdf"
  echo "Request $i completed"
  sleep 1
done
```

### Load Testing

Use tools like `locust` or `k6` for comprehensive load testing:

```python
# locustfile.py
from locust import HttpUser, task, between

class APIUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task
    def get_files(self):
        self.client.get("/api/files")
```

---

## Security Considerations

1. **DDoS Protection**: Rate limiting is the first line of defense, but consider additional layers (WAF, CDN)
2. **Distributed Attacks**: Monitor for distributed attacks from multiple IPs
3. **Application-Level DoS**: Rate limiting alone doesn't protect against all DoS vectors (e.g., slowloris)
4. **Redis Security**: Ensure Redis is properly secured and not publicly accessible

---

## References

- [SlowAPI Documentation](https://slowapi.readthedocs.io/)
- [API.md](API.md) - API documentation with rate limiting examples
- [ConfigurationGuide.md](ConfigurationGuide.md) - Rate limiting configuration
- [SECURITY_AUDIT.md](../SECURITY_AUDIT.md) - Security best practices
