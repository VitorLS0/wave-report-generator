#!/usr/bin/env node
/**
 * WAVE Report Parser
 * Extracts accessibility data from WAVE HTML sidebar reports.
 * Usage: node wave-parser.js <file1.html> [file2.html ...]
 * Outputs: <name>.json, wave-summary.csv, wave-details.csv
 */

const fs = require('fs');
const path = require('path');

// ─── WCAG / POUR / Screen-reader metadata ──────────────────────────────────────
//
// sr_relevance values for issue types (errors / alerts):
//   critical     — directly blocks screen reader access
//   high         — significantly impacts screen reader experience
//   medium       — impacts experience; workarounds may exist
//   low          — minor impact (e.g. mainly relevant to sighted/low-vision users)
// sr_relevance values for feature / structure / ARIA types:
//   positive     — accessibility feature that benefits screen reader users
//   informational — neutral element; presence is noted but not inherently good/bad

const WAVE_TYPE_MAP = {
  // ── Errors ──────────────────────────────────────────────────────────────────
  alt_missing:           { wcag: ['1.1.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'critical'      },
  alt_link_missing:      { wcag: ['1.1.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'critical'      },
  alt_spacer:            { wcag: ['1.1.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'medium'        },
  alt_input:             { wcag: ['1.1.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'critical'      },
  alt_map_missing:       { wcag: ['1.1.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'critical'      },
  label_missing:         { wcag: ['1.3.1', '3.3.2'],      level: 'A',   pour: ['Perceivable', 'Understandable'],   sr: 'critical'      },
  label_empty:           { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'high'          },
  label_multiple:        { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'high'          },
  th_empty:              { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'high'          },
  th_mergedcell:         { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'medium'        },
  caption_missing:       { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'medium'        },
  empty_button:          { wcag: ['4.1.2'],               level: 'A',   pour: ['Robust'],                          sr: 'critical'      },
  empty_link:            { wcag: ['2.4.4'],               level: 'A',   pour: ['Operable'],                        sr: 'critical'      },
  empty_heading:         { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'high'          },
  error_zoom:            { wcag: ['1.4.4'],               level: 'AA',  pour: ['Perceivable'],                     sr: 'low'           },
  language_missing:      { wcag: ['3.1.1'],               level: 'A',   pour: ['Understandable'],                  sr: 'high'          },
  select_missing_label:  { wcag: ['1.3.1', '3.3.2'],      level: 'A',   pour: ['Perceivable', 'Understandable'],   sr: 'critical'      },
  blink:                 { wcag: ['2.2.2'],               level: 'A',   pour: ['Operable'],                        sr: 'low'           },
  marquee:               { wcag: ['2.2.2'],               level: 'A',   pour: ['Operable'],                        sr: 'low'           },
  link_internal_broken:  { wcag: ['2.4.4'],               level: 'A',   pour: ['Operable'],                        sr: 'medium'        },
  audio_video:           { wcag: ['1.2.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'medium'        },
  event_handler:         { wcag: ['2.1.1'],               level: 'A',   pour: ['Operable'],                        sr: 'high'          },
  aria_reference_broken: { wcag: ['4.1.2'],               level: 'A',   pour: ['Robust'],                          sr: 'critical'      },
  aria_label_broken:     { wcag: ['4.1.2'],               level: 'A',   pour: ['Robust'],                          sr: 'critical'      },
  aria_menu_broken:      { wcag: ['4.1.2'],               level: 'A',   pour: ['Robust'],                          sr: 'high'          },
  // ── Contrast Errors ─────────────────────────────────────────────────────────
  contrast:              { wcag: ['1.4.3'],               level: 'AA',  pour: ['Perceivable'],                     sr: 'low'           },
  // ── Alerts ──────────────────────────────────────────────────────────────────
  alt_suspicious:        { wcag: ['1.1.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'high'          },
  alt_redundant:         { wcag: ['1.1.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'medium'        },
  alt_long:              { wcag: ['1.1.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'medium'        },
  label_orphaned:        { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'medium'        },
  link_suspicious:       { wcag: ['2.4.4'],               level: 'A',   pour: ['Operable'],                        sr: 'high'          },
  link_redundant:        { wcag: ['2.4.4'],               level: 'A',   pour: ['Operable'],                        sr: 'medium'        },
  link_pdf:              { wcag: ['2.4.4'],               level: 'A',   pour: ['Operable', 'Understandable'],      sr: 'medium'        },
  link_document:         { wcag: ['2.4.4'],               level: 'A',   pour: ['Operable', 'Understandable'],      sr: 'medium'        },
  link_excel:            { wcag: ['2.4.4'],               level: 'A',   pour: ['Operable', 'Understandable'],      sr: 'medium'        },
  link_word:             { wcag: ['2.4.4'],               level: 'A',   pour: ['Operable', 'Understandable'],      sr: 'medium'        },
  link_powerpoint:       { wcag: ['2.4.4'],               level: 'A',   pour: ['Operable', 'Understandable'],      sr: 'medium'        },
  table_layout:          { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'medium'        },
  table_missing_headers: { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'high'          },
  region_missing:        { wcag: ['1.3.1', '2.4.1'],      level: 'A',   pour: ['Perceivable', 'Operable'],         sr: 'critical'      },
  heading_missing:       { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'critical'      },
  heading_skipped:       { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'high'          },
  fieldset_missing:      { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'high'          },
  tabindex:              { wcag: ['2.4.3'],               level: 'A',   pour: ['Operable'],                        sr: 'high'          },
  accesskey:             { wcag: ['2.1.4'],               level: 'A',   pour: ['Operable'],                        sr: 'medium'        },
  title_invalid:         { wcag: ['2.4.2'],               level: 'A',   pour: ['Operable'],                        sr: 'high'          },
  language_possible:     { wcag: ['3.1.1', '3.1.2'],      level: 'A',   pour: ['Understandable'],                  sr: 'high'          },
  noscript:              { wcag: ['4.1.2'],               level: 'A',   pour: ['Robust'],                          sr: 'medium'        },
  youtube_video:         { wcag: ['1.2.2'],               level: 'A',   pour: ['Perceivable'],                     sr: 'medium'        },
  audio_video_found:     { wcag: ['1.2.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'medium'        },
  html5_video_audio:     { wcag: ['1.2.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'medium'        },
  video_found:           { wcag: ['1.2.1', '1.2.2'],      level: 'A',   pour: ['Perceivable'],                     sr: 'medium'        },
  animation_possible:    { wcag: ['2.2.2'],               level: 'A',   pour: ['Operable'],                        sr: 'medium'        },
  text_justified:        { wcag: ['1.4.8'],               level: 'AAA', pour: ['Perceivable'],                     sr: 'low'           },
  content_editable:      { wcag: ['4.1.2'],               level: 'A',   pour: ['Robust'],                          sr: 'high'          },
  meta_refresh:          { wcag: ['2.2.1', '2.2.2'],      level: 'A',   pour: ['Operable'],                        sr: 'high'          },
  object_includes:       { wcag: ['4.1.2'],               level: 'A',   pour: ['Robust'],                          sr: 'medium'        },
  script_onclick:        { wcag: ['2.1.1'],               level: 'A',   pour: ['Operable'],                        sr: 'high'          },
  // ── Features ────────────────────────────────────────────────────────────────
  alt:                   { wcag: ['1.1.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'positive'      },
  alt_link:              { wcag: ['1.1.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'positive'      },
  alt_map:               { wcag: ['1.1.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'positive'      },
  label:                 { wcag: ['1.3.1', '3.3.2'],      level: 'A',   pour: ['Perceivable', 'Understandable'],   sr: 'positive'      },
  fieldset:              { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'positive'      },
  link_skip:             { wcag: ['2.4.1'],               level: 'A',   pour: ['Operable'],                        sr: 'positive'      },
  link_skip_target:      { wcag: ['2.4.1'],               level: 'A',   pour: ['Operable'],                        sr: 'positive'      },
  lang:                  { wcag: ['3.1.1'],               level: 'A',   pour: ['Understandable'],                  sr: 'positive'      },
  title:                 { wcag: ['2.4.2'],               level: 'A',   pour: ['Operable'],                        sr: 'positive'      },
  caption:               { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'positive'      },
  // ── Structure ───────────────────────────────────────────────────────────────
  h1:                    { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'positive'      },
  h2:                    { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'positive'      },
  h3:                    { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'positive'      },
  h4:                    { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'positive'      },
  h5:                    { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'positive'      },
  h6:                    { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'positive'      },
  ul:                    { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'positive'      },
  ol:                    { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'positive'      },
  dl:                    { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'positive'      },
  table:                 { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'informational' },
  header:                { wcag: ['1.3.1', '2.4.1'],      level: 'A',   pour: ['Perceivable', 'Operable'],         sr: 'positive'      },
  nav:                   { wcag: ['1.3.1', '2.4.1'],      level: 'A',   pour: ['Perceivable', 'Operable'],         sr: 'positive'      },
  main:                  { wcag: ['1.3.1', '2.4.1'],      level: 'A',   pour: ['Perceivable', 'Operable'],         sr: 'positive'      },
  footer:                { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'positive'      },
  aside:                 { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'positive'      },
  section:               { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'informational' },
  article:               { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'informational' },
  figure:                { wcag: ['1.1.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'informational' },
  iframe:                { wcag: ['4.1.2'],               level: 'A',   pour: ['Robust'],                          sr: 'informational' },
  search:                { wcag: ['2.4.1'],               level: 'A',   pour: ['Operable'],                        sr: 'positive'      },
  form:                  { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable'],                     sr: 'informational' },
  button:                { wcag: ['4.1.2'],               level: 'A',   pour: ['Robust', 'Operable'],              sr: 'informational' },
  // ── ARIA ────────────────────────────────────────────────────────────────────
  aria:                  { wcag: ['4.1.2'],               level: 'A',   pour: ['Robust'],                          sr: 'informational' },
  aria_label:            { wcag: ['1.3.1', '4.1.2'],      level: 'A',   pour: ['Perceivable', 'Robust'],           sr: 'positive'      },
  aria_labelledby:       { wcag: ['1.3.1', '4.1.2'],      level: 'A',   pour: ['Perceivable', 'Robust'],           sr: 'positive'      },
  aria_describedby:      { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable', 'Robust'],           sr: 'positive'      },
  aria_role:             { wcag: ['4.1.2'],               level: 'A',   pour: ['Robust'],                          sr: 'informational' },
  aria_hidden:           { wcag: ['1.3.1'],               level: 'A',   pour: ['Perceivable', 'Robust'],           sr: 'informational' },
  aria_required:         { wcag: ['3.3.1', '4.1.2'],      level: 'A',   pour: ['Understandable', 'Robust'],        sr: 'informational' },
  aria_live_region:      { wcag: ['4.1.3'],               level: 'A',   pour: ['Robust'],                          sr: 'informational' },
  aria_expanded:         { wcag: ['4.1.2'],               level: 'A',   pour: ['Robust'],                          sr: 'informational' },
  aria_tabindex:         { wcag: ['2.4.3'],               level: 'A',   pour: ['Operable'],                        sr: 'informational' },
  aria_button:           { wcag: ['4.1.2'],               level: 'A',   pour: ['Robust', 'Operable'],              sr: 'informational' },
  aria_menu:             { wcag: ['4.1.2'],               level: 'A',   pour: ['Robust', 'Operable'],              sr: 'informational' },
  aria_dialog:           { wcag: ['4.1.2'],               level: 'A',   pour: ['Robust', 'Operable'],              sr: 'informational' },
};

function getTypeMeta(typeId) {
  const meta = WAVE_TYPE_MAP[typeId];
  if (!meta) return { wcag_criteria: null, wcag_level: null, pour_dimensions: null, sr_relevance: null };
  return {
    wcag_criteria:  meta.wcag,
    wcag_level:     meta.level,
    pour_dimensions: meta.pour,
    sr_relevance:   meta.sr,
  };
}

// ─── HTML helpers ──────────────────────────────────────────────────────────────

function decodeEntities(str) {
  return str
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&#39;/g, "'");
}

function extractCount(html, liId) {
  const re = new RegExp(`<li id="${liId}">[^<]*<img[^>]*>[^<]*<span>(\\d+)<\\/span>`);
  const m = html.match(re);
  return m ? parseInt(m[1], 10) : 0;
}

/** Extract the content of <div id="iconlist"> without a full HTML parser. */
function extractIconlistContent(html) {
  const startTag = '<div id="iconlist"';
  const startIdx = html.indexOf(startTag);
  if (startIdx === -1) return '';

  // Skip past the opening tag's closing >
  const tagEnd = html.indexOf('>', startIdx);
  if (tagEnd === -1) return '';

  // The iconlist div has no child <div> elements — its direct children are <li> elements.
  // So the very first </div> after tagEnd is the closing of iconlist.
  const closeIdx = html.indexOf('</div>', tagEnd + 1);
  if (closeIdx === -1) return '';

  return html.substring(tagEnd + 1, closeIdx);
}

// ─── Instance parser ───────────────────────────────────────────────────────────

function parseInstances(ulContent) {
  const instances = [];
  // Match every <li><img ...> in the ul
  const liRegex = /<li><img([^>]*)>/g;
  let liMatch;
  let index = 1;

  while ((liMatch = liRegex.exec(ulContent)) !== null) {
    const attrs = liMatch[1];

    // Extract alt attribute value
    const altMatch = attrs.match(/alt="([^"]*)"/);
    const rawAlt = altMatch ? decodeEntities(altMatch[1]) : '';

    // Determine if hidden
    const classMatch = attrs.match(/class="([^"]*)"/);
    const hidden = classMatch ? classMatch[1].includes('wave5_hiddenicon') : false;

    // Clean description: remove the trailing " (This icon...)" note
    const description = rawAlt.replace(/\s*\(This icon[^)]+\)\s*$/, '').trim();

    // Extract label (description without trailing instance number)
    const label = description.replace(/\s+\d+$/, '').trim();

    instances.push({ index, hidden, description, label });
    index++;
  }

  return instances;
}

// ─── Type parser ───────────────────────────────────────────────────────────────

function parseTypes(groupContent) {
  const types = [];
  // Split on icon_type list items
  const parts = groupContent.split('<li class="icon_type">');

  for (let i = 1; i < parts.length; i++) {
    const part = parts[i];

    // Type id from input
    const inputIdMatch = part.match(/id="toggle_type_(\w+)"/);
    const typeId = inputIdMatch ? inputIdMatch[1] : 'unknown';

    // Type label from label element (strip leading count)
    const labelMatch = part.match(/<label for="toggle_type_[^"]*">([^<]+)<\/label>/);
    const labelText = labelMatch ? labelMatch[1].trim() : '';
    const countLabelMatch = labelText.match(/^(\d+)\s+(.+)$/);
    const count = countLabelMatch ? parseInt(countLabelMatch[1], 10) : 0;
    const typeLabel = countLabelMatch ? countLabelMatch[2].trim() : labelText;

    // Instance ul content
    const ulRe = new RegExp(`<ul id="type_list_${typeId}">([\\.\\s\\S]*?)<\\/ul>`);
    const ulMatch = part.match(ulRe);
    const instances = ulMatch ? parseInstances(ulMatch[1]) : [];

    const meta = getTypeMeta(typeId);
    types.push({ type_id: typeId, type_label: typeLabel, count, ...meta, instances });
  }

  return types;
}

// ─── Group parser ──────────────────────────────────────────────────────────────

function parseGroups(iconlistContent) {
  const groups = [];
  const parts = iconlistContent.split('<li class="icon_group">');

  for (let i = 1; i < parts.length; i++) {
    const part = parts[i];

    // Category id from h3
    const h3Match = part.match(/<h3 id="group_(\w+)">/);
    const categoryId = h3Match ? h3Match[1] : 'unknown';

    // Category label from the group's label element (after img)
    const labelMatch = part.match(/<label for="toggle_group_\w+"><img[^>]*>([^<]+)<\/label>/);
    const labelText = labelMatch ? labelMatch[1].trim() : '';
    const countLabelMatch = labelText.match(/^(\d+)\s+(.+)$/);
    const total = countLabelMatch ? parseInt(countLabelMatch[1], 10) : 0;
    const categoryLabel = countLabelMatch ? countLabelMatch[2].trim() : labelText;

    const types = parseTypes(part);

    groups.push({ category: categoryId, category_label: categoryLabel, total, types });
  }

  return groups;
}

// ─── POUR / SR breakdown ───────────────────────────────────────────────────────

// Counts issue instances (errors + contrast + alerts) by POUR dimension and SR relevance.
// Features, structure, and ARIA categories are excluded — they represent presence of
// accessibility techniques, not barriers.
function computePourSummary(categories) {
  const ISSUE_CATEGORIES = new Set(['error', 'contrast', 'alert']);
  const pour = { perceivable: 0, operable: 0, understandable: 0, robust: 0 };
  const sr   = { critical: 0, high: 0, medium: 0, low: 0 };

  for (const cat of categories) {
    if (!ISSUE_CATEGORIES.has(cat.category)) continue;
    for (const type of cat.types) {
      const count = type.count || 0;
      if (type.pour_dimensions) {
        for (const dim of type.pour_dimensions) {
          const key = dim.toLowerCase();
          if (key in pour) pour[key] += count;
        }
      }
      if (type.sr_relevance && type.sr_relevance in sr) {
        sr[type.sr_relevance] += count;
      }
    }
  }

  return { pour_breakdown: pour, sr_relevance_breakdown: sr };
}

// ─── Main report parser ────────────────────────────────────────────────────────

function parseWaveReport(filePath) {
  const html = fs.readFileSync(filePath, 'utf8');
  const sourceFile = path.basename(filePath);

  // Summary counts
  const summary = {
    errors: extractCount(html, 'error'),
    contrast_errors: extractCount(html, 'contrastnum'),
    alerts: extractCount(html, 'alert'),
    features: extractCount(html, 'feature'),
    structure: extractCount(html, 'structure'),
    aria: extractCount(html, 'aria'),
  };

  // AIM score
  const aimMatch = html.match(/<span id="aim-score-value">([0-9.]+)<\/span>/);
  summary.aim_score = aimMatch ? parseFloat(aimMatch[1]) : null;

  // Detailed categories
  const iconlistContent = extractIconlistContent(html);
  const categories = parseGroups(iconlistContent);

  const { pour_breakdown, sr_relevance_breakdown } = computePourSummary(categories);
  summary.pour_breakdown = pour_breakdown;
  summary.sr_relevance_breakdown = sr_relevance_breakdown;

  return { source_file: sourceFile, summary, categories };
}

// ─── CSV helpers ───────────────────────────────────────────────────────────────

function csvEscape(value) {
  const str = String(value ?? '');
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return '"' + str.replace(/"/g, '""') + '"';
  }
  return str;
}

function toCSVRow(values) {
  return values.map(csvEscape).join(',');
}

// ─── Output writers ────────────────────────────────────────────────────────────

function writeSummaryCSV(reports, outDir) {
  const headers = [
    'source_file',
    'errors',
    'contrast_errors',
    'alerts',
    'features',
    'structure',
    'aria',
    'aim_score',
    'pour_perceivable',
    'pour_operable',
    'pour_understandable',
    'pour_robust',
    'sr_critical',
    'sr_high',
    'sr_medium',
    'sr_low',
  ];
  const rows = [headers.join(',')];
  for (const report of reports) {
    const p = report.summary.pour_breakdown;
    const sr = report.summary.sr_relevance_breakdown;
    rows.push(toCSVRow([
      report.source_file,
      report.summary.errors,
      report.summary.contrast_errors,
      report.summary.alerts,
      report.summary.features,
      report.summary.structure,
      report.summary.aria,
      report.summary.aim_score ?? '',
      p.perceivable,
      p.operable,
      p.understandable,
      p.robust,
      sr.critical,
      sr.high,
      sr.medium,
      sr.low,
    ]));
  }
  const outPath = path.join(outDir, 'wave-summary.csv');
  fs.writeFileSync(outPath, rows.join('\n'), 'utf8');
  console.log(`  Wrote:   ${path.relative(path.join(__dirname, '..'), outPath)}`);
}

function writeDetailsCSV(reports, outDir) {
  const headers = [
    'source_file',
    'category',
    'category_label',
    'type_id',
    'type_label',
    'type_count',
    'wcag_criteria',
    'wcag_level',
    'pour_dimensions',
    'sr_relevance',
    'instance_index',
    'hidden',
    'description',
    'label',
  ];
  const rows = [headers.join(',')];
  for (const report of reports) {
    for (const cat of report.categories) {
      for (const type of cat.types) {
        const wcag  = type.wcag_criteria  ? type.wcag_criteria.join(';')  : '';
        const pour  = type.pour_dimensions ? type.pour_dimensions.join(';') : '';
        const level = type.wcag_level      ?? '';
        const sr    = type.sr_relevance    ?? '';

        if (type.instances.length === 0) {
          // Record the type even if instances list is empty (shouldn't happen, but defensive)
          rows.push(toCSVRow([
            report.source_file,
            cat.category,
            cat.category_label,
            type.type_id,
            type.type_label,
            type.count,
            wcag,
            level,
            pour,
            sr,
            '',
            '',
            '',
            '',
          ]));
        } else {
          for (const inst of type.instances) {
            rows.push(toCSVRow([
              report.source_file,
              cat.category,
              cat.category_label,
              type.type_id,
              type.type_label,
              type.count,
              wcag,
              level,
              pour,
              sr,
              inst.index,
              inst.hidden,
              inst.description,
              inst.label,
            ]));
          }
        }
      }
    }
  }
  const outPath = path.join(outDir, 'wave-details.csv');
  fs.writeFileSync(outPath, rows.join('\n'), 'utf8');
  console.log(`  Wrote:   ${path.relative(path.join(__dirname, '..'), outPath)}`);
}

// ─── Entry point ───────────────────────────────────────────────────────────────

const ROOT = path.join(__dirname, '..');
const INPUT_DIR = path.join(ROOT, 'input');
const OUTPUT_DIR = path.join(ROOT, 'output');

function scanHtmlFiles(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...scanHtmlFiles(full));
    } else if (entry.isFile() && entry.name.toLowerCase().endsWith('.html')) {
      files.push(full);
    }
  }
  return files;
}

const args = process.argv.slice(2);
let filePaths;

if (args.length === 0) {
  filePaths = scanHtmlFiles(INPUT_DIR);
  if (filePaths.length === 0) {
    console.error(`No HTML files found in ${INPUT_DIR}`);
    process.exit(1);
  }
} else {
  filePaths = args.map(f => path.resolve(f));
}

// Group files by their output directory, mirroring the input folder structure
const groups = new Map(); // outDir → [absPath, ...]
for (const absPath of filePaths) {
  let outDir;
  const fileDir = path.dirname(absPath);
  if (fileDir === INPUT_DIR || (fileDir + path.sep).startsWith(INPUT_DIR + path.sep)) {
    const rel = path.relative(INPUT_DIR, fileDir);
    outDir = rel ? path.join(OUTPUT_DIR, rel) : OUTPUT_DIR;
  } else {
    outDir = OUTPUT_DIR;
  }
  if (!groups.has(outDir)) groups.set(outDir, []);
  groups.get(outDir).push(absPath);
}

for (const [outDir, groupFiles] of groups) {
  fs.mkdirSync(outDir, { recursive: true });

  const groupLabel = path.relative(OUTPUT_DIR, outDir) || '(root)';
  console.log(`\nFolder: ${groupLabel}`);

  const groupReports = [];

  for (const absPath of groupFiles) {
    if (!fs.existsSync(absPath)) {
      console.error(`File not found: ${absPath}`);
      process.exit(1);
    }

    console.log(`  Parsing: ${path.relative(INPUT_DIR, absPath)}`);
    const report = parseWaveReport(absPath);
    groupReports.push(report);

    const jsonName = path.basename(absPath).replace(/\.html$/i, '.json');
    const jsonOut = path.join(outDir, jsonName);
    fs.writeFileSync(jsonOut, JSON.stringify(report, null, 2), 'utf8');
    console.log(`  Wrote:   ${path.relative(ROOT, jsonOut)}`);
  }

  const combinedJsonPath = path.join(outDir, 'wave-report.json');
  fs.writeFileSync(combinedJsonPath, JSON.stringify(groupReports, null, 2), 'utf8');
  console.log(`  Wrote:   ${path.relative(ROOT, combinedJsonPath)}`);

  writeSummaryCSV(groupReports, outDir);
  writeDetailsCSV(groupReports, outDir);
}

console.log('\nDone.');
