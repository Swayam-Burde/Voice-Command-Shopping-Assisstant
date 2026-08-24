/**
 * VoiceShop AI — app.js  v3
 *
 * Features:
 *  - Functional sidebar view routing (shopping / search / suggestions / categories / history)
 *  - Search results displayed in CENTER main area
 *  - Silent DELETE for remove buttons (no transcript banner)
 *  - Qty +/- buttons merge into existing cart entry
 *  - Dynamic cart-aware suggestions in right panel
 *  - Full-page suggestions / categories / history views
 */
'use strict';

/* ── API ──────────────────────────────────────────────────── */
/* ── API ──────────────────────────────────────────────────── */
const API = {
  VOICE:            '/api/v1/voice-command',
  CART:             '/api/v1/cart',
  CART_ITEMS:       '/api/v1/cart/items',
  CART_ITEM_MODIFY: (n) => `/api/v1/cart/items/${encodeURIComponent(n)}`,
  CART_ITEM:        (n) => `/api/v1/cart/${encodeURIComponent(n)}`,
  SUGGEST:          '/api/v1/suggestions',
  CATALOG:          '/api/v1/catalog',
};

/* ── Purchase history (mirrors Python mock_db.py) ─────────── */
const PURCHASE_HISTORY = [
  'whole milk','bread','eggs','orange juice','greek yogurt',
  'chicken breast','pasta','olive oil','tomatoes','bananas',
  'cheddar cheese','coffee','oats','spinach','butter',
];

/* ── Emoji map ────────────────────────────────────────────── */
const ITEM_EMOJI = {
  milk:'🥛','almond milk':'🥛','oat milk':'🥛','whole milk':'🥛',
  cheese:'🧀','cheddar cheese':'🧀',yogurt:'🫙','greek yogurt':'🫙',
  butter:'🧈',cream:'🍦',eggs:'🥚',egg:'🥚',
  apple:'🍎',apples:'🍎',orange:'🍊',oranges:'🍊',mango:'🥭',mangoes:'🥭',
  banana:'🍌',bananas:'🍌',watermelon:'🍉',grapes:'🍇',
  strawberry:'🍓',strawberries:'🍓',lemon:'🍋',
  tomato:'🍅',tomatoes:'🍅',potato:'🥔',potatoes:'🥔',
  onion:'🧅',onions:'🧅',spinach:'🥬',carrot:'🥕',carrots:'🥕',
  garlic:'🧄',mushroom:'🍄',mushrooms:'🍄',lettuce:'🥗',
  broccoli:'🥦',cucumber:'🥒',corn:'🌽',
  bread:'🍞',pasta:'🍝',rice:'🍚',flour:'🌾',cereal:'🥣',
  ketchup:'🍅',sauce:'🫙',oil:'🫙','olive oil':'🫙',
  water:'💧',juice:'🧃',soda:'🥤',tea:'🍵',coffee:'☕',
  'orange juice':'🧃','green tea':'🍵','coconut water':'🥥',
  chips:'🍿','potato chips':'🍿',popcorn:'🍿',cookies:'🍪',
  chocolate:'🍫','dark chocolate':'🍫',candy:'🍬',nuts:'🥜',
  'mixed nuts':'🥜','peanut butter':'🥜',
  sugar:'🍬',salt:'🧂',dal:'🫘','moong dal':'🫘',lentils:'🫘',
  paneer:'🧀',ghee:'🫙',dahi:'🫙',
  soap:'🧼',shampoo:'🧴','toilet paper':'🧻',
  chicken:'🍗','chicken breast':'🍗',
  oats:'🌾',
};

const CAT_EMOJI = { Dairy:'🥛', Produce:'🥦', Snacks:'🍿', Beverages:'🥤', Pantry:'🫙', Other:'📦' };
const CAT_ORDER = ['Dairy','Produce','Beverages','Snacks','Pantry','Other'];

function itemEmoji(name) {
  const n = (name||'').toLowerCase().trim();
  if (ITEM_EMOJI[n]) return ITEM_EMOJI[n];
  for (const [k,v] of Object.entries(ITEM_EMOJI)) { if (n.includes(k)) return v; }
  return '🛒';
}

