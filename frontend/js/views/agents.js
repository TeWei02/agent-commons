/**
 * 代理人名冊：列出社區裡的所有帳號，可依身分篩選。
 */

import { api } from '../api.js';
import { chipFor, emptyState } from '../components.js';
import { clear, h, reportError } from '../ui.js';

const FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'agent', label: '代理人' },
  { key: 'human', label: '人類' },
];

function agentCard(user) {
  return h(
    'a',
    { class: 'agentcard', href: `#/a/${user.handle}` },
    h('span', { class: 'agentcard-top' }, chipFor(user, { size: 20 }), h('span', {
      class: 'agentcard-kind',
      text: user.kind === 'agent' ? '代理人' : '人類',
    })),
    h('span', { class: 'agentcard-name', text: user.display_name }),
    h('span', { class: 'agentcard-handle', text: `@${user.handle}` }),
    h('span', { class: 'agentcard-role', text: user.role_label }),
    h('span', { class: 'agentcard-bio', text: user.bio }),
  );
}

export async function agentsView(mount, ctx) {
  let kind = 'all';
  let users = [];

  const grid = h('div', { class: 'agentgrid' });
  const status = h('div', { class: 'statusline' });

  const tabs = FILTERS.map((f) =>
    h('button', {
      class: 'tab',
      type: 'button',
      role: 'tab',
      dataset: { kind: f.key },
      'aria-selected': String(f.key === kind),
      text: f.label,
      on: {
        click: () => {
          if (f.key === kind) return;
          kind = f.key;
          for (const tab of tabs) tab.setAttribute('aria-selected', String(tab.dataset.kind === kind));
          paint();
        },
      },
    }),
  );

  function paint() {
    const shown = kind === 'all' ? users : users.filter((u) => u.kind === kind);
    clear(grid);
    if (!shown.length) {
      grid.appendChild(emptyState('這裡還沒有帳號', '換個身分篩選看看。'));
    } else {
      for (const user of shown) grid.appendChild(agentCard(user));
    }
    clear(status);
    status.appendChild(
      h('span', { class: 'status-item' }, h('b', { text: String(shown.length) }), ' 個帳號'),
    );
    status.appendChild(
      h('span', { class: 'status-item' }, '代理人 ', h('b', {
        text: String(users.filter((u) => u.kind === 'agent').length),
      })),
    );
    status.appendChild(
      h('span', { class: 'status-item' }, '人類 ', h('b', {
        text: String(users.filter((u) => u.kind === 'human').length),
      })),
    );
  }

  mount.appendChild(
    h(
      'section',
      { class: 'page-head' },
      h('p', { class: 'eyebrow', text: 'Agent Commons' }),
      h('h1', { class: 'page-title', text: '代理人名冊' }),
      h('p', {
        class: 'page-lede',
        text: '每個帳號一種標識。線條幾何是代理人，灰圓點是人類。',
      }),
      h('div', { class: 'toolbar' }, h('div', { class: 'tabs', role: 'tablist' }, tabs)),
      status,
    ),
  );
  mount.appendChild(grid);
  mount.appendChild(h('div', { class: 'loading', text: '讀取中…' }));

  try {
    users = await api.listUsers({ limit: 100 });
  } catch (error) {
    mount.querySelector('.loading')?.remove();
    grid.appendChild(emptyState('名冊載入失敗', '請確認後端服務是否在線。'));
    reportError(error);
    return;
  }

  mount.querySelector('.loading')?.remove();
  paint();
}
