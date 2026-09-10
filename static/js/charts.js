(() => {
  'use strict';
  const palette = ['#0065ff', '#00a6c8', '#e32934', '#005cb9', '#55c4d8', '#071d49', '#4c8dff', '#26b97b'];
  const number = value => new Intl.NumberFormat(undefined, { notation: Math.abs(value || 0) >= 1000000 ? 'compact' : 'standard', maximumFractionDigits: 1 }).format(value || 0);
  const clampLabel = value => String(value ?? '').length > 28 ? String(value).slice(0, 27) + '…' : String(value ?? '');

  function parseSource(canvas) {
    const node = document.getElementById(canvas.dataset.chartSource);
    if (!node) return { labels: [], values: [] };
    try {
      const raw = JSON.parse(node.textContent || '{}');
      const root = canvas.closest('[data-analysis-root]');
      const mode = root?.dataset.analysisMode || root?.dataset.defaultMode || 'cases';
      if (raw && raw[mode] && raw[mode][canvas.dataset.chartKey]) return raw[mode][canvas.dataset.chartKey];
      return raw[canvas.dataset.chartKey] || { labels: [], values: [] };
    } catch (_) { return { labels: [], values: [] }; }
  }

  function setup(canvas) {
    const rect = canvas.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.max(1, Math.floor(rect.width * ratio));
    canvas.height = Math.max(1, Math.floor(rect.height * ratio));
    const ctx = canvas.getContext('2d');
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    return { ctx, width: rect.width, height: rect.height };
  }

  function empty(ctx, width, height) {
    ctx.fillStyle = '#7b899c'; ctx.font = '13px system-ui'; ctx.textAlign = 'center'; ctx.fillText('No data for this selection', width / 2, height / 2);
  }

  function lineChart(ctx, width, height, data) {
    const labels = data.labels || [], values = (data.values || []).map(Number);
    if (!values.length) return empty(ctx, width, height);
    const pad = { l: 58, r: 16, t: 20, b: 46 }, innerW = width - pad.l - pad.r, innerH = height - pad.t - pad.b;
    const max = Math.max(...values, 1) * 1.12;
    ctx.font = '11px system-ui'; ctx.strokeStyle = '#e4ebf1'; ctx.fillStyle = '#7b899c'; ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = pad.t + innerH * i / 4; ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(width - pad.r, y); ctx.stroke();
      ctx.textAlign = 'right'; ctx.fillText(number(max * (1 - i / 4)), pad.l - 8, y + 4);
    }
    const x = i => labels.length === 1 ? pad.l + innerW / 2 : pad.l + innerW * i / (labels.length - 1);
    const y = v => pad.t + innerH - innerH * v / max;
    const grad = ctx.createLinearGradient(0, pad.t, 0, pad.t + innerH); grad.addColorStop(0, 'rgba(0,101,255,.20)'); grad.addColorStop(1, 'rgba(0,166,200,.02)');
    ctx.beginPath(); values.forEach((v, i) => i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v))); ctx.lineTo(x(values.length - 1), pad.t + innerH); ctx.lineTo(x(0), pad.t + innerH); ctx.closePath(); ctx.fillStyle = grad; ctx.fill();
    ctx.beginPath(); values.forEach((v, i) => i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v))); ctx.strokeStyle = '#0065ff'; ctx.lineWidth = 2.6; ctx.stroke();
    values.forEach((v, i) => { ctx.beginPath(); ctx.arc(x(i), y(v), 3.2, 0, Math.PI * 2); ctx.fillStyle = '#00a6c8'; ctx.fill(); });
    const every = Math.max(1, Math.ceil(labels.length / 7)); ctx.fillStyle = '#7b899c'; ctx.textAlign = 'center';
    labels.forEach((label, i) => { if (i % every === 0 || i === labels.length - 1) ctx.fillText(clampLabel(label), x(i), height - 16); });
  }

  function fitLabel(ctx, value, maxWidth) {
    const text = String(value ?? '');
    if (ctx.measureText(text).width <= maxWidth) return text;
    let shortened = text;
    while (shortened.length > 4 && ctx.measureText(shortened + '…').width > maxWidth) shortened = shortened.slice(0, -1);
    return shortened + '…';
  }

  function barChart(ctx, width, height, data) {
    const labels = data.labels || [], values = (data.values || []).map(Number);
    if (!values.length) return empty(ctx, width, height);

    // Horizontal bars keep product sizes and salesman names readable without rotated text.
    const left = width < 430 ? 118 : 165;
    const pad = { l: left, r: 54, t: 16, b: 34 };
    const innerW = Math.max(40, width - pad.l - pad.r);
    const innerH = Math.max(40, height - pad.t - pad.b);
    const max = Math.max(...values, 1) * 1.12;
    const slot = innerH / values.length;
    const barH = Math.max(7, Math.min(24, slot * .58));

    ctx.font = '11px system-ui';
    ctx.strokeStyle = '#e6edf2';
    ctx.fillStyle = '#6d7e91';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const x = pad.l + innerW * i / 4;
      ctx.beginPath(); ctx.moveTo(x, pad.t); ctx.lineTo(x, pad.t + innerH); ctx.stroke();
      ctx.textAlign = 'center'; ctx.textBaseline = 'top';
      ctx.fillText(number(max * i / 4), x, pad.t + innerH + 9);
    }

    values.forEach((value, i) => {
      const cy = pad.t + slot * i + slot / 2;
      const w = innerW * value / max;
      const y = cy - barH / 2;
      const grad = ctx.createLinearGradient(pad.l, 0, pad.l + Math.max(w, 1), 0);
      grad.addColorStop(0, i % 2 ? '#005cb9' : '#0065ff');
      grad.addColorStop(1, palette[i % palette.length]);
      ctx.fillStyle = grad;
      ctx.beginPath();
      const r = Math.min(6, barH / 2);
      ctx.roundRect ? ctx.roundRect(pad.l, y, w, barH, [0, r, r, 0]) : ctx.rect(pad.l, y, w, barH);
      ctx.fill();

      ctx.font = '600 11.5px system-ui';
      ctx.fillStyle = '#334861';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      ctx.fillText(fitLabel(ctx, labels[i], pad.l - 18), pad.l - 10, cy);

      ctx.font = '600 10.5px system-ui';
      ctx.fillStyle = '#53647a';
      ctx.textAlign = 'left';
      const valueX = Math.min(width - pad.r + 5, pad.l + w + 7);
      ctx.fillText(number(value), valueX, cy);
    });
  }


  function donutChart(ctx, width, height, data) {
    const labels = data.labels || [], values = (data.values || []).map(Number), total = values.reduce((a, b) => a + b, 0);
    if (!values.length || total <= 0) return empty(ctx, width, height);
    const cx = width / 2, cy = height / 2 - 12, radius = Math.min(width, height) * .28, inner = radius * .62; let angle = -Math.PI / 2;
    values.forEach((value, i) => { const next = angle + Math.PI * 2 * value / total; ctx.beginPath(); ctx.arc(cx, cy, radius, angle, next); ctx.arc(cx, cy, inner, next, angle, true); ctx.closePath(); ctx.fillStyle = palette[i % palette.length]; ctx.fill(); angle = next; });
    ctx.fillStyle = '#17233b'; ctx.font = '700 16px system-ui'; ctx.textAlign = 'center'; ctx.fillText(number(total), cx, cy + 2); ctx.font = '10px system-ui'; ctx.fillStyle = '#7b899c'; ctx.fillText('TOTAL', cx, cy + 18);
    let lx = 12, ly = height - 30; ctx.textAlign = 'left'; ctx.font = '11px system-ui';
    labels.forEach((label, i) => { const text = clampLabel(label); ctx.fillStyle = palette[i % palette.length]; ctx.fillRect(lx, ly - 8, 9, 9); ctx.fillStyle = '#53647a'; ctx.fillText(text, lx + 14, ly); lx += Math.min(190, 25 + ctx.measureText(text).width); if (lx > width - 130) { lx = 12; ly += 17; } });
  }

  function render(canvas) {
    const data = parseSource(canvas), type = canvas.dataset.chartType || 'line';
    const { ctx, width, height } = setup(canvas); ctx.clearRect(0, 0, width, height);
    if (type === 'bar') barChart(ctx, width, height, data); else if (type === 'donut') donutChart(ctx, width, height, data); else lineChart(ctx, width, height, data);
  }

  const charts = Array.from(document.querySelectorAll('.mms-chart'));
  if (!charts.length) return;
  const renderAll = root => charts.filter(c => !root || root.contains(c)).forEach(render);
  renderAll();
  document.addEventListener('mms:analysis-mode', event => renderAll(event.target.closest?.('[data-analysis-root]') || null));
  let timer; window.addEventListener('resize', () => { clearTimeout(timer); timer = setTimeout(() => renderAll(), 120); });
})();
