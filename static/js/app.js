(() => {
  'use strict';
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  // Navigation shell.
  const sidebar = $('#sidebar');
  const backdrop = $('#sidebarBackdrop');
  const openButton = $('#sidebarToggle');
  const closeButton = $('#sidebarClose');
  const openSidebar = () => { if (sidebar) sidebar.classList.add('show'); if (backdrop) backdrop.classList.add('show'); };
  const closeSidebar = () => { if (sidebar) sidebar.classList.remove('show'); if (backdrop) backdrop.classList.remove('show'); };
  if (openButton) openButton.addEventListener('click', openSidebar);
  if (closeButton) closeButton.addEventListener('click', closeSidebar);
  if (backdrop) backdrop.addEventListener('click', closeSidebar);
  window.addEventListener('keydown', e => { if (e.key === 'Escape') closeSidebar(); });

  // Live date and time.
  const clock = $('#liveClock');
  if (clock) {
    const tick = () => {
      clock.textContent = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'medium' }).format(new Date());
    };
    tick();
    setInterval(tick, 1000);
  }

  // Entire records are clickable. Interactive controls inside a row keep their normal behavior.
  const isInteractive = target => target.closest('a,button,input,select,textarea,label,form');
  $$('.record-row[data-href]').forEach(row => {
    row.addEventListener('click', e => { if (!isInteractive(e.target)) window.location.href = row.dataset.href; });
    row.addEventListener('keydown', e => {
      if ((e.key === 'Enter' || e.key === ' ') && !isInteractive(e.target)) {
        e.preventDefault();
        window.location.href = row.dataset.href;
      }
    });
  });

  // Give mobile stacked tables readable field labels automatically.
  $$('.stack-table').forEach(table => {
    const headers = $$('thead th', table).map(th => th.textContent.trim());
    $$('tbody tr', table).forEach(row => {
      $$('td', row).forEach((cell, index) => {
        if (!cell.hasAttribute('colspan') && !cell.dataset.label) cell.dataset.label = headers[index] || '';
      });
    });
  });

  // Real-time server filters: no Filter/Search button is required.
  $$('.live-filter-form[data-live-filter-form]').forEach(form => {
    let timer;
    const submit = () => {
      clearTimeout(timer);
      form.classList.add('filter-loading');
      form.requestSubmit();
    };
    $$('[data-live-text]', form).forEach(input => {
      input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(submit, 420); });
      input.addEventListener('search', () => { clearTimeout(timer); submit(); });
    });
    $$('[data-live-change]', form).forEach(input => input.addEventListener('change', submit));
  });

  // Password visibility and live strength rules.
  $$('.password-wrap input').forEach(input => input.classList.add('form-control'));
  $$('[data-password-toggle]').forEach(button => {
    button.addEventListener('click', () => {
      const input = $(button.dataset.passwordToggle);
      if (!input) return;
      const showing = input.type === 'text';
      input.type = showing ? 'password' : 'text';
      button.setAttribute('aria-label', showing ? 'Show password' : 'Hide password');
      button.classList.toggle('showing', !showing);
    });
  });
  $$('.password-rules[data-password-rules]').forEach(box => {
    const input = $(box.dataset.passwordRules);
    if (!input) return;
    const tests = {
      length: value => value.length >= 10,
      upper: value => /[A-Z]/.test(value),
      lower: value => /[a-z]/.test(value),
      number: value => /\d/.test(value),
      symbol: value => /[^A-Za-z0-9]/.test(value),
    };
    const usernameInput = box.dataset.passwordUsername ? $(box.dataset.passwordUsername) : null;
    const currentUsername = () => (usernameInput?.value || box.dataset.passwordUsernameValue || '').trim().toLowerCase();
    const similarToUsername = value => {
      const username = currentUsername().replace(/[^a-z0-9]/g, '');
      const password = String(value || '').toLowerCase().replace(/[^a-z0-9]/g, '');
      if (!username || username.length < 3 || !password) return false;
      if (password.includes(username)) return true;
      let common = 0;
      for (let i = 0; i < Math.min(password.length, username.length); i++) if (password[i] === username[i]) common++;
      return username.length >= 4 && common / username.length >= .6;
    };
    const render = () => {
      const value = input.value || '';
      Object.entries(tests).forEach(([name, test]) => {
        const item = $(`[data-rule="${name}"]`, box);
        if (item) item.classList.toggle('valid', test(value));
      });
      const warning = $('[data-rule="username"]', box);
      if (warning) warning.classList.toggle('warning', similarToUsername(value));
    };
    input.addEventListener('input', render);
    if (usernameInput) usernameInput.addEventListener('input', render);
    render();
  });

  // Cases / Cash analysis switch. The underlying chart payload contains both measures.
  $$('[data-analysis-root]').forEach(root => {
    const buttons = $$('[data-analysis-mode]', root);
    const format = (value, kind, currency) => {
      const number = Number(value || 0);
      const text = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(Number.isFinite(number) ? number : 0);
      return kind === 'money' ? `${currency || ''} ${text}`.trim() : text;
    };
    const apply = mode => {
      root.dataset.analysisMode = mode;
      buttons.forEach(button => {
        const active = button.dataset.analysisMode === mode;
        button.classList.toggle('active', active);
        button.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
      $$('[data-mode-label]', root).forEach(node => {
        const label = mode === 'cash' ? node.dataset.cashLabel : node.dataset.casesLabel;
        if (label) node.textContent = label;
      });
      $$('[data-mode-value]', root).forEach(node => {
        const value = mode === 'cash' ? node.dataset.cash : node.dataset.cases;
        const kind = mode === 'cash' ? node.dataset.cashFormat : node.dataset.casesFormat;
        node.textContent = format(value, kind, node.dataset.currency);
      });
      $$('[data-mode-only]', root).forEach(node => { node.hidden = node.dataset.modeOnly !== mode; });
      root.dispatchEvent(new CustomEvent('mms:analysis-mode', { bubbles: true, detail: { mode } }));
    };
    buttons.forEach(button => button.addEventListener('click', () => apply(button.dataset.analysisMode)));
    apply(root.dataset.defaultMode || 'cases');
  });

  // Sales form behavior.
  const saleForm = $('#saleForm');
  if (!saleForm) return;

  const rows = $('#itemRows');
  const totalForms = $('#id_items-TOTAL_FORMS');
  const template = $('#emptyItemTemplate');
  const addItem = $('#addItem');
  const grandTotal = $('#grandTotal');
  const saleType = $('#id_sale_type');
  const pricingMode = $('#id_pricing_mode');
  const pricingSummary = $('#pricingSummary');
  const salesman = $('#id_salesman');
  const priceOverride = saleForm.dataset.priceOverride === '1';
  const formatNumber = value => new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(Number.isFinite(value) ? value : 0);

  function calculateRow(row) {
    const qty = parseFloat($('[name$="-quantity"]', row)?.value) || 0;
    const price = parseFloat($('[name$="-unit_price"]', row)?.value) || 0;
    const discount = parseFloat($('[name$="-discount"]', row)?.value) || 0;
    const total = Math.max(0, qty * price - discount);
    const display = $('.line-total', row);
    if (display) display.textContent = formatNumber(total);
    return total;
  }

  function calculateAll() {
    let total = 0;
    $$('.sale-item-row', rows).forEach(row => {
      const deleted = $('[name$="-DELETE"]', row);
      if (!(deleted && deleted.checked) && row.style.display !== 'none') total += calculateRow(row);
    });
    if (grandTotal) grandTotal.textContent = formatNumber(total);
  }

  async function loadProductPrice(select, force = false) {
    if (!select?.value || !window.MMS_PRODUCT_PRICE_URL) return;
    const row = select.closest('.sale-item-row');
    const priceInput = $('[name$="-unit_price"]', row);
    if (!priceInput) return;
    if (!force && priceInput.value) return;
    if (priceOverride && priceInput.dataset.userEdited === 'true' && force) return;
    const mode = pricingMode?.value || 'WHOLESALE';
    try {
      const url = window.MMS_PRODUCT_PRICE_URL.replace('__ID__', select.value) + `?pricing_mode=${encodeURIComponent(mode)}`;
      const response = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      if (!response.ok) return;
      const data = await response.json();
      priceInput.value = data.price;
      priceInput.dataset.userEdited = 'false';
      calculateAll();
    } catch (_) {
      // Django validation is authoritative even when the browser is offline.
    }
  }

  function bindRow(row) {
    $$('input,select', row).forEach(el => el.addEventListener('input', calculateAll));
    const product = $('[name$="-product"]', row);
    const price = $('[name$="-unit_price"]', row);
    if (product) product.addEventListener('change', () => { if (price) price.dataset.userEdited = 'false'; loadProductPrice(product, true); });
    if (price && priceOverride) price.addEventListener('input', () => { price.dataset.userEdited = 'true'; });
    const remove = $('.remove-item', row);
    if (remove) remove.addEventListener('click', () => {
      const deleted = $('[name$="-DELETE"]', row);
      if (deleted) { deleted.checked = true; row.style.display = 'none'; } else row.remove();
      calculateAll();
    });
    if (product && !price?.value) loadProductPrice(product);
  }

  $$('.sale-item-row', rows).forEach(bindRow);
  calculateAll();
  if (addItem && template && totalForms) addItem.addEventListener('click', () => {
    const index = parseInt(totalForms.value, 10);
    const holder = document.createElement('div');
    holder.innerHTML = template.innerHTML.replaceAll('__prefix__', index).trim();
    const row = holder.firstElementChild;
    rows.appendChild(row);
    totalForms.value = index + 1;
    bindRow(row);
    calculateAll();
  });

  // Customer typeahead search.
  const customerBlock = $('#customerPickerBlock');
  const customerInput = $('#customerSearch');
  const customerHidden = $('#id_customer');
  const customerResults = $('#customerSearchResults');
  const customerCard = $('#selectedCustomerCard');
  const customerName = $('#selectedCustomerName');
  const customerMeta = $('#selectedCustomerMeta');
  const clearCustomer = $('#clearCustomer');
  const browseCustomers = $('#browseCustomers');
  let searchTimer;
  let searchController;
  let selectedLabel = customerInput?.value || '';

  function clearCustomerSelection(clearText = true) {
    if (customerHidden) customerHidden.value = '';
    if (clearText && customerInput) customerInput.value = '';
    selectedLabel = '';
    if (customerCard) customerCard.classList.add('d-none');
    if (customerResults) { customerResults.classList.remove('show'); customerResults.innerHTML = ''; }
  }

  function chooseCustomer(item) {
    if (!customerHidden || !customerInput) return;
    customerHidden.value = item.id;
    selectedLabel = `${item.code} — ${item.name}`;
    customerInput.value = selectedLabel;
    if (customerName) customerName.textContent = item.name;
    if (customerMeta) customerMeta.textContent = `${item.code} · Zone ${item.zone}${item.phone ? ' · ' + item.phone : ''}`;
    if (customerCard) customerCard.classList.remove('d-none');
    if (customerResults) { customerResults.classList.remove('show'); customerResults.innerHTML = ''; }
  }

  function renderCustomerResults(items) {
    if (!customerResults) return;
    customerResults.innerHTML = '';
    if (!items.length) {
      const empty = document.createElement('div');
      empty.className = 'p-3 small text-secondary';
      empty.textContent = 'No matching customers found.';
      customerResults.appendChild(empty);
      customerResults.classList.add('show');
      return;
    }
    items.forEach(item => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'customer-result';
      const strong = document.createElement('strong');
      strong.textContent = `${item.code} — ${item.name}`;
      const small = document.createElement('small');
      small.textContent = `Zone ${item.zone}${item.phone ? ' · ' + item.phone : ''}${item.address ? ' · ' + item.address : ''}`;
      button.append(strong, small);
      button.addEventListener('click', () => chooseCustomer(item));
      customerResults.appendChild(button);
    });
    customerResults.classList.add('show');
  }

  async function searchCustomers(browseAll = false) {
    if (!customerInput || !window.MMS_CUSTOMER_SEARCH_URL) return;
    const query = customerInput.value.trim();
    if (!browseAll && query === selectedLabel) return;
    if (!browseAll) {
      if (customerHidden) customerHidden.value = '';
      if (customerCard) customerCard.classList.add('d-none');
      if (query.length < 1) { if (customerResults) customerResults.classList.remove('show'); return; }
    }
    if (searchController) searchController.abort();
    searchController = new AbortController();
    const params = browseAll ? new URLSearchParams({ all: '1' }) : new URLSearchParams({ q: query });
    if (salesman?.value) params.set('salesman', salesman.value);
    try {
      const response = await fetch(`${window.MMS_CUSTOMER_SEARCH_URL}?${params.toString()}`, { signal: searchController.signal, headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      if (!response.ok) return;
      const data = await response.json();
      renderCustomerResults(data.results || []);
    } catch (error) {
      if (error.name !== 'AbortError' && customerResults) customerResults.classList.remove('show');
    }
  }

  if (customerInput) customerInput.addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => searchCustomers(false), 220); });
  if (browseCustomers) browseCustomers.addEventListener('click', () => searchCustomers(true));
  if (clearCustomer) clearCustomer.addEventListener('click', () => { clearCustomerSelection(); customerInput?.focus(); });
  if (salesman) salesman.addEventListener('change', () => clearCustomerSelection());
  document.addEventListener('click', e => { if (customerResults && !e.target.closest('.customer-search-wrap')) customerResults.classList.remove('show'); });

  function syncSaleType() {
    const general = saleType?.value === 'GENERAL';
    if (customerBlock) customerBlock.classList.toggle('d-none', general);
    if (general) clearCustomerSelection();
    $$('.sale-item-row', rows).forEach(row => {
      const product = $('[name$="-product"]', row);
      if (product?.value) loadProductPrice(product, true);
    });
  }
  function syncPricingMode() {
    if (pricingSummary && pricingMode) {
      pricingSummary.textContent = pricingMode.options[pricingMode.selectedIndex]?.text || 'Wholesale';
    }
    $('.sale-item-row', rows).forEach(row => {
      const product = $('[name$="-product"]', row);
      if (product?.value) loadProductPrice(product, true);
    });
  }
  if (pricingMode) pricingMode.addEventListener('change', syncPricingMode);
  if (saleType) { saleType.addEventListener('change', syncSaleType); syncSaleType(); }
  syncPricingMode();
})();
