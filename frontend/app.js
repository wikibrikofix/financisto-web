const API = '/api';
let state = { view: 'accounts', accounts: [], categories: [], payees: [], currencies: [], txOffset: 0, currentAccount: null };

function fmt(cents, symbol = '€', decimals = 2) { return (cents / Math.pow(10, decimals)).toFixed(decimals) + ' ' + symbol; }
function fmtDate(ms) { return new Date(parseInt(ms)).toLocaleDateString('it-IT', {day:'2-digit',month:'short',year:'numeric'}); }
function $(id) { return document.getElementById(id); }
async function api(path, opts) { const res = await fetch(API + path, opts); return res.json(); }
async function apiPost(path, body) { return api(path, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) }); }
async function apiPut(path, body) { return api(path, { method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) }); }
async function apiDelete(path) { return api(path, { method:'DELETE' }); }

function showView(view) {
    state.view = view; state.txOffset = 0; state.currentAccount = null;
    clearInfiniteScroll();
    if (logsInterval) { clearInterval(logsInterval); logsInterval = null; }
    document.querySelectorAll('.bottom-nav button, .sidebar button').forEach(b => b.classList.remove('active'));
    ['nav-','side-'].forEach(p => { const el = $(p + view); if(el) el.classList.add('active'); });
    $('fab').classList.toggle('hidden', view === 'reports' || view === 'import');
    closeModal();
    history.pushState({view}, '', '#' + view);
    ({accounts: renderAccounts, transactions: renderTransactions, categories: renderCategories, reports: renderReports, import: renderImport, logs: renderLogs})[view]?.();
}

function onFabClick() {
    if (state.currentAccount) showTransactionForm();
    else if (state.view === 'accounts') showAccountForm();
    else if (state.view === 'transactions') showTransactionForm();
    else if (state.view === 'categories') showCategoryForm();
}

function showModal(html) { $('modal-root').innerHTML = `<div class="modal-overlay" onclick="if(event.target===this)closeModal()"><div class="modal">${html}</div></div>`; }
function closeModal() { $('modal-root').innerHTML = ''; }

async function loadData() {
    [state.accounts, state.categories, state.payees, state.currencies] = await Promise.all([
        api('/accounts'), api('/categories'), api('/payees'), api('/currencies')
    ]);
}

// --- Accounts ---
async function renderAccounts() {
    state.accounts = await api('/accounts');
    const active = state.accounts.filter(a => a.is_active);
    const closed = state.accounts.filter(a => !a.is_active);
    let html = '<div class="account-grid" id="account-grid">';
    if (!active.length) html += '<div class="card empty">Nessun conto. Premi + per crearne uno.</div>';
    html += active.map(a => `<div class="card account-card" draggable="true" data-id="${a.id}" onclick="openAccount(${a.id})"
        ondragstart="dragStart(event)" ondragover="dragOver(event)" ondrop="dropAccount(event)" ondragend="dragEnd(event)">
        <div class="type">${a.type}</div><div class="name">${a.title}</div>
        <div class="balance ${a.total_amount>=0?'positive':'negative'}">${fmt(a.total_amount, a.currency_symbol, a.currency_decimals)}</div>
    </div>`).join('') + '</div>';
    if (closed.length) {
        html += `<div class="section-title" style="margin-top:1rem;cursor:pointer" onclick="document.getElementById('closed-accounts').classList.toggle('hidden');this.querySelector('span').textContent=document.getElementById('closed-accounts').classList.contains('hidden')?'+':'−'">Conti chiusi (<span>+</span>)</div><div class="account-grid hidden" id="closed-accounts">`;
        html += closed.map(a => `<div class="card account-card inactive" onclick="openAccount(${a.id})">
            <div class="type">${a.type} (chiuso)</div><div class="name">${a.title}</div>
            <div class="balance">${fmt(a.total_amount, a.currency_symbol, a.currency_decimals)}</div>
        </div>`).join('') + '</div>';
    }
    $('content').innerHTML = html;
}

