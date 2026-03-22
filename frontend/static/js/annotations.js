// frontend/static/js/annotations.js
// Annotations panel — CRUD for PDF page annotations

(function () {
  'use strict';

  var _fileId = null;
  var _currentUserId = null;
  var _i18n = {};

  // -------------------------------------------------------------------------
  // Initialisation
  // -------------------------------------------------------------------------

  /**
   * Bootstrap the annotations panel.
   * @param {number} fileId
   * @param {string} currentUserId
   * @param {object} i18n
   */
  function initAnnotations(fileId, currentUserId, i18n) {
    _fileId = fileId;
    _currentUserId = currentUserId;
    _i18n = i18n || {};
    _loadAnnotations();

    // Expose reload function so the EmbedPDF viewer init script can refresh the
    // list after auto-saving an annotation created inside the viewer.
    window._reloadAnnotations = _loadAnnotations;

    var form = document.getElementById('annotation-form');
    if (form) {
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        _createAnnotation();
      });
    }
  }

  // -------------------------------------------------------------------------
  // Data fetching
  // -------------------------------------------------------------------------

  function _loadAnnotations() {
    var container = document.getElementById('annotations-list');
    if (!container) return;
    container.innerHTML = '<div class="annotations-loading"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i></div>';

    fetch('/api/files/' + _fileId + '/annotations')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        _renderAnnotations(data.annotations || [], container);
      })
      .catch(function () {
        container.innerHTML = '<p class="annotations-empty">' + (_i18n.empty || 'No annotations yet') + '</p>';
      });
  }

  // -------------------------------------------------------------------------
  // Rendering
  // -------------------------------------------------------------------------

  function _renderAnnotations(annotations, container) {
    container.innerHTML = '';
    if (!annotations.length) {
      container.innerHTML = '<p class="annotations-empty"><i class="fas fa-sticky-note" aria-hidden="true"></i> ' +
        (_i18n.empty || 'No annotations yet') + '</p>';
      return;
    }
    for (var i = 0; i < annotations.length; i++) {
      container.appendChild(_buildAnnotationNode(annotations[i]));
    }
  }

  function _buildAnnotationNode(ann) {
    var div = document.createElement('div');
    div.className = 'annotation-item';
    div.setAttribute('data-annotation-id', ann.id);

    // Type badge + color indicator
    var header = document.createElement('div');
    header.className = 'annotation-header';

    var typeBadge = document.createElement('span');
    typeBadge.className = 'annotation-type annotation-type--' + ann.annotation_type;
    typeBadge.textContent = _i18n['type_' + ann.annotation_type] || ann.annotation_type;

    var pageInfo = document.createElement('button');
    pageInfo.type = 'button';
    pageInfo.className = 'annotation-page annotation-page--link';
    pageInfo.setAttribute('aria-label', (_i18n.go_to_page || 'Go to page') + ' ' + ann.page);
    pageInfo.title = (_i18n.go_to_page || 'Go to page') + ' ' + ann.page;
    pageInfo.innerHTML = '<i class="fas fa-file-alt" aria-hidden="true"></i> ' +
      (_i18n.page || 'Page') + ' ' + ann.page;
    pageInfo.addEventListener('click', function () {
      if (typeof window._embedpdfScrollToPage === 'function') {
        window._embedpdfScrollToPage(ann.page);
      }
    });

    header.appendChild(typeBadge);
    if (ann.color) {
      var colorDot = document.createElement('span');
      colorDot.className = 'annotation-color-dot';
      colorDot.style.backgroundColor = ann.color;
      colorDot.setAttribute('aria-label', (_i18n.color || 'Color') + ': ' + ann.color);
      header.appendChild(colorDot);
    }
    header.appendChild(pageInfo);

    div.appendChild(header);

    // Content
    var content = document.createElement('div');
    content.className = 'annotation-content';
    content.id = 'annotation-content-' + ann.id;
    content.textContent = ann.content;
    div.appendChild(content);

    // Meta
    var meta = document.createElement('div');
    meta.className = 'annotation-meta';

    var author = document.createElement('span');
    author.className = 'annotation-author';
    author.textContent = ann.user_id;

    var time = document.createElement('time');
    time.className = 'annotation-time';
    time.setAttribute('datetime', ann.created_at);
    time.textContent = _formatDate(ann.created_at);

    meta.appendChild(author);
    meta.appendChild(time);
    div.appendChild(meta);

    // Actions (author only)
    if (ann.user_id === _currentUserId) {
      var actions = document.createElement('div');
      actions.className = 'annotation-actions';

      var editBtn = document.createElement('button');
      editBtn.type = 'button';
      editBtn.className = 'annotation-action-btn';
      editBtn.innerHTML = '<i class="fas fa-edit" aria-hidden="true"></i>';
      editBtn.setAttribute('aria-label', 'Edit annotation');
      editBtn.addEventListener('click', function () { _showEditForm(ann); });
      actions.appendChild(editBtn);

      var deleteBtn = document.createElement('button');
      deleteBtn.type = 'button';
      deleteBtn.className = 'annotation-action-btn annotation-action-btn--danger';
      deleteBtn.innerHTML = '<i class="fas fa-trash" aria-hidden="true"></i>';
      deleteBtn.setAttribute('aria-label', 'Delete annotation');
      deleteBtn.addEventListener('click', function () { _deleteAnnotation(ann.id); });
      actions.appendChild(deleteBtn);

      div.appendChild(actions);
    }

    return div;
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

  function _createAnnotation() {
    var content = document.getElementById('annotation-content-input');
    var page = document.getElementById('annotation-page-input');
    var type = document.getElementById('annotation-type-input');
    var color = document.getElementById('annotation-color-input');

    if (!content || !content.value.trim()) return;

    var payload = {
      content: content.value.trim(),
      page: parseInt(page ? page.value : '1', 10) || 1,
      annotation_type: type ? type.value : 'note',
      color: color ? color.value : null,
      x: 0,
      y: 0,
      width: 0,
      height: 0,
    };

    fetch('/api/files/' + _fileId + '/annotations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then(function (r) {
        if (!r.ok) throw new Error('Failed');
        return r.json();
      })
      .then(function () {
        content.value = '';
        if (page) page.value = '1';
        _loadAnnotations();
      })
      .catch(function () {});
  }

  function _deleteAnnotation(annotationId) {
    if (!window.confirm(_i18n.delete_confirm || 'Are you sure you want to delete this annotation?')) return;

    fetch('/api/files/' + _fileId + '/annotations/' + annotationId, {
      method: 'DELETE',
    })
      .then(function (r) {
        if (!r.ok) throw new Error('Failed');
        _loadAnnotations();
      })
      .catch(function () {});
  }

  function _showEditForm(ann) {
    var contentDiv = document.getElementById('annotation-content-' + ann.id);
    if (!contentDiv) return;
    if (contentDiv.querySelector('.annotation-edit-form')) return;

    var originalText = contentDiv.textContent;
    contentDiv.textContent = '';

    var form = document.createElement('div');
    form.className = 'annotation-edit-form';

    var textarea = document.createElement('textarea');
    textarea.className = 'annotation-textarea';
    textarea.value = ann.content;
    textarea.rows = 3;
    textarea.setAttribute('aria-label', 'Edit annotation');

    var typeSelect = document.createElement('select');
    typeSelect.className = 'annotation-select';
    typeSelect.setAttribute('aria-label', 'Annotation type');
    var types = ['note', 'highlight', 'underline', 'strikethrough'];
    for (var i = 0; i < types.length; i++) {
      var opt = document.createElement('option');
      opt.value = types[i];
      opt.textContent = _i18n['type_' + types[i]] || types[i];
      if (types[i] === ann.annotation_type) opt.selected = true;
      typeSelect.appendChild(opt);
    }

    var btns = document.createElement('div');
    btns.className = 'annotation-edit-btns';

    var saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.className = 'annotation-submit-btn';
    saveBtn.textContent = _i18n.save || 'Save';
    saveBtn.addEventListener('click', function () {
      var newContent = textarea.value.trim();
      if (!newContent) return;
      fetch('/api/files/' + _fileId + '/annotations/' + ann.id, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: newContent,
          annotation_type: typeSelect.value,
          page: ann.page,
          x: ann.x,
          y: ann.y,
        }),
      })
        .then(function (r) {
          if (!r.ok) throw new Error('Failed');
          _loadAnnotations();
        })
        .catch(function () {
          contentDiv.textContent = originalText;
        });
    });

    var cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'annotation-cancel-btn';
    cancelBtn.textContent = _i18n.cancel || 'Cancel';
    cancelBtn.addEventListener('click', function () {
      contentDiv.textContent = originalText;
    });

    btns.appendChild(saveBtn);
    btns.appendChild(cancelBtn);

    form.appendChild(textarea);
    form.appendChild(typeSelect);
    form.appendChild(btns);
    contentDiv.appendChild(form);
    textarea.focus();
  }

  // Expose
  window.initAnnotations = initAnnotations;
})();
