# Build Metadata Automation

## Overview

DocuElevate automatically generates and embeds build metadata (version, build date, Git commit SHA) into the application at build time. This metadata is displayed in the `/status` endpoint and helps track which version of the application is running in production.

## What is Automated

The following metadata is automatically generated and included in every build:

1. **Build Date** - The UTC date and time when the build was created (format: YYYY-MM-DDTHH:MM:SSZ)
2. **Git Commit SHA** - The short Git commit hash (7 characters) of the code being built
3. **Runtime Information** - A comprehensive summary including version, dates, commit info, and more
4. **Application Version** - Read from the `VERSION` file (automatically updated by semantic-release)

## How It Works

### Build Time Generation

When the Docker image is built (locally or in CI/CD), the following happens:

1. **GitHub Actions runs the metadata script** (`scripts/generate_build_metadata.sh`) before building the Docker image
2. **The script generates three files:**
   - `BUILD_DATE` - Contains the build date and time in ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)
   - `GIT_SHA` - Contains the short Git commit hash
   - `RUNTIME_INFO` - Contains detailed build information
3. **The script syncs VERSION** from the latest git tag if out of sync
4. **Docker copies these files** into the image during the build process
5. **The application reads the files** at runtime via `app/config.py` properties

### File Structure

```
DocuElevate/
├── scripts/
│   └── generate_build_metadata.sh    # Script that generates metadata
├── VERSION                             # Manually maintained version number
├── BUILD_DATE                          # Generated at build time (gitignored)
├── GIT_SHA                            # Generated at build time (gitignored)
└── RUNTIME_INFO                        # Generated at build time (gitignored)
```

### Generated Files Format

**BUILD_DATE:**
```
2026-02-11T14:38:06Z
```

**GIT_SHA:**
```
6812d0d
```

**RUNTIME_INFO:**
```
DocuElevate Build Information
==============================
Version: 0.9.1
Build Date: 2026-02-11T14:38:06Z
Git Commit: 6812d0d2c42a4782e78840b052f0e6da24ec8543
Git Short SHA: 6812d0d
Git Branch: main
Commit Date: 2026-02-07T19:32:04Z
Build Timestamp: 2026-02-11T14:38:06Z
==============================
```

## Configuration Properties

The `app/config.py` Settings class provides these properties for accessing build metadata:

### `settings.version` (property)
Returns the application version with the following priority:
1. `APP_VERSION` environment variable
2. Contents of `VERSION` file
3. Default: `"unknown"`

### `settings.build_date` (property)
Returns the build date with the following priority:
1. `BUILD_DATE` environment variable
2. Contents of `BUILD_DATE` file
3. Default: `"Unknown build date"`

### `settings.git_sha` (property)
Returns the Git commit SHA with the following priority:
1. `GIT_COMMIT_SHA` environment variable
2. Contents of `GIT_SHA` file
3. Default: `"unknown"`

### `settings.runtime_info` (property)
Returns detailed runtime information:
1. Contents of `RUNTIME_INFO` file
2. Default: Basic info string with version, build date, and Git SHA

## Usage in Application

### In Python Code

```python
from app.config import settings

# Get version
version = settings.version  # "0.9.1"

# Get build date
build_date = settings.build_date  # "2026-02-11T14:38:06Z"

# Get Git SHA
git_sha = settings.git_sha  # "6812d0d"

# Get full runtime info
runtime_info = settings.runtime_info  # Full multi-line string
```

### In Templates

The `/status` endpoint uses these properties to display metadata:

```python
# app/views/status.py
return templates.TemplateResponse(
    "status_dashboard.html",
    {
        "app_version": settings.version,
        "build_date": settings.build_date,
        "container_info": {
            "git_sha": settings.git_sha[:7],
            "runtime_info": settings.runtime_info,
        }
    }
)
```

## GitHub Actions Integration

The build metadata is generated in two GitHub Actions workflows:

### docker-build.yaml
```yaml
- name: Generate Build Metadata
  run: |
    chmod +x scripts/generate_build_metadata.sh
    ./scripts/generate_build_metadata.sh
```

### docker-ci.yml
```yaml
- name: Generate Build Metadata
  run: |
    chmod +x scripts/generate_build_metadata.sh
    ./scripts/generate_build_metadata.sh
```

These steps run **before** the Docker build step, ensuring the metadata files exist when Docker copies them into the image.

## Local Development

### Manual Generation

To generate build metadata locally:

```bash
# Run the script
./scripts/generate_build_metadata.sh

# Output:
# Generating build metadata...
# ✓ BUILD_DATE: 2026-02-11T14:38:06Z
# ✓ GIT_SHA: 6812d0d
# ✓ VERSION (from file): 0.9.1
# ✓ RUNTIME_INFO generated
```

