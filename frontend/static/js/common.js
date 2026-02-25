// frontend/static/js/common.js

// ---------------------------------------------------------------------------
// CSRF token helper
// ---------------------------------------------------------------------------
// Read the CSRF token from the <meta name="csrf-token"> tag injected by the
// server into base.html for every authenticated page.
function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute('content') : '';
}

// Wrap the native fetch() so that every state-changing request automatically
// includes the X-CSRF-Token header without requiring callers to remember it.
(function patchFetch() {
  const _CSRF_METHODS = new Set(['POST', 'PUT', 'DELETE', 'PATCH']);
  const _originalFetch = window.fetch;
  window.fetch = function (input, init) {
    init = init || {};
    const method = (init.method || 'GET').toUpperCase();
    if (_CSRF_METHODS.has(method)) {
      const token = getCsrfToken();
      if (token) {
        // Merge headers so a caller-supplied X-CSRF-Token is not overwritten,
        // but add the token when no override is present.
        const headers = Object.assign({}, init.headers || {});
        if (!headers['X-CSRF-Token']) {
          headers['X-CSRF-Token'] = token;
        }
        init.headers = headers;
      }
    }
    return _originalFetch.call(this, input, init);
  };
})();

// ---------------------------------------------------------------------------
// Dark mode
// ---------------------------------------------------------------------------
// Preference is stored in localStorage under the key 'colorScheme'.
// Values: 'dark' | 'light'  (absence means "follow server/system default").
// The anti-flash <script> in base.html applies the class before page paint.
// ---------------------------------------------------------------------------

/**
 * Sync the icon and label of both desktop and mobile toggle buttons to the
 * current dark-mode state.
 */
function _updateDarkModeButtons() {
  const isDark = document.documentElement.classList.contains('dark');

  // Desktop button
  const btn = document.getElementById('darkModeToggle');
  if (btn) {
    const icon = btn.querySelector('i');
    if (icon) {
      icon.className = isDark ? 'fas fa-sun' : 'fas fa-moon';
    }
    const label = isDark ? 'Switch to light mode' : 'Switch to dark mode';
    btn.setAttribute('title', label);
    btn.setAttribute('aria-label', label);
  }

  // Mobile button
  const mobileIcon = document.getElementById('darkModeIconMobile');
  if (mobileIcon) {
    mobileIcon.className = isDark ? 'fas fa-sun mr-2' : 'fas fa-moon mr-2';
  }
  const mobileText = document.getElementById('darkModeTextMobile');
  if (mobileText) {
    mobileText.textContent = isDark ? 'Light Mode' : 'Dark Mode';
  }
}

/**
 * Toggle dark mode and persist the choice to localStorage.
 * Called from the navbar button (onclick="toggleDarkMode()").
 */
function toggleDarkMode() {
  const isDark = document.documentElement.classList.toggle('dark');
  localStorage.setItem('colorScheme', isDark ? 'dark' : 'light');
  _updateDarkModeButtons();
}

// Initialise button state once the DOM is ready.
document.addEventListener('DOMContentLoaded', function () {
  _updateDarkModeButtons();
});

// React to OS-level theme changes when the user has not explicitly chosen a
// scheme (no localStorage value means "follow the server/system default").
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
  if (localStorage.getItem('colorScheme')) {
    return; // User has an explicit preference; ignore OS changes.
  }
  var serverDefault = document.documentElement.getAttribute('data-color-scheme-default') || 'system';
  if (serverDefault !== 'system') {
    return; // Admin has forced a specific scheme; ignore OS changes.
  }
  if (e.matches) {
    document.documentElement.classList.add('dark');
  } else {
    document.documentElement.classList.remove('dark');
  }
  _updateDarkModeButtons();
});

// ---------------------------------------------------------------------------
// Authentication status
// ---------------------------------------------------------------------------

