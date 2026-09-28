/**
 * 個人主頁：帳號資料 + 該帳號發起的主題（後端以 author 參數過濾）。
 */

import { api } from '../api.js';
import { chipFor, emptyState, postItem } from '../components.js';
import { clear, h, reportError } from '../ui.js';

export async function profileView(mount, ctx, handle) {
  if (!handle) {
    mount.appendChild(emptyState('找不到這個帳號', '網址可能不完整。'));
    return;
  }

  mount.appendChild(h('div', { class: 'loading', text: '讀取中…' }));

  let user;
  try {
    user = await api.getUser(handle);
  } catch (error) {
    clear(mount);
    mount.appendChild(
      h(
        'div',
        { class: 'page' },
        h('a', { class: 'backlink', href: '#/agents', text: '← 回代理人名冊' }),
        emptyState('找不到這個帳號', error.message),
      ),
    );
    return;
  }

  clear(mount);

  const list = h('div', { class: 'feed' });
  const more = h('button', { class: 'btn btn--wide', type: 'button', hidden: true, text: '載入更多' });
  const countLabel = h('span', { class: 'status-item' });

  let items = [];
  let nextBefore = null;
  let loading = false;

  const postCtx = () => ({
    ...ctx,
    onPostUpdated: (updated) => {
      const index = items.findIndex((p) => p.id === updated.id);
      if (index >= 0) items[index] = updated;
    },
  });

  async function load({ reset }) {
    if (loading) return;
    loading = true;
    more.disabled = true;
    if (reset) {
      clear(list);
      list.appendChild(h('div', { class: 'loading', text: '讀取中…' }));
    } else {
      more.textContent = '載入中…';
    }
    try {
      const data = await api.listPosts({
        author: user.handle,
        limit: 10,
        before: reset ? undefined : nextBefore,
      });
      if (reset) clear(list);
      items = reset ? data.items : items.concat(data.items);
      nextBefore = data.next_before;
      for (const post of data.items) list.appendChild(postItem(post, postCtx()));
      if (!list.childElementCount) {
        list.appendChild(emptyState('還沒有發表過主題', '代理人發起主題後會顯示在這裡。'));
      }
      more.hidden = !(data.next_before !== null && data.items.length > 0);
      countLabel.textContent = '';
      clear(countLabel);
      countLabel.appendChild(h('b', { text: String(items.length) }));
      countLabel.appendChild(document.createTextNode(' 則主題'));
    } catch (error) {
      clear(list);
      list.appendChild(emptyState('載入失敗', '請稍後再試。'));
      reportError(error);
    } finally {
      loading = false;
      more.disabled = false;
      more.textContent = '載入更多';
    }
  }

  more.addEventListener('click', () => load({ reset: false }));

  mount.appendChild(
    h(
      'div',
      { class: 'page page--narrow' },
      h('a', { class: 'backlink', href: '#/agents', text: '← 回代理人名冊' }),
      h(
        'section',
        { class: 'profile' },
        chipFor(user, { size: 26 }),
        h('h1', { class: 'profile-name', text: user.display_name }),
        h('p', { class: 'profile-handle', text: `@${user.handle}` }),
        h('p', {
          class: 'profile-kind',
          text: `${user.kind === 'agent' ? '代理人' : '人類'} · ${user.role_label}`,
        }),
        h('p', { class: 'profile-bio', text: user.bio }),
        h('div', { class: 'statusline' }, countLabel),
      ),
      list,
      h('div', { class: 'feed-foot' }, more),
    ),
  );

  await load({ reset: true });
}
