# GitHub Copilot Configuration

## Overview

This document explains the GitHub Copilot workspace configuration for the DocuElevate repository.

## Network Allowlist

The `.github/copilot.yml` file configures the network allowlist for GitHub Copilot coding agents. This allowlist enables the agents to connect to external API services during development and testing workflows.

### Purpose

GitHub Copilot coding agents run in a sandboxed environment with firewall restrictions. By default, most external network connections are blocked for security reasons. The network allowlist explicitly permits connections to trusted domains that are required for:

- Running integration tests with real API services
- Installing dependencies from package registries
- Validating external service configurations
- Testing cloud storage integrations

### Configured Domains

The following domains are currently allowed:

#### AI/ML Services
- **api.openai.com** - OpenAI API for GPT-based metadata extraction
- **test.cognitiveservices.azure.com** - Azure Document Intelligence for OCR
- **\*.cognitiveservices.azure.com** - Additional Azure AI endpoints

#### Cloud Storage & Authentication
- **oauth2.googleapis.com** - Google OAuth2 authentication
- **accounts.google.com** - Google account services
- **www.googleapis.com** - Google Drive API
- **login.microsoftonline.com** - Microsoft authentication
- **graph.microsoft.com** - Microsoft Graph API
- **s3.amazonaws.com** - AWS S3 storage
- **\*.s3.amazonaws.com** - Regional S3 endpoints
- **api.dropboxapi.com** - Dropbox API
- **content.dropboxapi.com** - Dropbox content endpoints

#### Package Registries
- **pypi.org** - Python Package Index
- **files.pythonhosted.org** - PyPI content distribution

## Configuration File Format

The configuration uses YAML format:

```yaml
network:
  allowlist:
    - domain1.com
    - domain2.com
    - "*.wildcard-domain.com"  # Wildcards must be quoted
```

## Modifying the Allowlist

To add new domains to the allowlist:

1. Edit `.github/copilot.yml`
2. Add the domain under `network.allowlist`
3. Use quotes for wildcard domains (e.g., `"*.example.com"`)
4. Add a comment explaining why the domain is needed
5. Validate YAML syntax: `python -c "import yaml; yaml.safe_load(open('.github/copilot.yml'))"`
6. Commit and push the changes

## Testing the Configuration

After updating the allowlist, verify that:

1. The YAML syntax is valid (no parse errors)
2. Integration tests can connect to the required services
3. No unnecessary domains are allowed (principle of least privilege)

## Security Considerations

- Only add domains that are **absolutely required** for development or testing
- Prefer specific subdomains over wildcards when possible
- Document the purpose of each domain in comments
- Review and audit the allowlist periodically
- Remove domains that are no longer needed

## Troubleshooting

### Firewall Blocking Errors

If you encounter errors like:
```
Firewall rules blocked me from connecting to one or more addresses
```

1. Check if the domain is in the allowlist
2. Verify the domain spelling and format
3. Ensure wildcards are properly quoted
4. Wait a few minutes for the configuration to propagate

### YAML Syntax Errors

If the configuration file has syntax errors:

1. Check for proper indentation (2 spaces per level)
2. Ensure wildcards are quoted: `"*.domain.com"`
3. Validate with: `python -c "import yaml; yaml.safe_load(open('.github/copilot.yml'))"`

## References

- [GitHub Copilot Documentation](https://docs.github.com/en/copilot)
- [YAML Specification](https://yaml.org/spec/)
- [DocuElevate Testing Guide](../tests/README_INTEGRATION_TESTS.md)

## Related Files

- `.github/copilot.yml` - Network allowlist configuration
- `tests/test_external_integrations.py` - Integration tests using external APIs
- `tests/conftest.py` - Test fixtures and configuration
