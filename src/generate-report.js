#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

const OUTPUT_DIR = path.resolve('./output');
const REPORT_PATH = path.join(OUTPUT_DIR, 'accessibility-report.html');

// ─── Data loading ─────────────────────────────────────────────────────────────

function loadFlows() {
  const flows = [];
  const dirs = fs.readdirSync(OUTPUT_DIR, { withFileTypes: true })
    .filter(e => e.isDirectory())
    .map(e => e.name)
    .sort();

  for (const dir of dirs) {
    const reportPath = path.join(OUTPUT_DIR, dir, 'wave-report.json');
    if (!fs.existsSync(reportPath)) continue;
    const pages = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
    flows.push({ name: dir, pages });
  }
  return flows;
}

// ─── Aggregation helpers ──────────────────────────────────────────────────────

function globalStats(flows) {
  let totalPages = 0, totalErrors = 0, totalCritical = 0, aimSum = 0, aimCount = 0;
  for (const { pages } of flows) {
    for (const page of pages) {
      totalPages++;
      const s = page.summary;
      totalErrors += (s.errors || 0) + (s.contrast_errors || 0) + (s.alerts || 0);
      totalCritical += s.sr_relevance_breakdown?.critical || 0;
      if (s.aim_score != null) { aimSum += s.aim_score; aimCount++; }
    }
  }
  return {
    totalFlows: flows.length,
    totalPages,
    totalErrors,
    totalCritical,
    avgAim: aimCount ? (aimSum / aimCount).toFixed(1) : 'N/A',
  };
}

function topIssues(flows, limit = 20) {
  const map = new Map();
  for (const { pages } of flows) {
    for (const page of pages) {
      for (const cat of (page.categories || [])) {
        for (const t of (cat.types || [])) {
          const key = t.type_id;
          if (!map.has(key)) {
            map.set(key, {
              type_id: t.type_id,
              type_label: t.type_label,
              category: cat.category,
              category_label: cat.category_label,
              total_count: 0,
              page_count: 0,
              wcag_criteria: t.wcag_criteria,
              wcag_level: t.wcag_level,
              pour_dimensions: t.pour_dimensions,
              sr_relevance: t.sr_relevance,
            });
          }
          const e = map.get(key);
          e.total_count += t.count || 0;
          e.page_count++;
        }
      }
    }
  }
  return [...map.values()].sort((a, b) => b.total_count - a.total_count).slice(0, limit);
}

// ─── HTML helpers ─────────────────────────────────────────────────────────────

const pageName = f => f.replace(/\.html?$/i, '').replace(/^\d+-/, '').replace(/[-_]/g, ' ');

const srBadge = sr => {
  const cfg = {
    critical: ['#7f1d1d', '#fca5a5', 'Crítico'],
    high:     ['#7c2d12', '#fdba74', 'Alto'],
    medium:   ['#713f12', '#fde047', 'Médio'],
    low:      ['#14532d', '#86efac', 'Baixo'],
    positive: ['#052e16', '#4ade80', 'Positivo'],
    informational: ['#1e3a5f', '#93c5fd', 'Informativo'],
  };
  const [bg, fg, label] = cfg[sr] || ['#374151', '#e5e7eb', sr || '—'];
  return `<span class="badge" style="background:${fg};color:${bg}">${label}</span>`;
};

const catBadge = cat => {
  const cfg = {
    error:    ['#fef2f2', '#dc2626', 'Erro'],
    contrast: ['#fff7ed', '#ea580c', 'Contraste'],
    alert:    ['#fefce8', '#ca8a04', 'Alerta'],
    feature:  ['#f0fdf4', '#16a34a', 'Funcionalidade'],
    structure:['#eff6ff', '#2563eb', 'Estrutura'],
    aria:     ['#faf5ff', '#7c3aed', 'ARIA'],
  };
  const [bg, fg, label] = cfg[cat] || ['#f3f4f6', '#374151', cat];
  return `<span class="badge" style="background:${bg};color:${fg};border:1px solid ${fg}33">${label}</span>`;
};