let draggedId = null;
function dragStart(e) { draggedId = e.currentTarget.dataset.id; e.currentTarget.classList.add('dragging'); }
function dragEnd(e) { e.currentTarget.classList.remove('dragging'); document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over')); }
function dragOver(e) { e.preventDefault(); const card = e.currentTarget; if (card.dataset.id !== draggedId) card.classList.add('drag-over'); }
async function dropAccount(e) {
    e.preventDefault();
    const targetId = e.currentTarget.dataset.id;
    e.currentTarget.classList.remove('drag-over');
    if (!draggedId || draggedId === targetId) return;
    // Reorder: put dragged before target
    const active = state.accounts.filter(a => a.is_active);
    const ids = active.map(a => String(a.id));
    const fromIdx = ids.indexOf(draggedId);
    const toIdx = ids.indexOf(targetId);
    ids.splice(fromIdx, 1);
    ids.splice(toIdx, 0, draggedId);
    // Save new order
    for (let i = 0; i < ids.length; i++) {
        await apiPut(`/accounts/${ids[i]}`, { ...active.find(a => a.id == ids[i]), sort_order: i });
    }
    draggedId = null;
    renderAccounts();
}

async function openAccount(id) {
    state.currentAccount = state.accounts.find(a => a.id === id); state.txOffset = 0;
    history.pushState({view: 'account', id}, '', '#account/' + id);
    const txs = await api(`/accounts/${id}/transactions?limit=50`);
    const a = state.currentAccount;
    let html = `<span class="back-link" onclick="showView('accounts')">← Conti</span>
        <div class="card" style="display:flex;justify-content:space-between;align-items:center">
            <div><div style="font-weight:700;font-size:1.1rem">${a.title}</div><div style="font-size:0.8rem;color:var(--muted)">${a.type}</div></div>
            <div style="text-align:right">
                <div class="${a.total_amount>=0?'positive':'negative'}" style="font-size:1.3rem;font-weight:700">${fmt(a.total_amount, a.currency_symbol, a.currency_decimals)}</div>
                <button onclick="showAccountForm(${a.id})" style="font-size:0.75rem;border:none;background:var(--border);padding:0.3rem 0.6rem;border-radius:4px;cursor:pointer;margin-top:0.3rem">Modifica</button>
            </div>
        </div><div class="card">`;
    if (!txs.length) html += '<div class="empty">Nessuna transazione</div>';
    html += txs.map(t => txItem(t, a.currency_symbol, a.currency_decimals)).join('');
    html += '</div>';
    $('content').innerHTML = html; $('fab').classList.remove('hidden');
    if (txs.length >= 50) setupInfiniteScroll(() => loadMoreAccountTx(id));
    else clearInfiniteScroll();
}

async function loadMoreAccountTx(id) {
    state.txOffset += 50;
    const txs = await api(`/accounts/${id}/transactions?limit=50&offset=${state.txOffset}`);
    const card = document.querySelectorAll('.card')[1];
    txs.forEach(t => card.insertAdjacentHTML('beforeend', txItem(t, state.currentAccount.currency_symbol, state.currentAccount.currency_decimals)));
    if (txs.length < 50) clearInfiniteScroll();
}

function showAccountForm(editId) {
    const a = editId ? state.accounts.find(x => x.id === editId) : null;
    const types = ['CASH','BANK','CARD','ELECTRONIC','ASSET','LIABILITY','OTHER'];
    showModal(`<h2>${a?'Modifica':'Nuovo'} Conto</h2>
        <div class="form-group"><label>Nome</label><input id="f-title" value="${a?.title||''}"></div>
        <div class="form-row">
            <div class="form-group"><label>Tipo</label><select id="f-type">${types.map(t=>`<option ${a?.type===t?'selected':''}>${t}</option>`).join('')}</select></div>
            <div class="form-group"><label>Valuta</label><select id="f-currency">${state.currencies.map(c=>`<option value="${c.id}" ${a?.currency_id===c.id?'selected':''}>${c.name} (${c.symbol})</option>`).join('')}</select></div>
        </div>
        <div class="form-group"><label>Note</label><textarea id="f-note">${a?.note||''}</textarea></div>
        <div class="btn-row"><button class="btn btn-secondary" onclick="closeModal()">Annulla</button><button class="btn btn-primary" onclick="saveAccount(${editId||'null'})">Salva</button></div>
        ${a?`<button class="btn btn-danger" style="margin-top:0.5rem" onclick="deleteAccount(${editId})">${a.is_active?'Chiudi conto':'Riattiva conto'}</button>`:''}
    `);
}
async function saveAccount(id) {
    const data = { title:$('f-title').value, type:$('f-type').value, currency_id:parseInt($('f-currency').value), note:$('f-note').value };
    if (!data.title) return alert('Inserisci un nome');
    if (id) await apiPut(`/accounts/${id}`, data); else await apiPost('/accounts', data);
    closeModal(); await loadData();
    if (id && state.currentAccount) openAccount(id); else renderAccounts();
}
async function deleteAccount(id) {
    const acc = state.accounts.find(a => a.id === id);
    if (acc && !acc.is_active) { await apiPut(`/accounts/${id}`, {...acc, is_active: true}); }
    else { if (!confirm('Chiudere questo conto?')) return; await apiDelete(`/accounts/${id}`); }
    closeModal(); await loadData(); showView('accounts');
}

// --- Transactions with Filters ---
let txFilters = {};
let selectedAccounts = [];
let selectedCategories = [];

async function renderTransactions() {
    txFilters = {};
    selectedAccounts = [];
    selectedCategories = [];
    let html = `<div class="card" style="padding:0.75rem">
        <div style="display:flex;gap:0.5rem;flex-wrap:wrap;align-items:center">
            <div class="multi-filter" style="position:relative;flex:1;min-width:150px">
                <input id="filter-account-input" placeholder="Conti..." oninput="showFilterDropdown('account')" onfocus="showFilterDropdown('account')" style="padding:0.4rem;border:1px solid var(--border);border-radius:6px;font-size:0.85rem;width:100%">
                <div id="filter-account-tags" style="display:flex;flex-wrap:wrap;gap:2px;margin-top:2px"></div>
                <div id="filter-account-dropdown" class="filter-dropdown hidden"></div>
            </div>
            <div class="multi-filter" style="position:relative;flex:1;min-width:150px">
                <input id="filter-category-input" placeholder="Categorie..." oninput="showFilterDropdown('category')" onfocus="showFilterDropdown('category')" style="padding:0.4rem;border:1px solid var(--border);border-radius:6px;font-size:0.85rem;width:100%">
                <div id="filter-category-tags" style="display:flex;flex-wrap:wrap;gap:2px;margin-top:2px"></div>
                <div id="filter-category-dropdown" class="filter-dropdown hidden"></div>
            </div>
            <input id="filter-from" type="date" onchange="applyFilters()" style="padding:0.4rem;border:1px solid var(--border);border-radius:6px;font-size:0.85rem">
            <input id="filter-to" type="date" onchange="applyFilters()" style="padding:0.4rem;border:1px solid var(--border);border-radius:6px;font-size:0.85rem">
            <button onclick="clearFilters()" style="padding:0.4rem 0.6rem;border:none;background:var(--border);border-radius:6px;font-size:0.8rem;cursor:pointer">✕ Reset</button>
        </div>
    </div>`;
    html += '<div class="card" id="tx-list-card"><div class="empty">Caricamento...</div></div>';
    $('content').innerHTML = html;
    await applyFilters();
}

async function applyFilters() {
    state.txOffset = 0;
    const params = new URLSearchParams();
    if (selectedAccounts.length) params.set('account_id', selectedAccounts.join(','));
    if (selectedCategories.length) params.set('category_id', selectedCategories.join(','));
    const from = $('filter-from')?.value; if (from) params.set('date_from', from);
    const to = $('filter-to')?.value; if (to) params.set('date_to', to);
    params.set('limit', '50');
    txFilters = Object.fromEntries(params);
    const txs = await api(`/transactions/search?${params}`);
    const card = $('tx-list-card');
    if (!txs.length) { card.innerHTML = '<div class="empty">Nessuna transazione trovata</div>'; clearInfiniteScroll(); return; }
    card.innerHTML = txs.map(t => txItem(t, t.currency_symbol, t.currency_decimals, true)).join('');
    if (txs.length >= 50) setupInfiniteScroll(loadMoreFilteredTx);
    else clearInfiniteScroll();
}

async function loadMoreFilteredTx() {
    state.txOffset += 50;
    const params = new URLSearchParams(txFilters);
    params.set('offset', state.txOffset); params.set('limit', '50');
    const txs = await api(`/transactions/search?${params}`);
    const card = $('tx-list-card');
    txs.forEach(t => card.insertAdjacentHTML('beforeend', txItem(t, t.currency_symbol, t.currency_decimals, true)));
    if (txs.length < 50) clearInfiniteScroll();
}

function clearFilters() {
    selectedAccounts = []; selectedCategories = [];
    if($('filter-account-input')) $('filter-account-input').value = '';
    if($('filter-category-input')) $('filter-category-input').value = '';
    if($('filter-from')) $('filter-from').value = '';
    if($('filter-to')) $('filter-to').value = '';
    renderFilterTags('account'); renderFilterTags('category');
    applyFilters();
}

// --- Multi-select filter logic ---
function showFilterDropdown(type) {
    const input = $(`filter-${type}-input`);
    const dropdown = $(`filter-${type}-dropdown`);
    const query = input.value.toLowerCase();
    const items = type === 'account' ? state.accounts.filter(a => a.is_active) : state.categories;
    const selected = type === 'account' ? selectedAccounts : selectedCategories;
    const filtered = items.filter(item => item.title.toLowerCase().includes(query) && !selected.includes(item.id));
    if (!filtered.length) { dropdown.classList.add('hidden'); return; }
    dropdown.innerHTML = filtered.slice(0, 10).map(item =>
        `<div class="filter-option" onmousedown="selectFilter('${type}', ${item.id}, '${item.title.replace(/'/g,"\\'")}')"> ${item.title}</div>`
    ).join('');
    dropdown.classList.remove('hidden');
    input.onblur = () => setTimeout(() => dropdown.classList.add('hidden'), 150);
}

function selectFilter(type, id, title) {
    const selected = type === 'account' ? selectedAccounts : selectedCategories;
    if (!selected.includes(id)) selected.push(id);
    $(`filter-${type}-input`).value = '';
    $(`filter-${type}-dropdown`).classList.add('hidden');
    renderFilterTags(type);
    applyFilters();
}

function removeFilter(type, id) {
    if (type === 'account') selectedAccounts = selectedAccounts.filter(x => x !== id);
    else selectedCategories = selectedCategories.filter(x => x !== id);
    renderFilterTags(type);
    applyFilters();
}

function renderFilterTags(type) {
    const container = $(`filter-${type}-tags`);
    const selected = type === 'account' ? selectedAccounts : selectedCategories;
    const items = type === 'account' ? state.accounts : state.categories;
    container.innerHTML = selected.map(id => {
        const item = items.find(x => x.id === id);
        return item ? `<span style="background:var(--primary);color:#fff;padding:2px 6px;border-radius:4px;font-size:0.75rem;display:inline-flex;align-items:center;gap:3px">${item.title}<span onclick="removeFilter('${type}',${id})" style="cursor:pointer;font-weight:bold">×</span></span>` : '';
    }).join('');
}

function txItem(t, symbol, decimals, showAccount) {
    const cls = t.from_amount >= 0 ? 'positive' : 'negative';
    const pending = !t.category_id || t.category_id === 0;
    const label = t.payee_title || t.category_title || (t.to_account_id > 0 ? '↔ Trasferimento' : (t.note ? t.note.substring(0, 40) : '—'));
    const meta = [showAccount ? t.account_title : null, t.category_title || t.note || null, fmtDate(t.datetime)].filter(Boolean).join(' • ');
    const pendingBadge = pending && t.to_account_id === 0 ? '<span style="color:#ff6d01;font-size:0.75rem;margin-right:0.3rem">⏳</span>' : '';
    const pendingStyle = pending && t.to_account_id === 0 ? 'border-left:3px solid #ff6d01;padding-left:0.5rem;' : '';
    return `<div class="tx-item" style="${pendingStyle}" onclick='showTxDetail(${JSON.stringify(t).replace(/'/g,"&#39;")})'>
        <div class="info"><div class="payee">${pendingBadge}${label}</div><div class="meta">${meta}</div></div>
        <div class="amount ${cls}">${fmt(t.from_amount, symbol||'€', decimals||2)}</div>
    </div>`;
}

function showTxDetail(t) {
    showModal(`<h2>Transazione</h2>
        <div style="margin-bottom:1rem">
            <div><strong>${t.payee_title||'—'}</strong></div>
            <div style="color:var(--muted)">${t.category_title||''}</div>
            <div style="font-size:1.3rem;font-weight:700;margin:0.5rem 0" class="${t.from_amount>=0?'positive':'negative'}">${fmt(t.from_amount)}</div>
            <div style="font-size:0.85rem;color:var(--muted)">${fmtDate(t.datetime)}</div>
            ${t.note?`<div style="margin-top:0.5rem;font-size:0.9rem">${t.note}</div>`:''}
        </div>
        <div class="btn-row">
            <button class="btn btn-secondary" onclick="showTransactionForm(editTx)">Modifica</button>
            <button class="btn btn-danger" onclick="deleteTx(${t.id})">Elimina</button>
        </div>
        <button class="btn btn-secondary" style="margin-top:0.5rem" onclick="closeModal()">Chiudi</button>
    `);
    window.editTx = t;
}

function showTransactionForm(t) {
    const accs = state.accounts.filter(a => a.is_active);
    const isEdit = t && t.id;
    const defaultAcc = isEdit ? t.from_account_id : (state.currentAccount?.id || (accs[0]?.id || ''));
    const absAmount = isEdit ? (Math.abs(t.from_amount) / 100).toFixed(2) : '';
    const editDate = isEdit ? new Date(parseInt(t.datetime)).toISOString().split('T')[0] : new Date().toISOString().split('T')[0];
    const editType = isEdit ? (t.to_account_id > 0 ? 'transfer' : (t.from_amount >= 0 ? 'income' : 'expense')) : 'expense';
    showModal(`<h2>${isEdit?'Modifica':'Nuova'} Transazione</h2>
        <div class="toggle-row" id="tx-type-toggle">
            <button class="${editType==='expense'?'active':''}" onclick="setTxType('expense')">Spesa</button>
            <button class="${editType==='income'?'active':''}" onclick="setTxType('income')">Entrata</button>
            <button class="${editType==='transfer'?'active':''}" onclick="setTxType('transfer')">Trasferimento</button>
        </div>
        <div class="form-group"><label>Conto</label><select id="f-account">${accs.map(a=>`<option value="${a.id}" ${a.id==defaultAcc?'selected':''}>${a.title}</option>`).join('')}</select></div>
        <div class="form-group ${editType==='transfer'?'':'hidden'}" id="f-to-account-group"><label>Verso conto</label><select id="f-to-account"><option value="0">—</option>${accs.map(a=>`<option value="${a.id}" ${isEdit&&a.id==t.to_account_id?'selected':''}>${a.title}</option>`).join('')}</select></div>
        <div class="form-group"><label>Importo</label><input id="f-amount" type="number" step="0.01" inputmode="decimal" placeholder="0.00" value="${absAmount}"></div>
        <div class="form-group"><label>Categoria</label><input id="f-category" list="cat-list" placeholder="Cerca categoria..." value="${isEdit?(t.category_title||''):''}"><datalist id="cat-list">${state.categories.map(c=>`<option value="${c.title}" data-id="${c.id}">`).join('')}</datalist></div>
        <div class="form-group"><label>Beneficiario</label><input id="f-payee" list="payee-list" placeholder="Cerca o crea..." value="${isEdit?(t.payee_title||''):''}"><datalist id="payee-list">${state.payees.map(p=>`<option value="${p.title}">`).join('')}</datalist></div>
        <div class="form-group"><label>Data</label><input id="f-date" type="date" value="${editDate}"></div>
        <div class="form-group"><label>Note</label><textarea id="f-note" rows="2">${isEdit?(t.note||''):''}</textarea></div>
        <div class="btn-row"><button class="btn btn-secondary" onclick="closeModal()">Annulla</button><button class="btn btn-primary" onclick="saveTx(${isEdit?t.id:'null'})">Salva</button></div>
    `);
    txType = editType;
}

let txType = 'expense';
function resolveCategoryId(val) {
    if (!val) return 0;
    const cat = state.categories.find(c => c.title.toLowerCase() === val.toLowerCase());
    return cat ? cat.id : 0;
}
function setTxType(type) {
    txType = type;
    document.querySelectorAll('#tx-type-toggle button').forEach((b,i) => b.classList.toggle('active', (i===0&&type==='expense')||(i===1&&type==='income')||(i===2&&type==='transfer')));
    $('f-to-account-group').classList.toggle('hidden', type !== 'transfer');
}

async function saveTx(editId) {
    const amountRaw = parseFloat($('f-amount').value);
    if (!amountRaw && amountRaw !== 0) return alert('Inserisci un importo');
    const amountCents = Math.round(amountRaw * 100);
    const fromAmount = txType === 'expense' ? -amountCents : amountCents;
    const payeeText = $('f-payee').value.trim();
    let payeeId = 0;
    if (payeeText) {
        const existing = state.payees.find(p => p.title.toLowerCase() === payeeText.toLowerCase());
        if (existing) payeeId = existing.id;
        else { const newP = await apiPost('/payees', {title:payeeText}); payeeId = newP.id; state.payees.push(newP); }
    }
    const data = { from_account_id:parseInt($('f-account').value), to_account_id:txType==='transfer'?parseInt($('f-to-account').value):0,
        from_amount:fromAmount, to_amount:txType==='transfer'?amountCents:0, category_id:resolveCategoryId($('f-category').value),
        payee_id:payeeId, datetime:new Date($('f-date').value).getTime(), note:$('f-note').value, status:'UR' };
    if (editId) await apiPut(`/transactions/${editId}`, data); else await apiPost('/transactions', data);
    closeModal(); await loadData();
    if (state.currentAccount) openAccount(state.currentAccount.id); else renderTransactions();
}

async function deleteTx(id) {
    if (!confirm('Eliminare questa transazione?')) return;
    await apiDelete(`/transactions/${id}`); closeModal(); await loadData();
    if (state.currentAccount) openAccount(state.currentAccount.id); else renderTransactions();
}

// --- Categories (hierarchical) ---
async function renderCategories() {
    const tree = await api('/categories/tree');
    state.categories = await api('/categories');
    let html = '<div class="card">';
    if (!tree.length) html += '<div class="empty">Nessuna categoria</div>';
    else html += renderCatTree(tree, 0);
    html += '</div>';
    $('content').innerHTML = html;
}

function renderCatTree(nodes, depth) {
    return nodes.map(c => {
        let html = `<div style="display:flex;justify-content:space-between;align-items:center;padding:0.55rem 0;padding-left:${depth*1.5}rem;border-bottom:1px solid var(--border)">
            <span style="font-weight:${depth===0?'600':'400'}">${depth>0?'└ ':''}${c.title}</span>
            <div style="display:flex;gap:0.3rem">
                <button onclick="showCategoryForm(null,${c.id})" title="Aggiungi sotto-categoria" style="border:none;background:#e8f5e9;padding:0.3rem 0.5rem;border-radius:4px;font-size:0.75rem;cursor:pointer">➕</button>
                <button onclick="showCategoryForm(${c.id})" style="border:none;background:var(--border);padding:0.3rem 0.5rem;border-radius:4px;font-size:0.75rem;cursor:pointer">✏️</button>
                <button onclick="deleteCat(${c.id})" style="border:none;background:#ffebee;padding:0.3rem 0.5rem;border-radius:4px;font-size:0.75rem;cursor:pointer">🗑️</button>
            </div>
        </div>`;
        if (c.children && c.children.length) html += renderCatTree(c.children, depth + 1);
        return html;
    }).join('');
}

function showCategoryForm(editId, parentId) {
    const c = editId ? state.categories.find(x => x.id === editId) : null;
    const title = c ? 'Modifica Categoria' : parentId ? 'Nuova Sotto-categoria' : 'Nuova Categoria';
    showModal(`<h2>${title}</h2>
        <div class="form-group"><label>Nome</label><input id="f-cat-title" value="${c?.title||''}"></div>
        <div class="btn-row"><button class="btn btn-secondary" onclick="closeModal()">Annulla</button>
        <button class="btn btn-primary" onclick="saveCat(${editId||'null'}, ${parentId||'null'})">Salva</button></div>
    `);
}

async function saveCat(id, parentId) {
    const title = $('f-cat-title').value.trim();
    if (!title) return alert('Inserisci un nome');
    if (id) await apiPut(`/categories/${id}`, {title});
    else if (parentId) await apiPost(`/categories/${parentId}/subcategory`, {title});
    else await apiPost('/categories', {title});
    closeModal(); await loadData(); renderCategories();
}

async function deleteCat(id) {
    if (!confirm('Eliminare questa categoria?')) return;
    await apiDelete(`/categories/${id}`); await loadData(); renderCategories();
}

// --- Reports ---
let charts = {};
function destroyCharts() { Object.values(charts).forEach(c => c.destroy()); charts = {}; }

const COLORS = ['#1a73e8','#ea4335','#fbbc04','#34a853','#ff6d01','#46bdc6','#7baaf7','#f07b72','#fcd04f','#57bb8a','#ff8a65','#4dd0e1','#ab47bc','#8d6e63','#78909c'];

async function renderReports() {
    destroyCharts();
    const now = new Date();
    $('content').innerHTML = `
        <div class="card" style="padding:0.75rem">
            <div style="display:flex;gap:0.5rem;flex-wrap:wrap;align-items:center">
                <select id="report-month" onchange="updateReports()" style="padding:0.4rem;border:1px solid var(--border);border-radius:6px;font-size:0.85rem">
                    ${Array.from({length:24}, (_,i) => { const d = new Date(now.getFullYear(), now.getMonth()-i, 1); const m = d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0'); return `<option value="${m}">${m}</option>`; }).join('')}
                </select>
                <button onclick="exportJSON()" class="btn-primary" style="padding:0.4rem 0.8rem;border:none;border-radius:6px;font-size:0.85rem;cursor:pointer;background:var(--primary);color:#fff">📥 Export JSON</button>
            </div>
        </div>
        <div class="report-grid">
            <div class="card"><h3 style="margin-bottom:0.5rem;font-size:0.95rem">Entrate vs Uscite (mensile)</h3><div class="chart-container"><canvas id="chart-monthly"></canvas></div></div>
            <div class="card"><h3 style="margin-bottom:0.5rem;font-size:0.95rem">Spese per Categoria</h3><div class="chart-container"><canvas id="chart-category"></canvas></div></div>
        </div>
        <div class="card"><h3 style="margin-bottom:0.5rem;font-size:0.95rem">Dettaglio Giornaliero per Categoria</h3><div class="chart-container chart-large"><canvas id="chart-daily-cat"></canvas></div></div>
        <div class="card"><h3 style="margin-bottom:0.5rem;font-size:0.95rem">Ultimi 12 Mesi — Entrate vs Uscite</h3><div class="chart-container chart-large"><canvas id="chart-12months"></canvas></div></div>
        <div class="card"><h3 style="margin-bottom:0.5rem;font-size:0.95rem">Andamento Risparmi</h3><div class="chart-container chart-large"><canvas id="chart-savings"></canvas></div></div>
        <div class="card"><h3 style="margin-bottom:0.5rem;font-size:0.95rem">Riepilogo Annuale</h3><div class="chart-container"><canvas id="chart-yearly"></canvas></div></div>
    `;
    await updateReports();
}

async function updateReports() {
    const month = $('report-month').value;
    const [monthly, dailyCat, byCat, savings, yearly] = await Promise.all([
        api('/stats/monthly'), api(`/stats/daily-by-category?month=${month}`),
        api(`/stats/by-category?month=${month}`), api('/stats/savings'), api('/stats/yearly')
    ]);
    drawMonthlyChart(monthly);
    draw12MonthsChart(monthly);
    drawDailyCategoryChart(dailyCat, month);
    drawCategoryChart(byCat);
    drawSavingsChart(savings);
    drawYearlyChart(yearly);
}

function chartOpts(extra = {}) {
    return { responsive: true, maintainAspectRatio: false, ...extra };
}

function drawMonthlyChart(data) {
    if (charts.monthly) charts.monthly.destroy();
    const labels = data.map(r => r.month).reverse();
    charts.monthly = new Chart($('chart-monthly'), {
        type: 'bar', data: { labels, datasets: [
            { label: 'Entrate', data: data.map(r => (r.income||0)/100).reverse(), backgroundColor: '#4caf50' },
            { label: 'Uscite', data: data.map(r => Math.abs(r.expense||0)/100).reverse(), backgroundColor: '#ef5350' }
        ]}, options: chartOpts({ plugins: { legend: { position: 'bottom' } }, scales: { y: { beginAtZero: true } } })
    });
}

function draw12MonthsChart(data) {
    if (charts.twelvemonths) charts.twelvemonths.destroy();
    const last12 = data.slice(0, 12).reverse();
    const labels = last12.map(r => r.month);
    const income = last12.map(r => (r.income||0)/100);
    const expense = last12.map(r => Math.abs(r.expense||0)/100);
    const net = last12.map(r => ((r.income||0)+(r.expense||0))/100);
    charts.twelvemonths = new Chart($('chart-12months'), {
        data: { labels, datasets: [
            { type: 'bar', label: 'Entrate', data: income, backgroundColor: 'rgba(16,185,129,0.7)', borderRadius: 4, yAxisID: 'y' },
            { type: 'bar', label: 'Uscite', data: expense, backgroundColor: 'rgba(239,68,68,0.7)', borderRadius: 4, yAxisID: 'y' },
            { type: 'line', label: 'Netto', data: net, borderColor: '#6366f1', borderWidth: 3, pointRadius: 5, pointBackgroundColor: net.map(v => v >= 0 ? '#10b981' : '#ef4444'), fill: false, tension: 0.3, yAxisID: 'y1' }
        ]}, options: chartOpts({ plugins: { legend: { position: 'bottom' } }, scales: { y: { position: 'left', beginAtZero: true, title: { display: true, text: '€' } }, y1: { position: 'right', title: { display: true, text: 'Netto €' }, grid: { drawOnChartArea: false } } } })
    });
}

function drawDailyCategoryChart(data, month) {
    if (charts.dailyCat) charts.dailyCat.destroy();
    // Pivot: group by day, stack by category
    const days = [...new Set(data.map(r => r.day))].sort();
    const categories = [...new Set(data.map(r => r.category))];
    const datasets = categories.map((cat, i) => ({
        label: cat,
        data: days.map(d => { const row = data.find(r => r.day === d && r.category === cat); return row ? row.total / 100 : 0; }),
        backgroundColor: COLORS[i % COLORS.length]
    }));
    charts.dailyCat = new Chart($('chart-daily-cat'), {
        type: 'bar', data: { labels: days.map(d => d.slice(8)), datasets },
        options: chartOpts({ plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 10 } } }, title: { display: true, text: 'Spese ' + month } }, scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } } })
    });
}

