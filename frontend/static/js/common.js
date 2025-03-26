// frontend/static/js/common.js

(async function checkAuth() {
    try {
      const resp = await fetch("/api/whoami");
      if (resp.ok) {
        const data = await resp.json();
        const authSection = document.getElementById("authSection");
        if (!authSection) return;
        authSection.innerHTML = '';
  
        const img = document.createElement('img');
        img.src = data.picture;
        img.alt = 'User Avatar';
        img.className = 'inline-block h-8 w-8 rounded-full mr-2';
  
        const textNode = document.createTextNode('Logged in as ');
        const strong = document.createElement('strong');
        strong.textContent = data.email;
  
        const logoutLink = document.createElement('a');
        logoutLink.href = '/logout';
        logoutLink.className = 'ml-4 text-blue-600 hover:text-blue-800';
        logoutLink.textContent = 'Logout';
  
        authSection.appendChild(img);
        authSection.appendChild(textNode);
        authSection.appendChild(strong);
        authSection.appendChild(logoutLink);
      } else {
        const authSection = document.getElementById("authSection");
        if (authSection) {
          authSection.innerHTML =
            `<a href="/login" class="text-blue-600">Login</a>`;
        }
      }
    } catch (error) {
      // Fallback if whoami endpoint fails
      const authSection = document.getElementById("authSection");
      if (authSection) {
        authSection.innerHTML =
          `<a href="/login" class="text-blue-600">Login</a>`;
      }
    }
  })();
  