/* ── State ────────────────────────────────────────────────── */
const state = {
  isRecording: false,
  isLoading: false,
  timerInterval: null,
  currentCart: [],
  currentSuggestions: null,
  currentSearchResults: [],
  storeCatalog: [],
  activeView: 'shopping',
  activeCatFilter: 'All',
};

/* ── DOM refs ─────────────────────────────────────────────── */
const el = {
  micBtn:           document.getElementById('micBtn'),
  micIcon:          document.getElementById('micIcon'),
  stopIcon:         document.getElementById('stopIcon'),
  micLabel:         document.getElementById('micLabel'),
  recTimer:         document.getElementById('recTimer'),
  timerDisplay:     document.getElementById('timerDisplay'),
  waveLeft:         document.getElementById('waveLeft'),
  waveRight:        document.getElementById('waveRight'),
  bubbleHint:       document.getElementById('bubbleHint'),
  bubbleResp:       document.getElementById('bubbleResponse'),
  intentTag:        document.getElementById('intentTag'),
  bubbleTrans:      document.getElementById('bubbleTranscript'),
  bubbleMsg:        document.getElementById('bubbleMsg'),
  loadingBar:       document.getElementById('loadingBar'),
  textInput:        document.getElementById('textInput'),
  sendBtn:          document.getElementById('sendBtn'),
  headerCount:      document.getElementById('headerCount'),
  pageTitle:        document.getElementById('pageTitle'),
  clearCartBtn:     document.getElementById('clearCartBtn'),
  themeToggle:      document.getElementById('themeToggle'),
  themeIcon:        document.getElementById('themeIcon'),
  navItems:         document.querySelectorAll('.nav-item[data-view]'),
  // Views
  shoppingView:     document.getElementById('shoppingView'),
  emptyBoard:       document.getElementById('emptyBoard'),
  cartSearchNotice: document.getElementById('cartSearchNotice'),
  cartSearchBadge:  document.getElementById('cartSearchBadge'),
  cartToSearchBtn:  document.getElementById('cartToSearchBtn'),
  cartToStoreBtn:   document.getElementById('cartToStoreBtn'),
  emptyToStoreBtn:  document.getElementById('emptyToStoreBtn'),
  searchView:       document.getElementById('searchView'),
  searchResultsGrid:document.getElementById('searchResultsGrid'),
  searchTotalBadge: document.getElementById('searchTotalBadge'),
  backToShoppingBtn:document.getElementById('backToShoppingBtn'),
  backToStoreBtn:   document.getElementById('backToStoreBtn'),
  suggestionsView:  document.getElementById('suggestionsView'),
  suggestionsGrid:  document.getElementById('suggestionsGrid'),
  refreshSugBtn:    document.getElementById('refreshSugBtn'),
  categoriesView:   document.getElementById('categoriesView'),
  catChips:         document.getElementById('catChips'),
  catItemsGrid:     document.getElementById('catItemsGrid'),
  storeToSearchBtn: document.getElementById('storeToSearchBtn'),
  storeToCartBtn:   document.getElementById('storeToCartBtn'),
  storeCartBadge:   document.getElementById('storeCartBadge'),
  historyView:      document.getElementById('historyView'),
  historyList:      document.getElementById('historyList'),
  reorderAllBtn:    document.getElementById('reorderAllBtn'),
  navSearch:        document.getElementById('navSearch'),
  // Right panel
  rightSubCards:    document.getElementById('rightSubCards'),
  rightSeasonalCards:document.getElementById('rightSeasonalCards'),
  rightRestockCards: document.getElementById('rightRestockCards'),
  // Bubble action row
  bubbleActionRow:  document.getElementById('bubbleActionRow'),
};

/* ── View routing ─────────────────────────────────────────── */
const VIEW_TITLES = {
  shopping: 'Shopping List',
  search:   'Search Results',
  suggestions: 'Smart Suggestions',
  categories: 'Store Catalog',
  history: 'History',
};

