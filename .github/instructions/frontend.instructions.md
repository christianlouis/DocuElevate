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

### Accessibility
- Use semantic HTML elements (`nav`, `main`, `article`, `section`)
- Include `alt` text for images
- Use proper heading hierarchy (h1 → h2 → h3)
- Add ARIA labels when needed
- Ensure keyboard navigation works

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
