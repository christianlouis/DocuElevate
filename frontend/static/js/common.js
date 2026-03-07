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

/**
 * Build a small icon + text menu item element.
 * @private
 * @param {string} href
 * @param {string} iconClass  - Font Awesome classes for the <i> element
 * @param {string} label
 * @param {string} [extraClasses] - additional classes for the <a>
 */
function _makeMenuLink(href, iconClass, label, extraClasses = '') {
  const a = document.createElement('a');
  a.href = href;
  a.className = `flex items-center px-4 py-2 text-sm hover:bg-gray-50 ${extraClasses}`.trim();
  a.setAttribute('role', 'menuitem');
  const icon = document.createElement('i');
  icon.className = `${iconClass} w-4 mr-2`;
  icon.setAttribute('aria-hidden', 'true');
  a.appendChild(icon);
  a.appendChild(document.createTextNode(label));
  return a;
}

// Check authentication status and update the auth section
(async function () {
  try {
    const response = await fetch('/api/auth/whoami');
    const data = await response.json();

    const authSection = document.getElementById('authSection');
    const mobileAuthSection = document.getElementById('mobileAuthSection');

    if (data && data.email) {
      const displayName = data.name || data.preferred_username || data.email;

      // ── Show admin menu items if the user is an admin ──────────────────────
      if (data.is_admin) {
        const adminMenuContainer = document.getElementById('adminMenuContainer');
        if (adminMenuContainer) adminMenuContainer.classList.remove('hidden');
        const mobileAdminSection = document.getElementById('mobileAdminSection');
        if (mobileAdminSection) mobileAdminSection.classList.remove('hidden');
      }

      // ── Desktop: account dropdown ─────────────────────────────────────────
      if (authSection) {
        authSection.textContent = '';

        // Wrapper – positions the dropdown
        const wrapper = document.createElement('div');
        wrapper.className = 'relative';

        // Toggle button
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className =
          'flex items-center gap-2 px-2 py-1 rounded-md text-gray-700 hover:text-gray-900 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-blue-500';
        btn.setAttribute('aria-haspopup', 'true');
        btn.setAttribute('aria-expanded', 'false');
        btn.setAttribute('aria-label', `Account menu for ${displayName}`);

        const avatar = document.createElement('img');
        avatar.src = data.picture;
        avatar.alt = 'Avatar';
        avatar.className = 'w-8 h-8 rounded-full';

        const nameSpan = document.createElement('span');
        nameSpan.className = 'hidden lg:inline text-sm font-medium max-w-[120px] truncate';
        nameSpan.textContent = displayName;

        const chevron = document.createElement('i');
        chevron.className = 'fas fa-chevron-down text-xs text-gray-400';
        chevron.setAttribute('aria-hidden', 'true');

        btn.appendChild(avatar);
        btn.appendChild(nameSpan);
        btn.appendChild(chevron);

        // Dropdown menu panel
        const menu = document.createElement('div');
        menu.className =
          'absolute right-0 mt-2 w-52 bg-white rounded-md shadow-lg ring-1 ring-black ring-opacity-5 z-50 hidden';
        menu.setAttribute('role', 'menu');
        menu.setAttribute('aria-label', 'Account menu');

        // User info header
        const header = document.createElement('div');
        header.className = 'px-4 py-3 border-b border-gray-100';
        const headerName = document.createElement('p');
        headerName.className = 'text-sm font-semibold text-gray-800 truncate';
        headerName.textContent = displayName;
        const headerEmail = document.createElement('p');
        headerEmail.className = 'text-xs text-gray-500 truncate';
        headerEmail.textContent = data.email;
        header.appendChild(headerName);
        header.appendChild(headerEmail);

        // Links section
        const linksDiv = document.createElement('div');
        linksDiv.className = 'py-1';
        linksDiv.appendChild(
          _makeMenuLink('/subscription', 'fas fa-layer-group text-indigo-400', 'My Subscription', 'text-gray-700')
        );

        // Divider + Sign Out
        const divider = document.createElement('div');
        divider.className = 'border-t border-gray-100';
        const signOutDiv = document.createElement('div');
        signOutDiv.className = 'py-1';
        signOutDiv.appendChild(
          _makeMenuLink('/logout', 'fas fa-sign-out-alt text-red-400', 'Sign Out', 'text-red-600')
        );

        menu.appendChild(header);
        menu.appendChild(linksDiv);
        menu.appendChild(divider);
        menu.appendChild(signOutDiv);

        // Toggle behaviour
        btn.addEventListener('click', function (e) {
          e.stopPropagation();
          const hidden = menu.classList.contains('hidden');
          menu.classList.toggle('hidden');
          btn.setAttribute('aria-expanded', hidden ? 'true' : 'false');
        });
        document.addEventListener('click', function () {
          menu.classList.add('hidden');
          btn.setAttribute('aria-expanded', 'false');
        });

        wrapper.appendChild(btn);
        wrapper.appendChild(menu);
        authSection.appendChild(wrapper);
      }

      // ── Mobile: user info + links ─────────────────────────────────────────
      if (mobileAuthSection) {
        mobileAuthSection.textContent = '';

        // User info row
        const userRow = document.createElement('div');
        userRow.className = 'flex items-center gap-3 px-3 py-3';
        const mAvatar = document.createElement('img');
        mAvatar.src = data.picture;
        mAvatar.alt = 'Avatar';
        mAvatar.className = 'w-8 h-8 rounded-full flex-shrink-0';
        const mUserInfo = document.createElement('div');
        mUserInfo.className = 'min-w-0';
        const mName = document.createElement('p');
        mName.className = 'text-sm font-semibold text-gray-800 truncate';
        mName.textContent = displayName;
        const mEmail = document.createElement('p');
        mEmail.className = 'text-xs text-gray-500 truncate';
        mEmail.textContent = data.email;
        mUserInfo.appendChild(mName);
        mUserInfo.appendChild(mEmail);
        userRow.appendChild(mAvatar);
        userRow.appendChild(mUserInfo);
        mobileAuthSection.appendChild(userRow);

        // Subscription link
        const subLink = document.createElement('a');
        subLink.href = '/subscription';
        subLink.className =
          'flex items-center px-3 py-3 rounded-md text-base font-medium text-gray-700 hover:text-gray-900 hover:bg-gray-50';
        const subIcon = document.createElement('i');
        subIcon.className = 'fas fa-layer-group mr-2 text-indigo-400';
        subIcon.setAttribute('aria-hidden', 'true');
        subLink.appendChild(subIcon);
        subLink.appendChild(document.createTextNode('My Subscription'));
        mobileAuthSection.appendChild(subLink);

        // Logout link
        const logoutLink = document.createElement('a');
        logoutLink.href = '/logout';
        logoutLink.className =
          'flex items-center px-3 py-3 rounded-md text-base font-medium text-red-600 hover:text-red-800 hover:bg-red-50';
        const logoutIcon = document.createElement('i');
        logoutIcon.className = 'fas fa-sign-out-alt mr-2';
        logoutIcon.setAttribute('aria-hidden', 'true');
        logoutLink.appendChild(logoutIcon);
        logoutLink.appendChild(document.createTextNode('Sign Out'));
        mobileAuthSection.appendChild(logoutLink);
      }
    } else {
      // ── User is NOT logged in ─────────────────────────────────────────────
      _renderLoggedOutAuth(authSection, mobileAuthSection);
    }
  } catch (_err) {
    // Fallback when whoami fails (network error, auth disabled, etc.)
    const authSection = document.getElementById('authSection');
    const mobileAuthSection = document.getElementById('mobileAuthSection');
    _renderLoggedOutAuth(authSection, mobileAuthSection);
  }
})();

