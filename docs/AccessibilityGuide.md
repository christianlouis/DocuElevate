# Accessibility Guide

DocuElevate targets **WCAG 2.1 Level AA** compliance across all user-facing pages. This guide documents the accessibility standards, patterns, and practices used in the project.

## Table of Contents

- [Standards Overview](#standards-overview)
- [ARIA Patterns Used](#aria-patterns-used)
- [Keyboard Navigation](#keyboard-navigation)
- [Color and Contrast](#color-and-contrast)
- [Forms and Inputs](#forms-and-inputs)
- [Tables](#tables)
- [Modals and Dialogs](#modals-and-dialogs)
- [Dynamic Content](#dynamic-content)
- [Images and Icons](#images-and-icons)
- [Testing and Validation](#testing-and-validation)
- [Developer Checklist](#developer-checklist)

## Standards Overview

DocuElevate follows [WCAG 2.1 Level AA](https://www.w3.org/WAI/WCAG21/quickref/?currentsidebar=%23col_overview&levels=aaa) guidelines. The key principles are:

| Principle | Description |
|-----------|-------------|
| **Perceivable** | Information and UI components must be presentable in ways all users can perceive |
| **Operable** | UI components and navigation must be operable via keyboard and assistive technologies |
| **Understandable** | Information and UI operation must be understandable |
| **Robust** | Content must be robust enough for a wide variety of user agents and assistive technologies |

## ARIA Patterns Used

### Landmarks

`base.html` provides the following landmark structure on every page:

```html
<a href="#main-content" class="skip-link">Skip to main content</a>
<nav aria-label="Main navigation">...</nav>
<main id="main-content">{% block content %}{% endblock %}</main>
<footer role="contentinfo">
  <nav aria-label="Footer navigation">...</nav>
</footer>
```

### Navigation

- Active page links use `aria-current="page"`
- The admin dropdown uses `aria-haspopup="true"`, `aria-expanded`, `role="menu"`, and `role="menuitem"`
- The mobile menu toggle has `aria-label="Toggle navigation menu"` and `aria-expanded`

### Decorative Icons

Font Awesome icons that appear next to descriptive text must have `aria-hidden="true"`:

```html
<!-- Correct: icon is decorative, text provides meaning -->
<a href="/settings">
  <i class="fas fa-cog" aria-hidden="true"></i> Settings
</a>

<!-- Correct: icon-only button needs aria-label -->
<button aria-label="Delete file">
  <i class="fas fa-trash" aria-hidden="true"></i>
</button>
```

## Keyboard Navigation

### Skip Link

Every page inherits a skip-to-content link from `base.html` that becomes visible on keyboard focus:

```css
.skip-link:focus {
  position: fixed;
  top: 0;
  left: 0;
  /* ... visible styles ... */
}
```

### Focus Indicators

Global `focus-visible` styles are defined in `frontend/static/styles.css`:

```css
a:focus-visible,
button:focus-visible,
input:focus-visible,
select:focus-visible,
textarea:focus-visible,
[tabindex]:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}
```

> **Warning:** Never remove or suppress focus indicators with `outline: none` unless you provide an equally visible alternative.

### Interactive Custom Elements

When using `<div>` or `<span>` as interactive elements (avoid when possible), ensure:

```html
<div
  role="button"
  tabindex="0"
  onclick="handleClick()"
  onkeydown="if(event.key==='Enter'||event.key===' '){handleClick();}"
  aria-label="Descriptive action name"
>
```

## Color and Contrast

### Minimum Ratios (WCAG 1.4.3)

| Text Type | Minimum Contrast Ratio |
|-----------|----------------------|
| Normal text (< 18pt) | 4.5:1 |
| Large text (≥ 18pt or ≥ 14pt bold) | 3:1 |
| UI components and graphical objects | 3:1 |

### Dark Mode

Dark mode overrides in `styles.css` are verified for WCAG AA contrast ratios. When adding new color values:

1. Verify light mode contrast at [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/)
2. Verify dark mode contrast for the corresponding dark override
3. Never rely on color alone — always pair with text, icons, or patterns

### Status Badges

Status indicators use both color **and** text:

```html
<span class="status-badge status-completed">Completed</span>
<span class="status-badge status-failed">Failed</span>
```

## Forms and Inputs

### Labels (WCAG 1.3.1, 3.3.2)

Every form input **must** have an associated label:

```html
<!-- Preferred: explicit label with for/id -->
<label for="username" class="block text-sm font-medium">Username</label>
<input type="text" id="username" name="username" required />

<!-- Hidden inputs: use aria-label -->
<input type="file" class="hidden" aria-label="Select files to upload" />
```

### Error Messages (WCAG 3.3.1)

Error messages must be announced to screen readers:

```html
<div role="alert" class="bg-red-100 text-red-700">
  <p>{{ error_message }}</p>
</div>
```

### Search Forms

Use `role="search"` and proper labelling:

```html
<div class="search-box" role="search">
  <label for="search-input" class="sr-only">Search documents</label>
  <input type="search" id="search-input" placeholder="Search..." />
  <button type="button" aria-label="Search documents">
    <i class="fas fa-search" aria-hidden="true"></i> Search
  </button>
</div>
```

## Tables

### Required Structure (WCAG 1.3.1)

```html
<table aria-label="File records">
  <thead>
    <tr>
      <th scope="col">Filename</th>
      <th scope="col">Size</th>
      <th scope="col">Status</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>document.pdf</td>
      <td>1.2 MB</td>
      <td>Completed</td>
    </tr>
  </tbody>
</table>
```

### Sortable Columns

Add `aria-sort` to indicate the current sort state:

```html
<th scope="col" class="sortable" aria-sort="ascending">
  Filename <span class="sort-indicator active">▲</span>
</th>
```

## Modals and Dialogs

### Required Attributes (WCAG 4.1.2)

```html
<div
  id="deleteModal"
  class="modal"
  role="dialog"
  aria-modal="true"
  aria-labelledby="deleteModalTitle"
>
  <div class="modal-content">
    <h2 id="deleteModalTitle">Confirm Deletion</h2>
    <p>Are you sure you want to delete this file?</p>
    <button>Cancel</button>
    <button>Delete</button>
  </div>
</div>
```

### Focus Management

When opening a modal:
1. Move focus into the dialog (first focusable element or the dialog itself)
2. Trap focus within the dialog while open
3. Return focus to the trigger element when closed

## Dynamic Content

### Live Regions (WCAG 4.1.3)

Content that updates dynamically must be announced to screen readers:

```html
<!-- Upload progress -->
<div id="uploadProgress" role="status" aria-live="polite">
  <!-- Dynamic progress updates appear here -->
</div>

<!-- Status messages -->
<div id="statusMessage" aria-live="polite">
  <!-- Success/error messages appear here -->
</div>

<!-- Search results -->
<div id="search-results" aria-live="polite" aria-relevant="additions removals">
  <!-- Results injected by JavaScript -->
</div>
```

| Attribute | Use When |
|-----------|----------|
| `aria-live="polite"` | Updates that don't require immediate attention (search results, progress) |
| `aria-live="assertive"` | Critical updates that require immediate attention (errors) |
| `role="status"` | Status information (equivalent to `aria-live="polite"`) |
| `role="alert"` | Important messages that require immediate attention |

## Images and Icons

### Content Images

```html
<img src="/static/images/logo.svg" alt="DocuElevate Logo" class="h-16" />
```

### Decorative Images

```html
<img src="/static/decoration.jpg" alt="" />
```

### Icon-Only Buttons

```html
<button aria-label="View file details" title="View details">
  <i class="fas fa-info-circle" aria-hidden="true"></i>
</button>
```

### Icons with Adjacent Text

```html
<a href="/upload">
  <i class="fas fa-upload" aria-hidden="true"></i> Upload
</a>
```

## Testing and Validation

### Automated Checks (CI Pipeline)

The CI pipeline runs `djlint` on every pull request:

```bash
# Run locally before committing
djlint frontend/templates/ --lint
```

Configuration is in `pyproject.toml` under `[tool.djlint]`. The linter enforces:

| Rule | Description |
|------|-------------|
| H005 | `<html>` tag must have `lang` attribute |
| H013 | `<img>` tag must have `alt` attribute |
| H016 | Document must have `<title>` tag |
| H025 | Tag should not be an orphan |
| H026 | Empty `id` and `class` attributes should be removed |

### Manual Testing

For each new feature or UI change, verify:

1. **Keyboard navigation**: Tab through all interactive elements; confirm logical focus order
2. **Screen reader**: Test with a screen reader (VoiceOver on macOS, NVDA on Windows, Orca on Linux)
3. **Color contrast**: Check new color combinations with [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/)
4. **Zoom**: Test at 200% zoom; ensure content remains usable
5. **Responsive**: Test at mobile viewport widths (320px, 375px)

### Browser Testing Tools

- **Chrome DevTools Accessibility panel** — audit ARIA attributes and contrast
- **axe DevTools** browser extension — automated WCAG scanning
- **Lighthouse** — includes accessibility audit in Performance tab

## Developer Checklist

Use this checklist when creating or modifying UI templates:

- [ ] All images have appropriate `alt` attributes
- [ ] All decorative icons have `aria-hidden="true"`
- [ ] All icon-only buttons have `aria-label`
- [ ] All form inputs have associated labels (via `for`/`id` or `aria-label`)
- [ ] All tables have `aria-label` or `<caption>` and `scope` on headers
- [ ] All modals have `role="dialog"`, `aria-modal="true"`, and `aria-labelledby`
- [ ] Dynamic content areas have `aria-live="polite"` or appropriate role
- [ ] Color contrast meets 4.5:1 for normal text, 3:1 for large text
- [ ] All interactive elements are keyboard-accessible
- [ ] Focus indicators are visible on all interactive elements
- [ ] `djlint frontend/templates/ --lint` passes with zero errors
- [ ] Page heading hierarchy is correct (h1 → h2 → h3, no skipped levels)
