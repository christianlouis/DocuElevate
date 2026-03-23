/**
 * claim.js — Claim-ownership UI helper for unowned documents.
 *
 * Usage: call initClaimOwnership(fileId, i18n) after DOMContentLoaded.
 * The i18n object must contain:
 *   confirm, success, failed
 */
function initClaimOwnership(fileId, i18n) {
  var btn = document.getElementById('claim-btn');
  var msg = document.getElementById('claim-msg');
  if (!btn) return;

  btn.addEventListener('click', function () {
    if (!confirm(i18n.confirm)) return;
    btn.disabled = true;
    fetch('/api/files/' + fileId + '/claim', { method: 'POST' })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
      .then(function (result) {
        if (result.ok || (result.data && result.data.status === 'already_owned')) {
          if (msg) {
            msg.textContent = i18n.success;
            msg.style.color = '#059669';
            msg.style.display = msg.tagName === 'SPAN' ? 'inline' : 'block';
          }
          setTimeout(function () { location.reload(); }, 1200);
        } else {
          if (msg) {
            msg.textContent = (result.data && result.data.detail) || i18n.failed;
            msg.style.color = '#dc2626';
            msg.style.display = msg.tagName === 'SPAN' ? 'inline' : 'block';
          }
          btn.disabled = false;
        }
      })
      .catch(function () {
        if (msg) {
          msg.textContent = i18n.failed;
          msg.style.color = '#dc2626';
          msg.style.display = msg.tagName === 'SPAN' ? 'inline' : 'block';
        }
        btn.disabled = false;
      });
  });
}
