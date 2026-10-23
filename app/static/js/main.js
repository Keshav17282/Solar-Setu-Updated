// filename: app/static/js/main.js

// -------------------------------------------------- Landing page flow -----
let selectedAddress = null;
let selectedLatLng = null;

function initSearch() {
  const searchBtn = document.getElementById('search-btn');
  const locateBtn = document.getElementById('locate-btn');
  const input = document.getElementById('address-search');
  const resultsBox = document.getElementById('search-results');
  const mapsInput = document.getElementById('maps-link-input');
  const mapsBtn = document.getElementById('maps-link-btn');

  if (!searchBtn) return; // not on the landing page

  async function applyMapsLink() {
    if (!mapsInput) return;
    const url = mapsInput.value.trim();
    if (!url) {
      alert('Paste a Google Maps link first.');
      return;
    }
    if (resultsBox) resultsBox.innerHTML = '<p class="search-status">Reading Google Maps link…</p>';
    try {
      const res = await fetch(`${PARSE_MAPS_URL}?url=${encodeURIComponent(url)}`);
      const data = await res.json();
      if (!res.ok) {
        if (resultsBox) resultsBox.innerHTML = '';
        alert(data.error || 'Could not read that Maps link.');
        return;
      }
      const lat = Number(data.lat);
      const lon = Number(data.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
        alert('Invalid coordinates from Maps link.');
        return;
      }
      selectedLatLng = { lat, lng: lon };
      selectedAddress = data.address || (lat + ', ' + lon);
      if (input) input.value = selectedAddress;
      if (typeof setMapCenter === 'function') {
        setMapCenter(lat, lon, 19);
        // Re-center after a tick in case the map was still settling
        setTimeout(() => setMapCenter(lat, lon, 19), 400);
      }
      if (resultsBox) {
        resultsBox.innerHTML =
          '<p class="search-status">Pinned at ' + lat.toFixed(5) + ', ' + lon.toFixed(5) +
          ' — draw your rooftop around the blue marker.</p>';
      }
    } catch (err) {
      if (resultsBox) resultsBox.innerHTML = '';
      alert('Failed to open Maps link. Check your connection and try again.');
    }
  }

  if (mapsBtn) mapsBtn.addEventListener('click', applyMapsLink);
  if (mapsInput) {
    mapsInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        applyMapsLink();
      }
    });
  }

  async function runSearch() {
    const query = input.value.trim();
    if (!query) return;
    resultsBox.innerHTML = '<p class="search-status">Searching for places…</p>';

    try {
      const res = await fetch(`${GEOCODE_URL}?q=${encodeURIComponent(query)}`);
      const data = await res.json();
      const list = data.results || [];
      if (data.source === 'mock_fallback') {
        resultsBox.innerHTML =
          '<p class="search-status">Live geocoding unavailable. Showing a fallback — try a fuller address (society / road / city).</p>';
      }
      renderSearchResults(list, data.source);
    } catch (err) {
      resultsBox.innerHTML = '<p class="search-status">Could not search right now. Check your connection and try again.</p>';
    }
  }

  searchBtn.addEventListener('click', runSearch);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      runSearch();
    }
  });

  locateBtn.addEventListener('click', () => {
    if (!navigator.geolocation) {
      alert('Geolocation is not supported by this browser.');
      return;
    }
    resultsBox.innerHTML = '<p class="search-status">Getting your location…</p>';
    navigator.geolocation.getCurrentPosition(async (pos) => {
      const { latitude, longitude } = pos.coords;
      selectedLatLng = { lat: latitude, lng: longitude };
      if (typeof setMapCenter === 'function') {
        setMapCenter(latitude, longitude, 19);
      }

      try {
        const res = await fetch(`${REVERSE_GEOCODE_URL}?lat=${latitude}&lon=${longitude}`);
        const data = await res.json();
        selectedAddress = data.address;
        input.value = selectedAddress;
        resultsBox.innerHTML = '';
      } catch (err) {
        selectedAddress = 'Current location';
        input.value = selectedAddress;
        resultsBox.innerHTML = '';
      }
    }, () => {
      resultsBox.innerHTML = '';
      alert('Unable to retrieve your location. Allow location access or search by address.');
    }, { enableHighAccuracy: true, timeout: 12000 });
  });

  function renderSearchResults(results, source) {
    if (!results.length) {
      resultsBox.innerHTML =
        '<p class="search-status">No results found. Try adding city/state (e.g. “GL Bajaj Greater Noida”) or a nearby landmark.</p>';
      return;
    }
    resultsBox.innerHTML = '';
    if (source) {
      const meta = document.createElement('p');
      meta.className = 'search-status';
      meta.textContent = results.length + ' place(s) found' + (source && source !== 'mock_fallback' ? '' : '');
      resultsBox.appendChild(meta);
    }
    results.forEach(r => {
      const div = document.createElement('div');
      div.className = 'search-result-item';
      const title = r.label || r.display_name;
      const sub = (r.label && r.display_name && r.label !== r.display_name)
        ? r.display_name
        : (r.type ? String(r.type) : '');
      div.innerHTML =
        '<div class="result-title"></div>' +
        (sub ? '<div class="result-sub"></div>' : '');
      div.querySelector('.result-title').textContent = title;
      if (sub) div.querySelector('.result-sub').textContent = sub;
      div.title = r.display_name || title;
      div.addEventListener('click', () => {
        selectedAddress = r.display_name || title;
        selectedLatLng = { lat: r.lat, lng: r.lon };
        input.value = selectedAddress;
        if (typeof setMapCenter === 'function') {
          setMapCenter(r.lat, r.lon, 19);
        }
        resultsBox.innerHTML = '';
      });
      resultsBox.appendChild(div);
    });
  }
}