function drawCategoryChart(data) {
    if (charts.category) charts.category.destroy();
    charts.category = new Chart($('chart-category'), {
        type: 'doughnut', data: { labels: data.map(r => r.category), datasets: [{ data: data.map(r => r.total/100), backgroundColor: COLORS.slice(0, data.length) }] },
        options: chartOpts({ plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 10 } } } } })
    });
}

function drawSavingsChart(data) {
    if (charts.savings) charts.savings.destroy();
    const last12 = data.slice(-12);
    const labels = last12.map(r => r.month);
    const net = last12.map(r => ((r.income||0)+(r.expense||0))/100);
    const cumulative = last12.map(r => (r.cumulative_savings||0)/100);
    charts.savings = new Chart($('chart-savings'), {
        data: { labels, datasets: [
            { type: 'bar', label: 'Risparmio mensile', data: net, backgroundColor: net.map(v => v >= 0 ? 'rgba(16,185,129,0.6)' : 'rgba(239,68,68,0.6)'), borderRadius: 4, yAxisID: 'y' },
            { type: 'line', label: 'Risparmi cumulativi', data: cumulative, borderColor: '#6366f1', borderWidth: 3, pointRadius: 4, fill: false, tension: 0.3, yAxisID: 'y1' }
        ]}, options: chartOpts({ plugins: { legend: { position: 'bottom' } }, scales: { y: { position: 'left', title: { display: true, text: 'Mensile €' } }, y1: { position: 'right', title: { display: true, text: 'Cumulativo €' }, grid: { drawOnChartArea: false } } } })
    });
}