const aimColor = score => {
  if (score == null) return '#94a3b8';
  if (score < 5)   return '#ef4444';
  if (score < 7)   return '#f97316';
  if (score < 8.5) return '#eab308';
  return '#22c55e';
};

const wcagCriteria = arr => arr?.length ? arr.join(', ') : '—';
const pourDims = arr => arr?.length ? arr.join(', ') : '—';

// ─── HTML sections ────────────────────────────────────────────────────────────

function kpiCards(stats) {
  const cards = [
    { label: 'Fluxos analisados', value: stats.totalFlows, icon: '🗂️', color: '#3b82f6' },
    { label: 'Páginas analisadas', value: stats.totalPages, icon: '📄', color: '#8b5cf6' },
    { label: 'Total de problemas', value: stats.totalErrors, icon: '⚠️', color: '#f97316' },
    { label: 'Problemas críticos (leitor de tela)', value: stats.totalCritical, icon: '🔴', color: '#ef4444' },
    { label: 'Pontuação AIM média', value: stats.avgAim + '/10', icon: '📊', color: '#22c55e' },
  ];
  return `<div class="kpi-grid">${cards.map(c => `
    <div class="kpi-card" style="border-left:4px solid ${c.color}">
      <div class="kpi-icon">${c.icon}</div>
      <div class="kpi-value" style="color:${c.color}">${c.value}</div>
      <div class="kpi-label">${c.label}</div>
    </div>`).join('')}</div>`;
}