function switchView(name) {
  state.activeView = name;
  document.querySelectorAll('.view-section').forEach(s => s.classList.remove('active'));
  document.getElementById(`${name}View`)?.classList.add('active');
  el.navItems.forEach(b => { b.classList.toggle('active', b.dataset.view === name); });
  el.pageTitle.textContent = VIEW_TITLES[name] || name;

  // Show/hide search nav
  el.navSearch.style.display = (name === 'search' || (state.currentSearchResults && state.currentSearchResults.length > 0)) ? 'flex' : 'none';

  // Populate on-demand
  if (name === 'suggestions') renderSuggestionsPage();
  if (name === 'categories')  renderCategoriesView();
  if (name === 'history')     renderHistoryView();
}

/* ── Recording ────────────────────────────────────────────── */
let mediaRecorder = null, audioChunks = [];

function bestMime() {
  const c = ['audio/webm;codecs=opus','audio/webm','audio/ogg;codecs=opus','audio/mp4'];
  return c.find(t => MediaRecorder.isTypeSupported(t)) || '';
}

async function startRecording() {
  if (state.isLoading) return;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];
    const mime = bestMime();
    mediaRecorder = new MediaRecorder(stream, mime ? { mimeType: mime } : {});
    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      const finalMime = mediaRecorder.mimeType || 'audio/webm';
      const ext = finalMime.includes('ogg') ? 'ogg' : finalMime.includes('mp4') ? 'mp4' : 'webm';
      const fd = new FormData();
      fd.append('audio', new Blob(audioChunks, { type: finalMime }), `recording.${ext}`);
      await callVoiceAPI(fd);
    };
    mediaRecorder.start(200);
    state.isRecording = true;
    setRecordingUI(true);
    startTimer();
  } catch(err) {
    alert(err.name === 'NotAllowedError'
      ? 'Microphone access denied. Please allow mic permissions.'
      : `Mic error: ${err.message}`);
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
  state.isRecording = false;
  setRecordingUI(false);
  stopTimer();
}

let timerStart = null;
function startTimer() {
  timerStart = Date.now();
  el.recTimer.classList.remove('hidden');
  state.timerInterval = setInterval(() => {
    const s = Math.floor((Date.now() - timerStart) / 1000);
    el.timerDisplay.textContent = `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`;
  }, 500);
}
function stopTimer() {
  clearInterval(state.timerInterval);
  el.recTimer.classList.add('hidden');
  el.timerDisplay.textContent = '0:00';
}

function setRecordingUI(on) {
  el.micBtn.classList.toggle('recording', on);
  el.micIcon.classList.toggle('hidden', on);
  el.stopIcon.classList.toggle('hidden', !on);
  el.micLabel.textContent = on ? 'Tap to stop' : 'Speak Now';
  el.micBtn.setAttribute('aria-label', on ? 'Stop recording' : 'Start recording');
  [el.waveLeft, el.waveRight].forEach(w => w.classList.toggle('waveform-active', on));
}

/* ── Text command ─────────────────────────────────────────── */
function sendText(text) {
  if (!text || !text.trim() || state.isLoading) return;
  const fd = new FormData();
  fd.append('transcript_override', text.trim());
  el.textInput.value = '';
  callVoiceAPI(fd);
}

/* ── Voice API call ───────────────────────────────────────── */
async function callVoiceAPI(formData) {
  setLoading(true);
  try {
    const res = await fetch(API.VOICE, { method:'POST', body:formData });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      throw new Error(d.detail || `Server error ${res.status}`);
    }
    const data = await res.json();
    handleVoiceResponse(data);
  } catch(err) {
    showBubble('', 'UNKNOWN', `⚠️ ${err.message}`);
  } finally {
    setLoading(false);
  }
}

/* ── Handle response ──────────────────────────────────────── */
function handleVoiceResponse(data) {
  const hasSearchResults = Array.isArray(data.search_results) && data.search_results.length > 0;
  showBubble(data.transcript || '', data.intent || 'UNKNOWN', data.message || '', data.search_results);

  if (Array.isArray(data.cart)) {
    state.currentCart = data.cart;
    renderCart(data.cart);
    updateItemCount(data.cart.length);
  }

  if (data.suggestions) {
    state.currentSuggestions = data.suggestions;
    renderRightPanel(data.suggestions);
  }

  // If search results exist, render them and switch to search view
  if (hasSearchResults) {
    state.currentSearchResults = data.search_results;
    renderSearchResults(data.search_results);
    el.navSearch.style.display = 'flex';
    switchView('search');
  } else if (state.activeView === 'shopping' || data.intent === 'ADD_ITEM' || data.intent === 'REMOVE_ITEM' || data.intent === 'MODIFY_QUANTITY') {
    if (state.activeView !== 'search') switchView('shopping');
  }
}