function drawYearlyChart(data) {
    if (charts.yearly) charts.yearly.destroy();
    charts.yearly = new Chart($('chart-yearly'), {
        type: 'bar', data: { labels: data.map(r => r.year), datasets: [
            { label: 'Entrate', data: data.map(r => (r.income||0)/100), backgroundColor: '#4caf50' },
            { label: 'Uscite', data: data.map(r => Math.abs(r.expense||0)/100), backgroundColor: '#ef5350' }
        ]}, options: chartOpts({ plugins: { legend: { position: 'bottom' } }, scales: { y: { beginAtZero: true } } })
    });
}

function exportJSON() { window.open(API + '/export', '_blank'); }

// --- Import ---
function renderImport() {
    $('content').innerHTML = `<div class="card">
        <h3 style="margin-bottom:0.75rem">Importa Backup Financisto</h3>
        <p style="color:var(--muted);margin-bottom:1rem;font-size:0.9rem">Carica il file .backup esportato dall'app Financisto.</p>
        <div id="dropzone" style="border:2px dashed var(--border);border-radius:8px;padding:2rem;text-align:center;cursor:pointer" onclick="document.getElementById('fileInput').click()">
            <input type="file" id="fileInput" accept=".backup,.gz" style="display:none" onchange="uploadFile(this.files[0])">
            <p style="font-size:1.1rem;margin-bottom:0.3rem">📁 Tocca per selezionare</p>
            <p style="color:var(--muted);font-size:0.85rem">o trascina il file qui</p>
        </div>
        <div id="status" style="margin-top:1rem;padding:0.75rem;border-radius:8px;display:none"></div>
    </div>
    <div class="card">
        <h3 style="margin-bottom:0.75rem">Database</h3>
        <div class="btn-row">
            <button class="btn btn-primary" onclick="exportDB()">📥 Export DB (JSON)</button>
            <button class="btn btn-secondary" onclick="document.getElementById('dbImportInput').click()">📤 Import DB (JSON)</button>
        </div>
        <input type="file" id="dbImportInput" accept=".json" style="display:none" onchange="importDB(this.files[0])">
        <p style="color:var(--muted);font-size:0.8rem;margin-top:0.75rem">L'export salva l'intero database. L'import sovrascrive tutti i dati.</p>
        <div id="db-status" style="margin-top:0.75rem;padding:0.75rem;border-radius:8px;display:none"></div>
    </div>
    <div class="card">
        <h3 style="margin-bottom:0.75rem">Backup Automatico S3</h3>
        <div id="backup-config-form"></div>
    </div>`;
    const dz = $('dropzone');
    dz.addEventListener('dragover', e => { e.preventDefault(); dz.style.borderColor='var(--primary)'; });
    dz.addEventListener('dragleave', () => dz.style.borderColor='var(--border)');
    dz.addEventListener('drop', e => { e.preventDefault(); uploadFile(e.dataTransfer.files[0]); });
    loadBackupConfig();
}

