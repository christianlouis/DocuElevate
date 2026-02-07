---
applyTo: "docs/**/*.md"
---

# Documentation Instructions

These instructions apply to all documentation files in the `docs/` directory.

## Documentation Structure
- User-facing documentation in `docs/` directory
- All documentation in Markdown format
- Follow existing documentation style and structure

## Existing Documentation
- `docs/UserGuide.md` - How to use DocuElevate
- `docs/API.md` - API reference and examples
- `docs/DeploymentGuide.md` - Deployment instructions
- `docs/ConfigurationGuide.md` - Configuration options
- `docs/Troubleshooting.md` - Common issues and solutions
- `AGENTIC_CODING.md` - Development guide for AI agents
- `CONTRIBUTING.md` - Contribution guidelines
- `README.md` - Project overview and quickstart

## Markdown Style

### Headers
```markdown
# H1 - Document Title (only one per file)

## H2 - Major Sections

### H3 - Subsections

#### H4 - Minor subsections (use sparingly)
```

### Code Blocks
Always specify the language for syntax highlighting:
````markdown
```python
def example_function():
    """Example Python code."""
    return "Hello, World!"
```

```bash
# Shell commands
docker-compose up -d
```

```json
{
  "key": "value"
}
```
````

### Lists
```markdown
- Unordered list item 1
- Unordered list item 2
  - Nested item
  - Another nested item

1. Ordered list item 1
2. Ordered list item 2
3. Ordered list item 3
```

### Links
```markdown
[Link text](https://example.com)
[Internal link](./UserGuide.md)
[Link to section](#installation)
```

### Images
```markdown
![Alt text](path/to/image.png)

<div align="center">
  <img src="path/to/image.png" alt="Descriptive alt text" width="80%" />
  <p><em>Image caption</em></p>
</div>
```

### Tables
```markdown
| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Value 1  | Value 2  | Value 3  |
| Value 4  | Value 5  | Value 6  |
```

### Admonitions and Notes
```markdown
> **Note:** This is an important note.

> **Warning:** This is a warning message.

> **Tip:** This is a helpful tip.
```

## Content Guidelines

### Writing Style
- Use clear, concise language
- Write in second person (you/your) for user-facing docs
- Use present tense
- Avoid jargon; explain technical terms when necessary
- Use active voice
- Keep sentences short and focused

### Documentation Types

#### User Documentation
- Focus on **how to use** features, not implementation details
- Include step-by-step instructions
- Provide examples for common use cases
- Add screenshots or diagrams when helpful
- Explain what each feature does and when to use it

Example:
```markdown
## Uploading Documents

To upload a document to DocuElevate:

1. Navigate to the Upload page
2. Click "Choose File" and select your document
3. Select the destination (Dropbox, Google Drive, etc.)
4. Click "Upload"

The document will be automatically processed and stored in your selected destination.
```

#### API Documentation
- Document all endpoints with examples
- Show request and response formats
- Include authentication requirements
- Provide example curl commands
- Document error responses

Example:
```markdown
### POST /api/documents/upload

Upload a new document for processing.

**Authentication:** Required

**Request:**
```bash
curl -X POST "http://localhost:8000/api/documents/upload" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@document.pdf"
```

**Response (201 Created):**
```json
{
  "id": 123,
  "filename": "document.pdf",
  "status": "processing"
}
```
```

#### Configuration Documentation
- List all configuration options
- Provide default values
- Explain what each option does
- Include example configurations
- Note which options are required vs. optional

Example:
```markdown
### OPENAI_API_KEY

**Type:** String  
**Required:** Yes  
**Default:** None

Your OpenAI API key for metadata extraction.

```bash
OPENAI_API_KEY=sk-...
```
```

#### Troubleshooting Documentation
- Start with the symptom/error
- Provide clear diagnosis steps
- Offer solutions
- Include common causes

Example:
```markdown
### Error: "Connection refused" when starting services

**Cause:** Docker services are not running or ports are already in use.

**Solution:**
1. Check if Docker is running: `docker ps`
2. Check port availability: `lsof -i :8000`
3. Restart Docker services: `docker-compose restart`
```

## Code Examples
- Always test code examples before including them
- Use realistic examples that users can adapt
- Include comments explaining non-obvious parts
- Show complete examples, not just fragments

## Version Information
- Update documentation when changing features
- Note version numbers when features are added
- Mark deprecated features clearly

## Cross-References
- Link to related documentation
- Reference other sections when appropriate
- Keep the documentation interconnected

Example:
```markdown
For deployment instructions, see the [Deployment Guide](./DeploymentGuide.md).

For API details, refer to the [API Documentation](./API.md).
```

## Updating Documentation
When making code changes:
1. Update relevant documentation in the same PR
2. Check for outdated information
3. Add new sections for new features
4. Update examples if behavior changes
5. Review related documentation for consistency

## Screenshots and Diagrams
- Use clear, high-quality images
- Annotate screenshots when helpful
- Keep diagrams simple and focused
- Update screenshots when UI changes
- Use consistent styling in diagrams

## Accessibility
- Use descriptive alt text for images
- Ensure proper heading hierarchy
- Make links descriptive (avoid "click here")
- Use semantic formatting (bold, italic, code) appropriately

## README.md Specific
- Keep README concise and focused on getting started
- Include badges for build status, version, license
- Show the most important features first
- Link to detailed documentation
- Include quick start instructions
- Add screenshots of the main interface

## Configuration Guide Updates
When adding new configuration options:
- Add to `docs/ConfigurationGuide.md`
- Include type, default value, and description
- Provide example usage
- Note any dependencies on other config options
- Update `.env.demo` with the new option
