(() => {
  const providerKey = (value, fallback) => {
    const normalized = String(value || '').toLocaleLowerCase().replace(/[^a-z0-9]+/g, '');
    return normalized || `id:${fallback}`;
  };
  const rawSolutions = Array.isArray(window.COMPARE_SOLUTIONS) ? window.COMPARE_SOLUTIONS : [];
  const solutions = rawSolutions.filter((item, index, items) => item && items.findIndex(candidate => candidate && providerKey(candidate.provider, candidate.id) === providerKey(item.provider, item.id)) === index);
  const selected = new Set();
  const grid = document.getElementById('solution-grid');
  const bar = document.getElementById('comparison-bar');
  const count = document.getElementById('selected-count');
  const sideBySide = document.getElementById('side-by-side');
  const table = document.getElementById('comparison-table');
  const money = value => `₹${new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(value || 0)}`;
  const getCards = () => [...document.querySelectorAll('.solution-card')];

  const seenCards = new Set();
  getCards().forEach(card => {
    const item = JSON.parse(card.dataset.solution || '{}');
    const key = providerKey(item.provider, item.id);
    if (seenCards.has(key)) card.remove();
    else seenCards.add(key);
  });

  function updateBar() {
    count.textContent = selected.size;
    bar.hidden = selected.size === 0;
    document.getElementById('result-count').textContent = `${getCards().filter(card => !card.hidden).length} options`;
  }

  function filteredSolutions() {
    const size = document.getElementById('size-filter').value;
    const budget = document.getElementById('budget-filter').value;
    const technology = document.getElementById('technology-filter').value;
    return solutions.filter(item => {
      const inSize = size === 'all' || (size === '1-3' && item.system_size_kw >= 1 && item.system_size_kw <= 3) || (size === '3-5' && item.system_size_kw > 3 && item.system_size_kw <= 5) || (size === '5-10' && item.system_size_kw > 5 && item.system_size_kw <= 10) || (size === '10' && item.system_size_kw > 10);
      const maxPrice = item.price_max;
      const inBudget = budget === 'all' || (maxPrice !== null && maxPrice !== undefined && ((budget === '2' && maxPrice < 200000) || (budget === '4' && maxPrice >= 200000 && maxPrice < 400000) || (budget === '6' && maxPrice >= 400000 && maxPrice < 600000) || (budget === '7' && maxPrice >= 600000)));
      return inSize && inBudget && (technology === 'all' || item.panel_type === technology);
    });
  }

  function applyFilters() {
    const visible = new Set(filteredSolutions().map(item => item.id));
    getCards().forEach(card => { card.hidden = !visible.has(JSON.parse(card.dataset.solution).id); });
    document.getElementById('no-matches').hidden = visible.size !== 0;
    updateBar();
  }

  function sortCards() {
    const order = document.getElementById('sort-order').value;
    const sorted = [...solutions].sort((a, b) => {
      if (order === 'price') return (a.price_max == null ? Infinity : a.price_max) - (b.price_max == null ? Infinity : b.price_max);
      if (order === 'efficiency') return (b.panel_efficiency || 0) - (a.panel_efficiency || 0);
      if (order === 'warranty') return ((b.performance_warranty_years || 0) + (b.inverter_warranty_years || 0)) - ((a.performance_warranty_years || 0) + (a.inverter_warranty_years || 0));
      return b.match_score - a.match_score;
    });
    sorted.forEach(item => grid.appendChild(getCards().find(card => JSON.parse(card.dataset.solution).id === item.id));
  }

  function renderComparison() {
    const rows = [['Provider', 'provider'], ['System Size', 'system_size_kw', ' kW'], ['Estimated Price', 'price_range'], ['Annual Generation', 'annual_generation', ' kWh'], ['Annual Savings', 'annual_savings'], ['Payback', 'payback_years', ' years'], ['Panel Technology', 'panel_type'], ['Panel Efficiency', 'panel_efficiency', '%'], ['Number of Panels', 'number_of_panels'], ['Panel Brand', 'panel_brand'], ['Inverter', 'inverter_brand'], ['Panel Warranty', 'panel_warranty_years', ' years'], ['Performance Warranty', 'performance_warranty_years', ' years'], ['Inverter Warranty', 'inverter_warranty_years', ' years'], ['Installation', 'installation_included'], ['Mounting', 'mounting_included'], ['AMC', 'amc_available'], ['Financing', 'financing_available'], ['Regional Availability', 'availability'], ['Solar Setu Match Score', 'match_score', '/100']];
    const chosen = solutions.filter(item => selected.has(item.id));
    let html = '<thead><tr><th>Measure</th>' + chosen.map(item => `<th>${item.provider}</th>`).join('') + '</tr></thead><tbody>';
    rows.forEach(([label, key, suffix = '']) => {
      const values = chosen.map(item => {
        let value = item[key];
        if (key === 'price_range') value = `${money(item.price_min)} – ${money(item.price_max)}`;
        if (typeof value === 'boolean') value = value ? 'Included / available' : 'Not listed';
        return value === null || value === undefined || value === '' ? 'Not available' : `${value}${suffix}`;
      });
      if (values.every(value => value === 'Not available')) return;
      html += `<tr><th>${label}</th>${values.map(value => `<td>${value}</td>`).join('')}</tr>`;
    });
    table.innerHTML = html + '</tbody>';
    sideBySide.hidden = false;
    sideBySide.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  document.querySelectorAll('.filter-control select, #sort-order').forEach(control => control.addEventListener('change', () => { sortCards(); applyFilters(); }));
  document.getElementById('priority')?.addEventListener('change', event => { window.location.search = `?location_id=${window.COMPARE_LOCATION.id}&priority=${encodeURIComponent(event.target.value)}`; });
  grid?.addEventListener('change', event => {
    const checkbox = event.target.closest('[data-compare-id]');
    if (!checkbox) return;
    const id = Number(checkbox.dataset.compareId);
    if (checkbox.checked && selected.size >= 3) { checkbox.checked = false; alert('You can compare up to 3 solutions.'); return; }
    if (checkbox.checked) selected.add(id); else selected.delete(id);
    updateBar();
  });
  document.getElementById('compare-now')?.addEventListener('click', renderComparison);
  grid?.addEventListener('click', event => {
    const button = event.target.closest('[data-details-id]');
    if (!button) return;
    const item = solutions.find(solution => solution.id === Number(button.dataset.detailsId));
    const dialog = document.getElementById('solution-dialog');
    const content = document.getElementById('solution-dialog-content');
    if (!item || !dialog || !content) return;
    content.innerHTML = `<span class="compare-kicker">LISTED SOLUTION</span><h2>${item.provider}</h2><p>${item.description || ''}</p><div class="solution-facts"><div><span>System size</span><strong>${item.system_size_kw} kW</strong></div><div><span>Panel</span><strong>${item.panel_brand || 'Not available'} · ${item.panel_type || 'Not available'}</strong></div><div><span>Inverter</span><strong>${item.inverter_brand || 'Not available'} ${item.inverter_model || ''}</strong></div><div><span>Estimated price</span><strong>${money(item.price_min)} – ${money(item.price_max)}</strong></div><div><span>Source</span><strong>${item.source}</strong></div><div><span>Last updated</span><strong>${item.last_updated}</strong></div></div><p class="dialog-important"><strong>Important:</strong> Pricing and availability are indicative unless explicitly marked as verified. Confirm the final quotation and equipment selection with the provider.</p>`;
    dialog.showModal();
  });
  document.getElementById('dialog-close')?.addEventListener('click', () => document.getElementById('solution-dialog')?.close());
  document.getElementById('reset-filters')?.addEventListener('click', () => { document.querySelectorAll('.compare-controls select').forEach(select => { select.selectedIndex = 0; }); applyFilters(); });
  document.getElementById('score-help')?.addEventListener('click', () => { const node = document.getElementById('score-explanation'); node.hidden = !node.hidden; });
  document.getElementById('save-comparison')?.addEventListener('click', async () => {
    const response = await fetch('/api/comparisons', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ solution_ids: [...selected], location_id: window.COMPARE_LOCATION.id, priority: document.getElementById('priority').value }) });
    const data = await response.json();
    if (!response.ok && response.status === 401) { window.location.href = `/signup?next=${encodeURIComponent(window.location.pathname + window.location.search)}`; return; }
    alert(data.id ? 'Comparison saved to your account.' : (data.error || 'Unable to save comparison.'));
  });
  document.getElementById('ask-compare-surya')?.addEventListener('click', () => {
    const context = {...window.SOLAR_CONTEXT, userPriority: document.getElementById('priority').value, selectedSolutions: solutions.filter(item => selected.has(item.id) || selected.size === 0).map(item => ({provider: item.provider, systemSize: item.system_size_kw, priceMin: item.price_min, priceMax: item.price_max, panelType: item.panel_type, efficiency: item.panel_efficiency, warranties: [item.panel_warranty_years, item.performance_warranty_years, item.inverter_warranty_years], inverter: item.inverter_brand}))};
    window.SOLAR_CONTEXT = context;
    document.getElementById('surya-launcher')?.click();
    document.getElementById('surya-input')?.focus();
    setTimeout(() => { const input = document.getElementById('surya-input'); if (input) { input.value = 'Compare these solar solutions for my rooftop and explain which one best matches my requirements.'; document.getElementById('surya-form')?.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true})); } }, 80);
  });
  updateBar();
  applyFilters();
})();
