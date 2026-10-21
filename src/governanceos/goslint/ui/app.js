// goslint ui: the page talks only to goslint on this computer, at this page's own address. The register goes from
// this page to that process in memory and is read by the same code as `goslint lint`.
const MAX_SHOWN = 40
const TERMINAL = 'goslint lint REGISTER.xlsx --pack osfi-e23'
const REFUSED = { xls: 'an Excel 97-2003 workbook', xlsb: 'a binary Excel workbook', ods: 'an OpenDocument spreadsheet', numbers: 'a Numbers file' }
const OLE = [0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1] // encrypted workbooks and old .xls files start with these bytes
const VERB = { required: 'Required by', expected: 'Expected by', recommended: 'Recommended by' }
const $ = s => document.querySelector(s)

const ui = {
  status: $('#status'), file: $('#file'), drop: $('#drop'), choose: $('#choose'), sample: $('#sample'),
  fileError: $('#file-error'), stepFile: $('#step-file'), stepPacks: $('#step-packs'), stepResults: $('#step-results'),
  fileName: $('#file-name'), hint: $('#hint'), change: $('#change'), regions: $('#regions'), chosen: $('#chosen'),
  asOf: $('#asof'), asOfLabel: $('#asof-label'), run: $('#run'), runError: $('#run-error'), results: $('#results'),
}
let register = null
let catalog = null
let busy = false