async function loadBackupConfig() {
    const config = await api('/backup/config');
    $('backup-config-form').innerHTML = `
        <div class="form-group"><label>Abilitato</label><select id="bk-enabled"><option value="true" ${config.enabled?'selected':''}>Sì</option><option value="false" ${!config.enabled?'selected':''}>No</option></select></div>
        <div class="form-group"><label>Bucket</label><input id="bk-bucket" value="${config.bucket||''}"></div>
        <div class="form-group"><label>Region</label><input id="bk-region" value="${config.region||'eu-west-1'}"></div>
        <div class="form-group"><label>Prefix</label><input id="bk-prefix" value="${config.prefix||'financisto-backup/'}"></div>
        <div class="form-group"><label>Access Key</label><input id="bk-access" value="${config.access_key||''}"></div>
        <div class="form-group"><label>Secret Key</label><input id="bk-secret" type="password" value="${config.secret_key||''}" placeholder="Lascia *** per non modificare"></div>
        <div class="form-group"><label>Frequenza (ore)</label><input id="bk-interval" type="number" value="${config.interval_hours||24}"></div>
        <div class="btn-row">
            <button class="btn btn-primary" onclick="saveBackupConfig()">Salva</button>
            <button class="btn btn-secondary" onclick="triggerBackup()">Backup Ora</button>
        </div>
        <div id="bk-status" style="margin-top:0.75rem;padding:0.75rem;border-radius:8px;display:none"></div>
    `;
}