function overviewCharts(flows) {
  // Build data for all-pages AIM chart
  const labels = [], aimData = [], aimColors = [], flowLabels = [];
  const pourP = [], pourO = [], pourU = [], pourR = [];
  const srCritical = [], srHigh = [], srMedium = [], srLow = [];
  const errData = [], contData = [], alertData = [];

  for (const { name, pages } of flows) {
    for (const page of pages) {
      const label = `${name.replace(/([A-Z])/g, ' $1').trim()}\n${pageName(page.source_file)}`;
      labels.push(label);
      flowLabels.push(name);
      const s = page.summary;
      aimData.push(s.aim_score);
      aimColors.push(aimColor(s.aim_score));
      pourP.push(s.pour_breakdown?.perceivable || 0);
      pourO.push(s.pour_breakdown?.operable || 0);
      pourU.push(s.pour_breakdown?.understandable || 0);
      pourR.push(s.pour_breakdown?.robust || 0);
      srCritical.push(s.sr_relevance_breakdown?.critical || 0);
      srHigh.push(s.sr_relevance_breakdown?.high || 0);
      srMedium.push(s.sr_relevance_breakdown?.medium || 0);
      srLow.push(s.sr_relevance_breakdown?.low || 0);
      errData.push(s.errors || 0);
      contData.push(s.contrast_errors || 0);
      alertData.push(s.alerts || 0);
    }
  }

  return `
<div class="chart-grid">
  <div class="chart-card chart-wide">
    <h3>Pontuação AIM por página</h3>
    <p class="chart-desc">Escala 0–10. Maior é melhor. Vermelho &lt; 5, laranja &lt; 7, amarelo &lt; 8.5, verde ≥ 8.5.</p>
    <div class="chart-wrap" style="height:300px"><canvas id="chartAimAll"></canvas></div>
  </div>
  <div class="chart-card">
    <h3>Problemas por tipo por página</h3>
    <p class="chart-desc">Erros, erros de contraste e alertas — apenas problemas.</p>
    <div class="chart-wrap" style="height:300px"><canvas id="chartIssuesByPage"></canvas></div>
  </div>
  <div class="chart-card">
    <h3>Impacto no leitor de tela</h3>
    <p class="chart-desc">Severidade dos problemas para usuários de leitores de tela.</p>
    <div class="chart-wrap" style="height:300px"><canvas id="chartSrAll"></canvas></div>
  </div>
  <div class="chart-card chart-wide">
    <h3>Dimensões POUR por página</h3>
    <p class="chart-desc">Distribuição de problemas pelas dimensões WCAG: Perceptível, Operável, Compreensível, Robusto.</p>
    <div class="chart-wrap" style="height:300px"><canvas id="chartPourAll"></canvas></div>
  </div>
</div>
<script>
(function() {
  const labels = ${JSON.stringify(labels)};
  const shortLabels = labels.map(l => l.split('\\n')[1]);

  // AIM chart
  new Chart(document.getElementById('chartAimAll'), {
    type: 'bar',
    data: {
      labels: shortLabels,
      datasets: [{
        label: 'AIM Score',
        data: ${JSON.stringify(aimData)},
        backgroundColor: ${JSON.stringify(aimColors)},
        borderRadius: 4,
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: {
        callbacks: { title: (items) => labels[items[0].dataIndex].replace('\\n', ' — ') }
      }},
      scales: {
        x: { min: 0, max: 10, title: { display: true, text: 'AIM Score' } },
        y: { ticks: { font: { size: 11 } } }
      }
    }
  });

  // Issues stacked bar
  new Chart(document.getElementById('chartIssuesByPage'), {
    type: 'bar',
    data: {
      labels: shortLabels,
      datasets: [
        { label: 'Erros', data: ${JSON.stringify(errData)}, backgroundColor: '#ef4444', borderRadius: 2 },
        { label: 'Contraste', data: ${JSON.stringify(contData)}, backgroundColor: '#f97316', borderRadius: 2 },
        { label: 'Alertas', data: ${JSON.stringify(alertData)}, backgroundColor: '#eab308', borderRadius: 2 },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { tooltip: {
        callbacks: { title: (items) => labels[items[0].dataIndex].replace('\\n', ' — ') }
      }},
      scales: { x: { stacked: true }, y: { stacked: true } }
    }
  });

  // SR relevance stacked bar
  new Chart(document.getElementById('chartSrAll'), {
    type: 'bar',
    data: {
      labels: shortLabels,
      datasets: [
        { label: 'Crítico', data: ${JSON.stringify(srCritical)}, backgroundColor: '#dc2626' },
        { label: 'Alto',    data: ${JSON.stringify(srHigh)},     backgroundColor: '#ea580c' },
        { label: 'Médio',   data: ${JSON.stringify(srMedium)},   backgroundColor: '#ca8a04' },
        { label: 'Baixo',   data: ${JSON.stringify(srLow)},      backgroundColor: '#16a34a' },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { tooltip: {
        callbacks: { title: (items) => labels[items[0].dataIndex].replace('\\n', ' — ') }
      }},
      scales: { x: { stacked: true }, y: { stacked: true } }
    }
  });

  // POUR stacked bar
  new Chart(document.getElementById('chartPourAll'), {
    type: 'bar',
    data: {
      labels: shortLabels,
      datasets: [
        { label: 'Perceptível', data: ${JSON.stringify(pourP)}, backgroundColor: '#3b82f6' },
        { label: 'Operável',    data: ${JSON.stringify(pourO)}, backgroundColor: '#8b5cf6' },
        { label: 'Compreensível', data: ${JSON.stringify(pourU)}, backgroundColor: '#ec4899' },
        { label: 'Robusto',     data: ${JSON.stringify(pourR)}, backgroundColor: '#14b8a6' },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { tooltip: {
        callbacks: { title: (items) => labels[items[0].dataIndex].replace('\\n', ' — ') }
      }},
      scales: { x: { stacked: true }, y: { stacked: true } }
    }
  });
})();
</script>`;
}

