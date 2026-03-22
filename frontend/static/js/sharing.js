/**
 * sharing.js – File sharing management UI.
 *
 * Renders the current shares for a document and lets the file owner
 * add new shares, change roles, or revoke access.
 *
 * Usage:
 *   initSharing(fileId, i18n)
 *
 * The i18n object is expected to contain all keys used below.
 */

/* global fetch */

(function () {
  'use strict';

  var _fileId = null;
  var _i18n = {};

  // ── DOM helpers ──────────────────────────────────────────────────────────

  function _el(id) {
    return document.getElementById(id);
  }

  function _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function _t(key) {
    return _i18n[key] || key;
  }

  // ── API helpers ──────────────────────────────────────────────────────────

  function _apiUrl(suffix) {
    return '/api/files/' + _fileId + suffix;
  }

  function _fetchShares() {
    return fetch(_apiUrl('/shares'), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); });
  }

  function _addShare(userId, role) {
    return fetch(_apiUrl('/shares'), {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ shared_with_user_id: userId, role: role }),
    }).then(function (r) {
      return r.json().then(function (body) {
        if (!r.ok) throw new Error((body && body.detail) || r.statusText);
        return body;
      });
    });
  }

  function _updateRole(shareId, role) {
    return fetch(_apiUrl('/shares/' + shareId), {
      method: 'PUT',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: role }),
    }).then(function (r) {
      return r.json().then(function (body) {
        if (!r.ok) throw new Error((body && body.detail) || r.statusText);
        return body;
      });
    });
  }

  function _revokeShare(shareId) {
    return fetch(_apiUrl('/shares/' + shareId), {
      method: 'DELETE',
      credentials: 'same-origin',
    }).then(function (r) {
      return r.json().then(function (body) {
        if (!r.ok) throw new Error((body && body.detail) || r.statusText);
        return body;
      });
    });
  }

  // ── Render ───────────────────────────────────────────────────────────────

  function _renderShares(shares) {
    var list = _el('sharing-list');
    if (!list) return;

    if (!shares || shares.length === 0) {
      list.innerHTML = '<p style="color:#64748b;font-size:0.875rem;">' + _esc(_t('no_shares')) + '</p>';
      return;
    }

    var rows = shares.map(function (s) {
      var roleLabel = s.role === 'editor' ? _t('role_editor') : _t('role_viewer');
      return (
        '<div style="display:flex;align-items:center;justify-content:space-between;gap:0.5rem;padding:0.5rem 0;border-bottom:1px solid #f1f5f9;">' +
          '<span style="font-size:0.875rem;color:#334155;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;" title="' + _esc(s.user_id) + '">' +
            _esc(s.display_name || s.user_id) +
          '</span>' +
          '<select' +
            ' data-share-id="' + _esc(s.share_id) + '"' +
            ' class="sharing-role-select"' +
            ' aria-label="' + _esc(_t('change_role')) + '"' +
            ' style="padding:0.25rem 0.5rem;border:1px solid #cbd5e1;border-radius:0.25rem;font-size:0.8rem;background:#fff;"' +
          '>' +
            '<option value="viewer"' + (s.role === 'viewer' ? ' selected' : '') + '>' + _esc(_t('role_viewer')) + '</option>' +
            '<option value="editor"' + (s.role === 'editor' ? ' selected' : '') + '>' + _esc(_t('role_editor')) + '</option>' +
          '</select>' +
          '<button' +
            ' data-share-id="' + _esc(s.share_id) + '"' +
            ' class="sharing-revoke-btn"' +
            ' aria-label="' + _esc(_t('revoke')) + '"' +
            ' title="' + _esc(_t('revoke')) + '"' +
            ' style="padding:0.25rem 0.5rem;background:#fee2e2;color:#b91c1c;border:1px solid #fca5a5;border-radius:0.25rem;font-size:0.8rem;cursor:pointer;"' +
          '>' +
            '<i class="fas fa-user-minus" aria-hidden="true"></i>' +
          '</button>' +
        '</div>'
      );
    });

    list.innerHTML = rows.join('');

    // Role change handlers
    list.querySelectorAll('.sharing-role-select').forEach(function (sel) {
      sel.addEventListener('change', function () {
        var shareId = sel.getAttribute('data-share-id');
        var newRole = sel.value;
        _updateRole(shareId, newRole)
          .then(function () { _loadAndRender(); })
          .catch(function (err) { _showError(err.message); });
      });
    });

    // Revoke handlers
    list.querySelectorAll('.sharing-revoke-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (!window.confirm(_t('revoke_confirm'))) return;
        var shareId = btn.getAttribute('data-share-id');
        _revokeShare(shareId)
          .then(function () { _loadAndRender(); })
          .catch(function (err) { _showError(err.message); });
      });
    });
  }

  function _loadAndRender() {
    var list = _el('sharing-list');
    if (!list) return;
    list.innerHTML = '<p style="color:#64748b;font-size:0.875rem;">' + _esc(_t('loading')) + '</p>';
    _fetchShares()
      .then(function (data) {
        // GET /files/{id}/shares returns an array; /files/{id}/shared-with also returns array
        var shares = Array.isArray(data) ? data : (data.shares || []);
        // Normalise keys: shares list uses share_id, but the shares endpoint returns id
        shares = shares.map(function (s) {
          return {
            share_id: s.share_id || s.id,
            user_id: s.user_id || s.shared_with_user_id,
            display_name: s.display_name || s.shared_with_user_id || s.user_id,
            role: s.role,
          };
        });
        _renderShares(shares);
      })
      .catch(function (err) {
        if (list) list.innerHTML = '<p style="color:#ef4444;font-size:0.875rem;">' + _esc(err.message) + '</p>';
      });
  }

  function _showError(msg) {
    var el = _el('sharing-form-error');
    if (!el) return;
    el.textContent = msg;
    el.style.display = 'block';
    setTimeout(function () { el.style.display = 'none'; }, 5000);
  }

  // ── Init ─────────────────────────────────────────────────────────────────

  function initSharing(fileId, i18n) {
    _fileId = fileId;
    _i18n = i18n || {};

    _loadAndRender();

    var form = _el('sharing-form');
    if (!form) return;

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var userInput = _el('share-user-input');
      var roleInput = _el('share-role-input');
      var userId = userInput ? userInput.value.trim() : '';
      var role = roleInput ? roleInput.value : 'viewer';

      if (!userId) {
        _showError(_t('error_empty_user'));
        return;
      }

      _addShare(userId, role)
        .then(function () {
          if (userInput) userInput.value = '';
          _loadAndRender();
        })
        .catch(function (err) { _showError(err.message); });
    });
  }

  // Expose
  window.initSharing = initSharing;
})();
