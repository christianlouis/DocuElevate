# Using Mock OAuth2 Server in CI/CD

This guide explains how to use the mock OAuth2 server infrastructure in continuous integration pipelines.

## GitHub Actions Configuration

### Running with Mock OAuth (Default)

The tests automatically use mock OAuth by default. No special configuration needed:

```yaml
name: Tests with Mock OAuth

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'
    
    - name: Install dependencies
      run: |
        pip install -r requirements-dev.txt
    
    - name: Run OAuth tests (mock)
      run: |
        pytest tests/test_oauth_integration_flows.py -v
```

### Running with Real OAuth (Using Secrets)

To test with real OAuth credentials (e.g., Authentik, Auth0):

```yaml
name: Tests with Real OAuth

on: [push, pull_request]

jobs:
  test-real-oauth:
    runs-on: ubuntu-latest
    # Only run if secrets are available (not on external PRs)
    if: github.event_name == 'push' || github.event.pull_request.head.repo.full_name == github.repository
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'
    
    - name: Install dependencies
      run: |
        pip install -r requirements-dev.txt
    
    - name: Run OAuth tests (real)
      env:
        AUTHENTIK_CLIENT_ID: ${{ secrets.AUTHENTIK_CLIENT_ID }}
        AUTHENTIK_CLIENT_SECRET: ${{ secrets.AUTHENTIK_CLIENT_SECRET }}
        AUTHENTIK_CONFIG_URL: ${{ secrets.AUTHENTIK_CONFIG_URL }}
      run: |
        # Tests auto-detect real credentials and use them
        pytest tests/test_oauth_integration_flows.py -v -m requires_external
```

### Hybrid Approach (Best Practice)

Run both mock and real tests in separate jobs:

```yaml
name: OAuth Tests

on: [push, pull_request]

jobs:
  test-mock-oauth:
    name: OAuth Tests (Mock)
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'
    
    - name: Install dependencies
      run: |
        pip install -r requirements-dev.txt
    
    - name: Run mock OAuth tests
      run: |
        pytest tests/test_oauth_integration_flows.py \
          -v \
          -m "not requires_external"
  
  test-real-oauth:
    name: OAuth Tests (Real - Internal Only)
    runs-on: ubuntu-latest
    # Only run on internal commits where secrets are available
    if: github.event_name == 'push' || github.event.pull_request.head.repo.full_name == github.repository
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'
    
    - name: Install dependencies
      run: |
        pip install -r requirements-dev.txt
    
    - name: Run real OAuth tests
      env:
        AUTHENTIK_CLIENT_ID: ${{ secrets.AUTHENTIK_CLIENT_ID }}
        AUTHENTIK_CLIENT_SECRET: ${{ secrets.AUTHENTIK_CLIENT_SECRET }}
        AUTHENTIK_CONFIG_URL: ${{ secrets.AUTHENTIK_CONFIG_URL }}
      run: |
        pytest tests/test_oauth_integration_flows.py \
          -v \
          -m requires_external
```

## Required GitHub Secrets

To enable real OAuth testing, configure these secrets in your repository:

1. Go to **Settings → Secrets and variables → Actions**
2. Add the following secrets:

| Secret Name | Description | Example Value |
|-------------|-------------|---------------|
| `AUTHENTIK_CLIENT_ID` | OAuth client ID | `docuelevate-app` |
| `AUTHENTIK_CLIENT_SECRET` | OAuth client secret | `super-secret-value` |
| `AUTHENTIK_CONFIG_URL` | OIDC discovery URL | `https://auth.example.com/application/o/docuelevate/.well-known/openid-configuration` |

## Docker Service (Alternative to Testcontainers)

If you prefer not to use testcontainers in CI, you can run mock-oauth2-server as a service:

```yaml
name: Tests with OAuth Service

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      mock-oauth:
        image: ghcr.io/navikt/mock-oauth2-server:2.1.1
        ports:
          - 8080:8080
        options: >-
          --health-cmd "wget -q -O /dev/null http://localhost:8080/default/.well-known/openid-configuration || exit 1"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'
    
    - name: Install dependencies
      run: |
        pip install -r requirements-dev.txt
    
    - name: Configure OAuth to use service
      run: |
        export OAUTH_MOCK_URL=http://localhost:8080
        export USE_MOCK_OAUTH=true
    
    - name: Run tests
      run: |
        pytest tests/test_oauth_integration_flows.py -v
```

