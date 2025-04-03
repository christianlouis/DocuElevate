# Contributing to DocuElevate

Thank you for your interest in contributing to DocuElevate! This document provides guidelines and instructions for contributing to the project.

## Code of Conduct

By participating in this project, you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).

## How to Contribute

### Reporting Bugs

If you find a bug in the codebase, please submit an issue on GitHub with:

1. A clear title and description
2. Steps to reproduce the issue
3. Expected behavior
4. Actual behavior
5. Environment information (OS, Docker version, etc.)

### Feature Requests

We welcome feature requests! Please submit an issue with:

1. A clear title and description
2. The problem the feature would solve
3. Any ideas you have for implementing the feature

### Pull Requests

1. Fork the repository
2. Create a new branch for your changes
3. Make your changes
4. Run the tests to ensure everything works
5. Submit a pull request with a clear description of the changes

## Development Environment

### Setting Up Your Environment

```bash
# Clone the repository
git clone https://github.com/christianlouis/document-processor.git
cd document-processor

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Running Tests

```bash
pytest
```

### Code Style

We use:
- Black for Python code formatting
- Flake8 for linting
- isort for import sorting

```bash
# Format code
black .

# Check linting
flake8

# Sort imports
isort .
```

## Project Structure

