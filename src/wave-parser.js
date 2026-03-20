#!/usr/bin/env node
/**
 * WAVE Report Parser
 * Extracts accessibility data from WAVE HTML sidebar reports.
 * Usage: node wave-parser.js <file1.html> [file2.html ...]
 * Outputs: <name>.json, wave-summary.csv, wave-details.csv
 */

const fs = require('fs');
const path = require('path');

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

    types.push({ type_id: typeId, type_label: typeLabel, count, instances });
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
  ];
  const rows = [headers.join(',')];
  for (const report of reports) {
    rows.push(toCSVRow([
      report.source_file,
      report.summary.errors,
      report.summary.contrast_errors,
      report.summary.alerts,
      report.summary.features,
      report.summary.structure,
      report.summary.aria,
      report.summary.aim_score ?? '',
    ]));
  }
  const outPath = path.join(outDir, 'wave-summary.csv');
  fs.writeFileSync(outPath, rows.join('\n'), 'utf8');
  console.log(`Wrote: ${outPath}`);
}

function writeDetailsCSV(reports, outDir) {
  const headers = [
    'source_file',
    'category',
    'category_label',
    'type_id',
    'type_label',
    'type_count',
    'instance_index',
    'hidden',
    'description',
    'label',
  ];
  const rows = [headers.join(',')];
  for (const report of reports) {
    for (const cat of report.categories) {
      for (const type of cat.types) {
        if (type.instances.length === 0) {
          // Record the type even if instances list is empty (shouldn't happen, but defensive)
          rows.push(toCSVRow([
            report.source_file,
            cat.category,
            cat.category_label,
            type.type_id,
            type.type_label,
            type.count,
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
  console.log(`Wrote: ${outPath}`);
}

// ─── Entry point ───────────────────────────────────────────────────────────────

const ROOT = path.join(__dirname, '..');
const INPUT_DIR = path.join(ROOT, 'input');
const OUTPUT_DIR = path.join(ROOT, 'output');

const args = process.argv.slice(2);
let filePaths;

if (args.length === 0) {
  // Auto-scan input/ directory
  filePaths = fs.readdirSync(INPUT_DIR)
    .filter(f => f.toLowerCase().endsWith('.html'))
    .map(f => path.join(INPUT_DIR, f));

  if (filePaths.length === 0) {
    console.error(`No HTML files found in ${INPUT_DIR}`);
    process.exit(1);
  }
} else {
  filePaths = args.map(f => path.resolve(f));
}

fs.mkdirSync(OUTPUT_DIR, { recursive: true });

const reports = [];

for (const absPath of filePaths) {
  if (!fs.existsSync(absPath)) {
    console.error(`File not found: ${absPath}`);
    process.exit(1);
  }

  console.log(`Parsing: ${absPath}`);
  const report = parseWaveReport(absPath);
  reports.push(report);

  // Write individual JSON to output/
  const jsonName = path.basename(absPath).replace(/\.html$/i, '.json');
  const jsonOut = path.join(OUTPUT_DIR, jsonName);
  fs.writeFileSync(jsonOut, JSON.stringify(report, null, 2), 'utf8');
  console.log(`Wrote:   ${jsonOut}`);
}

// Write combined JSON
const combinedJsonPath = path.join(OUTPUT_DIR, 'wave-report.json');
fs.writeFileSync(combinedJsonPath, JSON.stringify(reports, null, 2), 'utf8');
console.log(`Wrote: ${combinedJsonPath}`);

// Write CSVs
writeSummaryCSV(reports, OUTPUT_DIR);
writeDetailsCSV(reports, OUTPUT_DIR);

console.log('\nDone.');
