# DocuNova Configuration 

This section contains detailed documentation about configuring DocuNova for your environment.

## Configuration Overview

DocuNova is designed to be highly configurable through environment variables, typically set in a `.env` file. This allows you to enable only the services and integrations you need for your specific use case.

## Documentation Sections

- [Configuration Guide](ConfigurationGuide.md) - Complete list of all available configuration parameters
- [Google Drive Setup](GoogleDriveSetup.md) - How to set up Google Drive integration
- [Dropbox Setup](DropboxSetup.md) - How to set up Dropbox integration
- [OneDrive Setup](OneDriveSetup.md) - How to set up Microsoft OneDrive/Graph integration
- [Amazon S3 Setup](AmazonS3Setup.md) - How to set up Amazon S3 integration

## Configuration File Location

The `.env` file should be placed at the root of the project directory. When using Docker Compose, you can reference it with the `env_file` directive in your `docker-compose.yml`.

## Example Configuration

Below is a minimal example configuration to get started:

```dotenv
# Core settings
DATABASE_URL=sqlite:///./app/database.db
REDIS_URL=redis://redis:6379/0
WORKDIR=/workdir
GOTENBERG_URL=http://gotenberg:3000
EXTERNAL_HOSTNAME=docunova.example.com

# Enable only the services you need
# For detailed parameters, see the Configuration Guide
```

For a complete example with all possible parameters, see the [Configuration Guide](ConfigurationGuide.md).