/* ── Silent item remove ───────────────────────────────────── */
async function removeItemSilent(name) {
  try {
    const res = await fetch(API.CART_ITEM(name), { method:'DELETE' });
    if (res.ok) {
      const data = await res.json();
      state.currentCart = data.cart;
      renderCart(data.cart);
      updateItemCount(data.total_items || data.cart.length);
    }
  } catch(e) { console.error('Remove error:', e); }
}

/* ── Direct fast UI cart operations (0 LLM tokens, instant response) ── */
async function addItemDirect(itemObj, switchToCart = false) {
  try {
    const payload = typeof itemObj === 'string'
      ? { item_name: itemObj, quantity: 1 }
      : {
          item_name: itemObj.name || itemObj.item_name,
          quantity: itemObj.quantity || 1,
          category: itemObj.category || 'Other',
          price_estimate: itemObj.price != null ? itemObj.price : itemObj.price_estimate,
        };

    const res = await fetch(API.CART_ITEMS, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      const data = await res.json();
      state.currentCart = data.cart;
      renderCart(data.cart);
      updateItemCount(data.total_items || data.cart.length);
      if (switchToCart) switchView('shopping');
    }
  } catch (err) {
    console.error('Direct add error:', err);
  }
}

async function modifyQty(name, delta, currentQty) {
  try {
    const res = await fetch(API.CART_ITEM_MODIFY(name), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ delta: delta }),
    });
    if (res.ok) {
      const data = await res.json();
      state.currentCart = data.cart;
      renderCart(data.cart);
      updateItemCount(data.total_items || data.cart.length);
    }
  } catch (err) {
    console.error('Direct modify qty error:', err);
  }
}

/* ── Loading ──────────────────────────────────────────────── */
function setLoading(on) {
  state.isLoading = on;
  el.loadingBar.classList.toggle('hidden', !on);
  el.sendBtn.disabled = on;
  el.micBtn.disabled  = on;
}

/* ── Bubble ───────────────────────────────────────────────── */
function showBubble(transcript, intent, message, searchResults) {
  el.bubbleHint.classList.add('hidden');
  el.bubbleResp.classList.remove('hidden');
  el.bubbleTrans.textContent = transcript;
  el.bubbleMsg.textContent   = message;
  el.intentTag.textContent   = intent.replace(/_/g,' ');
  el.intentTag.className     = `intent-tag ib-${intent}`;

  if (el.bubbleActionRow) {
    el.bubbleActionRow.innerHTML = '';
    const hasSearch = Array.isArray(searchResults) && searchResults.length > 0;
    if (hasSearch) {
      el.bubbleActionRow.classList.remove('hidden');

      const viewSearchBtn = document.createElement('button');
      viewSearchBtn.className = 'bubble-cta-btn';
      viewSearchBtn.innerHTML = `🔍 View ${searchResults.length} Products Found →`;
      viewSearchBtn.addEventListener('click', () => switchView('search'));
      el.bubbleActionRow.appendChild(viewSearchBtn);

      const storeBtn = document.createElement('button');
      storeBtn.className = 'bubble-cta-btn secondary';
      storeBtn.innerHTML = `🏬 Browse Store`;
      storeBtn.addEventListener('click', () => switchView('categories'));
      el.bubbleActionRow.appendChild(storeBtn);
    } else {
      el.bubbleActionRow.classList.add('hidden');
    }
  }
}

/* ── Update header pill ───────────────────────────────────── */
function updateItemCount(n) {
  el.headerCount.textContent = `${n} item${n !== 1 ? 's' : ''}`;
}

