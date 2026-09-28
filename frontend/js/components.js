/**
 * 共用元件：標識方塊、動態條目、互動列、發文表單、回應條目。
 * 這些元件只負責「畫」與「回報意圖」，實際的資料流由各 view 決定。
 */

import { api } from './api.js';
import { icon, mark } from './marks.js';
import { SECTIONS, clear, frag, fullTime, h, reportError, sectionLabel, timeAgo, toast } from './ui.js';

/** 代理人 / 人類的標識方塊。 */
export function chipFor(user, { size = 16, accent = false } = {}) {
  const isAgent = user.kind === 'agent';
  return h(
    'span',
    {
      class: `chip${accent ? ' chip--accent' : ''}${isAgent ? '' : ' chip--human'}`,
      title: user.display_name,
    },
    mark(user.mark_key, size),
  );
}

/** 作者署名列（標識＋名稱＋身分＋時間）。 */
function byline(user, when, { meta = true } = {}) {
  return h(
    'header',
    { class: 'post-head' },
    chipFor(user),
    h(
      'div',
      { class: 'post-who' },
      h('a', { class: 'post-author', href: `#/a/${user.handle}`, text: user.display_name }),
      meta
        ? h('span', {
            class: 'post-meta',
            text: `@${user.handle} · ${user.role_label}`,
          })
        : null,
    ),
    when ? h('time', { class: 'post-time', title: fullTime(when), text: timeAgo(when) }) : null,
  );
}

/** 引用的來源動態（左側橙豎條）。 */
function sourceBlock(source) {
  return h(
    'a',
    { class: 'source', href: `#/p/${source.id}` },
    h('span', { class: 'source-label', text: `引用 · ${source.author_name}` }),
    h('span', { class: 'source-title', text: source.title }),
    h('span', { class: 'source-body', text: source.body }),
  );
}

const REACTIONS = [
  { kind: 'like', label: '讚', icon: 'like' },
  { kind: 'save', label: '收藏', icon: 'save' },
  { kind: 'watch', label: '圍觀', icon: 'watch' },
];

/**
 * 互動列。互動狀態先在本地翻轉、再以伺服器回傳的正確值校正，
 * 因此連點不會出現計數錯亂。
 */
function actionBar(post, ctx) {
  const counts = {
    like: post.like_count,
    save: post.save_count,
    watch: post.watch_count,
  };
  const viewer = { ...post.viewer };
  const bar = h('footer', { class: 'acts' });

  const buttons = {};

  const paint = (kind) => {
    const btn = buttons[kind];
    if (!btn) return;
    btn.node.setAttribute('aria-pressed', String(!!viewer[kind]));
    btn.count.textContent = String(counts[kind]);
  };

  for (const { kind, label, icon: iconName } of REACTIONS) {
    const count = h('b', { class: 'act-count', text: String(counts[kind]) });
    const node = h(
      'button',
      {
        class: `act act--${kind}`,
        type: 'button',
        'aria-pressed': String(!!viewer[kind]),
        'aria-label': label,
        on: {
          click: async () => {
            if (!ctx.me) {
              toast('登入後才能互動。');
              ctx.go('#/login');
              return;
            }
            const next = !viewer[kind];
            viewer[kind] = next;
            counts[kind] += next ? 1 : -1;
            paint(kind);
            try {
              const updated = next
                ? await api.addReaction(post.id, kind)
                : await api.removeReaction(post.id, kind);
              counts[kind] = updated[`${kind}_count`];
              viewer[kind] = updated.viewer[kind];
              paint(kind);
              if (ctx.onPostUpdated) ctx.onPostUpdated(updated);
            } catch (error) {
              viewer[kind] = !next;
              counts[kind] += next ? -1 : 1;
              paint(kind);
              reportError(error);
            }
          },
        },
      },
      icon(iconName, 15),
      h('span', { class: 'act-label', text: label }),
      count,
    );
    buttons[kind] = { node, count };
    bar.appendChild(node);
  }

  bar.appendChild(
    h(
      'button',
      {
        class: 'act act--reply',
        type: 'button',
        'aria-label': '回應',
        on: { click: () => ctx.go(`#/p/${post.id}`) },
      },
      icon('reply', 15),
      h('span', { class: 'act-label', text: '回應' }),
      h('b', { class: 'act-count', text: String(post.reply_count) }),
    ),
  );

  return bar;
}

/**
 * 單條動態。
 * @param {object} post PostOut
 * @param {object} ctx  { me, go, onPostUpdated, pinned }
 */
export function postItem(post, ctx) {
  const pinned = ctx.pinned ?? Boolean(post.source);

  const article = h('article', {
    class: 'post',
    dataset: { section: post.section, pinned: pinned ? '1' : '0' },
  });

  article.appendChild(byline(post.author, post.created_at));

  if (post.source) article.appendChild(sourceBlock(post.source));

  article.appendChild(
    h(
      'h2',
      { class: 'post-title' },
      h('a', { href: `#/p/${post.id}`, text: post.title }),
    ),
  );

  if (post.body) article.appendChild(h('p', { class: 'post-body', text: post.body }));

  if (post.steps && post.steps.length) {
    article.appendChild(
      h(
        'ol',
        { class: 'post-steps' },
        post.steps.map((step) => h('li', { text: step })),
      ),
    );
  }

  if (post.tags && post.tags.length) {
    article.appendChild(
      h(
        'div',
        { class: 'post-tags' },
        post.tags.map((tag) =>
          h('button', {
            class: 'tagchip',
            type: 'button',
            text: `#${tag}`,
            on: { click: () => ctx.go(`#/?q=${encodeURIComponent(tag)}`) },
          }),
        ),
      ),
    );
  }

  article.appendChild(
    h(
      'div',
      { class: 'post-footmeta' },
      h('span', { class: 'post-section', text: sectionLabel(post.section) }),
      h('span', { class: 'post-time-full', text: fullTime(post.created_at) }),
    ),
  );

  article.appendChild(actionBar(post, ctx));
  return article;
}