function el (tag, attrs = {}, kids = []) {
  const n = document.createElement(tag)
  for (const [k, v] of Object.entries(attrs)) {
    if (v === false || v == null) continue
    if (k === 'text') n.textContent = v
    else if (k === 'onclick') n.addEventListener('click', v)
    else n.setAttribute(k, v === true ? '' : v)
  }
  for (const k of [].concat(kids)) if (k != null) n.append(k)
  return n
}
function say (msg, kind = '') { ui.status.textContent = msg; ui.status.dataset.kind = kind }
function plural (n, one, many) { return `${n} ${n === 1 ? one : many}` }
function today () {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function show (step) {
  ui.stepFile.hidden = step !== 'file'
  ui.stepPacks.hidden = step !== 'packs'
  ui.stepResults.hidden = step !== 'results'
}

// heartbeat: goslint stops a little after this page closes
const beat = () => fetch('beat', { method: 'POST' }).catch(() => say('goslint has stopped. Run goslint ui again to continue.', 'error'))
beat()
setInterval(beat, 5000)
addEventListener('pagehide', () => navigator.sendBeacon('bye'))

function basisLine (p) {
  const parts = [['required', p.counts.required], ['expected', p.counts.expected], ['recommended', p.counts.recommended]]
    .filter(([, n]) => n).map(([b, n]) => `${n} ${b}`)
  return `${p.id}, ${plural(p.fields, 'field', 'fields')}: ${parts.join(', ')}`
}

function renderPacks (cat) {
  ui.regions.replaceChildren()
  for (const region of cat.regions) {
    const packs = cat.packs.filter(p => p.region === region)
    if (!packs.length) continue
    const total = plural(packs.length, 'pack', 'packs')
    const count = el('span', { class: 'count', text: total })
    const details = el('details', { class: 'region' }, [
      el('summary', {}, [el('span', { text: region === 'GCC, six states' ? 'GCC' : region }), el('span', { class: 'who', text: cat.hints[region] || '' }), count]),
      el('ul', { class: 'packs' }, packs.map(p => el('li', {}, el('label', { class: 'pack' }, [
        el('input', { type: 'checkbox', name: 'pack', value: p.id }),
        el('span', { class: 'pack-text' }, [el('span', { class: 'pack-name', text: p.title.split(': ')[0] }), el('span', { class: 'pack-meta', text: basisLine(p) })]),
      ])))),
    ])
    details.addEventListener('change', () => {
      const n = details.querySelectorAll('input:checked').length
      count.textContent = n ? `${n} chosen` : total
      count.dataset.chosen = n ? 'yes' : ''
      updateRun()
    })
    ui.regions.append(details)
  }
}

function chosen () { return [...ui.regions.querySelectorAll('input[name="pack"]:checked')].map(i => i.value) }
function packName (id) { const p = catalog && catalog.packs.find(x => x.id === id); return p ? p.title.split(': ')[0] : id }

function updateRun () {
  const ids = chosen()
  ui.run.textContent = ids.length ? `Check my register against ${plural(ids.length, 'pack', 'packs')}` : 'Check my register'
  ui.chosen.textContent = ids.length ? `Chosen: ${ids.join(', ')}.` : ''
  if (ids.length) ui.runError.textContent = ''
}

function take (name, bytes, hint = '') {
  ui.fileError.textContent = ''
  const ext = (name.split('.').pop() || '').toLowerCase()
  if (REFUSED[ext]) { ui.fileError.textContent = `${name} is ${REFUSED[ext]}. Save it as .xlsx or .csv, then choose that copy.`; return }
  if (!['xlsx', 'xlsm', 'csv'].includes(ext)) { ui.fileError.textContent = 'goslint reads .xlsx, .xlsm and .csv files. Save your register as one of these, then choose it.'; return }
  if (!bytes.length) { ui.fileError.textContent = `${name} is empty. Choose the saved register.`; return }
  if (ext !== 'csv' && OLE.every((b, i) => bytes[i] === b)) {
    ui.fileError.textContent = 'This workbook is encrypted or password-protected, so goslint cannot open it. Save a copy without protection, or save it as .csv, then choose that copy.'
    return
  }
  register = { name, bytes }
  ui.fileName.textContent = `${name} (${Math.max(1, Math.round(bytes.length / 1024))} KB)`
  ui.hint.textContent = hint
  ui.hint.hidden = !hint
  show('packs')
  ui.stepPacks.querySelector('h2').focus()
}
async function fromFile (f) { if (f) take(f.name, new Uint8Array(await f.arrayBuffer())) }

async function run () {
  if (busy) return
  const ids = chosen()
  if (!ids.length) { ui.runError.textContent = 'Choose at least one regulator first.'; ui.regions.querySelector('summary')?.focus(); return }
  busy = true
  ui.run.setAttribute('aria-disabled', 'true')
  ui.run.textContent = 'Checking your register'
  try {
    const q = new URLSearchParams({ name: register.name, packs: ids.join(','), as_of: ui.asOf.value || today() })
    const res = await fetch('lint?' + q, { method: 'POST', body: register.bytes, headers: { 'Content-Type': 'application/octet-stream' } })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const out = await res.json()
    if (out.error) { ui.runError.textContent = out.error.replace(/^goslint: /, ''); return }
    if (!out.doc.workbook.entries) {
      const w = out.doc.workbook
      ui.runError.textContent = `No entries were found under header row ${w.header_row} of sheet "${w.sheet}". Check that each model has its own row, then choose the file again.`
      return
    }
    renderResults(out.doc, out.text)
    show('results')
    ui.results.querySelector('h2').focus()
  } catch (e) {
    console.error(e)
    ui.runError.textContent = `goslint on this computer did not answer. Run goslint ui again, or use the command line: ${TERMINAL}`
  } finally {
    busy = false
    ui.run.removeAttribute('aria-disabled')
    updateRun()
  }
}

function where (f) { return f.row == null ? 'Whole register' : `Row ${f.row}, ${f.entry}` }
function findingList (items) {
  const ul = el('ul', { class: 'findings' })
  items.forEach((f, i) => ul.append(el('li', { class: `f f-${f.severity}`, hidden: i >= MAX_SHOWN }, [
    el('span', { class: 'where', text: where(f) }),
    el('span', { text: f.message }),
    f.citation ? el('span', { class: 'cite', text: `${VERB[f.basis]} ${f.citation}. Pack ${f.pack}.` }) : null,
  ])))
  const out = [ul]
  if (items.length > MAX_SHOWN) {
    const more = el('button', { type: 'button', class: 'btn', text: `Show all ${items.length}` })
    more.addEventListener('click', () => {
      const hidden = [...ul.querySelectorAll('li[hidden]')]
      hidden.forEach(li => { li.hidden = false })
      hidden[0].tabIndex = -1
      hidden[0].focus()
      more.remove()
    })
    out.push(more)
  }
  return out
}
function group (id, title, intro, items) {
  return items.length ? el('section', { class: 'group', id }, [el('h3', { text: `${title} (${items.length})` }), el('p', { class: 'sub', text: intro }), ...findingList(items)]) : null
}
function download (name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const a = el('a', { href: url, download: name })
  document.body.append(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
async function copy (button, text) {
  try { await navigator.clipboard.writeText(text); button.textContent = 'Report copied' } catch (e) { button.textContent = 'Copy blocked here: use Save the report' }
  setTimeout(() => { button.textContent = 'Copy the report' }, 2500)
}
function headline (s) {
  const fix = plural(s.errors, 'item', 'items')
  const rev = plural(s.warnings, 'item', 'items')
  if (s.errors && s.warnings) return `Start with the ${fix} to fix, then the ${rev} to review.`
  if (s.errors) return `Start with the ${fix} to fix.`
  if (s.warnings) return `Nothing to fix. Start with the ${rev} to review.`
  return 'Nothing to fix or review against the packs you chose.'
}

function renderResults (doc, text) {
  const w = doc.workbook
  const s = doc.summary
  const by = sev => doc.findings.filter(f => f.severity === sev)
  const stem = w.file.replace(/\.[^.]+$/, '')
  const report = `Checked on this computer with goslint ui on ${today()}.\n\n${text}`
  const card = (n, label, kind) => {
    const kids = [el('span', { class: 'cnt-n', text: String(n) }), el('span', { text: label })]
    return n ? el('a', { class: `cnt cnt-${kind}`, href: `#g-${kind}` }, kids) : el('div', { class: `cnt cnt-${kind}` }, kids)
  }
  const prov = doc.provenance
  const pv = doc.provability
  const derived = prov.available ? prov.columns.filter(c => c.derived) : []
  const cells = prov.available
    ? `${plural(prov.typed, 'cell', 'cells')} typed by a person, ${plural(prov.derived, 'cell', 'cells')} derived by a formula, ${plural(prov.blank, 'cell', 'cells')} blank.` +
      (derived.length ? ' Derived: ' + derived.map(c => `column ${c.column} "${c.header}" (${c.derived_cells.join(', ')})`).join('; ') + '.' : '')
    : prov.reason
  ui.results.replaceChildren(
    el('h2', { tabindex: '-1', text: `${plural(w.entries, 'entry', 'entries')} checked` }),
    el('p', { class: 'sub', text: `${w.file}, sheet "${w.sheet}", header row ${w.header_row}. Next review dates as of ${doc.as_of}. Checked against ${doc.packs.map(p => packName(p.id)).join('; ')}.` }),
    el('div', { class: 'counts' }, [card(s.errors, 'to fix', 'error'), card(s.warnings, 'to review', 'warning'), card(s.notes, s.notes === 1 ? 'note' : 'notes', 'note')]),
    el('p', { class: 'headline', text: headline(s) }),
    el('div', { class: 'actions' }, [
      el('button', { type: 'button', class: 'btn btn-primary', text: 'Copy the report', onclick: e => copy(e.currentTarget, report) }),
      el('button', { type: 'button', class: 'btn', text: 'Save the report (.txt)', onclick: () => download(`goslint-report-${stem}.txt`, report, 'text/plain') }),
      el('button', { type: 'button', class: 'btn', text: 'Save the findings (JSON)', onclick: () => download(`goslint-findings-${stem}.json`, JSON.stringify(doc, null, 2) + '\n', 'application/json') }),
      el('button', { type: 'button', class: 'linkbtn', text: 'Check another register', onclick: () => { register = null; show('file'); ui.choose.focus() } }),
    ]),
    group('g-error', 'To fix', 'Fields a regulator requires that are missing or empty, and next review dates that have passed.', by('error')),
    group('g-warning', 'To review', 'Fields a regulator expects, and dates goslint cannot read.', by('warning')),
    group('g-note', 'Notes', 'Fields a regulator recommends.', by('note')),
    el('section', { class: 'group' }, [el('h3', { text: 'Typed or derived' }), el('p', { class: 'sub', text: cells })]),
    el('section', { class: 'prove' }, [
      el('h3', { text: 'What a spreadsheet cannot prove' }),
      el('ul', {}, pv.findings.map(t => el('li', { text: t }))),
      el('p', { class: 'prove-close', text: `${w.entries === 1 ? 'The 1 entry' : `All ${w.entries} entries`} in this register ${w.entries === 1 ? 'is' : 'are'} affected. ${pv.statement}` }),
      el('p', { text: 'The Register tier is free for institutions: import the spreadsheet you already keep and claim your tenant under your own sign-in.' }),
      el('div', { class: 'row' }, [
        el('a', { class: 'btn btn-primary', href: 'https://governanceos.si/register?from=goslint-ui', rel: 'noopener', text: 'See the Register tier' }),
        el('a', { href: 'https://governanceos.si/practitioners?from=goslint-ui', rel: 'noopener', text: 'Advising several clients? GovernanceOS for practitioners' }),
      ]),
    ]),
    el('p', { class: 'sub proof', text: `Checked on this computer by ${doc.tool} (${doc.package}). SHA-256 of the file as read: ${w.sha256}.` }),
  )
}

// wiring
ui.asOf.value = today()
ui.asOf.addEventListener('change', () => { ui.asOfLabel.textContent = ui.asOf.value && ui.asOf.value !== today() ? ui.asOf.value : 'today' })
ui.choose.addEventListener('click', () => ui.file.click())
ui.drop.addEventListener('click', e => { if (!e.target.closest('button')) ui.file.click() })
ui.file.addEventListener('change', () => { const f = ui.file.files[0]; ui.file.value = ''; fromFile(f) })
ui.change.addEventListener('click', () => { show('file'); ui.choose.focus() })
ui.sample.addEventListener('click', async () => {
  try {
    const res = await fetch('sample.xlsx')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    take('nebula-mutual-register.xlsx', new Uint8Array(await res.arrayBuffer()),
      'The sample is a fictional Canadian life insurer. Its register was kept for OSFI E-23 and the AMF guideline, both under Canada.')
  } catch (e) {
    ui.fileError.textContent = 'The sample could not load. Run goslint ui again, then try once more.'
  }
})
for (const ev of ['dragenter', 'dragover']) ui.drop.addEventListener(ev, e => { e.preventDefault(); ui.drop.dataset.over = 'yes' })
for (const ev of ['dragleave', 'drop']) ui.drop.addEventListener(ev, () => { ui.drop.dataset.over = '' })
addEventListener('dragover', e => e.preventDefault())
addEventListener('drop', e => { e.preventDefault(); const f = e.dataTransfer && e.dataTransfer.files[0]; if (f && !ui.stepFile.hidden) fromFile(f) })
ui.run.addEventListener('click', run)

fetch('catalog').then(r => r.json()).then(cat => {
  catalog = cat
  renderPacks(cat)
  updateRun()
  say(`Ready: goslint ${cat.goslint}, ${cat.packs.length} rule packs, running on this computer.`, 'ready')
}).catch(() => say('goslint on this computer did not answer. Run goslint ui again.', 'error'))