### Local Docker Build

When building Docker images locally:

```bash
# Generate metadata first
./scripts/generate_build_metadata.sh

# Then build the Docker image
docker build -t docuelevate:local .

# Or use docker-compose
docker-compose build
```

### Testing Without Docker

The application will still work without the generated files:

- `BUILD_DATE` will show "Unknown build date"
- `GIT_SHA` will show "unknown"
- The app will use defaults from `app/config.py`

## Environment Variable Override

You can override any metadata value using environment variables:

```bash
# Override version
export APP_VERSION="1.0.0-custom"

# Override build date
export BUILD_DATE="2026-01-15T10:30:00Z"

# Override Git SHA
export GIT_COMMIT_SHA="abc1234"

# Run the application
python -m uvicorn app.main:app
```

This is useful for:
- Custom builds
- Testing different versions
- Development environments

## Updating the Version

The `VERSION` file is **automatically updated** by semantic-release based on conventional commits. The `generate_build_metadata.sh` script also syncs the `VERSION` file from the latest git tag if it's out of date.

The semantic-release workflow:
1. Analyzes conventional commit messages on the `main` branch
2. Determines the next version number (major, minor, or patch bump)
3. Creates a git tag (e.g., `v0.10.0`)
4. Runs `generate_build_metadata.sh` as the build command, which syncs the `VERSION` file
5. Commits and pushes updated build metadata files

## Troubleshooting

### Problem: Build metadata shows "unknown"

**Solution:** Ensure the script runs before Docker build:
```bash
./scripts/generate_build_metadata.sh
docker build -t docuelevate .
```

### Problem: Git SHA is "unknown"

**Cause:** Building outside of a Git repository

**Solution:**
- Clone the repository properly with `.git` directory
- Or set `GIT_COMMIT_SHA` environment variable

### Problem: Build date is outdated

**Cause:** Using cached Docker layers

**Solution:**
```bash
# Rebuild without cache
docker build --no-cache -t docuelevate .
```

### Problem: Files not copied to Docker image

**Cause:** Files listed in `.dockerignore`

**Solution:**
- Check `.dockerignore` doesn't block `BUILD_DATE`, `GIT_SHA`, or `RUNTIME_INFO`
- The `VERSION` file should always be committed to git

## Best Practices

1. **Always run the script before building** - The CI/CD pipeline does this automatically
2. **Don't commit generated files** - `GIT_SHA` and `RUNTIME_INFO` are in `.gitignore`
3. **Use conventional commits** - Semantic-release determines versions from commit messages
4. **Use semantic versioning** - Follow `MAJOR.MINOR.PATCH` format
5. **Don't manually edit VERSION** - It's managed by semantic-release and the build script

## CI/CD Pipeline Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Semantic Release Workflow (on push to main)                 │
├─────────────────────────────────────────────────────────────┤
│ 1. Analyze conventional commits                             │
│ 2. Determine next version (major/minor/patch)               │
│ 3. Create git tag (e.g., v0.10.0)                           │
│ 4. Run build_command (generate_build_metadata.sh)           │
│    - Syncs VERSION file from latest git tag                 │
│    - Creates BUILD_DATE (with time)                         │
│    - Creates GIT_SHA                                        │
│    - Creates RUNTIME_INFO                                   │
│ 5. Commit and push updated metadata files                   │
│ 6. Create GitHub Release                                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Docker CI Workflow (on push to main)                        │
├─────────────────────────────────────────────────────────────┤
│ 1. Checkout Code                                            │
│ 2. Generate Build Metadata (run script)                     │
│    - Syncs VERSION from git tag                             │
│    - Creates BUILD_DATE, GIT_SHA, RUNTIME_INFO              │
│ 3. Build Docker Image                                       │
│    - Copies VERSION, BUILD_DATE, GIT_SHA, RUNTIME_INFO      │
│ 4. Push to Docker Hub                                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Running Container                                           │
├─────────────────────────────────────────────────────────────┤
│ Application reads metadata from files in /app:              │
│ - /app/VERSION                                              │
│ - /app/BUILD_DATE                                           │
│ - /app/GIT_SHA                                              │
│ - /app/RUNTIME_INFO                                         │
│                                                              │
│ Displays in /status endpoint                                │
└─────────────────────────────────────────────────────────────┘
```

## Future Enhancements

Potential improvements to the build metadata system:

1. **Build number tracking** - Track sequential build numbers
2. **Deployment tracking** - Record when/where each build was deployed
3. **Performance metrics** - Include build time, image size, etc.

## Related Documentation

- [Deployment Guide](./DeploymentGuide.md) - How to deploy DocuElevate
- [Configuration Guide](./ConfigurationGuide.md) - All configuration options
- [API Documentation](./API.md) - API endpoints including `/status`
