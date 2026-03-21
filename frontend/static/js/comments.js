// frontend/static/js/comments.js
// Comments panel — threaded comments with @mention autocomplete

(function () {
  'use strict';

  var _fileId = null;
  var _currentUserId = null;
  var _i18n = {};
  var _mentionableUsers = [];

  // -------------------------------------------------------------------------
  // Initialisation
  // -------------------------------------------------------------------------

  /**
   * Bootstrap the comments panel.
   * @param {number} fileId
   * @param {string} currentUserId
   * @param {object} i18n
   */
  function initComments(fileId, currentUserId, i18n) {
    _fileId = fileId;
    _currentUserId = currentUserId;
    _i18n = i18n || {};
    _loadComments();
    _loadMentionableUsers();

    var form = document.getElementById('comment-form');
    if (form) {
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        _submitComment(null);
      });
    }

    var input = document.getElementById('comment-input');
    if (input) {
      input.addEventListener('input', function () {
        _handleMentionInput(this);
      });
      input.addEventListener('keydown', function (e) {
        _handleMentionKeydown(e);
      });
      // Close dropdown when clicking outside
      document.addEventListener('click', function (e) {
        var dropdown = document.getElementById('mention-dropdown');
        if (dropdown && !dropdown.contains(e.target) && e.target !== input) {
          dropdown.classList.add('hidden');
        }
      });
    }
  }

  // -------------------------------------------------------------------------
  // Data fetching
  // -------------------------------------------------------------------------

  function _loadComments() {
    var container = document.getElementById('comments-list');
    if (!container) return;
    container.innerHTML = '<div class="comments-loading"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i></div>';

    fetch('/api/files/' + _fileId + '/comments')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        _renderComments(data.comments || [], container);
      })
      .catch(function () {
        container.innerHTML = '<p class="comments-error">' + (_i18n.empty || 'No comments yet') + '</p>';
      });
  }

  function _loadMentionableUsers() {
    fetch('/api/users/mentionable')
      .then(function (r) { return r.json(); })
      .then(function (users) {
        _mentionableUsers = users || [];
      })
      .catch(function () {
        _mentionableUsers = [];
      });
  }

  // -------------------------------------------------------------------------
  // Rendering
  // -------------------------------------------------------------------------

  function _renderComments(comments, container) {
    container.innerHTML = '';
    if (!comments.length) {
      container.innerHTML = '<p class="comments-empty"><i class="fas fa-comments" aria-hidden="true"></i> ' +
        (_i18n.empty || 'No comments yet') + '</p>';
      return;
    }
    for (var i = 0; i < comments.length; i++) {
      container.appendChild(_buildCommentNode(comments[i], false));
    }
  }

  function _buildCommentNode(comment, isReply) {
    var div = document.createElement('div');
    div.className = 'comment-item' + (isReply ? ' comment-reply' : '') +
      (comment.is_resolved ? ' comment-resolved' : '');
    div.setAttribute('data-comment-id', comment.id);

    // Header
    var header = document.createElement('div');
    header.className = 'comment-header';

    var author = document.createElement('span');
    author.className = 'comment-author';
    author.textContent = comment.user_id;

    var time = document.createElement('time');
    time.className = 'comment-time';
    time.setAttribute('datetime', comment.created_at);
    time.textContent = _formatDate(comment.created_at);

    header.appendChild(author);
    header.appendChild(time);

    if (comment.is_resolved) {
      var badge = document.createElement('span');
      badge.className = 'comment-resolved-badge';
      badge.innerHTML = '<i class="fas fa-check-circle" aria-hidden="true"></i> ' + (_i18n.resolved || 'Resolved');
      header.appendChild(badge);
    }

    div.appendChild(header);

    // Body
    var bodyDiv = document.createElement('div');
    bodyDiv.className = 'comment-body';
    bodyDiv.id = 'comment-body-' + comment.id;
    bodyDiv.innerHTML = _renderMentions(comment.body);
    div.appendChild(bodyDiv);

    // Actions
    var actions = document.createElement('div');
    actions.className = 'comment-actions';

    // Reply button (only for top-level)
    if (!isReply) {
      var replyBtn = document.createElement('button');
      replyBtn.type = 'button';
      replyBtn.className = 'comment-action-btn';
      replyBtn.innerHTML = '<i class="fas fa-reply" aria-hidden="true"></i> ' + (_i18n.add_reply || 'Reply');
      replyBtn.setAttribute('aria-label', _i18n.add_reply || 'Reply');
      replyBtn.addEventListener('click', function () { _showReplyForm(comment.id, div); });
      actions.appendChild(replyBtn);

      // Resolve / Unresolve
      var resolveBtn = document.createElement('button');
      resolveBtn.type = 'button';
      resolveBtn.className = 'comment-action-btn';
      if (comment.is_resolved) {
        resolveBtn.innerHTML = '<i class="fas fa-undo" aria-hidden="true"></i> ' + (_i18n.unresolve || 'Reopen');
        resolveBtn.setAttribute('aria-label', _i18n.unresolve || 'Reopen');
      } else {
        resolveBtn.innerHTML = '<i class="fas fa-check" aria-hidden="true"></i> ' + (_i18n.resolve || 'Resolve');
        resolveBtn.setAttribute('aria-label', _i18n.resolve || 'Resolve');
      }
      resolveBtn.addEventListener('click', function () { _toggleResolve(comment.id, !comment.is_resolved); });
      actions.appendChild(resolveBtn);
    }

    // Edit (author only)
    if (comment.user_id === _currentUserId) {
      var editBtn = document.createElement('button');
      editBtn.type = 'button';
      editBtn.className = 'comment-action-btn';
      editBtn.innerHTML = '<i class="fas fa-edit" aria-hidden="true"></i> ' + (_i18n.edit || 'Edit');
      editBtn.setAttribute('aria-label', _i18n.edit || 'Edit');
      editBtn.addEventListener('click', function () { _showEditForm(comment.id, comment.body, div); });
      actions.appendChild(editBtn);

      // Delete
      var deleteBtn = document.createElement('button');
      deleteBtn.type = 'button';
      deleteBtn.className = 'comment-action-btn comment-action-btn--danger';
      deleteBtn.innerHTML = '<i class="fas fa-trash" aria-hidden="true"></i>';
      deleteBtn.setAttribute('aria-label', 'Delete comment');
      deleteBtn.addEventListener('click', function () { _deleteComment(comment.id); });
      actions.appendChild(deleteBtn);
    }

    div.appendChild(actions);

    // Replies
    if (comment.replies && comment.replies.length) {
      var repliesDiv = document.createElement('div');
      repliesDiv.className = 'comment-replies';
      for (var j = 0; j < comment.replies.length; j++) {
        repliesDiv.appendChild(_buildCommentNode(comment.replies[j], true));
      }
      div.appendChild(repliesDiv);
    }

    return div;
  }

  function _renderMentions(text) {
    if (!text) return '';
    // Escape HTML first
    var escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    // Highlight @mentions
    return escaped.replace(/@([\w.\-]+)/g, '<span class="comment-mention">@$1</span>');
  }

  function _formatDate(iso) {
    if (!iso) return '';
    try {
      var d = new Date(iso);
      return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) +
        ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    } catch (_e) {
      return iso;
    }
  }

  // -------------------------------------------------------------------------
  // Actions
  // -------------------------------------------------------------------------

  function _submitComment(parentId) {
    var inputId = parentId ? 'reply-input-' + parentId : 'comment-input';
    var input = document.getElementById(inputId);
    if (!input) return;
    var body = input.value.trim();
    if (!body) return;

    var payload = { body: body };
    if (parentId) payload.parent_id = parentId;

    fetch('/api/files/' + _fileId + '/comments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then(function (r) {
        if (!r.ok) throw new Error('Failed');
        return r.json();
      })
      .then(function () {
        input.value = '';
        _loadComments();
      })
      .catch(function () {
        // Silently fail — the CSRF wrapper in common.js handles token injection
      });
  }

  function _toggleResolve(commentId, resolve) {
    fetch('/api/files/' + _fileId + '/comments/' + commentId + '/resolve', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resolve: resolve }),
    })
      .then(function (r) {
        if (!r.ok) throw new Error('Failed');
        _loadComments();
      })
      .catch(function () {});
  }

  function _deleteComment(commentId) {
    if (!window.confirm(_i18n.delete_confirm || 'Are you sure you want to delete this comment?')) return;

    fetch('/api/files/' + _fileId + '/comments/' + commentId, {
      method: 'DELETE',
    })
      .then(function (r) {
        if (!r.ok) throw new Error('Failed');
        _loadComments();
      })
      .catch(function () {});
  }

  function _showReplyForm(commentId, containerNode) {
    // Remove existing reply forms
    var existing = containerNode.querySelector('.comment-reply-form');
    if (existing) { existing.remove(); return; }

    var form = document.createElement('div');
    form.className = 'comment-reply-form';

    var textarea = document.createElement('textarea');
    textarea.id = 'reply-input-' + commentId;
    textarea.className = 'comment-textarea';
    textarea.placeholder = _i18n.reply_placeholder || 'Write a reply...';
    textarea.rows = 2;
    textarea.setAttribute('aria-label', _i18n.reply_placeholder || 'Write a reply...');

    var submitBtn = document.createElement('button');
    submitBtn.type = 'button';
    submitBtn.className = 'comment-submit-btn';
    submitBtn.textContent = _i18n.add_reply || 'Reply';
    submitBtn.addEventListener('click', function () { _submitComment(commentId); });

    form.appendChild(textarea);
    form.appendChild(submitBtn);

    // Insert before the replies section or at end
    var repliesDiv = containerNode.querySelector('.comment-replies');
    if (repliesDiv) {
      containerNode.insertBefore(form, repliesDiv);
    } else {
      containerNode.appendChild(form);
    }
    textarea.focus();
  }

  function _showEditForm(commentId, currentBody, containerNode) {
    var bodyDiv = document.getElementById('comment-body-' + commentId);
    if (!bodyDiv) return;

    // Already editing?
    if (bodyDiv.querySelector('.comment-edit-form')) return;

    var originalHTML = bodyDiv.innerHTML;
    bodyDiv.innerHTML = '';

    var form = document.createElement('div');
    form.className = 'comment-edit-form';

    var textarea = document.createElement('textarea');
    textarea.className = 'comment-textarea';
    textarea.value = currentBody;
    textarea.rows = 3;
    textarea.setAttribute('aria-label', _i18n.edit || 'Edit');

    var btns = document.createElement('div');
    btns.className = 'comment-edit-btns';

    var saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.className = 'comment-submit-btn';
    saveBtn.textContent = _i18n.save || 'Save';
    saveBtn.addEventListener('click', function () {
      var newBody = textarea.value.trim();
      if (!newBody) return;
      fetch('/api/files/' + _fileId + '/comments/' + commentId, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ body: newBody }),
      })
        .then(function (r) {
          if (!r.ok) throw new Error('Failed');
          _loadComments();
        })
        .catch(function () {
          bodyDiv.innerHTML = originalHTML;
        });
    });

    var cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'comment-cancel-btn';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.addEventListener('click', function () {
      bodyDiv.innerHTML = originalHTML;
    });

    btns.appendChild(saveBtn);
    btns.appendChild(cancelBtn);
    form.appendChild(textarea);
    form.appendChild(btns);
    bodyDiv.appendChild(form);
    textarea.focus();
  }

  // -------------------------------------------------------------------------
  // @mention autocomplete
  // -------------------------------------------------------------------------

  function _handleMentionInput(input) {
    var val = input.value;
    var cursorPos = input.selectionStart;
    var textBefore = val.substring(0, cursorPos);
    var match = textBefore.match(/@([\w.\-]*)$/);

    var dropdown = document.getElementById('mention-dropdown');
    if (!dropdown) return;

    if (!match) {
      dropdown.classList.add('hidden');
      return;
    }

    var query = match[1].toLowerCase();
    var filtered = _mentionableUsers.filter(function (u) {
      return u.user_id.toLowerCase().indexOf(query) !== -1 ||
        (u.display_name && u.display_name.toLowerCase().indexOf(query) !== -1);
    }).slice(0, 8);

    if (!filtered.length) {
      dropdown.classList.add('hidden');
      return;
    }

    dropdown.innerHTML = '';
    for (var i = 0; i < filtered.length; i++) {
      (function (user) {
        var item = document.createElement('button');
        item.type = 'button';
        item.className = 'mention-item';
        item.setAttribute('role', 'option');
        item.innerHTML = '<span class="mention-user-id">' + _escapeHtml(user.user_id) + '</span>' +
          (user.display_name ? '<span class="mention-display-name">' + _escapeHtml(user.display_name) + '</span>' : '');
        item.addEventListener('click', function () {
          _insertMention(input, match.index, cursorPos, user.user_id);
          dropdown.classList.add('hidden');
        });
        dropdown.appendChild(item);
      })(filtered[i]);
    }
    dropdown.classList.remove('hidden');
  }

  function _handleMentionKeydown(e) {
    var dropdown = document.getElementById('mention-dropdown');
    if (!dropdown || dropdown.classList.contains('hidden')) return;

    if (e.key === 'Escape') {
      dropdown.classList.add('hidden');
      e.preventDefault();
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      var items = dropdown.querySelectorAll('.mention-item');
      var focused = dropdown.querySelector('.mention-item:focus');
      var idx = Array.prototype.indexOf.call(items, focused);
      if (e.key === 'ArrowDown') {
        idx = (idx + 1) % items.length;
      } else {
        idx = idx <= 0 ? items.length - 1 : idx - 1;
      }
      items[idx].focus();
    } else if (e.key === 'Enter' || e.key === 'Tab') {
      var active = dropdown.querySelector('.mention-item:focus');
      if (active) {
        active.click();
        e.preventDefault();
      }
    }
  }

  function _insertMention(input, matchStart, cursorPos, userId) {
    var before = input.value.substring(0, matchStart);
    var after = input.value.substring(cursorPos);
    input.value = before + '@' + userId + ' ' + after;
    var newPos = matchStart + userId.length + 2;
    input.setSelectionRange(newPos, newPos);
    input.focus();
  }

  function _escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }

  // Expose
  window.initComments = initComments;
})();