/* ══════════════════════════════════════════════════════════
   RENDER: SHOPPING LIST (categorized cards)
══════════════════════════════════════════════════════════ */
function renderCart(cart) {
  // Clear only the cat-sections (not the emptyBoard)
  el.shoppingView.querySelectorAll('.cat-section').forEach(s => s.remove());

  if (el.storeCartBadge) el.storeCartBadge.textContent = cart.length;

  // Search results notice in Cart top bar
  if (state.currentSearchResults && state.currentSearchResults.length > 0) {
    if (el.cartSearchNotice) el.cartSearchNotice.classList.remove('hidden');
    if (el.cartSearchBadge) el.cartSearchBadge.textContent = state.currentSearchResults.length;
    if (el.storeToSearchBtn) el.storeToSearchBtn.style.display = 'inline-flex';
  } else {
    if (el.cartSearchNotice) el.cartSearchNotice.classList.add('hidden');
    if (el.storeToSearchBtn) el.storeToSearchBtn.style.display = 'none';
  }

  if (!cart.length) {
    el.emptyBoard.classList.remove('hidden');
    return;
  }
  el.emptyBoard.classList.add('hidden');

  const groups = {};
  cart.forEach(item => {
    const cat = item.category || 'Other';
    (groups[cat] = groups[cat] || []).push(item);
  });

  const sortedCats = [
    ...CAT_ORDER.filter(c => groups[c]),
    ...Object.keys(groups).filter(c => !CAT_ORDER.includes(c)),
  ];

  sortedCats.forEach(cat => {
    const section = document.createElement('div');
    section.className = 'cat-section';

    const label = document.createElement('div');
    label.className = `cat-label cat-${cat}`;
    label.innerHTML = `<span>${CAT_EMOJI[cat]||'📦'}</span> ${cat}`;
    section.appendChild(label);

    const grid = document.createElement('div');
    grid.className = 'product-grid';
    groups[cat].forEach(item => grid.appendChild(makeCard(item)));
    section.appendChild(grid);

    el.shoppingView.appendChild(section);
  });
}

function makeCard(item) {
  const card = document.createElement('div');
  card.className = 'product-card';
  const qty = Number(item.quantity);
  const qtyStr = qty === Math.floor(qty) ? qty : qty.toFixed(1);
  const qtyLabel = item.unit ? `${qtyStr} ${item.unit}` : `×${qtyStr}`;
  const emoji = itemEmoji(item.item_name);
  const cat = item.category || 'Other';

  card.innerHTML = `
    <button class="card-remove" title="Remove ${esc(item.item_name)}" aria-label="Remove ${esc(item.item_name)}">✕</button>
    <div class="card-emoji">${emoji}</div>
    <div class="card-name">${esc(item.item_name)}</div>
    ${item.price_estimate != null ? `<div class="card-price">₹${Number(item.price_estimate).toFixed(0)}</div>` : ''}
    <div class="qty-row">
      <button class="qty-btn qty-minus" aria-label="Decrease">−</button>
      <span class="qty-val">${esc(qtyLabel)}</span>
      <button class="qty-btn qty-plus" aria-label="Increase">+</button>
    </div>
    <div class="card-badge cat-${cat}">${CAT_EMOJI[cat]||'📦'} ${cat}</div>
  `;

  card.querySelector('.card-remove').addEventListener('click', e => {
    e.stopPropagation();
    card.style.opacity = '0.4';
    removeItemSilent(item.item_name);
  });
  card.querySelector('.qty-minus').addEventListener('click', e => {
    e.stopPropagation();
    qty <= 1 ? removeItemSilent(item.item_name) : modifyQty(item.item_name, -1, qty);
  });
  card.querySelector('.qty-plus').addEventListener('click', e => {
    e.stopPropagation();
    modifyQty(item.item_name, +1, qty);
  });
  return card;
}

