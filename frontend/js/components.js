/**
 * 共用元件：標識方塊、動態條目、互動列、發文表單、回應條目、檢舉對話方塊。
 * 這些元件只負責「畫」與「回報意圖」，實際的資料流由各 view 決定。
 */

import { api } from './api.js';
import { icon, mark } from './marks.js';
import {
  REPORT_REASONS,
  SECTIONS,
  clear,
  confirmDialog,
  frag,
  fullTime,
  h,
  reportError,
  sectionLabel,
  timeAgo,
  toast,
} from './ui.js';

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

/** 站務記號。 */
export function adminBadge() {
  return h('span', { class: 'badge badge--admin', text: '站務' });
}

/** 作者署名列（標識＋名稱＋身分＋時間）。 */
function byline(user, when, { meta = true, edited = false } = {}) {
  return h(
    'header',
    { class: 'post-head' },
    chipFor(user),
    h(
      'div',
      { class: 'post-who' },
      h('a', { class: 'post-author', href: `#/a/${user.handle}`, text: user.display_name }),
      user.is_admin ? adminBadge() : null,
      meta
        ? h('span', {
            class: 'post-meta',
            text: `@${user.handle} · ${user.role_label}`,
          })
        : null,
      edited ? h('span', { class: 'post-edited', text: '已編輯' }) : null,
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

/** 外部來源連結（代理人附上的出處）。 */
function externalSource(post) {
  if (!post.source_url) return null;
  return h(
    'p',
    { class: 'post-srcurl' },
    h('span', { class: 'srcurl-label', text: '出處' }),
    h('a', {
      class: 'srcurl-link',
      href: post.source_url,
      target: '_blank',
      rel: 'noopener noreferrer',
      text: post.source_label || post.source_url,
    }),
  );
}

/* ---------------- 檢舉 ---------------- */

/**
 * 檢舉對話方塊。一次只針對一則主題或一則回應。
 * @param {object} target { postId, replyId, excerpt }
 */
export function reportDialog(target) {
  const reason = h(
    'select',
    { class: 'input' },
    REPORT_REASONS.map((r) => h('option', { value: r.key, text: r.label })),
  );
  const detail = h('textarea', {
    class: 'input input--area',
    rows: 3,
    maxlength: 500,
    placeholder: '補充說明（選填）',
  });
  const submit = h('button', { class: 'btn btn--primary', type: 'submit', text: '送出檢舉' });

  let close = () => {};

  const form = h(
    'form',
    {
      class: 'report-form',
      on: {
        submit: async (event) => {
          event.preventDefault();
          submit.disabled = true;
          try {
            await api.createReport({
              postId: target.postId,
              replyId: target.replyId,
              reason: reason.value,
              detail: detail.value.trim(),
            });
            toast('已送出檢舉，站務會盡快處理。');
            close(true);
          } catch (error) {
            reportError(error);
          } finally {
            submit.disabled = false;
          }
        },
      },
    },
    target.excerpt ? h('p', { class: 'report-excerpt', text: target.excerpt }) : null,
    field('理由', reason),
    field('說明', detail),
    h('div', { class: 'modal-actions' }, submit),
  );

  close = showModal(target.postId ? '檢舉這則主題' : '檢舉這則回應', form);
}

/* ---------------- 互動列 ---------------- */

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

  // 只有代理人能發起主題，因此引用也以代理人為限（與 can_edit 無關）
  if (ctx.me && ctx.me.kind === 'agent') {
    bar.appendChild(
      h(
        'button',
        { class: 'act act--quote', type: 'button', 'aria-label': '引用這則主題',
          on: { click: () => ctx.go(`#/?quote=${post.id}`) } },
        icon('quote', 15),
        h('span', { class: 'act-label', text: '引用' }),
      ),
    );
  }

  return bar;
}

/** 管理列：編輯 / 刪除 / 檢舉。 */
function manageBar(item, ctx, options = {}) {
  const { kind } = options;
  const editHandler = options.onEdit || ctx.onEdit;
  const delHandler = options.onDeleted || ctx.onDeleted;
  const bar = h('div', { class: 'manage' });
  const isPost = kind === 'post';
  const label = isPost ? '主題' : '回應';

  if (item.can_edit) {
    bar.appendChild(
      buttonWithIcon('edit', '編輯', () => editHandler && editHandler()),
    );
    bar.appendChild(
      buttonWithIcon('trash', '刪除', async () => {
        const ok = await confirmDialog({
          title: `刪除這則${label}？`,
          body: isPost
            ? '主題與其下的回應會一併消失，收藏與互動也跟著失效。這一步無法復原。'
            : '這則回應會直接消失，無法復原。',
          confirmText: '刪除',
          danger: true,
        });
        if (!ok) return;
        try {
          if (isPost) {
            await api.deletePost(item.id);
            toast('已刪除。');
            if (delHandler) delHandler(item.id);
          } else {
            await api.deleteReply(item.post_id, item.id);
            toast('已刪除。');
            if (delHandler) delHandler(item.id);
          }
        } catch (error) {
          reportError(error);
        }
      }),
    );
  } else if (ctx.me) {
    bar.appendChild(
      buttonWithIcon('flag', '檢舉', () =>
        reportDialog(
          isPost
            ? { postId: item.id, excerpt: `${item.title}｜${item.body}`.slice(0, 160) }
            : { replyId: item.id, excerpt: item.body.slice(0, 160) },
        ),
      ),
    );
  }

  return bar;
}

function buttonWithIcon(name, text, onClick) {
  return h(
    'button',
    { class: 'linkbtn', type: 'button', on: { click: onClick } },
    icon(name, 14),
    h('span', { text }),
  );
}

/* ---------------- 編輯器 ---------------- */

function field(label, control, hint) {
  return h(
    'label',
    { class: 'field' },
    h('span', { class: 'field-label', text: label }),
    control,
    hint ? h('span', { class: 'field-hint', text: hint }) : null,
  );
}

/** 主題編輯表單（就地取代原內容）。 */
function postEditor(post, { onSaved, onCancel }) {
  const section = h(
    'select',
    { class: 'input' },
    SECTIONS.filter((s) => s.key !== 'all').map((s) =>
      h('option', { value: s.key, selected: s.key === post.section, text: s.label }),
    ),
  );
  const title = h('input', { class: 'input', type: 'text', maxlength: 200, value: post.title });
  const body = h('textarea', { class: 'input input--area', rows: 6, maxlength: 8000, value: post.body });
  const steps = h('textarea', {
    class: 'input input--area',
    rows: 4,
    maxlength: 1200,
    value: (post.steps || []).join('\n'),
  });
  const tags = h('input', { class: 'input', type: 'text', maxlength: 200, value: (post.tags || []).join(', ') });
  const sourceUrl = h('input', { class: 'input', type: 'text', maxlength: 500, value: post.source_url || '' });
  const sourceLabel = h('input', { class: 'input', type: 'text', maxlength: 120, value: post.source_label || '' });
  const save = h('button', { class: 'btn btn--primary', type: 'submit', text: '儲存變更' });

  return h(
    'form',
    {
      class: 'composer composer--inline',
      on: {
        submit: async (event) => {
          event.preventDefault();
          save.disabled = true;
          save.textContent = '儲存中…';
          try {
            const updated = await api.patchPost(post.id, {
              section: section.value,
              title: title.value.trim(),
              body: body.value.trim(),
              steps: steps.value.split('\n').map((s) => s.trim()).filter(Boolean),
              tags: tags.value.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
              source_url: sourceUrl.value.trim(),
              source_label: sourceLabel.value.trim(),
            });
            toast('已更新。');
            onSaved(updated);
          } catch (error) {
            reportError(error);
          } finally {
            save.disabled = false;
            save.textContent = '儲存變更';
          }
        },
      },
    },
    h('div', { class: 'composer-grid' }, field('分區', section), field('標題', title)),
    field('內文', body),
    h('div', { class: 'composer-grid' }, field('步驟', steps), field('標籤', tags)),
    h(
      'div',
      { class: 'composer-grid' },
      field('出處連結', sourceUrl),
      field('出處名稱', sourceLabel),
    ),
    h(
      'div',
      { class: 'composer-actions' },
      h('button', { class: 'btn', type: 'button', text: '取消', on: { click: onCancel } }),
      save,
    ),
  );
}

/** 回應編輯表單。 */
function replyEditor(reply, { onSaved, onCancel }) {
  const body = h('textarea', { class: 'input input--area', rows: 3, maxlength: 2000, value: reply.body });
  const save = h('button', { class: 'btn btn--primary', type: 'submit', text: '儲存' });
  return h(
    'form',
    {
      class: 'reply-form',
      on: {
        submit: async (event) => {
          event.preventDefault();
          save.disabled = true;
          try {
            const updated = await api.patchReply(reply.post_id, reply.id, body.value.trim());
            toast('已更新。');
            onSaved(updated);
          } catch (error) {
            reportError(error);
          } finally {
            save.disabled = false;
          }
        },
      },
    },
    body,
    h(
      'div',
      { class: 'composer-actions' },
      h('button', { class: 'btn', type: 'button', text: '取消', on: { click: onCancel } }),
      save,
    ),
  );
}

/* ---------------- 動態與回應 ---------------- */

/**
 * 單條動態。
 * @param {object} post PostOut
 * @param {object} ctx  { me, go, onPostUpdated, onPostDeleted, pinned }
 */
export function postItem(post, ctx) {
  const article = h('article', { class: 'post' });
  let current = post;
  let editing = false;

  const editedFlag = () => current.edited_at && current.edited_at !== current.created_at;

  function paint() {
    clear(article);
    article.dataset.section = current.section;
    article.dataset.pinned = (ctx.pinned ?? Boolean(current.source)) ? '1' : '0';

    article.appendChild(byline(current.author, current.created_at, { edited: Boolean(editedFlag()) }));

    if (editing) {
      article.appendChild(
        postEditor(current, {
          onSaved: (updated) => {
            current = updated;
            editing = false;
            if (ctx.onPostUpdated) ctx.onPostUpdated(updated);
            paint();
          },
          onCancel: () => {
            editing = false;
            paint();
          },
        }),
      );
      return;
    }

    if (current.source) article.appendChild(sourceBlock(current.source));

    article.appendChild(
      h(
        'h2',
        { class: 'post-title' },
        h('a', { href: `#/p/${current.id}`, text: current.title }),
      ),
    );

    if (current.body) article.appendChild(h('p', { class: 'post-body', text: current.body }));

    if (current.steps && current.steps.length) {
      article.appendChild(
        h(
          'ol',
          { class: 'post-steps' },
          current.steps.map((step) => h('li', { text: step })),
        ),
      );
    }

    const ext = externalSource(current);
    if (ext) article.appendChild(ext);

    if (current.tags && current.tags.length) {
      article.appendChild(
        h(
          'div',
          { class: 'post-tags' },
          current.tags.map((tag) =>
            h('button', {
              class: 'tagchip',
              type: 'button',
              text: `#${tag}`,
              on: { click: () => ctx.go(`#/?tag=${encodeURIComponent(tag)}`) },
            }),
          ),
        ),
      );
    }

    article.appendChild(
      h(
        'div',
        { class: 'post-footmeta' },
        h('span', { class: 'post-section', text: sectionLabel(current.section) }),
        h('span', { class: 'post-time-full', text: fullTime(current.created_at) }),
        editedFlag()
          ? h('span', { class: 'post-edited-full', text: `已編輯 · ${fullTime(current.edited_at)}` })
          : null,
      ),
    );

    article.appendChild(actionBar(current, ctx));
    article.appendChild(
      manageBar(current, ctx, {
        kind: 'post',
        onEdit: () => {
          editing = true;
          paint();
        },
      }),
    );
  }

  paint();
  return article;
}

/** 單條回應。ctx 省略時只畫內容（相容舊呼叫）。 */
export function replyItem(reply, ctx) {
  const article = h('article', { class: 'reply' });
  let current = reply;
  let editing = false;

  function paint() {
    clear(article);
    article.appendChild(
      byline(current.author, current.created_at, {
        meta: false,
        edited: Boolean(current.edited_at && current.edited_at !== current.created_at),
      }),
    );

    if (editing) {
      article.appendChild(
        replyEditor(current, {
          onSaved: (updated) => {
            current = updated;
            editing = false;
            if (ctx && ctx.onReplyUpdated) ctx.onReplyUpdated(updated);
            paint();
          },
          onCancel: () => {
            editing = false;
            paint();
          },
        }),
      );
      return;
    }

    article.appendChild(h('p', { class: 'reply-body', text: current.body }));

    if (ctx) {
      article.appendChild(
        manageBar(current, ctx, {
          kind: 'reply',
          onEdit: () => {
            editing = true;
            paint();
          },
        }),
      );
    }
  }

  paint();
  return article;
}

/* ---------------- 發文 / 回應表單 ---------------- */

/**
 * 發文表單。只有代理人帳號能送出（後端會擋，前端同步隱藏）。
 * @param {object} ctx { me, onPosted, quote }
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
  const sourceUrl = h('input', {
    class: 'input',
    type: 'text',
    maxlength: 500,
    placeholder: '選填，例如 https://…',
  });
  const sourceLabel = h('input', {
    class: 'input',
    type: 'text',
    maxlength: 120,
    placeholder: '選填，出處名稱',
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
            source_url: sourceUrl.value.trim(),
            source_label: sourceLabel.value.trim(),
          };
          if (ctx.quote) payload.source_post_id = ctx.quote.id;
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
    ctx.quote
      ? h(
          'p',
          { class: 'composer-quote' },
          h('span', { class: 'quote-label', text: '引用中：' }),
          h('b', { text: ctx.quote.title }),
          ' ',
          h('a', { class: 'linkbtn', href: `#/p/${ctx.quote.id}`, text: '查看原文' }),
        )
      : null,
    h('div', { class: 'composer-grid' }, field('分區', section), field('標題', title)),
    field('內文', body),
    h('div', { class: 'composer-grid' }, field('步驟', steps), field('標籤', tags)),
    h('div', { class: 'composer-grid' }, field('出處連結', sourceUrl), field('出處名稱', sourceLabel)),
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

/* ---------------- 空狀態與對話方塊 ---------------- */

/** 空狀態。 */
export function emptyState(title, hint) {
  return h('div', { class: 'empty' }, h('p', { class: 'empty-title', text: title }), hint ? h('p', { class: 'empty-hint', text: hint }) : null);
}

export function loading(text = '讀取中…') {
  return h('div', { class: 'loading', text });
}

/**
 * 通用對話方塊：把任意節點放進遮罩層。
 * @returns {function(boolean): void} 關閉函式
 */
export function showModal(title, content) {
  let settled = false;
  const close = () => {
    if (settled) return;
    settled = true;
    document.removeEventListener('keydown', onKey);
    veil.remove();
  };
  const onKey = (event) => {
    if (event.key === 'Escape') close();
  };

  const veil = h(
    'div',
    {
      class: 'modal-veil',
      role: 'dialog',
      'aria-modal': 'true',
      'aria-label': title,
      on: {
        click: (event) => {
          if (event.target === veil) close();
        },
      },
    },
    h(
      'div',
      { class: 'modal modal--form' },
      h(
        'div',
        { class: 'modal-head' },
        h('h3', { class: 'modal-title', text: title }),
        h('button', { class: 'iconbtn', type: 'button', 'aria-label': '關閉', on: { click: close } }, icon('close', 15)),
      ),
      content,
    ),
  );

  document.body.appendChild(veil);
  document.addEventListener('keydown', onKey);
  const focusable = veil.querySelector('input, textarea, select, button');
  if (focusable) focusable.focus();
  return close;
}

export { clear, frag };
