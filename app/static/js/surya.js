// Surya is a lightweight, context-aware chat layer for Solar Setu.
(() => {
  const launcher = document.getElementById('surya-launcher');
  const panel = document.getElementById('surya-panel');
  const closeButton = document.getElementById('surya-close');
  const minimizeButton = document.getElementById('surya-minimize');
  const messages = document.getElementById('surya-messages');
  const form = document.getElementById('surya-form');
  const input = document.getElementById('surya-input');
  const quickActions = document.getElementById('surya-quick-actions');
  const clearButton = document.getElementById('surya-clear');
  const contextNote = document.getElementById('surya-context-note');
  if (!launcher || !panel || !messages || !form || !input) return;

  const storageKey = 'solar-setu-surya-chat-v2';
  const context = window.SOLAR_CONTEXT || {};
  let pending = false;
  let history = [];

  const hasReport = Object.keys(context).some((key) => context[key] !== null && context[key] !== undefined);
  if (hasReport) {
    contextNote.textContent = 'I can explain the results from this rooftop analysis.';
  }

  function openPanel() {
    panel.classList.add('is-open');
    panel.setAttribute('aria-hidden', 'false');
    launcher.setAttribute('aria-expanded', 'true');
    input.focus();
  }

  function closePanel() {
    panel.classList.remove('is-open');
    panel.setAttribute('aria-hidden', 'true');
    launcher.setAttribute('aria-expanded', 'false');
  }

  function addMessage(role, text, persist = true) {
    const row = document.createElement('div');
    row.className = `surya-message surya-message-${role}`;
    if (role === 'assistant') {
      const avatar = document.createElement('span');
      avatar.className = 'surya-message-avatar';
      avatar.textContent = '☼';
      row.appendChild(avatar);
    }
    const bubble = document.createElement('div');
    bubble.className = 'surya-bubble';
    bubble.textContent = text;
    row.appendChild(bubble);
    messages.appendChild(row);
    messages.scrollTop = messages.scrollHeight;
    if (persist) {
      history.push({ role, text });
      localStorage.setItem(storageKey, JSON.stringify(history.slice(-30)));
    }
  }

  function showThinking() {
    const row = document.createElement('div');
    row.className = 'surya-message surya-message-assistant surya-thinking';
    row.innerHTML = '<span class="surya-message-avatar">☼</span><div class="surya-bubble"><span>Surya is thinking</span><i></i><i></i><i></i></div>';
    messages.appendChild(row);
    messages.scrollTop = messages.scrollHeight;
    return row;
  }

  function welcome() {
    addMessage('assistant', "Hi! I'm Surya.\n\nI can help you understand your rooftop's solar potential, savings, system size and environmental impact.\n\nWhat would you like to know?", false);
  }

  function restore() {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) || '[]');
      if (Array.isArray(saved) && saved.length) {
        history = saved;
        saved.forEach((item) => addMessage(item.role, item.text, false));
        return;
      }
    } catch (error) {
      localStorage.removeItem(storageKey);
    }
    welcome();
  }

  function formatValue(value, suffix = '') {
    if (value === null || value === undefined || value === '') return 'not available';
    return `${value}${suffix}`;
  }

  function contextualQuestion(action) {
    const system = formatValue(context.systemSize, ' kW');
    const monthly = formatValue(context.monthlySavings, ' INR/month');
    const generation = formatValue(context.annualGeneration, ' kWh/year');
    const payback = formatValue(context.paybackPeriod, ' years');
    const co2 = formatValue(context.co2ReductionTons, ' tonnes/year');
    const usable = formatValue(context.usableRoofArea, ' m2');
    const location = formatValue(context.location);
    const questions = {
      'system-size': `Why was a ${system} system recommended for my rooftop at ${location}? Explain using my usable roof area (${usable}) and other available analysis values.`,
      'monthly-savings': `How was my estimated monthly saving of ${monthly} calculated? Use my actual annual generation (${generation}), bill and available analysis context.`,
      payback: `Explain my payback period of ${payback} using the actual investment and savings values in my Solar Setu analysis.`,
      generation: `Explain my annual generation of ${generation} for this rooftop, including orientation and usable area when available.`,
      environment: `Explain my environmental impact of ${co2} based on this Solar Setu analysis.`,
      report: 'Explain my complete Solar Setu report. Start with the most important result, then explain savings, payback and environmental impact using only the values available.',
      battery: 'Should I choose a battery for this analysis? Explain the trade-offs using my actual battery, backup, savings and property details when available.'
      ,savings: 'Explain my solar savings and payback period using the actual monthly savings, annual savings, net investment and payback values in my current Solar Setu assessment.'
    };
    return questions[action] || action;
  }

  async function sendMessage(text) {
    const message = (text || '').trim();
    if (!message || pending) return;
    pending = true;
    input.value = '';
    addMessage('user', message);
    const thinking = showThinking();
    try {
      const response = await fetch(window.SURYA_API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, context })
      });
      const data = await response.json().catch(() => ({}));
      thinking.remove();
      addMessage('assistant', data.reply || "Sorry, I couldn't connect right now. Please try again.");
    } catch (error) {
      thinking.remove();
      addMessage('assistant', "Sorry, I couldn't connect right now. Please try again.");
    } finally {
      pending = false;
      input.focus();
    }
  }

  launcher.addEventListener('click', () => {
    if (panel.classList.contains('is-open')) closePanel();
    else openPanel();
  });
  closeButton?.addEventListener('click', closePanel);
  minimizeButton?.addEventListener('click', closePanel);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    sendMessage(input.value);
  });
  quickActions?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-surya-quick]');
    if (button) sendMessage(button.dataset.suryaQuick);
  });
  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-surya-action]');
    if (!button) return;
    openPanel();
    sendMessage(contextualQuestion(button.dataset.suryaAction));
  });
  clearButton?.addEventListener('click', () => {
    history = [];
    localStorage.removeItem(storageKey);
    messages.innerHTML = '';
    welcome();
  });

  restore();
})();