function topIssuesSection(flows) {
  const issues = topIssues(flows, 20);
  const negIssues = issues.filter(i => ['error','contrast','alert'].includes(i.category));
  const rows = negIssues.map((i, idx) => `
    <tr>
      <td class="num">${idx + 1}</td>
      <td>${catBadge(i.category)}</td>
      <td><strong>${i.type_label}</strong><br><small class="muted">${i.type_id}</small></td>
      <td class="num"><strong>${i.total_count}</strong></td>
      <td class="num">${i.page_count}</td>
      <td>${wcagCriteria(i.wcag_criteria)}</td>
      <td>${i.wcag_level || '—'}</td>
      <td>${pourDims(i.pour_dimensions)}</td>
      <td>${srBadge(i.sr_relevance)}</td>
    </tr>`).join('');

  const chartData = negIssues.slice(0, 12);
  const chartColors = chartData.map(i => ({
    error: '#ef4444', contrast: '#f97316', alert: '#eab308'
  }[i.category] || '#94a3b8'));

  return `
<h2>Principais problemas de acessibilidade</h2>
  <p>Os problemas mais frequentes encontrados somando todas as páginas e fluxos analisados.</p>

  <div class="chart-card" style="margin-bottom:2rem">
    <h3>Principais 12 problemas por ocorrências</h3>
    <div class="chart-wrap" style="height:340px"><canvas id="chartTopIssues"></canvas></div>
  </div>

  <div class="table-wrap">
    <table class="data-table">
      <thead>
        <tr>
          <th>#</th><th>Tipo</th><th>Problema</th><th>Ocorrências</th>
          <th>Páginas</th><th>Critério WCAG</th><th>Nível</th><th>POUR</th><th>Impacto LS</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  </div>
<script>
(function() {
  const labels = ${JSON.stringify(chartData.map(i => i.type_label))};
  const counts = ${JSON.stringify(chartData.map(i => i.total_count))};
  const colors = ${JSON.stringify(chartColors)};
  new Chart(document.getElementById('chartTopIssues'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{ label: 'Ocorrências', data: counts, backgroundColor: colors, borderRadius: 4 }]
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { x: { title: { display: true, text: 'Total de ocorrências' } } }
    }
  });
})();
</script>`;
}

function srNarrative(pages, flowName) {
  return pages.map(page => {
    const name = pageName(page.source_file);
    const s = page.summary;
    const criticalIssues = [];
    const highIssues = [];

    for (const cat of (page.categories || [])) {
      for (const t of (cat.types || [])) {
        if (t.sr_relevance === 'critical') criticalIssues.push({ ...t, category: cat.category });
        else if (t.sr_relevance === 'high') highIssues.push({ ...t, category: cat.category });
      }
    }

    const hasCritical = criticalIssues.length > 0;
    const score = s.aim_score;
    const scoreStyle = `color:${aimColor(score)};font-weight:700`;

    const issueRows = [...criticalIssues, ...highIssues].map(t => `
      <tr>
        <td>${catBadge(t.category)}</td>
        <td>${t.type_label}</td>
        <td class="num">${t.count}</td>
        <td>${srBadge(t.sr_relevance)}</td>
        <td>${wcagCriteria(t.wcag_criteria)}</td>
        <td>${pourDims(t.pour_dimensions)}</td>
      </tr>`).join('');

    return `
<div class="page-card">
  <div class="page-card-header">
    <div>
      <h4>${name}</h4>
      <small class="muted">${page.source_file}</small>
    </div>
    <div class="aim-badge" style="background:${aimColor(score)}22;border:2px solid ${aimColor(score)}">
      <span style="${scoreStyle}">${score ?? '—'}</span>
      <span class="muted" style="font-size:0.75rem">/ 10 AIM</span>
    </div>
  </div>

  <div class="sr-summary-row">
    <div class="sr-chip sr-critical">🔴 ${s.sr_relevance_breakdown?.critical || 0} críticos</div>
    <div class="sr-chip sr-high">🟠 ${s.sr_relevance_breakdown?.high || 0} altos</div>
    <div class="sr-chip sr-medium">🟡 ${s.sr_relevance_breakdown?.medium || 0} médios</div>
    <div class="sr-chip sr-low">🟢 ${s.sr_relevance_breakdown?.low || 0} baixos</div>
    <div class="sr-chip" style="background:#f0f9ff;color:#0369a1">Erros: ${s.errors}</div>
    <div class="sr-chip" style="background:#fff7ed;color:#c2410c">Contraste: ${s.contrast_errors}</div>
    <div class="sr-chip" style="background:#fefce8;color:#a16207">Alertas: ${s.alerts}</div>
  </div>

  ${issueRows ? `
  <div class="table-wrap" style="margin-top:1rem">
    <table class="data-table compact">
      <thead><tr><th>Tipo</th><th>Problema</th><th>Qtd</th><th>Impacto LS</th><th>WCAG</th><th>POUR</th></tr></thead>
      <tbody>${issueRows}</tbody>
    </table>
  </div>` : `<p class="muted" style="margin-top:0.75rem">Nenhum problema crítico ou alto para leitores de tela.</p>`}
</div>`;
  }).join('');
}

