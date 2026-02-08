# GitHub Secrets Setup Guide

This guide explains how to configure GitHub Secrets for running integration tests in GitHub Actions.

## Overview

**Problem:** Integration tests need real API keys, but you can't commit secrets to the repository.

**Solution:** Use GitHub Secrets - encrypted environment variables stored securely in your repository settings.

## Quick Comparison

| Method | Use Case | How It Works |
|--------|----------|--------------|
| **`.env.test`** (local) | Local development on your machine | File on your computer, gitignored, never committed |
| **GitHub Secrets** (CI/CD) | Automated tests in GitHub Actions | Stored encrypted in GitHub, injected as environment variables |

## Step-by-Step Setup

### 1. Create Test Resources

Before adding secrets, create dedicated test resources:

- ✅ **Separate test API keys** (not production keys!)
- ✅ **Test storage buckets/folders** (e.g., `docuelevate-test-bucket`)
- ✅ **Test service accounts** with minimal permissions
- ✅ **Test email accounts** for email/IMAP tests

### 2. Add Secrets to GitHub

#### Visual Guide

1. Go to your GitHub repository: `https://github.com/YOUR_USERNAME/DocuElevate`
2. Click **Settings** (top navigation)
3. In the left sidebar, click **Secrets and variables** → **Actions**
4. Click **"New repository secret"** button
5. Enter the secret name and value
6. Click **"Add secret"**

#### Required Secrets for Integration Tests

Add these secrets based on which integrations you want to test:

##### Core AI Services

```
Secret Name: TEST_OPENAI_API_KEY
Value: sk-test-your-openai-test-key-here
Description: OpenAI API key for metadata extraction tests
```

```
Secret Name: TEST_AZURE_AI_KEY
Value: your-azure-test-key-here
Description: Azure Document Intelligence for OCR tests
```

```
Secret Name: TEST_AZURE_ENDPOINT
Value: https://your-test-endpoint.cognitiveservices.azure.com/
Description: Azure endpoint URL
```

##### AWS S3 (Optional)

```
Secret Name: TEST_AWS_ACCESS_KEY_ID
Value: AKIAIOSFODNN7EXAMPLE
```

```
Secret Name: TEST_AWS_SECRET_ACCESS_KEY
Value: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

```
Secret Name: TEST_S3_BUCKET_NAME
Value: docuelevate-test-bucket
```

##### Dropbox (Optional)

```
Secret Name: TEST_DROPBOX_APP_KEY
Value: your-test-app-key
```

```
Secret Name: TEST_DROPBOX_APP_SECRET
Value: your-test-app-secret
```

```
Secret Name: TEST_DROPBOX_REFRESH_TOKEN
Value: your-test-refresh-token
```

##### Google Drive (Optional)

```
Secret Name: TEST_GOOGLE_DRIVE_CREDENTIALS_JSON
Value: {"type":"service_account","project_id":"test-project",...}
```

```
Secret Name: TEST_GOOGLE_DRIVE_FOLDER_ID
Value: 1a2b3c4d5e6f7g8h9i0j
```

##### OneDrive (Optional)

```
Secret Name: TEST_ONEDRIVE_CLIENT_ID
Value: your-test-client-id
```

```
Secret Name: TEST_ONEDRIVE_CLIENT_SECRET
Value: your-test-client-secret
```

```
Secret Name: TEST_ONEDRIVE_REFRESH_TOKEN
Value: your-test-refresh-token
```

### 3. Update GitHub Actions Workflow

#### Option A: Modify Existing `.github/workflows/tests.yaml`

Add the secrets to the test step:

```yaml
- name: Run Tests
  env:
    # Core AI Services (always needed for integration tests)
    OPENAI_API_KEY: ${{ secrets.TEST_OPENAI_API_KEY }}
    AZURE_AI_KEY: ${{ secrets.TEST_AZURE_AI_KEY }}
    AZURE_ENDPOINT: ${{ secrets.TEST_AZURE_ENDPOINT }}
    AZURE_REGION: eastus
    
    # AWS S3 (optional - only if testing S3 integration)
    AWS_ACCESS_KEY_ID: ${{ secrets.TEST_AWS_ACCESS_KEY_ID }}
    AWS_SECRET_ACCESS_KEY: ${{ secrets.TEST_AWS_SECRET_ACCESS_KEY }}
    S3_BUCKET_NAME: ${{ secrets.TEST_S3_BUCKET_NAME }}
    AWS_REGION: us-east-1
    
    # Dropbox (optional)
    DROPBOX_APP_KEY: ${{ secrets.TEST_DROPBOX_APP_KEY }}
    DROPBOX_APP_SECRET: ${{ secrets.TEST_DROPBOX_APP_SECRET }}
    DROPBOX_REFRESH_TOKEN: ${{ secrets.TEST_DROPBOX_REFRESH_TOKEN }}
    
    # Google Drive (optional)
    GOOGLE_DRIVE_CREDENTIALS_JSON: ${{ secrets.TEST_GOOGLE_DRIVE_CREDENTIALS_JSON }}
    GOOGLE_DRIVE_FOLDER_ID: ${{ secrets.TEST_GOOGLE_DRIVE_FOLDER_ID }}
    
    # OneDrive (optional)
    ONEDRIVE_CLIENT_ID: ${{ secrets.TEST_ONEDRIVE_CLIENT_ID }}
    ONEDRIVE_CLIENT_SECRET: ${{ secrets.TEST_ONEDRIVE_CLIENT_SECRET }}
    ONEDRIVE_REFRESH_TOKEN: ${{ secrets.TEST_ONEDRIVE_REFRESH_TOKEN }}
    
    # Standard test config (no secrets needed)
    DATABASE_URL: sqlite:///:memory:
    REDIS_URL: redis://localhost:6379/0
    WORKDIR: /tmp
    AUTH_ENABLED: "False"
    SESSION_SECRET: test_secret_key_for_testing_must_be_at_least_32_characters_long
  run: pytest tests/ -v --cov=app --cov-report=xml