function initSystemOptions() {
  const batteryToggle = document.getElementById('battery-toggle');
  const batteryWrap = document.getElementById('battery-size-wrap');
  if (batteryToggle && batteryWrap) {
    batteryToggle.addEventListener('change', () => {
      batteryWrap.classList.toggle('hidden', !batteryToggle.checked);
    });
  }
}

function initEstimationButton() {
  const btn = document.getElementById('start-estimation-btn');
  if (!btn) return;

  btn.addEventListener('click', async () => {
    const polygon = getCurrentPolygon();
    const obstructions = typeof getCurrentObstructions === 'function' ? getCurrentObstructions() : [];
    if (!polygon) {
      alert('Please draw your rooftop boundary on the map first.');
      return;
    }
    if (!selectedLatLng) {
      // Fall back to the polygon's own centroid if no address was searched.
      const avgLat = polygon.reduce((s, p) => s + p[0], 0) / polygon.length;
      const avgLng = polygon.reduce((s, p) => s + p[1], 0) / polygon.length;
      selectedLatLng = { lat: avgLat, lng: avgLng };
    }
    if (!selectedAddress) {
      selectedAddress = document.getElementById('address-search').value || 'Selected rooftop';
    }

    const orientationSelect = document.getElementById('orientation-select');
    const orientationValue = orientationSelect ? orientationSelect.value : 'auto';
    const batteryEnabled = document.getElementById('battery-toggle')?.checked || false;
    const batteryKwh = batteryEnabled
      ? parseFloat(document.getElementById('battery-size')?.value || '10')
      : 0;
    const monthlyBillRaw = document.getElementById('monthly-bill')?.value;
    const monthlyBill = monthlyBillRaw !== undefined && monthlyBillRaw !== ''
      ? parseFloat(monthlyBillRaw)
      : null;
    const propertyType = document.getElementById('property-type')?.value || 'residential';
    const needsBackup = document.getElementById('needs-backup')?.checked || false;
    const inverterPreference = document.getElementById('inverter-preference')?.value || 'auto';

    document.getElementById('loading-panel').classList.remove('hidden');
    btn.disabled = true;

    try {
      const res = await fetch(ESTIMATE_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          address: selectedAddress,
          latitude: selectedLatLng.lat,
          longitude: selectedLatLng.lng,
          polygon: polygon,
          obstructions: obstructions,
          orientation: orientationValue,
          battery_kwh: batteryKwh,
          monthly_bill: monthlyBill,
          property_type: propertyType,
          needs_backup: needsBackup,
          inverter_preference: inverterPreference
        })
      });
      let data;
      try {
        data = await res.json();
      } catch (parseErr) {
        alert('Server returned an invalid response (HTTP ' + res.status + '). Check the Flask terminal for errors.');
        return;
      }
      if (!res.ok) {
        alert(data.error || ('Estimation failed (HTTP ' + res.status + ').'));
        return;
      }
      if (data.redirect_url) {
        window.location.href = data.redirect_url;
      } else {
        alert(data.error || 'Something went wrong generating your estimate.');
      }
    } catch (err) {
      console.error(err);
      alert('Estimation failed: ' + (err && err.message ? err.message : 'network or server error. Check the Flask terminal.'));
    } finally {
      document.getElementById('loading-panel').classList.add('hidden');
      btn.disabled = false;
    }
  });
}

// -------------------------------------------------------- Report page -----
function initTabs() {
  const tabButtons = document.querySelectorAll('.tab-btn');
  if (!tabButtons.length) return;

  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
    });
  });
}