function flowSection(flow, flowIndex) {
  const { name, pages } = flow;
  const flowLabel = name.replace(/([A-Z])/g, ' $1').trim();

  // Per-page summary table
  const tableRows = pages.map(page => {
    const s = page.summary;
    const score = s.aim_score;
    return `<tr>
      <td>${pageName(page.source_file)}</td>
      <td class="num"><span style="color:${aimColor(score)};font-weight:700">${score ?? '—'}</span></td>
      <td class="num">${s.errors}</td>
      <td class="num">${s.contrast_errors}</td>
      <td class="num">${s.alerts}</td>
      <td class="num">${s.features}</td>
      <td class="num">${s.structure}</td>
      <td class="num">${s.aria}</td>
      <td class="num">${s.sr_relevance_breakdown?.critical || 0}</td>
      <td class="num">${s.sr_relevance_breakdown?.medium || 0}</td>
    </tr>`;
  }).join('');

  // Chart data
  const pageLabels = pages.map(p => pageName(p.source_file));
  const aimScores = pages.map(p => p.summary.aim_score);
  const aimColors = aimScores.map(s => aimColor(s));
  const errD = pages.map(p => p.summary.errors);
  const contD = pages.map(p => p.summary.contrast_errors);
  const alrtD = pages.map(p => p.summary.alerts);
  const featD = pages.map(p => p.summary.features);
  const strD  = pages.map(p => p.summary.structure);
  const ariaD = pages.map(p => p.summary.aria);
  const pourP = pages.map(p => p.summary.pour_breakdown?.perceivable || 0);
  const pourO = pages.map(p => p.summary.pour_breakdown?.operable || 0);
  const pourU = pages.map(p => p.summary.pour_breakdown?.understandable || 0);
  const pourR = pages.map(p => p.summary.pour_breakdown?.robust || 0);
  const srCr  = pages.map(p => p.summary.sr_relevance_breakdown?.critical || 0);
  const srHi  = pages.map(p => p.summary.sr_relevance_breakdown?.high || 0);
  const srMd  = pages.map(p => p.summary.sr_relevance_breakdown?.medium || 0);
  const srLo  = pages.map(p => p.summary.sr_relevance_breakdown?.low || 0);

  const chartId = `flow${flowIndex}`;

  // Top issues for this flow
  const flowIssues = topIssues([flow], 10).filter(i => ['error','contrast','alert'].includes(i.category));

  return `
<h2>${flowLabel}</h2>

  <h3>Resumo por página</h3>
  <div class="table-wrap">
    <table class="data-table">
      <thead>
        <tr>
          <th>Página</th><th>AIM</th><th>Erros</th><th>Contraste</th><th>Alertas</th>
          <th>Funcionalidades</th><th>Estrutura</th><th>ARIA</th>
          <th>LS Crítico</th><th>LS Médio</th>
        </tr>
      </thead>
      <tbody>${tableRows}</tbody>
    </table>
  </div>

  <div class="chart-grid" style="margin-top:1.5rem">
    <div class="chart-card">
      <h3>AIM Score</h3>
      <div class="chart-wrap" style="height:240px"><canvas id="${chartId}_aim"></canvas></div>
    </div>
    <div class="chart-card">
      <h3>Problemas</h3>
      <div class="chart-wrap" style="height:240px"><canvas id="${chartId}_issues"></canvas></div>
    </div>
    <div class="chart-card">
      <h3>Boas práticas</h3>
      <p class="chart-desc">Funcionalidades, Estrutura e ARIA são indicadores positivos.</p>
      <div class="chart-wrap" style="height:240px"><canvas id="${chartId}_positive"></canvas></div>
    </div>
    <div class="chart-card">
      <h3>Dimensões POUR</h3>
      <div class="chart-wrap" style="height:240px"><canvas id="${chartId}_pour"></canvas></div>
    </div>
    <div class="chart-card">
      <h3>Impacto no leitor de tela</h3>
      <div class="chart-wrap" style="height:240px"><canvas id="${chartId}_sr"></canvas></div>
    </div>
    ${flowIssues.length ? `
    <div class="chart-card">
      <h3>Principais problemas neste fluxo</h3>
      <div class="chart-wrap" style="height:240px"><canvas id="${chartId}_top"></canvas></div>
    </div>` : ''}
  </div>

  <h3 style="margin-top:2rem">Perspectiva do leitor de tela — página a página</h3>
  <p>Problemas com impacto crítico ou alto para usuários de leitores de tela.</p>
  <div class="page-cards">
    ${srNarrative(pages, name)}
  </div>
</div>
<script>
(function() {
  const labels = ${JSON.stringify(pageLabels)};
  const opts = (extra={}) => ({ responsive:true, maintainAspectRatio:false, ...extra });

  new Chart(document.getElementById('${chartId}_aim'), {
    type: 'bar',
    data: { labels, datasets: [{ label:'AIM', data:${JSON.stringify(aimScores)}, backgroundColor:${JSON.stringify(aimColors)}, borderRadius:4 }] },
    options: opts({ plugins:{legend:{display:false}}, scales:{ y:{min:0,max:10} } })
  });

  new Chart(document.getElementById('${chartId}_issues'), {
    type: 'bar',
    data: { labels, datasets: [
      { label:'Erros', data:${JSON.stringify(errD)}, backgroundColor:'#ef4444' },
      { label:'Contraste', data:${JSON.stringify(contD)}, backgroundColor:'#f97316' },
      { label:'Alertas', data:${JSON.stringify(alrtD)}, backgroundColor:'#eab308' },
    ]},
    options: opts({ scales:{ x:{stacked:true}, y:{stacked:true} } })
  });

  new Chart(document.getElementById('${chartId}_positive'), {
    type: 'bar',
    data: { labels, datasets: [
      { label:'Funcionalidades', data:${JSON.stringify(featD)}, backgroundColor:'#22c55e' },
      { label:'Estrutura', data:${JSON.stringify(strD)}, backgroundColor:'#3b82f6' },
      { label:'ARIA', data:${JSON.stringify(ariaD)}, backgroundColor:'#8b5cf6' },
    ]},
    options: opts({ scales:{ x:{stacked:true}, y:{stacked:true} } })
  });

  new Chart(document.getElementById('${chartId}_pour'), {
    type: 'bar',
    data: { labels, datasets: [
      { label:'Perceptível',    data:${JSON.stringify(pourP)}, backgroundColor:'#3b82f6' },
      { label:'Operável',       data:${JSON.stringify(pourO)}, backgroundColor:'#8b5cf6' },
      { label:'Compreensível',  data:${JSON.stringify(pourU)}, backgroundColor:'#ec4899' },
      { label:'Robusto',        data:${JSON.stringify(pourR)}, backgroundColor:'#14b8a6' },
    ]},
    options: opts({ scales:{ x:{stacked:true}, y:{stacked:true} } })
  });

  new Chart(document.getElementById('${chartId}_sr'), {
    type: 'bar',
    data: { labels, datasets: [
      { label:'Crítico', data:${JSON.stringify(srCr)}, backgroundColor:'#dc2626' },
      { label:'Alto',    data:${JSON.stringify(srHi)}, backgroundColor:'#ea580c' },
      { label:'Médio',   data:${JSON.stringify(srMd)}, backgroundColor:'#ca8a04' },
      { label:'Baixo',   data:${JSON.stringify(srLo)}, backgroundColor:'#16a34a' },
    ]},
    options: opts({ scales:{ x:{stacked:true}, y:{stacked:true} } })
  });

  ${flowIssues.length ? `
  new Chart(document.getElementById('${chartId}_top'), {
    type: 'bar',
    data: {
      labels: ${JSON.stringify(flowIssues.map(i => i.type_label))},
      datasets: [{ label:'Ocorrências', data:${JSON.stringify(flowIssues.map(i => i.total_count))},
        backgroundColor: ${JSON.stringify(flowIssues.map(i => ({error:'#ef4444',contrast:'#f97316',alert:'#eab308'}[i.category]||'#94a3b8')))}, borderRadius:4 }]
    },
    options: { ...opts(), indexAxis:'y', plugins:{legend:{display:false}} }
  });` : ''}
})();
</script>`;
}

