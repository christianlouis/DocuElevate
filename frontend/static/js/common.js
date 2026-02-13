// frontend/static/js/common.js

/**
 * Safely escape a string for use in text content to prevent XSS.
 * @param {string} str
 * @returns {string}
 */
function escapeText(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.textContent;
}

/**
 * Build the authenticated user UI using DOM API (avoids innerHTML / XSS).
 * @param {string} pictureUrl  Gravatar or profile image URL
 * @param {string} name        Display name
 * @param {string} size        Tailwind size class pair, e.g. "w-8 h-8"
 * @param {boolean} showLabel  Whether to show "Logout" text next to icon
 * @returns {HTMLElement}
 */
function buildAuthElement(pictureUrl, name, size, showLabel) {
  const wrapper = document.createElement('div');
  wrapper.className = showLabel
    ? 'flex items-center justify-between'
    : 'flex items-center';

  const inner = document.createElement('div');
  inner.className = 'flex items-center';

  const img = document.createElement('img');
  img.src = pictureUrl;
  img.alt = 'Avatar';
  img.className = `${size} rounded-full mr-2`;

  const span = document.createElement('span');
  span.textContent = escapeText(name);

  inner.appendChild(img);
  inner.appendChild(span);

  const link = document.createElement('a');
  link.href = '/logout';
  link.className = showLabel
    ? 'text-red-600 hover:text-red-800'
    : 'ml-3 text-red-600 hover:text-red-800';

  const icon = document.createElement('i');
  icon.className = 'fas fa-sign-out-alt';
  link.appendChild(icon);
  if (showLabel) {
    link.appendChild(document.createTextNode(' Logout'));
  }

  if (showLabel) {
    wrapper.appendChild(inner);
    wrapper.appendChild(link);
  } else {
    inner.appendChild(link);
    wrapper.appendChild(inner);
  }

  return wrapper;
}

/**
 * Build a simple login link element (safe – no dynamic data).
 * @returns {HTMLAnchorElement}
 */
function buildLoginLink() {
  const a = document.createElement('a');
  a.href = '/login';
  a.className = 'text-blue-600';
  a.textContent = 'Login';
  return a;
}

/**
 * Replace all children of a container with a single new child.
 * @param {HTMLElement|null} container
 * @param {HTMLElement} child
 */
function replaceContent(container, child) {
  if (!container) return;
  container.textContent = '';          // clear existing content safely
  container.appendChild(child);
}

// Check authentication status and update the auth section
(async function() {
  console.log('Checking authentication status...');
  try {
    const response = await fetch('/api/auth/whoami');
    const data = await response.json();

    const authSection = document.getElementById("authSection");
    const mobileAuthSection = document.getElementById("mobileAuthSection");

    if (data.email) {
      const displayName = data.name || data.preferred_username || data.email;

      replaceContent(authSection,       buildAuthElement(data.picture, displayName, 'w-8 h-8', false));
      replaceContent(mobileAuthSection, buildAuthElement(data.picture, displayName, 'w-6 h-6', true));
    } else {
      replaceContent(authSection,       buildLoginLink());
      replaceContent(mobileAuthSection, buildLoginLink());
    }
  } catch (error) {
    console.error('Authentication check failed:', error);
    const authSection = document.getElementById("authSection");
    const mobileAuthSection = document.getElementById("mobileAuthSection");

    replaceContent(authSection,       buildLoginLink());
    replaceContent(mobileAuthSection, buildLoginLink());
  }
})();

// Other common functionality can be added here