async function saveBackupConfig() {
    const data = {
        enabled: $('bk-enabled').value === 'true',
        bucket: $('bk-bucket').value,
        region: $('bk-region').value,
        prefix: $('bk-prefix').value,
        access_key: $('bk-access').value,
        secret_key: $('bk-secret').value,
        interval_hours: parseInt($('bk-interval').value) || 24
    };
    const res = await apiPost('/backup/config', data);
    const status = $('bk-status');
    status.style.display='block'; status.style.background='#e8f5e9'; status.style.color='var(--success)';
    status.textContent = '✅ Configurazione salvata';
}

async function triggerBackup() {
    const status = $('bk-status');
    status.style.display='block'; status.style.background='#e3f2fd'; status.style.color='var(--text)';
    status.textContent = 'Backup in corso...';
    const res = await fetch(API+'/backup/now', {method:'POST'});
    const data = await res.json();
    if (res.ok) { status.style.background='#e8f5e9'; status.style.color='var(--success)'; status.textContent='✅ Backup salvato: '+data.key; }
    else { status.style.background='#ffebee'; status.style.color='var(--danger)'; status.textContent='❌ '+data.error; }
}

function exportDB() { window.open(API + '/db/export', '_blank'); }

async function importDB(file) {
    if (!file) return;
    if (!confirm('Questo sovrascriverà TUTTI i dati. Continuare?')) return;
    const status = $('db-status');
    status.style.display='block'; status.style.background='#e3f2fd'; status.style.color='var(--text)';
    status.textContent = 'Importazione in corso...';
    const form = new FormData(); form.append('file', file);
    try {
        const res = await fetch(API+'/db/import', {method:'POST', body:form});
        const data = await res.json();
        if (res.ok) { status.style.background='#e8f5e9'; status.style.color='var(--success)'; status.textContent='✅ Database importato!'; await loadData(); }
        else { status.style.background='#ffebee'; status.style.color='var(--danger)'; status.textContent='❌ '+data.error; }
    } catch(e) { status.style.background='#ffebee'; status.style.color='var(--danger)'; status.textContent='❌ '+e.message; }
}

