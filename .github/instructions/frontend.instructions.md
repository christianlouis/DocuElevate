---
applyTo: "frontend/**/*"
---

# Frontend Instructions

These instructions apply to all files in the `frontend/` directory (templates, CSS, JavaScript, images).

## Templates (Jinja2)

### Location and Structure
- All templates in `frontend/templates/`
- Use template inheritance with `base.html`
- Keep templates organized by feature

### Template Patterns
```jinja2
{% extends "base.html" %}

{% block title %}Document Upload - DocuElevate{% endblock %}

{% block content %}
<div class="container mx-auto px-4 py-8">
    <h1 class="text-2xl font-bold mb-4">{{ page_title }}</h1>

    {% if error_message %}
    <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
        {{ error_message }}
    </div>
    {% endif %}

    <form method="post" enctype="multipart/form-data">
        <!-- Form content -->
    </form>
</div>
{% endblock %}
```

### Tailwind CSS Usage
- Use Tailwind utility classes (already configured)
- Follow responsive design: `md:`, `lg:` breakpoints
- Use existing color scheme from the project
- Common patterns:
  - Containers: `container mx-auto px-4`
  - Buttons: `bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded`
  - Cards: `bg-white shadow-md rounded-lg p-6`
  - Forms: `w-full px-3 py-2 border rounded`

### Static Files
- CSS files in `frontend/static/css/`
- JavaScript in `frontend/static/js/`
- Images in `frontend/static/images/`
- Reference with `{{ url_for('static', path='css/style.css') }}`

### JavaScript
- Keep JavaScript minimal - prefer server-side rendering
- Use vanilla JavaScript or minimal dependencies
- Place scripts at the end of the body
- Use `defer` or `async` for external scripts
```html
<script src="{{ url_for('static', path='js/upload.js') }}" defer></script>
```

### Forms
- Use CSRF protection when needed
- Include proper validation
- Show clear error messages
- Use proper `method` (GET/POST) and `enctype` for file uploads
```html
<form method="post" enctype="multipart/form-data">
    <div class="mb-4">
        <label class="block text-gray-700 text-sm font-bold mb-2" for="file">
            Document File
        </label>
        <input
            type="file"
            id="file"
            name="file"
            class="w-full px-3 py-2 border rounded"
            required
        />
    </div>
    <button type="submit" class="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded">
        Upload
    </button>
</form>
```

### Accessibility (WCAG 2.1 Level AA Required)

DocuElevate targets **WCAG 2.1 Level AA** compliance. Every template change **must** follow these rules.
For the full guide with examples, see `docs/AccessibilityGuide.md`.

#### Semantic HTML (WCAG 1.3.1)
- Use semantic elements: `<nav>`, `<main>`, `<article>`, `<section>`, `<header>`, `<footer>`
- Use proper heading hierarchy: one `<h1>` per page, then `<h2>` → `<h3>` (never skip levels)
- Use `<button>` for actions (not `<a>` or `<div>`) and `<a>` for navigation
- Use `<table>` with `<caption>` or `aria-label`, `<thead>`/`<tbody>`, and `scope="col"`/`scope="row"` on headers

#### Images & Icons (WCAG 1.1.1)
- All `<img>` elements **must** have an `alt` attribute — descriptive for content images, `alt=""` for purely decorative ones
- Decorative Font Awesome `<i>` icons **must** have `aria-hidden="true"` when adjacent text already conveys meaning
- Icon-only buttons **must** have `aria-label` describing the action (e.g., `aria-label="Delete file"`)

#### Keyboard Navigation (WCAG 2.1.1, 2.4.1, 2.4.7)
- All interactive elements must be keyboard-reachable (native `<a>`, `<button>`, `<input>`, or add `tabindex="0"` + key handlers)
- `base.html` provides a **skip-to-content** link (`<a href="#main-content" class="skip-link">`) — do not remove it
- Never suppress focus indicators — the global `focus-visible` outline in `styles.css` is required
- Custom interactive widgets (dropdowns, modals) must trap focus correctly

#### ARIA Attributes
- `aria-label` — use on elements whose purpose isn't clear from visible text (icon-only buttons, unlabelled inputs)
- `aria-hidden="true"` — use on purely decorative icons and elements that duplicate adjacent text
- `aria-live="polite"` — add to any container whose content updates dynamically (status messages, search results, upload progress)
- `aria-expanded` — add to buttons that toggle visibility of content (menus, accordions)
- `aria-current="page"` — mark the current page's navigation link
- `aria-sort` — use on sortable table column headers

#### Forms (WCAG 1.3.1, 3.3.2)
- Every `<input>`, `<select>`, and `<textarea>` **must** have an associated `<label>` (via `for`/`id`) or `aria-label`
- Error messages must be linked via `aria-describedby` or announced with `role="alert"`
- Use `role="search"` on search form containers

#### Modals / Dialogs (WCAG 4.1.2)
- Add `role="dialog"`, `aria-modal="true"`, and `aria-labelledby` pointing to the dialog title
- Focus must move into the dialog when opened and return to the trigger when closed

#### Color & Contrast (WCAG 1.4.3, 1.4.1)
- Text must meet 4.5:1 contrast ratio against its background (3:1 for large text)
- Never rely on color alone to convey information — pair color with icons, text labels, or patterns
- Dark-mode overrides in `styles.css` are WCAG AA-verified; maintain this when adding new colors

#### Touch Targets (WCAG 2.5.8)
- All clickable/tappable elements must be at least 44×44 CSS pixels (`min-height:44px; min-width:44px`)

#### Automated Checks
- The CI pipeline runs `djlint` on every PR to catch common accessibility regressions
- Run locally: `djlint frontend/templates/ --lint`
- Configuration is in `pyproject.toml` under `[tool.djlint]`

### Error Handling
- Display user-friendly error messages
- Use flash messages for feedback
- Show loading states for async operations
```jinja2
{% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
        {% for category, message in messages %}
        <div class="bg-{{ category }}-100 border border-{{ category }}-400 text-{{ category }}-700 px-4 py-3 rounded mb-4">
            {{ message }}
        </div>
        {% endfor %}
    {% endif %}
{% endwith %}
```

### URL Generation
- Always use `url_for()` for URLs, never hardcode
- Examples:
  - Routes: `{{ url_for('upload_document') }}`
  - Static: `{{ url_for('static', path='css/style.css') }}`
  - API: `{{ url_for('api_document', document_id=doc.id) }}`

### Template Variables
- Check if variables exist before using them
- Use filters for formatting
```jinja2
{% if document %}
    <p>Uploaded: {{ document.created_at|datetime }}</p>
    <p>Size: {{ document.file_size|filesizeformat }}</p>
{% else %}
    <p>No document found</p>
{% endif %}
```

### Common Components
- Follow existing patterns for headers, footers, navigation
- Reuse template blocks and includes
- Keep components modular
```jinja2
{% include 'components/navigation.html' %}
{% include 'components/document_card.html' with document=doc %}
```

## UI/UX Guidelines
- Maintain consistent spacing using Tailwind's scale (4, 8, 16, etc.)
- Use the existing color palette from the design
- Ensure mobile responsiveness
- Show loading indicators for long operations
- Provide feedback for user actions (success/error messages)
- Keep the interface clean and minimal

## Performance
- Optimize images (compress, use appropriate formats)
- Minimize JavaScript bundle size
- Use lazy loading for images when appropriate
- Cache static assets
