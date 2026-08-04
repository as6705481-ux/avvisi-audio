(function () {
  const TABLE_SELECTOR = '.av-table';

  function initTable(root) {
    const searchInput = root.querySelector('.av-search');
    const roleFilter  = root.querySelector('.av-roleFilter');   // puede ser null
    const tbody = root.querySelector('tbody');

    const prevBtn = root.querySelector('.av-prev');
    const nextBtn = root.querySelector('.av-next');
    const pagerMeta = root.querySelector('.av-pagerMeta');
    const pagerPage = root.querySelector('.av-pagerPage');

    if (!tbody || !searchInput || !prevBtn || !nextBtn || !pagerMeta || !pagerPage) return;

    const PAGE_SIZE = 5;
    let page = 1;

    const rows = () => Array.from(tbody.querySelectorAll('tr'));
    const isEmptyRow = (row) => row.children.length === 1 && row.querySelector('td[colspan]');

    /* En móvil la tabla se muestra como tarjetas "etiqueta: valor".
       La etiqueta se toma del encabezado y se guarda en data-label,
       que el CSS pinta con ::before. Así no hay que tocar cada
       plantilla que use el componente. */
    function labelCells() {
      const heads = Array.from(root.querySelectorAll('thead th')).map(th => {
        const clone = th.cloneNode(true);
        clone.querySelectorAll('.icon-arrow').forEach(n => n.remove());
        return (clone.textContent || '').trim();
      });
      if (!heads.length) return;

      rows().forEach(row => {
        if (isEmptyRow(row)) return;
        Array.from(row.children).forEach((cell, i) => {
          if (heads[i] && !cell.hasAttribute('data-label')) {
            cell.setAttribute('data-label', heads[i]);
          }
        });
      });
    }

    function buildRoleOptions() {
      if (!roleFilter) return;

      const roles = new Set();
      rows().forEach(r => {
        if (isEmptyRow(r)) return;
        const role = (r.getAttribute('data-role') || '').trim();
        if (role) roles.add(role);
      });

      roleFilter.querySelectorAll('option:not([value=""])').forEach(o => o.remove());

      Array.from(roles).sort((a,b) => a.localeCompare(b)).forEach(role => {
        const opt = document.createElement('option');
        opt.value = role;
        opt.textContent = role.charAt(0).toUpperCase() + role.slice(1);
        roleFilter.appendChild(opt);
      });
    }

    // Animación “hide” + luego “gone”
    function applyFiltersOnly() {
        const q = (searchInput.value || '').trim().toLowerCase();
        const role = (roleFilter ? (roleFilter.value || '').trim().toLowerCase() : '');

        const all = rows().filter(r => !isEmptyRow(r));

        all.forEach((row, i) => {
            const txt = row.textContent.toLowerCase();
            const rowRole = (row.getAttribute('data-role') || '').toLowerCase();

            const matchText = !q || txt.includes(q);
            const matchRole = !role || rowRole === role;
            const ok = matchText && matchRole;

            row.style.setProperty('--delay', (i / 25) + 's');

            if (!ok) {
                // si ya está oculto, no repitas
                if (row.classList.contains('hide') || row.classList.contains('gone')) return;

                row.classList.remove('gone');
                row.classList.add('hide');

                // duración total: 0.5s (tr) + 0.2s delay (td) + 0.5s delay interno = ~700ms
                // dejémoslo seguro en 800ms
                clearTimeout(row._avHideTimer);
                row._avHideTimer = setTimeout(() => {
                    // si sigue oculto, lo sacamos del layout
                    if (row.classList.contains('hide')) row.classList.add('gone');
                }, 800);

            } else {
                // mostrar
                clearTimeout(row._avHideTimer);
                row.classList.remove('gone');

                if (row.classList.contains('hide')) {
                    row.getBoundingClientRect();
                    requestAnimationFrame(() => row.classList.remove('hide'));
                }
            }

        });
        }


    function applyPagination() {
      const all = rows();
      const dataRows = all.filter(r => !isEmptyRow(r));
      const candidates = dataRows.filter(r => !r.classList.contains('hide') && !r.classList.contains('gone'));

      const total = candidates.length;
      const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
      page = Math.min(Math.max(1, page), totalPages);

      dataRows.forEach(r => r.classList.remove('page-hide'));
      candidates.forEach(r => r.classList.add('page-hide'));

      const start = (page - 1) * PAGE_SIZE;
      const end = Math.min(start + PAGE_SIZE, total);
      candidates.slice(start, end).forEach(r => r.classList.remove('page-hide'));

      const emptyRow = all.find(isEmptyRow);
      if (emptyRow) emptyRow.classList.toggle('page-hide', !(dataRows.length === 0));

      const shownFrom = total === 0 ? 0 : start + 1;
      const shownTo   = total === 0 ? 0 : end;

      pagerMeta.textContent = `Mostrando ${shownFrom}–${shownTo} de ${total}`;
      pagerPage.textContent = `Página ${page} de ${totalPages}`;
      prevBtn.disabled = page <= 1;
      nextBtn.disabled = page >= totalPages;

      // zebra
      const visibleNow = candidates.slice(start, end);
      visibleNow.forEach((r, i) => {
        r.style.backgroundColor = (i % 2 === 0) ? 'transparent' : '#0000000b';
      });
    }

    function runAll() {
      applyFiltersOnly();
      page = 1;
      applyPagination();
    }

    prevBtn.addEventListener('click', () => { page -= 1; applyPagination(); });
    nextBtn.addEventListener('click', () => { page += 1; applyPagination(); });

    labelCells();
    buildRoleOptions();
    runAll();

    searchInput.addEventListener('input', runAll);
    if (roleFilter) roleFilter.addEventListener('change', runAll);
  }

  document.querySelectorAll(TABLE_SELECTOR).forEach(initTable);
})();