function initCharts() {
  if (typeof MONTHLY_DATA === 'undefined' || typeof Chart === 'undefined') return;

  const months = Object.keys(MONTHLY_DATA);
  const values = Object.values(MONTHLY_DATA);
  const palette = {
    purple: '#3d2570',
    orange: '#ff7a45',
    amber: '#ffb347',
    pink: '#c24fa8',
    green: '#2e9e5b'
  };
  const currency = (value) => new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0
  }).format(value || 0);
  const chartAnimation = (canvas) => ({
    duration: 650,
    easing: 'easeOutQuart',
    onComplete: () => canvas.parentElement?.classList.remove('is-loading')
  });
  const prepareCanvas = (canvas) => {
    canvas.parentElement?.classList.add('is-loading');
  };

  const genCtx = document.getElementById('monthlyGenerationChart');
  if (genCtx) {
    prepareCanvas(genCtx);
    new Chart(genCtx, {
      type: 'bar',
      data: {
        labels: months,
        datasets: [{
          label: 'Generation (kWh)',
          data: values,
          backgroundColor: palette.orange,
          borderColor: palette.orange,
          borderRadius: 6,
          maxBarThickness: 34
        }]
      },
      options: {
        responsive: true,
        animation: chartAnimation(genCtx),
        plugins: { legend: { display: false } },
        scales: {
          x: {
            title: { display: true, text: 'Month', color: palette.purple },
            grid: { display: false }
          },
          y: {
            beginAtZero: true,
            title: { display: true, text: 'Generation (kWh)', color: palette.purple },
            grid: { color: 'rgba(61, 37, 112, 0.08)' }
          }
        }
      }
    });
  }

  const donutCtx = document.getElementById('financialDonutChart');
  if (donutCtx && typeof NET_INVESTMENT !== 'undefined') {
    const labels = ['Net Investment', 'Subsidy', 'You Save (25yrs)'];
    const data = [NET_INVESTMENT, SUBSIDY_AMOUNT, TOTAL_25YR_SAVINGS];
    const colors = [palette.purple, palette.orange, palette.amber];
    if (typeof BATTERY_COST !== 'undefined' && BATTERY_COST > 0) {
      labels.splice(1, 0, 'Battery');
      data.splice(1, 0, BATTERY_COST);
      colors.splice(1, 0, palette.green);
    }
    prepareCanvas(donutCtx);
    new Chart(donutCtx, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{ data, backgroundColor: colors, borderWidth: 0, hoverOffset: 6 }]
      },
      options: {
        responsive: true,
        animation: chartAnimation(donutCtx),
        plugins: {
          legend: { position: 'bottom', labels: { usePointStyle: true, padding: 16 } },
          tooltip: { callbacks: { label: (context) => `${context.label}: ${currency(context.raw)}` } }
        },
        cutout: '65%'
      }
    });
  }

  const cashCtx = document.getElementById('cashflowChart');
  if (cashCtx) {
    // 25-year cumulative savings curve; visually anchored to the 15L/20L/25L
    // milestones shown beneath the chart.
    const years = Array.from({ length: 25 }, (_, i) => `Yr ${i + 1}`);
    const netInvestment = (typeof NET_INVESTMENT !== 'undefined') ? NET_INVESTMENT : 0;
    const annualSavings = (typeof ANNUAL_SAVINGS !== 'undefined') ? ANNUAL_SAVINGS : 0;
    let cumulative = -netInvestment;
    const cashflow = years.map(() => {
      cumulative += annualSavings;
      return Math.round(cumulative);
    });

    prepareCanvas(cashCtx);
    new Chart(cashCtx, {
      type: 'line',
      data: {
        labels: years,
        datasets: [{
          label: 'Cumulative Savings (₹)',
          data: cashflow,
          borderColor: palette.purple,
          backgroundColor: 'rgba(255, 122, 69, 0.16)',
          pointBackgroundColor: palette.orange,
          pointBorderColor: '#fff',
          pointBorderWidth: 2,
          pointRadius: 3,
          fill: true,
          tension: 0.3
        }]
      },
      options: {
        responsive: true,
        animation: chartAnimation(cashCtx),
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (context) => `${context.dataset.label}: ${currency(context.raw)}` } }
        },
        scales: {
          x: {
            title: { display: true, text: 'Year', color: palette.purple },
            grid: { display: false },
            ticks: { maxTicksLimit: 9 }
          },
          y: {
            title: { display: true, text: 'Cumulative value (INR)', color: palette.purple },
            grid: { color: 'rgba(61, 37, 112, 0.08)' },
            ticks: { callback: (value) => currency(value) }
          }
        }
      }
    });
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initSearch();
  initSystemOptions();
  initEstimationButton();
  initTabs();
  initCharts();
});