## Forcing Mock or Real Mode

You can override the automatic detection with environment variables:

```bash
# Force mock mode (even if real credentials available)
export USE_MOCK_OAUTH=true
pytest tests/test_oauth_integration_flows.py -v

# Force real mode (will skip if credentials not available)
export USE_REAL_OAUTH=true
pytest tests/test_oauth_integration_flows.py -v
```

## Debugging OAuth Tests in CI

### View Container Logs

Add this step to debug mock OAuth server issues:

```yaml
- name: Show mock OAuth logs (on failure)
  if: failure()
  run: |
    docker ps -a
    docker logs $(docker ps -aq --filter ancestor=ghcr.io/navikt/mock-oauth2-server:2.1.1)
```

### Enable Verbose Logging

```yaml
- name: Run tests with verbose logging
  run: |
    pytest tests/test_oauth_integration_flows.py -vvs --log-cli-level=DEBUG
```

### Check Well-Known Endpoint

```yaml
- name: Verify mock OAuth server
  run: |
    curl -f http://localhost:8080/default/.well-known/openid-configuration || exit 1
```

## Performance Considerations

- **Mock OAuth**: ~1s startup time, tests run in <10s
- **Real OAuth**: Depends on network latency, typically <30s
- **Docker Service**: Fastest for CI (pre-started), ~0.5s overhead

## Security Best Practices

1. ✅ **Never commit real OAuth credentials** to the repository
2. ✅ **Use GitHub secrets** for real credentials
3. ✅ **Restrict real OAuth tests** to internal PRs only
4. ✅ **Use mock OAuth** for external/fork PRs
5. ✅ **Rotate secrets** regularly if compromised

## Troubleshooting

### Tests Skip with "OAuth credentials not available"

**Cause**: Real OAuth credentials not configured or not accessible.

**Solution**: 
- For local dev: Use mock mode (default)
- For CI: Add secrets to GitHub repository settings
- Check secret availability: `if github.event_name == 'push'`

### Mock OAuth Server Won't Start

**Cause**: Docker not available or testcontainers can't start container.

**Solution**:
```yaml
- name: Start Docker
  run: |
    sudo systemctl start docker
    docker ps
```

### Tests Timeout Waiting for Server

**Cause**: Server taking too long to start or health check failing.

**Solution**: Increase timeout in `conftest_oauth.py`:
```python
container.wait_for_ready(timeout=60)  # Increase from 30
```

## Example: Complete GitHub Actions Workflow

```yaml
name: Full OAuth Testing Suite

on: [push, pull_request]

jobs:
  # Fast mock OAuth tests (always run)
  mock-oauth-tests:
    name: OAuth Tests (Mock) 
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'
    
    - name: Install dependencies
      run: pip install -r requirements-dev.txt
    
    - name: Run mock OAuth tests
      run: |
        pytest tests/test_oauth_integration_flows.py \
          -v \
          -m "not requires_external" \
          --cov=app.auth \
          --cov-report=term-missing
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        files: ./coverage.xml
        flags: oauth-mock

  # Real OAuth tests (only for internal PRs/pushes)
  real-oauth-tests:
    name: OAuth Tests (Real - Internal)
    runs-on: ubuntu-latest
    if: github.event_name == 'push' || github.event.pull_request.head.repo.full_name == github.repository
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'
    
    - name: Install dependencies
      run: pip install -r requirements-dev.txt
    
    - name: Run real OAuth tests
      env:
        AUTHENTIK_CLIENT_ID: ${{ secrets.AUTHENTIK_CLIENT_ID }}
        AUTHENTIK_CLIENT_SECRET: ${{ secrets.AUTHENTIK_CLIENT_SECRET }}
        AUTHENTIK_CONFIG_URL: ${{ secrets.AUTHENTIK_CONFIG_URL }}
      run: |
        pytest tests/test_oauth_integration_flows.py \
          -v \
          -m requires_external
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        files: ./coverage.xml
        flags: oauth-real
```

This workflow:
- ✅ Runs mock tests on all PRs (fast, no secrets needed)
- ✅ Runs real tests only when secrets available
- ✅ Uploads separate coverage reports
- ✅ Provides detailed feedback