async function uploadFile(file) {
    if (!file) return;
    const status = $('status');
    status.style.display='block'; status.style.background='#e3f2fd'; status.style.color='var(--text)';
    status.textContent = 'Importazione in corso...';
    const form = new FormData(); form.append('file', file);
    try {
        const res = await fetch(API+'/import', {method:'POST', body:form});
        const data = await res.json();
        if (res.ok) { status.style.background='#e8f5e9'; status.style.color='var(--success)'; status.textContent='✅ Importazione completata!'; await loadData(); }
        else { status.style.background='#ffebee'; status.style.color='var(--danger)'; status.textContent='❌ '+data.error; }
    } catch(e) { status.style.background='#ffebee'; status.style.color='var(--danger)'; status.textContent='❌ '+e.message; }
}

// --- Logs ---
let logsInterval = null;

function renderLogs() {
    if (logsInterval) clearInterval(logsInterval);
    $('content').innerHTML = `<div class="card" style="padding:0.75rem">
        <div style="display:flex;gap:0.5rem;align-items:center;margin-bottom:0.75rem">
            <select id="log-service" onchange="fetchLogs()" style="padding:0.4rem;border:1px solid var(--border);border-radius:6px;font-size:0.85rem">
                <option value="">Tutti</option>
                <option value="backend">Backend</option>
                <option value="email-worker">Email Worker</option>
                <option value="db">Database</option>
            </select>
            <span style="font-size:0.8rem;color:var(--muted)">Auto-refresh ogni 5s</span>
        </div>
        <div id="log-output" style="background:#1e293b;color:#e2e8f0;padding:1rem;border-radius:10px;font-family:monospace;font-size:0.8rem;max-height:70vh;overflow-y:auto;white-space:pre-wrap;word-break:break-all"></div>
    </div>`;
    fetchLogs();
    logsInterval = setInterval(fetchLogs, 5000);
}