/* ══════════════════════════════════════════════════════════
   RENDER: SEARCH RESULTS (center view)
══════════════════════════════════════════════════════════ */
function renderSearchResults(results) {
  el.searchResultsGrid.innerHTML = '';
  el.searchTotalBadge.textContent = results.length;

  if (!results.length) {
    el.searchResultsGrid.innerHTML =
      '<p style="font-size:13px;color:var(--txt3);padding:12px 0">No products matched your search. Try a different query.</p>';
    return;
  }

  results.forEach(p => {
    const card = document.createElement('div');
    card.className = 'search-card';
    const tagsHtml = (p.tags||[]).slice(0,3).map(t => `<span class="sc-tag">${esc(t)}</span>`).join('');
    card.innerHTML = `
      <div class="sc-name">${esc(p.name)}</div>
      ${p.brand ? `<div class="sc-brand">by ${esc(p.brand)}</div>` : ''}
      ${p.price != null ? `<div class="sc-price">₹${Number(p.price * 83).toFixed(0)} <small style="font-size:9px;color:var(--txt3)">(~$${Number(p.price).toFixed(2)})</small></div>` : ''}
      ${tagsHtml ? `<div class="sc-tags">${tagsHtml}</div>` : ''}
      <div class="sc-actions">
        <button class="sc-btn add">+ Add to List</button>
        <button class="sc-btn sub">Substitutes</button>
      </div>
    `;
    card.querySelector('.sc-btn.add').addEventListener('click', e => {
      e.stopPropagation();
      addItemDirect(p, true);
    });
    card.querySelector('.sc-btn.sub').addEventListener('click', e => {
      e.stopPropagation();
      sendText(`Suggest substitutes for ${p.name}`);
    });
    el.searchResultsGrid.appendChild(card);
  });
}

/* ══════════════════════════════════════════════════════════
   RENDER: RIGHT PANEL (quick picks)
══════════════════════════════════════════════════════════ */
function renderRightPanel(sugg) {
  // Substitutes
  el.rightSubCards.innerHTML = '';
  const subs = sugg.substitutes || [];
  if (!subs.length) {
    el.rightSubCards.innerHTML = '<p style="font-size:11px;color:var(--txt3)">None available</p>';
  } else {
    subs.forEach(sub => {
      const c = document.createElement('div');
      c.className = 'sub-card';
      c.innerHTML = `
        <div class="sub-orig">${esc(sub.original)}</div>
        <div class="sub-new">${esc(sub.substitute)}</div>
        <div class="sub-reason">${esc(sub.reason)}</div>
      `;
      c.addEventListener('click', () => addItemDirect(sub.substitute, true));
      el.rightSubCards.appendChild(c);
    });
  }

  // Seasonal
  renderRightChips(el.rightSeasonalCards, sugg.seasonal_recommendations || []);
  // Restock
  renderRightChips(el.rightRestockCards, sugg.historical_recommendations || []);
}

function renderRightChips(container, items) {
  container.innerHTML = '';
  if (!items.length) {
    container.innerHTML = '<p style="font-size:11px;color:var(--txt3)">None available</p>';
    return;
  }
  items.forEach(name => {
    const c = document.createElement('div');
    c.className = 'sug-card';
    c.innerHTML = `
      <div class="sug-name">${esc(name)}</div>
      <div class="sug-actions">
        <button class="sug-btn add">+ Add</button>
      </div>
    `;
    c.querySelector('.sug-btn.add').addEventListener('click', e => {
      e.stopPropagation();
      addItemDirect(name, false);
    });
    container.appendChild(c);
  });
}

/* ══════════════════════════════════════════════════════════
   RENDER: SUGGESTIONS full page
══════════════════════════════════════════════════════════ */
function renderSuggestionsPage() {
  if (!state.currentSuggestions) return;
  const sugg = state.currentSuggestions;
  el.suggestionsGrid.innerHTML = '';

  const sections = [
    { title:'🔁 Restock Soon',    icon:'', items: sugg.historical_recommendations||[], type:'chip' },
    { title:'🌿 Seasonal Picks',  icon:'', items: sugg.seasonal_recommendations||[],  type:'chip' },
    { title:'💡 Substitutes',     icon:'', items: sugg.substitutes||[],               type:'sub'  },
  ];

  sections.forEach(sec => {
    const card = document.createElement('div');
    card.className = 'sug-section-card';
    const titleEl = document.createElement('div');
    titleEl.className = 'sug-section-title';
    titleEl.textContent = sec.title;
    card.appendChild(titleEl);

    if (!sec.items.length) {
      const p = document.createElement('p');
      p.style.cssText = 'font-size:12px;color:var(--txt3)';
      p.textContent = 'No suggestions yet';
      card.appendChild(p);
    } else if (sec.type === 'chip') {
      sec.items.forEach(name => {
        const row = document.createElement('div');
        row.className = 'sug-card';
        row.innerHTML = `
          <div class="sug-name">${esc(name)}</div>
          <div class="sug-actions"><button class="sug-btn add">+ Add to List</button></div>
        `;
        row.querySelector('.sug-btn.add').addEventListener('click', e => {
          e.stopPropagation();
          addItemDirect(name, true);
        });
        card.appendChild(row);
      });
    } else {
      sec.items.forEach(sub => {
        const row = document.createElement('div');
        row.className = 'sub-card';
        row.style.cursor = 'pointer';
        row.innerHTML = `
          <div class="sub-orig">${esc(sub.original)}</div>
          <div class="sub-new">${esc(sub.substitute)}</div>
          <div class="sub-reason">${esc(sub.reason)}</div>
        `;
        row.addEventListener('click', () => {
          addItemDirect(sub.substitute, true);
        });
        card.appendChild(row);
      });
    }

    el.suggestionsGrid.appendChild(card);
  });
}