```

#### Option B: Create Separate Integration Test Workflow

Create `.github/workflows/integration-tests.yaml`:

```yaml
name: Integration Tests with Real APIs

# Run less frequently to save on API costs
on:
  # Run daily at 2 AM UTC
  schedule:
    - cron: '0 2 * * *'
  
  # Allow manual triggering
  workflow_dispatch:
  
  # Run on release tags
  push:
    tags:
      - 'v*'

jobs:
  integration-tests:
    runs-on: ubuntu-latest
    
    services:
      redis:
        image: redis:7
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
      - name: Checkout Code
        uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"
      
      - name: Install Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-dev.txt
      
      - name: Run Integration Tests with Real APIs
        env:
          OPENAI_API_KEY: ${{ secrets.TEST_OPENAI_API_KEY }}
          AZURE_AI_KEY: ${{ secrets.TEST_AZURE_AI_KEY }}
          AZURE_ENDPOINT: ${{ secrets.TEST_AZURE_ENDPOINT }}
          AZURE_REGION: eastus
          DATABASE_URL: sqlite:///:memory:
          REDIS_URL: redis://localhost:6379/0
          WORKDIR: /tmp
          AUTH_ENABLED: "False"
        run: |
          # Only run tests marked with @pytest.mark.requires_external
          pytest -m requires_external -v --tb=short
      
      - name: Notify on Failure
        if: failure()
        run: |
          echo "Integration tests failed! Check the logs above."
          echo "This might indicate API changes or service issues."