async function fetchLogs() {
    const service = $('log-service')?.value || '';
    const data = await api(`/logs?service=${service}&lines=100`);
    const output = $('log-output');
    if (!output) return;
    if (service && data.logs) {
        output.textContent = data.logs.join('\n');
    } else if (data.error) {
        output.textContent = 'Error: ' + data.error;
    } else {
        let text = '';
        for (const [svc, lines] of Object.entries(data)) {
            text += `━━━ ${svc.toUpperCase()} ━━━\n${lines.join('\n')}\n\n`;
        }
        output.textContent = text;
    }
    output.scrollTop = output.scrollHeight;
}

// --- Init ---
let scrollHandler = null;
function setupInfiniteScroll(loadFn) {
    if (scrollHandler) window.removeEventListener('scroll', scrollHandler);
    let loading = false;
    scrollHandler = async () => {
        if (loading) return;
        if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 200) {
            loading = true;
            await loadFn();
            loading = false;
        }
    };
    window.addEventListener('scroll', scrollHandler);
}
function clearInfiniteScroll() { if (scrollHandler) { window.removeEventListener('scroll', scrollHandler); scrollHandler = null; } }

(async () => {
    await loadData();
    window.addEventListener('popstate', (e) => {
        if (e.state?.view === 'account' && e.state.id) openAccount(e.state.id);
        else if (e.state?.view) showView(e.state.view);
        else showView('accounts');
    });
    const hash = location.hash.slice(1);
    if (hash && !hash.startsWith('account/')) showView(hash);
    else showView('accounts');
})();
