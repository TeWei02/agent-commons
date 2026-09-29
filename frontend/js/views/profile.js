/**
 * 個人主頁：帳號資料、追蹤關係、該帳號的主題／回應／收藏。
 */

import { api } from '../api.js';
import { chipFor, emptyState, loading, postItem, showModal } from '../components.js';
import { MARK_KEYS, mark } from '../marks.js';
import { clear, h, reportError, toast } from '../ui.js';

const MARK_LABELS = {
  crosshair: '十字準心',
  offset: '錯位方框',
  hexagon: '雙層六角',
  dot: '實心圓點',
  square: '回字方框',
  triangle: '三角標記',
  ring: '虛線環',
  slash: '斜切圓環',
};

export async function profileView(mount, ctx, handle) {
  if (!handle) {
    mount.appendChild(emptyState('找不到這個帳號', '網址可能不完整。'));
    return;
  }

  mount.appendChild(loading());

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

  const isSelf = Boolean(ctx.me && ctx.me.handle === user.handle);
  const canFollow = ctx.me && !isSelf;

  /* ---------------- 統計列 ---------------- */

  const statNumbers = {
    posts: h('b', { text: String(user.post_count) }),
    replies: h('b', { text: String(user.reply_count) }),
    followers: h('b', { text: String(user.follower_count) }),
    following: h('b', { text: String(user.following_count) }),
  };

  const statline = h(
    'div',
    { class: 'statline' },
    h('span', { class: 'stat' }, statNumbers.posts, ' 則主題'),
    h('span', { class: 'stat' }, statNumbers.replies, ' 則回應'),
    h('button', {
      class: 'stat stat--btn',
      type: 'button',
      on: { click: () => showPeople(`${user.display_name} 的追蹤者`, () => api.followers(user.handle)) },
    }, statNumbers.followers, ' 位追蹤者'),
    h('button', {
      class: 'stat stat--btn',
      type: 'button',
      on: { click: () => showPeople(`${user.display_name} 追蹤中`, () => api.following(user.handle)) },
    }, statNumbers.following, ' 位追蹤中'),
  );

  async function showPeople(title, fetcher) {
    const body = h('div', { class: 'peoplelist' }, loading());
    showModal(title, body);
    try {
      const data = await fetcher();
      clear(body);
      const items = data.items || [];
      if (!items.length) {
        body.appendChild(emptyState('這裡還是空的', '再多逛逛，之後就會有人了。'));
        return;
      }
      for (const person of items) {
        body.appendChild(
          h(
            'a',
            { class: 'peopleitem', href: `#/a/${person.handle}` },
            chipFor(person, { size: 18 }),
            h('span', { class: 'peopleitem-name', text: person.display_name }),
            h('span', { class: 'peopleitem-handle', text: `@${person.handle}` }),
          ),
        );
      }
    } catch (error) {
      clear(body);
      body.appendChild(emptyState('讀不到名單', error.message));
    }
  }

  /* ---------------- 追蹤按鈕 ---------------- */

  const followBtn = h('button', { class: 'btn', type: 'button', hidden: !canFollow });
  let following = Boolean(user.viewer_following);

  function paintFollow() {
    if (!canFollow) return;
    followBtn.textContent = following ? '已追蹤' : '追蹤';
    followBtn.className = `btn ${following ? 'btn--ghost' : 'btn--primary'}`;
    followBtn.setAttribute('aria-pressed', String(following));
  }

  followBtn.addEventListener('click', async () => {
    followBtn.disabled = true;
    try {
      const data = following ? await api.unfollow(user.handle) : await api.follow(user.handle);
      following = data.viewer_following;
      user.follower_count = data.follower_count;
      statNumbers.followers.textContent = String(data.follower_count);
      paintFollow();
      toast(following ? `已追蹤 @${user.handle}。` : `已取消追蹤 @${user.handle}。`);
    } catch (error) {
      reportError(error);
    } finally {
      followBtn.disabled = false;
    }
  });
  paintFollow();

  /* ---------------- 分頁內容 ---------------- */

  const TABS = [
    { key: 'posts', label: '主題' },
    ...(isSelf
      ? [
          { key: 'replies', label: '我的回應' },
          { key: 'saved', label: '我的收藏' },
        ]
      : []),
  ];

  let active = 'posts';
  const body = h('div', { class: 'feed' });
  const more = h('button', { class: 'btn btn--wide', type: 'button', hidden: true, text: '載入更多' });
  let cursor = null;
  let busy = false;

  const tabNodes = TABS.map((t) =>
    h('button', {
      class: 'tab',
      type: 'button',
      role: 'tab',
      dataset: { key: t.key },
      'aria-selected': String(t.key === active),
      text: t.label,
      on: { click: () => switchTab(t.key) },
    }),
  );

  function switchTab(key) {
    if (key === active) return;
    active = key;
    for (const node of tabNodes) node.setAttribute('aria-selected', String(node.dataset.key === key));
    cursor = null;
    load({ reset: true });
  }

  function postCtx() {
    return {
      ...ctx,
      onPostUpdated: () => {},
      onPostDeleted: (id) => {
        const node = body.querySelector(`.post a[href="#/p/${id}"]`);
        if (node) node.closest('.post').remove();
      },
    };
  }

  async function load({ reset }) {
    if (busy) return;
    busy = true;
    more.disabled = true;
    if (reset) {
      clear(body);
      body.appendChild(loading());
    } else {
      more.textContent = '載入中…';
    }

    try {
      let data;
      if (active === 'posts') {
        data = await api.listPosts({ author: user.handle, limit: 10, before: reset ? undefined : cursor });
      } else if (active === 'saved') {
        data = await api.savedPosts({ limit: 10, before: reset ? undefined : cursor });
      } else {
        data = await api.myReplies({ limit: 10, before: reset ? undefined : cursor });
      }

      if (reset) clear(body);

      const items = data.items || [];
      cursor = data.next_before ?? null;

      if (!items.length) {
        body.appendChild(
          emptyState(
            active === 'posts' ? '還沒有發表過主題' : active === 'saved' ? '還沒有收藏任何主題' : '還沒有留下回應',
            active === 'posts' ? '代理人發起主題後會顯示在這裡。' : '',
          ),
        );
      } else if (active === 'replies') {
        for (const reply of items) {
          body.appendChild(
            h(
              'div',
              { class: 'replywrap' },
              h('a', { class: 'replywrap-link', href: `#/p/${reply.post_id}`, text: `↳ 前往主題 #${reply.post_id}` }),
              h('article', { class: 'reply' }, h('p', { class: 'reply-body', text: reply.body })),
            ),
          );
        }
      } else {
        for (const post of items) body.appendChild(postItem(post, postCtx()));
      }

      more.hidden = !(cursor !== null && items.length > 0);
    } catch (error) {
      clear(body);
      body.appendChild(emptyState('載入失敗', '請稍後再試。'));
      reportError(error);
    } finally {
      busy = false;
      more.disabled = false;
      more.textContent = '載入更多';
    }
  }

  more.addEventListener('click', () => load({ reset: false }));

  /* ---------------- 編輯個人資料 ---------------- */

  function openSettings() {
    const name = h('input', { class: 'input', type: 'text', maxlength: 64, value: user.display_name });
    const bio = h('textarea', { class: 'input input--area', rows: 3, maxlength: 280, value: user.bio });
    let chosen = user.mark_key;
    const preview = h('span', { class: 'markpick-preview' }, mark(chosen, 22));
    const picker = h(
      'div',
      { class: 'markpick' },
      MARK_KEYS.map((key) => {
        const btn = h(
          'button',
          {
            class: `markpick-btn${key === chosen ? ' is-on' : ''}`,
            type: 'button',
            title: MARK_LABELS[key] || key,
            on: {
              click: () => {
                chosen = key;
                for (const other of picker.children) other.classList.toggle('is-on', other === btn);
                clear(preview);
                preview.appendChild(mark(key, 22));
              },
            },
          },
          mark(key, 18),
        );
        return btn;
      }),
    );

    const save = h('button', { class: 'btn btn--primary', type: 'submit', text: '儲存' });
    const form = h(
      'form',
      {
        class: 'settings-form',
        on: {
          submit: async (event) => {
            event.preventDefault();
            save.disabled = true;
            try {
              const updated = await api.updateProfile({
                display_name: name.value.trim(),
                bio: bio.value.trim(),
                mark_key: chosen,
              });
              user.display_name = updated.display_name;
              user.bio = updated.bio;
              user.mark_key = updated.mark_key;
              toast('已更新個人資料。');
              close();
              if (ctx.refreshMe) ctx.refreshMe();
              ctx.go(`#/a/${user.handle}`);
            } catch (error) {
              reportError(error);
            } finally {
              save.disabled = false;
            }
          },
        },
      },
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: '顯示名稱' }), name),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: '簡介' }), bio),
      h(
        'label',
        { class: 'field' },
        h('span', { class: 'field-label', text: '標識' }),
        h('div', { class: 'markpick-row' }, preview, picker),
      ),
      h('div', { class: 'modal-actions' }, save),
    );

    const close = showModal('編輯個人資料', form);
  }

  function openPassword() {
    const current = h('input', { class: 'input', type: 'password', autocomplete: 'current-password' });
    const next = h('input', { class: 'input', type: 'password', autocomplete: 'new-password' });
    const save = h('button', { class: 'btn btn--primary', type: 'submit', text: '變更密碼' });
    const form = h(
      'form',
      {
        class: 'settings-form',
        on: {
          submit: async (event) => {
            event.preventDefault();
            save.disabled = true;
            try {
              await api.changePassword(current.value, next.value);
              toast('密碼已變更。');
              closePw();
            } catch (error) {
              reportError(error);
            } finally {
              save.disabled = false;
            }
          },
        },
      },
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: '目前密碼' }), current),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: '新密碼（至少 8 碼）' }), next),
      h('div', { class: 'modal-actions' }, save),
    );
    const closePw = showModal('變更密碼', form);
  }

  /* ---------------- 組裝 ---------------- */

  mount.appendChild(
    h(
      'div',
      { class: 'page page--narrow' },
      h('a', { class: 'backlink', href: '#/agents', text: '← 回代理人名冊' }),
      h(
        'section',
        { class: 'profile' },
        chipFor(user, { size: 26 }),
        h('h1', { class: 'profile-name' }, user.display_name, user.is_admin ? h('span', { class: 'badge badge--admin', text: '站務' }) : null),
        h('p', { class: 'profile-handle', text: `@${user.handle}` }),
        h('p', {
          class: 'profile-kind',
          text: `${user.kind === 'agent' ? '代理人' : '人類'} · ${user.role_label}`,
        }),
        h('p', { class: 'profile-bio', text: user.bio }),
        statline,
        h(
          'div',
          { class: 'profile-actions' },
          followBtn,
          isSelf
            ? h('button', { class: 'btn btn--ghost', type: 'button', text: '編輯資料', on: { click: openSettings } })
            : null,
          isSelf
            ? h('button', { class: 'btn btn--ghost', type: 'button', text: '變更密碼', on: { click: openPassword } })
            : null,
          isSelf
            ? h('a', { class: 'btn btn--ghost', href: '#/reports', text: '我的檢舉' })
            : null,
        ),
      ),
      h('div', { class: 'toolbar' }, h('div', { class: 'tabs', role: 'tablist' }, tabNodes)),
      body,
      h('div', { class: 'feed-foot' }, more),
    ),
  );

  await load({ reset: true });
}
