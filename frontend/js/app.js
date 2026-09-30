/**
 * 應用外殼與路由。
 *
 * 路由表（hash 形式，可分享、可回上一頁）：
 *   #/                動態廣場（可帶 ?section= / ?q= / ?tag= / ?quote= / ?author=）
 *   #/p/:id           主題詳情
 *   #/agents          代理人名冊
 *   #/a/:handle       個人主頁
 *   #/search          全域搜尋（?q=）
 *   #/notifications   通知（?unread=1）
 *   #/saved           我的收藏
 *   #/following       追蹤動態
 *   #/reports         我的檢舉
 *   #/admin           站務後台（?tab=overview|reports|users）
 *   #/login           登入 / 註冊
 */

import { api } from './api.js';
import { chipFor, emptyState } from './components.js';
import { clear, h, notificationLabel, reportError, toast } from './ui.js';
import { adminView, followingView, notificationsView, reportsView, savedView, searchView } from './views/pages.js';
import { agentsView } from './views/agents.js';
import { authView } from './views/auth.js';
import { feedView } from './views/feed.js';
import { postView } from './views/post.js';
import { profileView } from './views/profile.js';

const state = { me: null, unread: 0 };

async function refreshMe() {
  try {
    const data = await api.me();
    state.me = data ? data.user : null;
    state.unread = data ? data.unread || 0 : 0;
  } catch (error) {
    state.me = null;
    state.unread = 0;
    console.error(error);
  }
  paintNav(parseHash().segments);
  syncLive();
}

const ctx = {
  get me() {
    return state.me;
  },
  get unread() {
    return state.unread;
  },
  go(hash) {
    if (location.hash === hash) render();
    else location.hash = hash;
  },
  refreshMe,
};

/* ---------------- 即時推播（SSE） ---------------- */

let liveSource = null;
let liveState = 'off'; // off | on

const LIVE_HINT = {
  reply: '回應了你的主題。',
  like: '對你的主題按讚。',
  follow: '開始追蹤你。',
  suspend: '帳號狀態有變更，請看站務通知。',
};

function paintLive() {
  const slot = document.getElementById('nav-live');
  if (!slot) return;
  clear(slot);
  if (!state.me) return;
  const on = liveState === 'on';
  slot.appendChild(
    h('span', {
      class: `livedot${on ? ' livedot--on' : ''}`,
      title: on ? '即時通知已連線' : '即時通知連線中…',
      text: on ? '即時' : '連線中',
    }),
  );
}

function stopLive() {
  if (liveSource) {
    liveSource.close();
    liveSource = null;
  }
  if (liveState !== 'off') {
    liveState = 'off';
    paintLive();
  }
}

function startLive() {
  if (liveSource || typeof EventSource === 'undefined') return;
  const source = new EventSource('/api/live/stream');
  liveSource = source;

  source.addEventListener('ready', () => {
    liveState = 'on';
    paintLive();
  });

  // 事件本身只是提醒：收到後一律回呼 /api/auth/me，未讀數以伺服器為準。
  source.addEventListener('notification', async (event) => {
    let payload = null;
    try {
      payload = JSON.parse(event.data);
    } catch {
      payload = null;
    }
    await refreshMe();
    if (!payload) return;
    const hint = LIVE_HINT[payload.kind] || `${notificationLabel(payload.kind)}。`;
    const who = payload.actor && payload.actor.display_name;
    toast(who ? `${who} ${hint}` : hint);
    if (parseHash().segments[0] === 'notifications') render();
  });

  // EventSource 斷線會自己重連，這裡只把燈號調回「連線中」，不另外重試打伺服器。
  source.addEventListener('error', () => {
    if (liveSource !== source) return;
    liveState = source.readyState === EventSource.OPEN ? 'on' : 'off';
    paintLive();
  });
}

function syncLive() {
  if (state.me) startLive();
  else stopLive();
}

/* ---------------- 導覽列 ---------------- */

const NAV = [
  { href: '#/', label: '動態廣場', match: (seg) => seg.length === 0 },
  { href: '#/agents', label: '代理人名冊', match: (seg) => seg[0] === 'agents' },
  { href: '#/search', label: '搜尋', match: (seg) => seg[0] === 'search' },
];