/* ══════════════════════════════════════════════════════════
   RENDER: STORE PRODUCT CATALOG VIEW
══════════════════════════════════════════════════════════ */
async function renderCategoriesView() {
  if (!state.storeCatalog || !state.storeCatalog.length) {
    try {
      const res = await fetch(API.CATALOG);
      if (res.ok) {
        state.storeCatalog = await res.json();
      }
    } catch(e) { console.error('Catalog fetch error:', e); }
  }

  const catalog = state.storeCatalog || [];
  const allCats = ['All', 'Produce', 'Dairy', 'Meat', 'Beverages', 'Snacks', 'Pantry', 'Personal Care'];

  // Chips
  el.catChips.innerHTML = '';
  allCats.forEach(cat => {
    const count = cat === 'All' ? catalog.length : catalog.filter(p => (p.category||'Other') === cat).length;
    if (cat !== 'All' && count === 0) return;
    const chip = document.createElement('button');
    chip.className = `cat-chip${cat === state.activeCatFilter ? ' active' : ''}`;
    chip.textContent = `${cat === 'All' ? '🏬' : (CAT_EMOJI[cat]||'📦')} ${cat} (${count})`;
    chip.addEventListener('click', () => {
      state.activeCatFilter = cat;
      renderCategoriesView();
    });
    el.catChips.appendChild(chip);
  });

  // Products Grid
  el.catItemsGrid.innerHTML = '';
  const filtered = state.activeCatFilter === 'All'
    ? catalog
    : catalog.filter(p => (p.category||'Other') === state.activeCatFilter);

  if (!filtered.length) {
    el.catItemsGrid.innerHTML = '<p style="font-size:13px;color:var(--txt3);padding:16px 0">No products found in this category.</p>';
    return;
  }

  filtered.forEach(p => {
    const card = document.createElement('div');
    card.className = 'search-card';
    const tagsHtml = (p.tags||[]).slice(0,3).map(t => `<span class="sc-tag">${esc(t)}</span>`).join('');
    card.innerHTML = `
      <div class="sc-name">${esc(p.name)}</div>
      ${p.brand ? `<div class="sc-brand">by ${esc(p.brand)}</div>` : ''}
      ${p.price != null ? `<div class="sc-price">₹${Number(p.price * 83).toFixed(0)} <small style="font-size:9px;color:var(--txt3)">(~$${Number(p.price).toFixed(2)})</small></div>` : ''}
      ${tagsHtml ? `<div class="sc-tags">${tagsHtml}</div>` : ''}
      <div class="sc-actions">
        <button class="sc-btn add">+ Add to Cart</button>
        <button class="sc-btn sub">Substitutes</button>
      </div>
    `;
    card.querySelector('.sc-btn.add').addEventListener('click', e => {
      e.stopPropagation();
      addItemDirect(p, false);
    });
    card.querySelector('.sc-btn.sub').addEventListener('click', e => {
      e.stopPropagation();
      sendText(`Suggest substitutes for ${p.name}`);
    });
    el.catItemsGrid.appendChild(card);
  });
}