/**
 * Render the login / get-started buttons for unauthenticated visitors.
 * Reads the data-multi-user attribute that the server injects on <body> to
 * decide whether to show a prominent "Get Started" CTA alongside the login link.
 */
function _renderLoggedOutAuth(authSection, mobileAuthSection) {
  const multiUser = document.body.getAttribute('data-multi-user') === 'true';

  if (authSection) {
    authSection.textContent = '';
    const row = document.createElement('div');
    row.className = 'flex items-center gap-2';

    const loginLink = document.createElement('a');
    loginLink.href = '/login';
    loginLink.className =
      'px-3 py-1.5 rounded-md text-sm font-medium text-gray-700 hover:text-gray-900 hover:bg-gray-100 border border-gray-300';
    loginLink.textContent = 'Log In';
    row.appendChild(loginLink);

    if (multiUser) {
      const startLink = document.createElement('a');
      startLink.href = '/pricing';
      startLink.className =
        'px-3 py-1.5 rounded-md text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500';
      startLink.textContent = 'Get Started';
      row.appendChild(startLink);
    }

    authSection.appendChild(row);
  }

  if (mobileAuthSection) {
    mobileAuthSection.textContent = '';

    const loginLink = document.createElement('a');
    loginLink.href = '/login';
    loginLink.className =
      'block px-3 py-3 rounded-md text-base font-medium text-blue-600 hover:text-blue-800 hover:bg-blue-50';
    const loginIcon = document.createElement('i');
    loginIcon.className = 'fas fa-sign-in-alt mr-2';
    loginIcon.setAttribute('aria-hidden', 'true');
    loginLink.appendChild(loginIcon);
    loginLink.appendChild(document.createTextNode('Log In'));
    mobileAuthSection.appendChild(loginLink);

    if (multiUser) {
      const startLink = document.createElement('a');
      startLink.href = '/pricing';
      startLink.className =
        'block px-3 py-3 rounded-md text-base font-medium text-white bg-blue-600 hover:text-white hover:bg-blue-700 mt-1';
      const startIcon = document.createElement('i');
      startIcon.className = 'fas fa-arrow-right mr-2';
      startIcon.setAttribute('aria-hidden', 'true');
      startLink.appendChild(startIcon);
      startLink.appendChild(document.createTextNode('Get Started'));
      mobileAuthSection.appendChild(startLink);
    }
  }
}
