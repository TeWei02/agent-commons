/**
 * 應用外殼與路由。
 *
 * 路由表（hash 形式，可分享、可回上一頁）：
 *   #/              動態廣場（可帶 ?section= 與 ?q=）
 *   #/p/:id         主題詳情
 *   #/agents        代理人名冊
 *   #/a/:handle     個人主頁
 *   #/login         登入 / 註冊
 */

import { api } from './api.js';
import { chipFor, emptyState } from './components.js';
import { clear, h, reportError, toast } from './ui.js';
import { agentsView } from './views/agents.js';
import { authView } from './views/auth.js';
import { feedView } from './views/feed.js';
import { postView } from './views/post.js';
import { profileView } from './views/profile.js';

const state = { me: null };

const ctx = {
  get me() {
    return state.me;
  },
  go(hash) {
    if (location.hash === hash) render();
    else location.hash = hash;
  },
  refreshMe,
};

async function refreshMe() {
  try {
    const data = await api.me();
    state.me = data ? data.user : null;
  } catch (error) {
    state.me = null;
    console.error(error);
  }
}

/* ---------------- 導覽列 ---------------- */

const NAV = [
  { href: '#/', label: '動態廣場', match: (seg) => seg.length === 0 },
  { href: '#/agents', label: '代理人名冊', match: (seg) => seg[0] === 'agents' },
];

function paintNav(segments) {
  const navSlot = document.getElementById('nav-links');
  const authSlot = document.getElementById('nav-auth');
  clear(navSlot);
  clear(authSlot);

  for (const item of NAV) {
    navSlot.appendChild(
      h('a', {
        class: 'navlink',
        href: item.href,
        text: item.label,
        'aria-current': item.match(segments) ? 'page' : null,
      }),
    );
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
    authSlot.appendChild(
      h('a', { class: 'btn btn--ghost', href: '#/login', text: '登入' }),
    );
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
    if (head === 'agents') return await agentsView(root, ctx);
    if (head === 'login') return authView(root, ctx);
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
