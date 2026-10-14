const { JSDOM } = require('jsdom'); const fs = require('fs'); const assert = require('assert');
const html = fs.readFileSync('../../index.html', 'utf8');
const modal = html.slice(html.indexOf('<!-- PDF EXPORT: patient details modal'), html.indexOf('            <div id="results-section"'));
const js = html.slice(html.indexOf('// === PDF EXPORT START'), html.indexOf('// === PDF EXPORT END'));
const report = JSON.parse(fs.readFileSync('../../examples/input/sample_input.json', 'utf8'));
['name','age','language','date'].forEach(k => delete report[k]);
report.originalText = 'PRIVATE ORIGINAL PRESCRIPTION TEXT'; report.timestamp = 123; report.userId = 'uid1';

async function run(name, fn) { try { await fn(); console.log('ok  ', name); } catch (e) { console.log('FAIL', name, '\n    ', e.message); process.exitCode = 1; } }
function setup({ displayName = 'Ravi Kumar', base = 'http://127.0.0.1:8777' } = {}) {
  const dom = new JSDOM(`<body><button id="dl" onclick="downloadReport()">dl</button>${modal}</body>`, { runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window; const calls = []; const downloads = [];
  w.eval(`var auth={currentUser:${displayName === null ? 'null' : JSON.stringify({ displayName })}}; var lucide={createIcons(){}}; var currentLanguage='Telugu'; var currentReportData=null;`);
  w.fetch = (u, o) => { calls.push({ u, o }); return fetch(base + u, o); };
  w.URL.createObjectURL = (b) => 'blob:x'; w.URL.revokeObjectURL = () => {};
  w.HTMLAnchorElement.prototype.click = function () { downloads.push(this.download); };
  w.HTMLElement.prototype.focus = function () { w.document.__focus = this.id; };
  Object.defineProperty(w.HTMLElement.prototype, 'offsetParent', { get() { return this.parentNode; } });
  w.eval(js); w.eval('window.__setReport=(r)=>{currentReportData=r}; window.__getReport=()=>currentReportData;');
  w.__setReport(report);
  const $ = (id) => w.document.getElementById(id);
  const fill = (n, a) => { $('pdf-patient-name').value = n; $('pdf-patient-age').value = a; };
  const submit = () => w.eval('handlePatientDetailsSubmit(new Event("submit",{cancelable:true}))');
  return { w, $, calls, downloads, fill, submit };
}
const visible = (t) => !t.$('patient-details-modal').classList.contains('hidden');

(async () => {
  await run('download with no report does nothing', async () => { const t = setup(); t.w.__setReport(null); t.w.eval('downloadReport()'); assert(!visible(t)); });
  await run('open modal; fields empty; account hint shows name', async () => { const t = setup(); t.w.eval('downloadReport()'); assert(visible(t)); assert.equal(t.$('pdf-patient-name').value, ''); assert(t.$('pdf-account-hint').textContent.includes('Ravi Kumar')); });
  await run('cancel closes, no request', async () => { const t = setup(); t.w.eval('downloadReport()'); t.w.eval('closePatientDetailsModal()'); assert(!visible(t)); assert.equal(t.calls.length, 0); });
  await run('empty name -> error, no request', async () => { const t = setup(); t.w.eval('downloadReport()'); t.fill('   ', '45'); t.submit(); assert(!t.$('pdf-name-error').classList.contains('hidden')); assert.equal(t.calls.length, 0); assert(visible(t)); });
  for (const bad of ['', 'abc', '-1', '121', '4.5', '045', '1e2', '٤٥', ' ']) await run(`invalid age ${JSON.stringify(bad)} rejected`, async () => { const t = setup(); t.w.eval('downloadReport()'); t.fill('Ravi', bad); t.submit(); assert(!t.$('pdf-age-error').classList.contains('hidden')); assert.equal(t.calls.length, 0); });
  for (const good of ['0', '7', '45', '120']) await run(`valid age ${good} accepted by validator`, async () => { const t = setup(); assert.equal(t.w.eval(`validatePatientAge('${good}').value`), Number(good)); });
  await run('account checkbox fills + locks name', async () => { const t = setup(); t.w.eval('downloadReport()'); t.fill('typed', ''); t.$('pdf-use-account').checked = true; t.w.eval('onAccountDetailsToggle()'); assert.equal(t.$('pdf-patient-name').value, 'Ravi Kumar'); assert(t.$('pdf-patient-name').readOnly); t.$('pdf-use-account').checked = false; t.w.eval('onAccountDetailsToggle()'); assert.equal(t.$('pdf-patient-name').value, 'typed'); assert(!t.$('pdf-patient-name').readOnly); });
  await run('account without name: unchecks + asks for name', async () => { const t = setup({ displayName: '   ' }); t.w.eval('downloadReport()'); t.$('pdf-use-account').checked = true; t.w.eval('onAccountDetailsToggle()'); assert(!t.$('pdf-use-account').checked); assert(t.$('pdf-account-hint').textContent.includes('no name')); });
  await run('no logged-in user handled', async () => { const t = setup({ displayName: null }); t.w.eval('downloadReport()'); assert(t.$('pdf-account-hint').textContent.includes('No name')); });
  await run('account checked -> name taken from account at submit', async () => { const t = setup(); t.w.eval('downloadReport()'); t.$('pdf-use-account').checked = true; t.w.eval('onAccountDetailsToggle()'); t.$('pdf-patient-age').value = '62'; t.submit(); await new Promise(r => setTimeout(r, 1500)); assert.equal(JSON.parse(t.calls[0].o.body).patient.name, 'Ravi Kumar'); });

  await run('success: one request, busy state, double-click safe, PDF downloaded, modal closed', async () => {
    const t = setup(); t.w.eval('downloadReport()'); t.fill('  Ravi   Kumar Reddy ', '62');
    t.submit(); t.submit(); t.submit();                                   // rapid duplicate submits
    assert(t.$('pdf-submit-btn').disabled, 'button disabled while generating'); assert(!t.$('pdf-submit-busy').classList.contains('hidden'));
    assert(t.$('pdf-submit-busy').textContent.includes('Generating PDF...'));
    await new Promise(r => setTimeout(r, 2500));
    assert.equal(t.calls.length, 1, 'exactly one request'); assert.deepEqual(t.downloads, ['Rxora-Ravi-Kumar-Reddy-Medical-Summary.pdf']);
    assert(!visible(t), 'modal closed'); assert(!t.$('pdf-submit-btn').disabled, 'button restored'); assert(t.$('pdf-submit-busy').classList.contains('hidden'));
    const body = JSON.parse(t.calls[0].o.body);
    assert.deepEqual(body.patient, { name: 'Ravi Kumar Reddy', age: 62 }); assert.equal(body.language, 'Telugu'); assert(/^\d{4}-\d{2}-\d{2}$/.test(body.date));
    assert(!('originalText' in body.result) && !('timestamp' in body.result) && !('userId' in body.result), 'history metadata not sent');
    assert.deepEqual(body.result.dosage_table, report.dosage_table, 'result sent unmodified'); assert.equal(body.result.summary, report.summary);
  });

  await run('server failure: friendly error, modal stays, result kept, button restored', async () => {
    const t = setup({ base: 'http://127.0.0.1:1' }); t.w.eval('downloadReport()'); t.fill('Ravi', '40'); t.submit(); await new Promise(r => setTimeout(r, 800));
    assert(visible(t)); assert.equal(t.$('pdf-error-text').textContent, 'Could not generate the PDF. Please try again.'); assert(!t.$('pdf-submit-btn').disabled);
    assert.strictEqual(t.w.__getReport(), report); assert.equal(t.downloads.length, 0);
  });
  await run('HTML/JSON response is never downloaded as a PDF', async () => {
    const t = setup(); t.w.fetch = async () => new t.w.Response ? null : null; t.w.fetch = async () => new Response('<html>oops</html>', { status: 200, headers: { 'Content-Type': 'text/html' } });
    t.w.eval('downloadReport()'); t.fill('Ravi', '40'); t.submit(); await new Promise(r => setTimeout(r, 300));
    assert.equal(t.downloads.length, 0); assert(!t.$('pdf-error').classList.contains('hidden'));
  });
  await run('200 + application/pdf but not a PDF is rejected', async () => {
    const t = setup(); t.w.fetch = async () => new Response('x'.repeat(500), { status: 200, headers: { 'Content-Type': 'application/pdf' } });
    t.w.eval('downloadReport()'); t.fill('Ravi', '40'); t.submit(); await new Promise(r => setTimeout(r, 300)); assert.equal(t.downloads.length, 0);
  });
  await run('cancel during generation aborts silently', async () => {
    const t = setup(); t.w.fetch = (u, o) => new Promise((_, rej) => o.signal.addEventListener('abort', () => rej(new Error('aborted'))));
    t.w.eval('downloadReport()'); t.fill('Ravi', '40'); t.submit(); assert(t.$('pdf-submit-btn').disabled); t.w.eval('closePatientDetailsModal()'); await new Promise(r => setTimeout(r, 100));
    assert(!visible(t)); assert(t.$('pdf-error').classList.contains('hidden')); assert(!t.$('pdf-submit-btn').disabled);
  });

  await run('missing /api (404 HTML) -> endpoint_unavailable hint', async () => {
    const t = setup(); t.w.fetch = async () => new Response('<html>Not found</html>', { status: 404, headers: { 'Content-Type': 'text/html' } });
    t.w.eval('downloadReport()'); t.fill('Ravi', '40'); t.submit(); await new Promise(r => setTimeout(r, 300));
    assert.equal(t.$('pdf-error-text').textContent, 'Could not generate the PDF. Please try again.');
    assert(t.$('pdf-error-ref').textContent.includes('PDF service was not found')); assert.equal(t.downloads.length, 0); assert(visible(t));
  });
  await run('static server 405/501 -> endpoint_unavailable', async () => {
    for (const status of [405, 501]) { const t = setup(); t.w.fetch = async () => new Response('', { status });
      t.w.eval('downloadReport()'); t.fill('Ravi', '40'); t.submit(); await new Promise(r => setTimeout(r, 200)); assert(t.$('pdf-error-ref').textContent.includes('not found'), status); }
  });
  await run('server 400 message is shown (user-safe)', async () => {
    const t = setup(); t.w.fetch = async () => new Response(JSON.stringify({ error: 'Report is too large to export.', code: 'too_large' }), { status: 413, headers: { 'Content-Type': 'application/json' } });
    t.w.eval('downloadReport()'); t.fill('Ravi', '40'); t.submit(); await new Promise(r => setTimeout(r, 200));
    assert.equal(t.$('pdf-error-ref').textContent, 'Report is too large to export.');
  });
  await run('server 500 -> generic text + reference, nothing leaked', async () => {
    const t = setup(); t.w.fetch = async () => new Response(JSON.stringify({ error: 'Could not generate the PDF.', code: 'generation_failed' }), { status: 500, headers: { 'Content-Type': 'application/json' } });
    t.w.eval('downloadReport()'); t.fill('Ravi', '40'); t.submit(); await new Promise(r => setTimeout(r, 200));
    assert(t.$('pdf-error-ref').textContent.includes('generation_failed')); assert(!/Traceback|File "/.test(t.$('pdf-error').textContent));
  });
  await run('network failure -> connection hint; retry works after error', async () => {
    const t = setup({ base: 'http://127.0.0.1:1' }); t.w.eval('downloadReport()'); t.fill('Ravi', '40'); t.submit(); await new Promise(r => setTimeout(r, 600));
    assert(t.$('pdf-error-ref').textContent.includes('internet')); assert(!t.$('pdf-submit-btn').disabled);
  });
  await run('Escape closes modal; focus returns', async () => { const t = setup(); t.$('dl').focus(); t.w.eval('downloadReport()'); t.$('patient-details-modal').dispatchEvent(new t.w.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); assert(!visible(t)); });
})();
