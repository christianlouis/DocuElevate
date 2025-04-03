/*
 * Self-hosted Font Awesome loader - loads only what we need
 */
(function() {
  // Create link element for CSS
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = '/static/fontawesome/css/all.min.css';
  document.head.appendChild(link);
  
  console.log('Font Awesome loaded locally');
})();
