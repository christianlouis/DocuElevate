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
