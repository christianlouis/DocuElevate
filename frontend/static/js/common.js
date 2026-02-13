// frontend/static/js/common.js

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

      // User is logged in
      let authHTML = `
        <div class="flex items-center">
          <img src="${data.picture}" alt="Avatar" class="w-8 h-8 rounded-full mr-2" />
          <span>${displayName}</span>
          <a href="/logout" class="ml-3 text-red-600 hover:text-red-800">
            <i class="fas fa-sign-out-alt"></i>
          </a>
        </div>
      `;

      if (authSection) {
        authSection.innerHTML = authHTML;
      }

      if (mobileAuthSection) {
        mobileAuthSection.innerHTML = `
          <div class="flex items-center justify-between">
            <div class="flex items-center">
              <img src="${data.picture}" alt="Avatar" class="w-6 h-6 rounded-full mr-2" />
              <span>${displayName}</span>
            </div>
            <a href="/logout" class="text-red-600 hover:text-red-800">
              <i class="fas fa-sign-out-alt"></i> Logout
            </a>
          </div>
        `;
      }
    } else {
      // User is not logged in (this shouldn't happen with current setup, but keeping as fallback)
      if (authSection) {
        authSection.innerHTML = `<a href="/login" class="text-blue-600">Login</a>`;
      }

      if (mobileAuthSection) {
        mobileAuthSection.innerHTML = `<a href="/login" class="text-blue-600">Login</a>`;
      }
    }
  } catch (error) {
    console.error('Authentication check failed:', error);
    // Fallback if whoami endpoint fails
    const authSection = document.getElementById("authSection");
    const mobileAuthSection = document.getElementById("mobileAuthSection");

    if (authSection) {
      authSection.innerHTML = `<a href="/login" class="text-blue-600">Login</a>`;
    }

    if (mobileAuthSection) {
      mobileAuthSection.innerHTML = `<a href="/login" class="text-blue-600">Login</a>`;
    }
  }
})();

// Other common functionality can be added here
