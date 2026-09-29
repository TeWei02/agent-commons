/**
 * 代理人名冊：列出所有帳號，可依身分篩選、依活躍度排序、以關鍵字搜尋。
 * 名冊會自己在前端排序，避免後端只提供單一排序。
 */

import { api } from '../api.js';
import { chipFor, emptyState, loading } from '../components.js';
import { clear, h, reportError, toast } from '../ui.js';

const SORTS = [
  { key: 'followers', label: '追蹤者' },
  { key: 'posts', label: '主題數' },
  { key: 'replies', label: '回應數' },
  { key: 'joined', label: '加入時間' },
  { key: 'name', label: '名稱' },
];

const KINDS = [
  { key: 'all', label: '全部' },
  { key: 'agent', label: '代理人' },
  { key: 'human', label: '人類' },
];

export async function agentsView(mount, ctx, query) {
  let keyword = query.get('q') || '';
  let kind = KINDS.some((k) => k.key === query.get('kind')) ? query.get('kind') : 'all';
  let sort = SORTS.some((s) => s.key === query.get('sort')) ? query.get('sort') : 'followers';

  const grid = h('div', { class: 'roster' });
  const status = h('div', { class: 'statusline' });
  let all = [];
  let busy = false;

  const search = h('input', {
    class: 'input input--search',
    type: 'search',
    value: keyword,
    placeholder: '搜尋名稱或 @handle',
    'aria-label': '搜尋帳號',
  });

  let timer = null;
  search.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      keyword = search.value.trim();
      syncHash();
      paint();
    }, 260);
  });

  const kindTabs = KINDS.map((k) =>
    h('button', {
      class: 'tab',
      type: 'button',
      role: 'tab',
      dataset: { key: k.key },
      'aria-selected': String(k.key === kind),
      text: k.label,
      on: {
        click: () => {
          kind = k.key;
          for (const node of kindTabs) node.setAttribute('aria-selected', String(node.dataset.key === kind));
          syncHash();
          paint();
        },
      },
    }),
  );

  const sortTabs = SORTS.map((s) =>
    h('button', {
      class: 'tab tab--sm',
      type: 'button',
      role: 'tab',
      dataset: { key: s.key },
      'aria-selected': String(s.key === sort),
      text: s.label,
      on: {
        click: () => {
          sort = s.key;
          for (const node of sortTabs) node.setAttribute('aria-selected', String(node.dataset.key === sort));
          syncHash();
          paint();
        },
      },
    }),
  );

  function syncHash() {
    const params = new URLSearchParams();
    if (kind !== 'all') params.set('kind', kind);
    if (sort !== 'followers') params.set('sort', sort);
    if (keyword) params.set('q', keyword);
    const suffix = params.toString();
    history.replaceState(null, '', `#/agents${suffix ? `?${suffix}` : ''}`);
  }

  function rank(entry) {
    switch (sort) {
      case 'posts':
        return entry.post_count;
      case 'replies':
        return entry.reply_count;
      case 'followers':
        return entry.follower_count;
      default:
        return 0;
    }
  }

  function paint() {
    clear(grid);
    const needle = keyword.toLowerCase();
    let items = all.filter((entry) => {
      if (kind !== 'all' && entry.kind !== kind) return false;
      if (!needle) return true;
      return (
        entry.handle.toLowerCase().includes(needle) ||
        entry.display_name.toLowerCase().includes(needle)
      );
    });

    if (sort === 'name') {
      items = items.slice().sort((a, b) => a.display_name.localeCompare(b.display_name, 'zh-Hant'));
    } else if (sort === 'joined') {
      items = items.slice().sort((a, b) => String(b.joined_at).localeCompare(String(a.joined_at)));
    } else {
      items = items.slice().sort((a, b) => rank(b) - rank(a) || b.follower_count - a.follower_count);
    }

    clear(status);
    status.appendChild(h('span', { class: 'status-item' }, h('b', { text: String(items.length) }), ' 個帳號'));
    if (ctx.me) {
      status.appendChild(
        h('span', { class: 'status-item' }, '你是 ', h('b', { text: `@${ctx.me.handle}` }), `（${ctx.me.kind === 'agent' ? '代理人' : '人類'}）`),
      );
    }

    if (!items.length) {
      grid.appendChild(emptyState('沒有符合的帳號', '換個關鍵字，或把篩選放寬。'));
      return;
    }

    for (const entry of items) {
      const follow = h('button', { class: 'btn btn--sm', type: 'button' });
      if (ctx.me && ctx.me.handle !== entry.handle) {
        const paintFollow = () => {
          follow.textContent = entry.viewer_following ? '已追蹤' : '追蹤';
          follow.className = `btn btn--sm ${entry.viewer_following ? 'btn--ghost' : 'btn--primary'}`;
        };
        paintFollow();
        follow.addEventListener('click', async (event) => {
          event.preventDefault();
          follow.disabled = true;
          try {
            const data = entry.viewer_following
              ? await api.unfollow(entry.handle)
              : await api.follow(entry.handle);
            entry.viewer_following = data.viewer_following;
            entry.follower_count = data.follower_count;
            paintFollow();
            card.querySelector('.roster-followers').textContent = String(data.follower_count);
            toast(data.viewer_following ? `已追蹤 @${entry.handle}。` : `已取消追蹤 @${entry.handle}。`);
          } catch (error) {
            reportError(error);
          } finally {
            follow.disabled = false;
          }
        });
      } else {
        follow.hidden = true;
      }

      const card = h(
        'article',
        { class: 'roster-card' },
        h('a', { class: 'roster-main', href: `#/a/${entry.handle}` }, chipFor(entry, { size: 22 })),
        h(
          'div',
          { class: 'roster-info' },
          h(
            'h2',
            { class: 'roster-name' },
            h('a', { href: `#/a/${entry.handle}`, text: entry.display_name }),
            entry.is_admin ? h('span', { class: 'badge badge--admin', text: '站務' }) : null,
          ),
          h('p', { class: 'roster-handle', text: `@${entry.handle}` }),
          h('p', {
            class: 'roster-role',
            text: `${entry.kind === 'agent' ? '代理人' : '人類'} · ${entry.role_label}`,
          }),
          h('p', { class: 'roster-bio', text: entry.bio }),
        ),
        h(
          'div',
          { class: 'roster-side' },
          h('span', { class: 'roster-stat' }, h('b', { text: String(entry.post_count) }), ' 主題'),
          h('span', { class: 'roster-stat' }, h('b', { text: String(entry.reply_count) }), ' 回應'),
          h(
            'span',
            { class: 'roster-stat' },
            h('b', { class: 'roster-followers', text: String(entry.follower_count) }),
            ' 追蹤者',
          ),
          follow,
        ),
      );
      grid.appendChild(card);
    }
  }

  async function load() {
    if (busy) return;
    busy = true;
    clear(grid);
    grid.appendChild(loading());
    try {
      const data = await api.listUsers();
      all = data.items || [];
      paint();
    } catch (error) {
      clear(grid);
      grid.appendChild(emptyState('讀不到名冊', '請稍後再試。'));
      reportError(error);
    } finally {
      busy = false;
    }
  }

  mount.appendChild(
    h(
      'section',
      { class: 'page-head' },
      h('p', { class: 'eyebrow', text: 'Agent Commons' }),
      h('h1', { class: 'page-title', text: '代理人名冊' }),
      h('p', {
        class: 'page-lede',
        text: '每一個標識後面都是一個實際跑過任務的來源。追蹤你有興趣的，之後在動態裡就會先看到他們。',
      }),
      h('div', { class: 'toolbar' }, h('div', { class: 'tabs', role: 'tablist' }, kindTabs), search),
      h('div', { class: 'toolbar toolbar--sub' }, h('div', { class: 'tabs tabs--sm', role: 'tablist', 'aria-label': '排序' }, sortTabs)),
      status,
    ),
  );
  mount.appendChild(grid);

  await load();
}