// ─── Main HTML builder ────────────────────────────────────────────────────────

function buildHtml(flows) {
  const stats = globalStats(flows);
  const navItems = flows.map((f, i) =>
    `<button class="nav-btn" onclick="showSection('flow${i}')">${f.name.replace(/([A-Z])/g, ' $1').trim()}</button>`
  ).join('\n');

  return `<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Relatório de Acessibilidade WAVE</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"><\/script>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, -apple-system, sans-serif; background: #f8fafc; color: #1e293b; line-height: 1.5; }
    a { color: #3b82f6; }

    /* Layout */
    .app-header { background: #1e293b; color: #f8fafc; padding: 1.25rem 2rem; }
    .app-header h1 { font-size: 1.5rem; font-weight: 700; }
    .app-header p { color: #94a3b8; font-size: 0.875rem; margin-top: 0.25rem; }
    .nav-bar { background: #fff; border-bottom: 1px solid #e2e8f0; padding: 0.75rem 2rem; display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; position: sticky; top: 0; z-index: 10; }
    .nav-btn { padding: 0.375rem 0.875rem; border-radius: 0.375rem; border: 1px solid #e2e8f0; background: transparent; cursor: pointer; font-size: 0.875rem; color: #475569; transition: all 0.15s; white-space: nowrap; }
    .nav-btn:hover, .nav-btn.active { background: #3b82f6; color: #fff; border-color: #3b82f6; }
    .nav-divider { width: 1px; height: 24px; background: #e2e8f0; margin: 0 0.25rem; }
    .main { max-width: 1400px; margin: 0 auto; padding: 2rem; }
    .section { display: none; }
    .section.active { display: block; }
    .section h2 { font-size: 1.5rem; font-weight: 700; margin-bottom: 1rem; color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 0.5rem; }
    .section h3 { font-size: 1.125rem; font-weight: 600; margin: 1.5rem 0 0.75rem; color: #1e293b; }

    /* KPI */
    .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
    .kpi-card { background: #fff; border-radius: 0.75rem; padding: 1.25rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
    .kpi-icon { font-size: 1.5rem; margin-bottom: 0.5rem; }
    .kpi-value { font-size: 2rem; font-weight: 800; line-height: 1; }
    .kpi-label { font-size: 0.8rem; color: #64748b; margin-top: 0.25rem; }

    /* Charts */
    .chart-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 1rem; }
    .chart-card { background: #fff; border-radius: 0.75rem; padding: 1.25rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
    .chart-card.chart-wide { grid-column: 1 / -1; }
    .chart-card h3 { font-size: 1rem; font-weight: 600; margin: 0 0 0.25rem; }
    .chart-desc { font-size: 0.8rem; color: #64748b; margin-bottom: 0.75rem; }
    .chart-wrap { position: relative; }

    /* Tables */
    .table-wrap { overflow-x: auto; border-radius: 0.75rem; border: 1px solid #e2e8f0; }
    .data-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; background: #fff; }
    .data-table th { background: #f1f5f9; padding: 0.625rem 0.875rem; text-align: left; font-weight: 600; color: #475569; font-size: 0.8rem; white-space: nowrap; border-bottom: 1px solid #e2e8f0; }
    .data-table td { padding: 0.5rem 0.875rem; border-bottom: 1px solid #f1f5f9; vertical-align: middle; }
    .data-table tr:last-child td { border-bottom: none; }
    .data-table tr:hover td { background: #f8fafc; }
    .data-table.compact td { padding: 0.375rem 0.75rem; }
    .num { text-align: right; font-variant-numeric: tabular-nums; }

    /* Badges */
    .badge { display: inline-block; padding: 0.125rem 0.5rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; white-space: nowrap; }

    /* Page cards (SR narrative) */
    .page-cards { display: flex; flex-direction: column; gap: 1rem; margin-top: 1rem; }
    .page-card { background: #fff; border-radius: 0.75rem; padding: 1.25rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08); border: 1px solid #e2e8f0; }
    .page-card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.75rem; }
    .page-card h4 { font-size: 1.05rem; font-weight: 700; text-transform: capitalize; }
    .aim-badge { display: flex; flex-direction: column; align-items: center; padding: 0.5rem 0.875rem; border-radius: 0.5rem; min-width: 80px; text-align: center; }
    .aim-badge span:first-child { font-size: 1.5rem; line-height: 1; }
    .sr-summary-row { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.5rem; }
    .sr-chip { padding: 0.25rem 0.625rem; border-radius: 0.375rem; font-size: 0.8rem; font-weight: 600; }
    .sr-critical { background: #fee2e2; color: #991b1b; }
    .sr-high     { background: #ffedd5; color: #9a3412; }
    .sr-medium   { background: #fef9c3; color: #854d0e; }
    .sr-low      { background: #dcfce7; color: #166534; }
    .muted { color: #94a3b8; }

    @media (max-width: 640px) {
      .chart-grid { grid-template-columns: 1fr; }
      .main { padding: 1rem; }
      .kpi-grid { grid-template-columns: 1fr 1fr; }
    }
  </style>
</head>
<body>

<header class="app-header">
  <h1>Relatório de Acessibilidade WAVE</h1>
  <p>Análise de acessibilidade web — perspectiva de usuários de leitores de tela</p>
</header>

<nav class="nav-bar">
  <button class="nav-btn active" onclick="showSection('overview')">Visão geral</button>
  <div class="nav-divider"></div>
  ${navItems}
  <div class="nav-divider"></div>
  <button class="nav-btn" onclick="showSection('issues')">Principais problemas</button>
</nav>

<main class="main">

  <!-- Overview -->
  <div id="overview" class="section active">
    <h2>Visão geral</h2>
    ${kpiCards(stats)}
    ${overviewCharts(flows)}
  </div>

  <!-- Per-flow sections -->
  ${flows.map((f, i) => `
  <div id="flow${i}" class="section">
    ${flowSection(f, i)}
  </div>`).join('\n')}

  <!-- Top issues -->
  <div id="issues" class="section">
    ${topIssuesSection(flows)}
  </div>

</main>

<script>
function showSection(id) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  event.target.classList.add('active');
  window.scrollTo(0, 0);
}
<\/script>
</body>
</html>`;
}

// ─── Entry point ──────────────────────────────────────────────────────────────

const flows = loadFlows();
if (flows.length === 0) {
  console.error('Nenhum wave-report.json encontrado em', OUTPUT_DIR);
  process.exit(1);
}

console.log(`Carregando ${flows.length} fluxo(s)...`);
flows.forEach(f => console.log(`  • ${f.name}: ${f.pages.length} página(s)`));

const html = buildHtml(flows);
fs.writeFileSync(REPORT_PATH, html, 'utf8');
console.log(`\nRelatório gerado em: ${REPORT_PATH}`);