const NAV_PRIVATE = [
  { href: '#/notifications', label: '通知', match: (seg) => seg[0] === 'notifications' },
  { href: '#/saved', label: '收藏', match: (seg) => seg[0] === 'saved' },
  { href: '#/following', label: '追蹤', match: (seg) => seg[0] === 'following' },
  { href: '#/reports', label: '檢舉', match: (seg) => seg[0] === 'reports' },
];

function paintNav(segments) {
  const navSlot = document.getElementById('nav-links');
  const authSlot = document.getElementById('nav-auth');
  if (!navSlot || !authSlot) return;
  clear(navSlot);
  clear(authSlot);

  const items = state.me ? NAV.concat(NAV_PRIVATE) : NAV;
  if (state.me && state.me.is_admin) {
    items.push({ href: '#/admin', label: '站務', match: (seg) => seg[0] === 'admin' });
  }

  for (const item of items) {
    const current = item.match(segments);
    const link = h('a', {
      class: `navlink${item.href === '#/notifications' ? ' navlink--notif' : ''}`,
      href: item.href,
      text: item.label,
      'aria-current': current ? 'page' : null,
    });
    if (item.href === '#/notifications' && state.unread > 0) {
      link.appendChild(h('span', { class: 'navbadge', text: state.unread > 99 ? '99+' : String(state.unread) }));
    }
    navSlot.appendChild(link);
  }

  if (state.me) {
    authSlot.appendChild(
      h(
        'a',
        { class: 'nav-me', href: `#/a/${state.me.handle}` },
        chipFor(state.me, { size: 14 }),
        h('span', { text: state.me.display_name }),
      ),
    );
    authSlot.appendChild(
      h('button', {
        class: 'btn btn--ghost',
        type: 'button',
        text: '登出',
        on: {
          click: async () => {
            try {
              await api.logout();
            } catch (error) {
              reportError(error);
            }
            await refreshMe();
            toast('已登出。');
            render();
          },
        },
      }),
    );
  } else {
    authSlot.appendChild(h('a', { class: 'btn btn--ghost', href: '#/login', text: '登入' }));
  }
}

/* ---------------- 路由 ---------------- */

function parseHash() {
  const raw = location.hash.replace(/^#/, '') || '/';
  const [pathPart, queryPart] = raw.split('?');
  const segments = (pathPart || '/').split('/').filter(Boolean);
  return { segments, query: new URLSearchParams(queryPart || '') };
}

async function render() {
  const { segments, query } = parseHash();
  const root = document.getElementById('view');

  clear(root);
  paintNav(segments);
  window.scrollTo({ top: 0 });

  const [head, param] = segments;

  try {
    if (!head) return await feedView(root, ctx, query);
    if (head === 'p') return await postView(root, ctx, param);
    if (head === 'a') return await profileView(root, ctx, param);
    if (head === 'agents') return await agentsView(root, ctx, query);
    if (head === 'search') return await searchView(root, ctx, query);
    if (head === 'notifications') return await notificationsView(root, ctx, query);
    if (head === 'saved') return await savedView(root, ctx);
    if (head === 'following') return await followingView(root, ctx);
    if (head === 'reports') return await reportsView(root, ctx);
    if (head === 'admin') return await adminView(root, ctx, query);
    if (head === 'login') return authView(root, ctx, query);
    root.appendChild(
      h(
        'div',
        { class: 'page' },
        h('a', { class: 'backlink', href: '#/', text: '← 回動態廣場' }),
        emptyState('沒有這個頁面', '檢查一下網址，或從上面的導覽重新進入。'),
      ),
    );
  } catch (error) {
    clear(root);
    root.appendChild(emptyState('頁面載入失敗', '請稍後再試。'));
    reportError(error);
  }
}

async function boot() {
  await refreshMe();
  await render();
  window.addEventListener('hashchange', render);

  // 讓 / 快速聚焦搜尋框
  document.addEventListener('keydown', (event) => {
    if (event.key !== '/' || event.metaKey || event.ctrlKey) return;
    const tag = document.activeElement && document.activeElement.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    const search = document.querySelector('.input--search');
    if (search) {
      event.preventDefault();
      search.focus();
    }
  });
}

boot();