// Check authentication status and update the auth section
(async function() {
  console.log('Checking authentication status...');
  try {
    const response = await fetch('/api/auth/whoami');
    const data = await response.json();


    const authSection = document.getElementById("authSection");
    const mobileAuthSection = document.getElementById("mobileAuthSection");

    // If we have an email, user is authenticated (the whoami endpoint would have thrown 401 otherwise)
    if (data.email) {
      // Get the display name (prefer name, fall back to preferred_username, then email)
      const displayName = data.name || data.preferred_username || data.email;

      // Show admin menu items if the user is an admin
      if (data.is_admin) {
        const adminMenuContainer = document.getElementById("adminMenuContainer");
        if (adminMenuContainer) {
          adminMenuContainer.classList.remove("hidden");
        }
        const mobileAdminSection = document.getElementById("mobileAdminSection");
        if (mobileAdminSection) {
          mobileAdminSection.classList.remove("hidden");
        }
      }

      // User is logged in - use DOM API to prevent XSS
      if (authSection) {
        authSection.textContent = ''; // Clear existing content
        const container = document.createElement('div');
        container.className = 'flex items-center';
        
        const img = document.createElement('img');
        img.src = data.picture;
        img.alt = 'Avatar';
        img.className = 'w-8 h-8 rounded-full mr-2';
        
        const span = document.createElement('span');
        span.textContent = displayName;
        
        const logoutLink = document.createElement('a');
        logoutLink.href = '/logout';
        logoutLink.className = 'ml-3 text-red-600 hover:text-red-800';
        const icon = document.createElement('i');
        icon.className = 'fas fa-sign-out-alt';
        logoutLink.appendChild(icon);
        
        container.appendChild(img);
        container.appendChild(span);
        container.appendChild(logoutLink);
        authSection.appendChild(container);
      }

      if (mobileAuthSection) {
        mobileAuthSection.textContent = ''; // Clear existing content
        const outerContainer = document.createElement('div');
        outerContainer.className = 'flex items-center justify-between';
        
        const innerContainer = document.createElement('div');
        innerContainer.className = 'flex items-center';
        
        const img = document.createElement('img');
        img.src = data.picture;
        img.alt = 'Avatar';
        img.className = 'w-6 h-6 rounded-full mr-2';
        
        const span = document.createElement('span');
        span.textContent = displayName;
        
        innerContainer.appendChild(img);
        innerContainer.appendChild(span);
        
        const logoutLink = document.createElement('a');
        logoutLink.href = '/logout';
        logoutLink.className = 'text-red-600 hover:text-red-800';
        const icon = document.createElement('i');
        icon.className = 'fas fa-sign-out-alt';
        logoutLink.appendChild(icon);
        logoutLink.appendChild(document.createTextNode(' Logout'));
        
        outerContainer.appendChild(innerContainer);
        outerContainer.appendChild(logoutLink);
        mobileAuthSection.appendChild(outerContainer);
      }
    } else {
      // User is not logged in - use DOM API
      if (authSection) {
        authSection.textContent = '';
        const loginLink = document.createElement('a');
        loginLink.href = '/login';
        loginLink.className = 'text-blue-600';
        loginLink.textContent = 'Login';
        authSection.appendChild(loginLink);
      }

      if (mobileAuthSection) {
        mobileAuthSection.textContent = '';
        const loginLink = document.createElement('a');
        loginLink.href = '/login';
        loginLink.className = 'text-blue-600';
        loginLink.textContent = 'Login';
        mobileAuthSection.appendChild(loginLink);
      }
    }
  } catch (error) {
    console.error('Authentication check failed:', error);
    // Fallback if whoami endpoint fails - use DOM API
    const authSection = document.getElementById("authSection");
    const mobileAuthSection = document.getElementById("mobileAuthSection");

    if (authSection) {
      authSection.textContent = '';
      const loginLink = document.createElement('a');
      loginLink.href = '/login';
      loginLink.className = 'text-blue-600';
      loginLink.textContent = 'Login';
      authSection.appendChild(loginLink);
    }

    if (mobileAuthSection) {
      mobileAuthSection.textContent = '';
      const loginLink = document.createElement('a');
      loginLink.href = '/login';
      loginLink.className = 'text-blue-600';
      loginLink.textContent = 'Login';
      mobileAuthSection.appendChild(loginLink);
    }
  }
})();

// Other common functionality can be added here
