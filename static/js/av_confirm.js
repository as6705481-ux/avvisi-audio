(function () {
  // Inyecta el modal una sola vez (para que NO tengas que editar el layout con HTML extra)
  function ensureModal() {
    if (document.getElementById('avConfirmBackdrop')) return;

    const wrap = document.createElement('div');
    wrap.innerHTML = `
      <div class="av-confirm-backdrop" id="avConfirmBackdrop" aria-hidden="true">
        <div class="av-confirm" role="dialog" aria-modal="true" aria-labelledby="avConfirmTitle">
          <h1 id="avConfirmTitle">¿Eliminar?</h1>
          <p id="avConfirmMsg">Esta acción no se puede deshacer.</p>
          <div class="av-confirm__actions">
            <button type="button" id="avConfirmCancel">Cancelar</button>
            <button type="button" id="avConfirmOk">Eliminar</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(wrap.firstElementChild);
  }

  ensureModal();

  const backdrop = document.getElementById('avConfirmBackdrop');
  const btnCancel = document.getElementById('avConfirmCancel');
  const btnOk = document.getElementById('avConfirmOk');
  const titleEl = document.getElementById('avConfirmTitle');
  const msgEl = document.getElementById('avConfirmMsg');

  let pendingForm = null;
  let lastFocusEl = null;

  function openConfirm({ title, message, form, focusEl }) {
    pendingForm = form;
    lastFocusEl = focusEl || null;

    titleEl.textContent = title || '¿Eliminar?';
    msgEl.textContent = message || 'Esta acción no se puede deshacer.';

    backdrop.classList.add('is-open');
    backdrop.setAttribute('aria-hidden', 'false');
    btnCancel.focus();
  }

  function closeConfirm() {
    backdrop.classList.remove('is-open');
    backdrop.setAttribute('aria-hidden', 'true');

    pendingForm = null;
    if (lastFocusEl) lastFocusEl.focus();
    lastFocusEl = null;
  }

  // Delegación global: funciona en todas las tablas/páginas
  document.addEventListener('click', (e) => {
    const trigger = e.target.closest('[data-av-confirm]');
    if (!trigger) return;

    const form = trigger.closest('form');
    if (!form) return;

    e.preventDefault();

    openConfirm({
      title: trigger.getAttribute('data-av-title') || '¿Eliminar?',
      message: trigger.getAttribute('data-av-message') || 'Esta acción no se puede deshacer.',
      form,
      focusEl: trigger
    });
  });

  btnCancel.addEventListener('click', closeConfirm);
  btnOk.addEventListener('click', () => {
    if (pendingForm) pendingForm.submit();
    closeConfirm();
  });

  backdrop.addEventListener('click', (e) => {
    if (e.target === backdrop) closeConfirm();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && backdrop.classList.contains('is-open')) closeConfirm();
  });
})();