/* ══════════════════════════════════════════════════════════
   RENDER: HISTORY VIEW
══════════════════════════════════════════════════════════ */
function renderHistoryView() {
  el.historyList.innerHTML = '';
  PURCHASE_HISTORY.forEach(name => {
    const row = document.createElement('div');
    row.className = 'history-item';
    row.innerHTML = `
      <div class="history-emoji">${itemEmoji(name)}</div>
      <div class="history-name">${esc(name)}</div>
      <button class="history-reorder" data-name="${esc(name)}">+ Reorder</button>
    `;
    row.querySelector('.history-reorder').addEventListener('click', e => {
      e.stopPropagation();
      addItemDirect(name, true);
    });
    el.historyList.appendChild(row);
  });
}

/* ══════════════════════════════════════════════════════════
   HYDRATE on load
══════════════════════════════════════════════════════════ */
async function hydrate() {
  try {
    const res = await fetch(API.CART);
    if (res.ok) {
      const d = await res.json();
      state.currentCart = d.cart || [];
      renderCart(d.cart || []);
      updateItemCount((d.cart||[]).length);
    }
  } catch(e) { /* offline */ }

  try {
    const res = await fetch(API.SUGGEST);
    if (res.ok) {
      const d = await res.json();
      state.currentSuggestions = d;
      renderRightPanel(d);
    }
  } catch(e) { /* offline */ }
}

/* ── Clear cart ───────────────────────────────────────────── */
async function clearAllItems() {
  if (!confirm('Clear your entire shopping list?')) return;
  try {
    const res = await fetch(API.CART, { method:'DELETE' });
    if (res.ok) {
      state.currentCart = [];
      renderCart([]);
      updateItemCount(0);
      el.bubbleHint.classList.remove('hidden');
      el.bubbleResp.classList.add('hidden');
      switchView('shopping');
    }
  } catch(e) { console.error(e); }
}

/* ── Theme ────────────────────────────────────────────────── */
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  el.themeIcon.innerHTML = t === 'dark'
    ? '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>'
    : '<path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>';
}

/* ── Utility ──────────────────────────────────────────────── */
function esc(str) {
  const d = document.createElement('div');
  d.textContent = String(str||'');
  return d.innerHTML;
}

/* ══════════════════════════════════════════════════════════
   EVENT LISTENERS
══════════════════════════════════════════════════════════ */

// Mic
el.micBtn.addEventListener('click', () => {
  if (state.isLoading) return;
  state.isRecording ? stopRecording() : startRecording();
});

// Text input
el.sendBtn.addEventListener('click', () => sendText(el.textInput.value));
el.textInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendText(el.textInput.value); }
});

// Sidebar navigation
el.navItems.forEach(btn => {
  btn.addEventListener('click', () => switchView(btn.dataset.view));
});

// View routing actions
el.backToShoppingBtn?.addEventListener('click', () => switchView('shopping'));
el.backToStoreBtn?.addEventListener('click', () => switchView('categories'));
el.cartToSearchBtn?.addEventListener('click', () => switchView('search'));
el.cartToStoreBtn?.addEventListener('click', () => switchView('categories'));
el.emptyToStoreBtn?.addEventListener('click', () => switchView('categories'));
el.storeToSearchBtn?.addEventListener('click', () => switchView('search'));
el.storeToCartBtn?.addEventListener('click', () => switchView('shopping'));

// Refresh suggestions
el.refreshSugBtn.addEventListener('click', async () => {
  el.suggestionsGrid.innerHTML = '<div class="skel-card" style="grid-column:1/-1;height:80px"></div>';
  try {
    const res = await fetch(API.SUGGEST);
    if (res.ok) {
      const d = await res.json();
      state.currentSuggestions = d;
      renderRightPanel(d);
      renderSuggestionsPage();
    }
  } catch(e) { console.error(e); }
});

// Reorder all history
el.reorderAllBtn.addEventListener('click', async () => {
  const topItems = PURCHASE_HISTORY.slice(0, 5);
  for (const item of topItems) {
    await addItemDirect(item, false);
  }
  switchView('shopping');
});

// Clear cart
el.clearCartBtn.addEventListener('click', clearAllItems);

// Theme
el.themeToggle.addEventListener('click', () => {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  localStorage.setItem('vc-theme', next);
});

/* ══════════════════════════════════════════════════════════
   BOOT
══════════════════════════════════════════════════════════ */
(function init() {
  applyTheme(localStorage.getItem('vc-theme') || 'light');
  renderHistoryView();
  hydrate();
})();
