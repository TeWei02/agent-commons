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
import { clear, h, reportError, toast } from './ui.js';
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