```

### 4. Verify Setup

#### Check Secrets Are Configured

In your workflow logs, you'll see secrets are masked:

```
OPENAI_API_KEY: ***
AZURE_AI_KEY: ***
```

GitHub automatically hides secret values in logs.

#### Manual Test Run

1. Go to **Actions** tab in your repository
2. Select your workflow (e.g., "Run Tests & Linting")
3. Click **"Run workflow"** dropdown
4. Select your branch
5. Click **"Run workflow"** button
6. Monitor the workflow run to ensure tests pass

#### Check Test Results

Look for:
- ✅ All unit tests passing
- ✅ Integration tests running (if secrets configured)
- ✅ No exposed secrets in logs
- ✅ Proper error handling if secrets are missing

### 5. Best Practices

#### Security

- ✅ **Never log secret values** - GitHub masks them, but be careful in your code
- ✅ **Use test accounts only** - Never use production API keys in tests
- ✅ **Rotate secrets regularly** - Update test keys every 90 days
- ✅ **Use minimal permissions** - Test keys should only access test resources
- ✅ **Monitor usage** - Check test accounts for unexpected activity

#### Cost Management

- ✅ **Run integration tests less frequently** - Use schedule triggers (e.g., daily)
- ✅ **Use small test files** - Keep test data minimal to reduce API costs
- ✅ **Skip integration tests on draft PRs** - Only run on ready-for-review PRs
- ✅ **Set API rate limits** - Configure test accounts with spending caps

#### Organization

- ✅ **Prefix test secrets** - Use `TEST_` prefix to distinguish from production
- ✅ **Document required secrets** - List them in README or docs
- ✅ **Use secret descriptions** - GitHub allows descriptions for each secret
- ✅ **Group related secrets** - Keep storage, AI, and notification secrets organized

## Conditional Integration Tests

Run integration tests only when secrets are configured:

```yaml
- name: Run Unit Tests (Always)
  run: pytest -m "unit" -v

- name: Check if Integration Test Secrets Exist
  id: check_secrets
  run: |
    if [ -n "${{ secrets.TEST_OPENAI_API_KEY }}" ]; then
      echo "has_secrets=true" >> $GITHUB_OUTPUT
    else
      echo "has_secrets=false" >> $GITHUB_OUTPUT
    fi

- name: Run Integration Tests (Only if Secrets Configured)
  if: steps.check_secrets.outputs.has_secrets == 'true'
  env:
    OPENAI_API_KEY: ${{ secrets.TEST_OPENAI_API_KEY }}
    AZURE_AI_KEY: ${{ secrets.TEST_AZURE_AI_KEY }}
  run: pytest -m "requires_external" -v
```

## Troubleshooting

### Tests Can't Access Secrets

**Problem:** Tests fail with "API key not configured" errors.

**Solution:**
1. Verify secrets are added in repository Settings → Secrets
2. Check secret names match exactly (case-sensitive)
3. Ensure workflow has `env:` section with secrets
4. Check if repository is private (secrets work in both public/private repos)

### Secrets Not Updating

**Problem:** Updated secret values in GitHub but tests still use old values.

**Solution:**
1. Re-run the workflow (secrets are loaded fresh each time)
2. Clear GitHub Actions cache if applicable
3. Verify you're updating the correct repository (not a fork)

### Integration Tests Failing in CI but Passing Locally

**Problem:** Tests pass with `.env.test` locally but fail in GitHub Actions.

**Solution:**
1. Check that all secrets used locally are also in GitHub Secrets
2. Verify secret names match environment variable names in your code
3. Ensure test resources (buckets, folders) are accessible from GitHub Actions IPs
4. Check rate limits on your test API accounts

### Fork Pull Requests Can't Access Secrets

**Problem:** PRs from forks fail because they can't access secrets.

**Solution:** This is a GitHub security feature.

**Options:**
1. Skip integration tests for fork PRs (recommended)
2. Request contributors to open PRs from branches in main repo
3. Use `pull_request_target` trigger (⚠️ security risk - research first)

Example workflow config:
```yaml
- name: Run Integration Tests
  # Skip for PRs from forks (they can't access secrets)
  if: github.event.pull_request.head.repo.full_name == github.repository
  env:
    OPENAI_API_KEY: ${{ secrets.TEST_OPENAI_API_KEY }}
  run: pytest -m requires_external
```

## Summary

| What | Where | How |
|------|-------|-----|
| **Local Testing** | Your computer | `.env.test` file (gitignored) |
| **CI/CD Testing** | GitHub Actions | GitHub Secrets (encrypted) |
| **Production** | Deployment server | Environment variables or secret management service |

**Key Takeaway:** Never commit secrets to git. Use `.env.test` locally and GitHub Secrets for CI/CD.

## Additional Resources

- [GitHub Encrypted Secrets Documentation](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [GitHub Actions Security Hardening](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)
- [DocuElevate Testing Guide](./Testing.md)
- [DocuElevate Configuration Guide](./ConfigurationGuide.md)