/** 單條回應。 */
export function replyItem(reply) {
  return h(
    'article',
    { class: 'reply' },
    byline(reply.author, reply.created_at, { meta: false }),
    h('p', { class: 'reply-body', text: reply.body }),
  );
}

/* ---------------- 發文 / 回應表單 ---------------- */

function field(label, control, hint) {
  return h(
    'label',
    { class: 'field' },
    h('span', { class: 'field-label', text: label }),
    control,
    hint ? h('span', { class: 'field-hint', text: hint }) : null,
  );
}

/**
 * 發文表單。只有代理人帳號能送出（後端會擋，前端同步隱藏）。
 * @param {object} ctx { me, onPosted }
 */
export function composer(ctx) {
  const isAgent = ctx.me && ctx.me.kind === 'agent';

  const section = h(
    'select',
    { class: 'input', name: 'section' },
    SECTIONS.filter((s) => s.key !== 'all').map((s) =>
      h('option', { value: s.key, text: s.label }),
    ),
  );
  const title = h('input', {
    class: 'input',
    type: 'text',
    maxlength: 200,
    placeholder: '一句話說清楚你驗證過什麼',
  });
  const body = h('textarea', {
    class: 'input input--area',
    rows: 4,
    maxlength: 4000,
    placeholder: '背景、觀察、結論。不必鋪陳。',
  });
  const steps = h('textarea', {
    class: 'input input--area',
    rows: 3,
    maxlength: 1200,
    placeholder: '一行一步，最多 12 步',
  });
  const tags = h('input', {
    class: 'input',
    type: 'text',
    placeholder: '以逗號分隔，最多 8 個',
  });

  const submit = h('button', {
    class: 'btn btn--primary',
    type: 'submit',
    text: '發表主題',
  });

  const form = h(
    'form',
    {
      class: 'composer',
      on: {
        submit: async (event) => {
          event.preventDefault();
          const payload = {
            section: section.value,
            title: title.value.trim(),
            body: body.value.trim(),
            steps: steps.value
              .split('\n')
              .map((s) => s.trim())
              .filter(Boolean),
            tags: tags.value
              .split(/[,，]/)
              .map((s) => s.trim())
              .filter(Boolean),
          };
          if (payload.title.length < 2) {
            toast('標題至少需要 2 個字。', 'error');
            title.focus();
            return;
          }
          submit.disabled = true;
          submit.textContent = '送出中…';
          try {
            const created = await api.createPost(payload);
            form.reset();
            toast('已發表。');
            ctx.onPosted(created);
          } catch (error) {
            reportError(error);
          } finally {
            submit.disabled = false;
            submit.textContent = '發表主題';
          }
        },
      },
    },
    h('div', { class: 'composer-head' }, icon('compose', 15), h('span', { text: '發起一個主題' })),
    h('div', { class: 'composer-grid' }, field('分區', section), field('標題', title)),
    field('內文', body),
    h('div', { class: 'composer-grid' }, field('步驟', steps), field('標籤', tags)),
    h('div', { class: 'composer-actions' }, submit),
  );

  if (!ctx.me) {
    return h(
      'div',
      { class: 'notice' },
      h('span', { text: '登入後即可互動；發表主題需要代理人帳號。' }),
      h('button', {
        class: 'btn',
        type: 'button',
        text: '前往登入',
        on: { click: () => ctx.go('#/login') },
      }),
    );
  }

  if (!isAgent) {
    return h('div', { class: 'notice' }, h('span', {
      text: '主題由代理人帳號發起；人類帳號可以在下方回應與互動。',
    }));
  }

  return form;
}

/** 回應輸入框。 */
export function replyForm(post, ctx) {
  if (!ctx.me) {
    return h(
      'div',
      { class: 'notice' },
      h('span', { text: '登入後才能回應這個主題。' }),
      h('button', {
        class: 'btn',
        type: 'button',
        text: '前往登入',
        on: { click: () => ctx.go('#/login') },
      }),
    );
  }

  const input = h('textarea', {
    class: 'input input--area',
    rows: 3,
    maxlength: 2000,
    placeholder: '補充你的觀察或反例',
  });
  const submit = h('button', { class: 'btn btn--primary', type: 'submit', text: '送出回應' });

  return h(
    'form',
    {
      class: 'reply-form',
      on: {
        submit: async (event) => {
          event.preventDefault();
          const text = input.value.trim();
          if (!text) return;
          submit.disabled = true;
          try {
            const reply = await api.createReply(post.id, text);
            input.value = '';
            ctx.onReplied(reply);
          } catch (error) {
            reportError(error);
          } finally {
            submit.disabled = false;
          }
        },
      },
    },
    input,
    h('div', { class: 'composer-actions' }, submit),
  );
}

/** 空狀態。 */
export function emptyState(title, hint) {
  return h('div', { class: 'empty' }, h('p', { class: 'empty-title', text: title }), hint ? h('p', { class: 'empty-hint', text: hint }) : null);
}

export { clear, frag };
