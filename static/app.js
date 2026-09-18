const $ = (selector) => document.querySelector(selector);
let documents = [], currentRequest = null, selectedFeedback = null, asking = false, savingFeedback = false;
const labels = {ok:'已检索', empty:'无相关资料', timeout:'超时', error:'暂不可用', disabled:'未启用', not_configured:'未配置 DeepSeek Key'};
const element = (tag, text, cls) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (cls) el.className = cls; return el; };
function safeLink(url) { return /^(https?:\/\/|\/documents\/|\/reference\/|\/compiler\/pages\/)/.test(url) ? url : '#'; }
async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = `请求失败（${response.status}），请稍后重试`;
    try { const data = await response.json(); if (typeof data.detail === 'string') message = data.detail; } catch (_) {}
    throw new Error(message);
  }
  return response.json();
}
function post(path, data) { return api(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)}); }
function showError(message) { $('#error').textContent = message; $('#error').hidden = !message; }
function renderDocuments(category='all') {
  const list = documents.filter(doc => category === 'all' || doc.category === category);
  $('#library-title').textContent = category === 'all' ? '浏览知识库' : category;
  $('#documents').replaceChildren(); $('#empty').hidden = list.length > 0;
  for (const doc of list) {
    const card = element('article', undefined, 'document-card');
    const top = element('div', undefined, 'card-top'); top.append(element('span', doc.category, 'category-label'), element('span', doc.fictional ? '演示' : 'WIKI'));
    const heading = element('h3'), link = element('a', doc.title); link.href = safeLink(doc.url || `/documents/${doc.id}`); link.target = '_blank'; link.rel = 'noopener noreferrer'; heading.append(link);
    const tags = element('div', undefined, 'tags'); doc.tags.slice(0,4).forEach(tag => tags.append(element('span', tag)));
    const bottom = element('div', undefined, 'card-bottom'); const more = element('a', '阅读文档 ↗'); more.href = link.href; more.target = '_blank'; more.rel = 'noopener noreferrer';
    bottom.append(element('span', doc.updated_at ? doc.updated_at.slice(0,10) : '更新时间未提供'), more);
    card.append(top, heading, tags, bottom); $('#documents').append(card);
  }
  document.querySelectorAll('.nav-item').forEach(button => { const active = button.dataset.category === category; button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active)); });
}
async function load() {
  try {
    const data = await api('/api/navigation'); documents = data.documents;
    $('#count').textContent = documents.length;
    $('#external').checked = data.external_default; $('#external').disabled = data.external_mode === 'off';
    $('#demo-notice').textContent = documents.some(d=>d.fictional) || data.external_mode === 'demo' ? '演示资料 · 当前示例内容为虚构，请结合引用阅读。' : '回答附资料来源，请结合原文阅读。';
    const sync = data.state.sync; $('#sync-status').textContent = sync ? `最近同步 ${new Date(sync.at).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}` : '等待首次同步';
    const counts = new Map([['all', documents.length]]); documents.forEach(doc=>counts.set(doc.category,(counts.get(doc.category)||0)+1));
    $('#categories').replaceChildren();
    counts.forEach((count, category) => { const button = element('button', category === 'all' ? '全部知识' : category, 'nav-item'); button.dataset.category = category; button.append(element('span', count)); button.addEventListener('click', ()=>renderDocuments(category)); $('#categories').append(button); });
    renderDocuments();
  } catch (error) { $('#demo-notice').textContent = '知识库暂时无法加载'; showError(error.message); }
}
function renderAnswer(data) {
  currentRequest = data.request_id; selectedFeedback = null;
  $('#answer-panel').hidden = false;
  $('#answer-mode').textContent = {compiler:'Compiler 回答', extractive:'原文摘录', generated:'融合回答', fallback:'资料列表', no_results:'暂无资料', unavailable:'检索暂不可用'}[data.mode];
  $('#source-status').textContent = `团队 Wiki：${labels[data.sources.internal]}　·　其他资料：${labels[data.sources.external]}`;
  $('#answer-fictional').hidden = !data.fictional;
  // Only use HTML produced by the server's restricted Markdown renderer.
  if (typeof data.answer_html === 'string') $('#answer').innerHTML = data.answer_html;
  else $('#answer').textContent = data.answer;
  $('#answer').querySelectorAll('a').forEach(link=>{ link.target = '_blank'; link.rel = 'noopener noreferrer'; });
  $('#evidence').replaceChildren();
  for (const item of data.evidence) {
    const card = element('article', undefined, 'evidence-card'); const link = element('a', `[${item.citation}] ${item.title}`); link.href = safeLink(item.url); link.target = '_blank'; link.rel = 'noopener noreferrer';
    const details = element('details'), summary = element('summary', '查看引用片段');
    const excerpt = element('div', undefined, 'evidence-markdown');
    if (typeof item.text_html === 'string') excerpt.innerHTML = item.text_html; else excerpt.textContent = item.text;
    excerpt.querySelectorAll('a').forEach(sourceLink=>{ sourceLink.target = '_blank'; sourceLink.rel = 'noopener noreferrer'; });
    details.append(summary, excerpt);
    card.append(link, element('small', `${item.source_name}${item.fictional ? ' · 虚构演示' : ''}`), details);
    if (item.wiki_page) { const wiki = element('a', '查看关联知识页 →'); wiki.href = `/wiki/${item.wiki_page.split('/').map(encodeURIComponent).join('/')}`; wiki.target = '_blank'; wiki.rel = 'noopener noreferrer'; card.append(wiki); }
    $('#evidence').append(card);
  }
  const keywordResults = Array.isArray(data.keyword_results) ? data.keyword_results : [];
  $('#keyword-count').textContent = `${keywordResults.length} 条结果`;
  $('#keyword-results').replaceChildren();
  if (!keywordResults.length) $('#keyword-results').append(element('p', '没有匹配到包含这些关键词的文档。', 'keyword-empty'));
  for (const item of keywordResults) {
    const result = element('article', undefined, 'keyword-result');
    const heading = element('h4'), link = element('a', item.title); link.href = safeLink(item.url); link.target = '_blank'; link.rel = 'noopener noreferrer';
    const meta = element('span', `${item.updated_at ? item.updated_at.slice(0,10) : '时间未提供'}${item.fictional ? ' · 演示资料' : ''}`);
    const snippet = element('div', undefined, 'keyword-snippet');
    if (typeof item.snippet_html === 'string') snippet.innerHTML = item.snippet_html; else snippet.textContent = item.snippet;
    snippet.querySelectorAll('a').forEach(sourceLink=>{ sourceLink.target = '_blank'; sourceLink.rel = 'noopener noreferrer'; });
    heading.append(link); result.append(heading, snippet, meta); $('#keyword-results').append(result);
  }
  $('#feedback').hidden = false; $('#feedback-detail').hidden = true; $('#feedback-status').textContent = ''; $('#reason').value = '';
  document.querySelectorAll('[data-solved]').forEach(button=>{button.classList.remove('selected');button.disabled=false;});
}
$('#ask-form').addEventListener('submit', async event => {
  event.preventDefault(); if (asking) return;
  const question = $('#question').value.trim(); if (question.length < 2) return;
  asking = true; showError('');
  const askButton = $('#ask-button'); askButton.disabled = true; askButton.classList.add('loading'); askButton.setAttribute('aria-busy','true');
  askButton.replaceChildren(element('span', undefined, 'spinner'), element('span', '正在搜索'));
  // Hide the previous result so it cannot be mistaken for the new question's answer.
  $('#answer-panel').hidden = true;
  try { renderAnswer(await post('/api/ask', {question, include_external:$('#external').checked})); }
  catch (error) { showError(error.message); }
  finally { asking = false; askButton.disabled = false; askButton.classList.remove('loading'); askButton.removeAttribute('aria-busy'); askButton.replaceChildren(element('span','搜索知识','button-label'), element('span','↗')); }
});
document.querySelectorAll('[data-query]').forEach(button=>button.addEventListener('click',()=>{ if (asking) return; $('#question').value = button.dataset.query; $('#ask-form').requestSubmit(); }));
async function saveFeedback() {
  if (!currentRequest || selectedFeedback === null || savingFeedback) return;
  savingFeedback = true;
  document.querySelectorAll('#feedback button').forEach(button=>{button.disabled=true;});
  const requestId = currentRequest, solved = selectedFeedback, reason = $('#reason').value;
  $('#feedback-status').textContent = '保存中…';
  try { await post('/api/feedback',{request_id:requestId, solved, reason}); if (currentRequest === requestId) { $('#feedback-status').textContent = '反馈已保存，谢谢'; $('#feedback-detail').hidden = true; } }
  catch (error) { if (currentRequest === requestId) $('#feedback-status').textContent = error.message; }
  finally { savingFeedback = false; document.querySelectorAll('#feedback button').forEach(button=>{button.disabled=false;}); }
}
document.querySelectorAll('[data-solved]').forEach(button=>button.addEventListener('click', async()=>{
  selectedFeedback = button.dataset.solved === 'true'; $('#feedback-status').textContent = '';
  document.querySelectorAll('[data-solved]').forEach(item=>item.classList.toggle('selected',item===button));
  $('#feedback-detail').hidden = selectedFeedback;
  if (selectedFeedback) await saveFeedback(); else $('#reason').focus();
}));
$('#feedback').addEventListener('submit',async event=>{event.preventDefault();await saveFeedback();});
$('#dismiss-feedback').addEventListener('click',()=>{$('#feedback').hidden=true;});
load();
