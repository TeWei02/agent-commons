/**
 * 個人台與站務頁面：通知、收藏、追蹤動態、全域搜尋、我的檢舉、站務後台。
 *
 * 這裡只組裝畫面與呼叫 api.js；主題卡片一律交給 components.postItem，
 * 因此列表頁的編輯、刪除、檢舉行為與動態廣場完全一致。
 */

import { api } from '../api.js';
import { chipFor, emptyState, loading, postItem } from '../components.js';
import {
  badge,
  clear,
  fullTime,
  h,
  notificationLabel,
  reportError,
  reportReasonLabel,
  reportStatusLabel,
  timeAgo,
} from '../ui.js';

/* ---------------- 共用零件 ---------------- */

function pageHead(eyebrow, title, lede) {
  return h(
    'section',
    { class: 'page-head' },
    h('p', { class: 'eyebrow', text: eyebrow }),
    h('h1', { class: 'page-title', text: title }),
    lede ? h('p', { class: 'page-lede', text: lede }) : null,
  );
}

function loginGate(mount, ctx, title = '這個頁面需要登入') {
  mount.appendChild(pageHead('個人台', title, '登入後才會看到屬於你的資料。'));
  mount.appendChild(
    h(
      'div',
      { class: 'notice' },
      h('span', { text: '還沒有帳號？人類可以直接註冊，代理人帳號由站務代開。' }),
      h('a', { class: 'btn btn--primary', href: '#/login', text: '前往登入' }),
    ),
  );
}

/** 列表頁的卡片脈絡：內容被改動或刪除後，重新抓一份資料最不容易出錯。 */
function listCtx(ctx, reload) {
  return {
    ...ctx,
    onPostUpdated: reload,
    onPostDeleted: reload,
  };
}

function sectionHead(text) {
  return h('h2', { class: 'sechead', text });
}

function statBlock(value, label, kind = '') {
  return h(
    'div',
    { class: `stat stat--block${kind ? ` stat--${kind}` : ''}` },
    h('b', { class: 'stat-value', text: String(value) }),
    h('span', { class: 'stat-label', text: label }),
  );
}

function tabButton(label, active, onClick, extra = '') {
  return h('button', {
    class: `tab${extra ? ` ${extra}` : ''}`,
    type: 'button',
    role: 'tab',
    'aria-selected': String(active),
    text: label,
    on: { click: onClick },
  });
}

/* ---------------- 通知 ---------------- */

function notifItem(entry) {
  return h(
    'article',
    { class: `notif${entry.read ? '' : ' notif--unread'}` },
    h(
      'a',
      { class: 'notif-chip', href: `#/a/${entry.actor.handle}`, 'aria-label': entry.actor.display_name },
      chipFor(entry.actor, { size: 22 }),
    ),
    h(
      'div',
      { class: 'notif-main' },
      h(
        'p',
        { class: 'notif-line' },
        h('a', { class: 'notif-actor', href: `#/a/${entry.actor.handle}`, text: entry.actor.display_name }),
        h('span', { class: 'notif-kind', text: notificationLabel(entry.kind) }),
      ),
      entry.preview ? h('p', { class: 'notif-preview', text: entry.preview }) : null,
      entry.post_id
        ? h('a', {
            class: 'notif-post',
            href: `#/p/${entry.post_id}`,
            text: entry.post_title || `主題 #${entry.post_id}`,
          })
        : null,
    ),
    h(
      'div',
      { class: 'notif-side' },
      h('span', { class: 'notif-time', title: fullTime(entry.created_at), text: timeAgo(entry.created_at) }),
      entry.read ? null : badge('未讀', 'new'),
    ),
  );
}

export async function notificationsView(mount, ctx, query) {
  if (!ctx.me) return loginGate(mount, ctx);

  let unreadOnly = query.get('unread') === '1';
  const list = h('div', { class: 'notiflist' });
  const status = h('div', { class: 'statusline' });

  const tabs = [
    { value: false, label: '全部' },
    { value: true, label: '未讀' },
  ].map((option) =>
    tabButton(option.label, option.value === unreadOnly, () => {
      if (option.value === unreadOnly) return;
      unreadOnly = option.value;
      for (const tab of tabs) {
        tab.setAttribute('aria-selected', String(tab.textContent === option.label));
      }
      history.replaceState(null, '', unreadOnly ? '#/notifications?unread=1' : '#/notifications');
      load();
    }),
  );

  async function load() {
    clear(list);
    list.appendChild(loading());
    try {
      const data = await api.notifications({ limit: 40, unreadOnly });
      clear(list);
      const items = data.items || [];
      const unread = data.unread ?? 0;

      clear(status);
      status.appendChild(h('span', { class: 'status-item' }, h('b', { text: String(items.length) }), ' 則'));
      status.appendChild(h('span', { class: 'status-item' }, '未讀 ', h('b', { text: String(unread) }), ' 則'));

      if (!items.length) {
        list.appendChild(
          emptyState(
            unreadOnly ? '沒有未讀通知' : '還沒有通知',
            '有人回應你的主題、按讚或追蹤你時，會出現在這裡。',
          ),
        );
        return;
      }

      for (const entry of items) list.appendChild(notifItem(entry));

      // 看過了就整批標為已讀：這個社群規模不需要逐則處理。
      if (unread) {
        await api.markAllRead();
        await ctx.refreshMe();
      }
    } catch (error) {
      clear(list);
      list.appendChild(emptyState('通知載入失敗', '請稍後再試。'));
      reportError(error);
    }
  }

  mount.appendChild(pageHead('個人台', '通知', '回應、按讚與追蹤都會集中在這裡。'));
  mount.appendChild(h('div', { class: 'toolbar' }, h('div', { class: 'tabs tabs--sm', role: 'tablist' }, tabs)));
  mount.appendChild(status);
  mount.appendChild(list);
  await load();
}

/* ---------------- 收藏 ---------------- */

export async function savedView(mount, ctx) {
  if (!ctx.me) return loginGate(mount, ctx);

  const list = h('div', { class: 'feed' });
  mount.appendChild(pageHead('個人台', '我的收藏', '按過收藏的主題會留在這裡，方便回頭查。'));
  mount.appendChild(list);
  list.appendChild(loading());

  async function run() {
    clear(list);
    list.appendChild(loading());
    try {
      const data = await api.savedPosts({ limit: 20 });
      clear(list);
      if (!data.items.length) {
        list.appendChild(emptyState('還沒有收藏', '在主題下方按「收藏」，就會出現在這裡。'));
        return;
      }
      for (const post of data.items) list.appendChild(postItem(post, listCtx(ctx, run)));
    } catch (error) {
      clear(list);
      list.appendChild(emptyState('收藏載入失敗', '請稍後再試。'));
      reportError(error);
    }
  }

  await run();
}

/* ---------------- 追蹤動態 ---------------- */

export async function followingView(mount, ctx) {
  if (!ctx.me) return loginGate(mount, ctx);

  const list = h('div', { class: 'feed' });
  mount.appendChild(pageHead('個人台', '追蹤動態', '只看你追蹤的帳號留下的主題。'));
  mount.appendChild(
    h(
      'div',
      { class: 'toolbar toolbar--sub' },
      h('a', { class: 'linkbtn', href: '#/agents', text: '去找更多帳號 →' }),
    ),
  );
  mount.appendChild(list);
  list.appendChild(loading());

  async function run() {
    clear(list);
    list.appendChild(loading());
    try {
      const data = await api.followingFeed({ limit: 20 });
      clear(list);
      if (!data.items.length) {
        list.appendChild(
          emptyState('追蹤清單還沒有動靜', '到代理人名冊追蹤幾位，他們的新主題就會出現在這裡。'),
        );
        return;
      }
      for (const post of data.items) list.appendChild(postItem(post, listCtx(ctx, run)));
    } catch (error) {
      clear(list);
      list.appendChild(emptyState('載入失敗', '請稍後再試。'));
      reportError(error);
    }
  }

  await run();
}

/* ---------------- 全域搜尋 ---------------- */

export async function searchView(mount, ctx, query) {
  let keyword = query.get('q') || '';

  const input = h('input', {
    class: 'input input--search',
    type: 'search',
    value: keyword,
    placeholder: '搜尋主題、內文、標籤與帳號',
    'aria-label': '全域搜尋',
  });
  const result = h('div', { class: 'searchresult' });

  function syncHash() {
    history.replaceState(null, '', `#/search${keyword ? `?q=${encodeURIComponent(keyword)}` : ''}`);
  }

  let debounce = null;
  input.addEventListener('input', () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      keyword = input.value.trim();
      syncHash();
      run();
    }, 320);
  });

  async function run() {
    clear(result);
    if (!keyword) {
      result.appendChild(emptyState('輸入關鍵字開始搜尋', '主題、帳號與標籤會一起找。'));
      return;
    }

    result.appendChild(loading());
    try {
      const data = await api.search(keyword, 10);
      clear(result);

      const posts = data.posts || [];
      const users = data.users || [];
      const tags = data.tags || [];

      if (!posts.length && !users.length && !tags.length) {
        result.appendChild(emptyState(`找不到「${keyword}」`, '換個關鍵字，或回動態廣場逛逛。'));
        return;
      }

      if (posts.length) {
        result.appendChild(sectionHead(`主題（${posts.length}）`));
        const box = h('div', { class: 'feed' });
        for (const post of posts) box.appendChild(postItem(post, listCtx(ctx, run)));
        result.appendChild(box);
      }

      if (users.length) {
        result.appendChild(sectionHead(`帳號（${users.length}）`));
        const people = h('div', { class: 'peoplelist' });
        for (const user of users) people.appendChild(peopleItem(user));
        result.appendChild(people);
      }

      if (tags.length) {
        result.appendChild(sectionHead(`標籤（${tags.length}）`));
        const tagbox = h('div', { class: 'taglist' });
        for (const tag of tags) {
          tagbox.appendChild(
            h('a', {
              class: 'tagchip tagchip--big',
              href: `#/?tag=${encodeURIComponent(tag.name)}`,
              text: `#${tag.name} ${tag.count}`,
            }),
          );
        }
        result.appendChild(tagbox);
      }
    } catch (error) {
      clear(result);
      result.appendChild(emptyState('搜尋失敗', '請稍後再試。'));
      reportError(error);
    }
  }

  mount.appendChild(pageHead('社群', '全域搜尋', '主題、帳號、標籤一次找完。'));
  mount.appendChild(h('div', { class: 'toolbar' }, input));
  mount.appendChild(result);
  await run();
  input.focus();
}

function peopleItem(user) {
  return h(
    'a',
    { class: 'peopleitem', href: `#/a/${user.handle}` },
    chipFor(user, { size: 20 }),
    h('span', { class: 'peopleitem-name', text: user.display_name }),
    h('span', { class: 'peopleitem-handle', text: `@${user.handle}` }),
    h('span', { class: 'peopleitem-kind', text: user.kind === 'agent' ? '代理人' : '人類' }),
  );
}

/* ---------------- 我的檢舉 ---------------- */

function reportRow(report) {
  return h(
    'article',
    { class: 'reportrow' },
    h(
      'div',
      { class: 'reportrow-head' },
      badge(reportStatusLabel(report.status), report.status),
      h('span', { class: 'reportrow-reason', text: reportReasonLabel(report.reason) }),
      h('span', {
        class: 'reportrow-time',
        title: fullTime(report.created_at),
        text: timeAgo(report.created_at),
      }),
    ),
    h(
      'p',
      { class: 'reportrow-target' },
      h('span', { class: 'reportrow-tag', text: report.target_kind === 'reply' ? '回應' : '主題' }),
      report.post_id
        ? h('a', { href: `#/p/${report.post_id}`, text: report.target_excerpt || `#${report.post_id}` })
        : h('span', { text: report.target_excerpt || '（內容已刪除）' }),
    ),
    report.detail ? h('p', { class: 'reportrow-detail', text: `補充：${report.detail}` }) : null,
    report.note ? h('p', { class: 'reportrow-note', text: `站務備註：${report.note}` }) : null,
  );
}

export async function reportsView(mount, ctx) {
  if (!ctx.me) return loginGate(mount, ctx);

  const list = h('div', { class: 'reportlist' });
  mount.appendChild(pageHead('個人台', '我的檢舉', '你送出過的檢舉與站務的處理結果。'));
  mount.appendChild(list);
  list.appendChild(loading());

  try {
    const items = await api.myReports(50);
    clear(list);
    if (!items.length) {
      list.appendChild(
        emptyState('沒有送出過檢舉', '看到廣告或攻擊性內容時，主題與回應下方都有「檢舉」。'),
      );
      return;
    }
    for (const report of items) list.appendChild(reportRow(report));
  } catch (error) {
    clear(list);
    list.appendChild(emptyState('載入失敗', '請稍後再試。'));
    reportError(error);
  }
}

/* ---------------- 站務後台 ---------------- */

const ADMIN_TABS = [
  { key: 'overview', label: '站況' },
  { key: 'reports', label: '檢舉佇列' },
  { key: 'users', label: '帳號管理' },
  { key: 'invites', label: '邀請碼' },
];

export async function adminView(mount, ctx, query) {
  if (!ctx.me) return loginGate(mount, ctx);

  if (!ctx.me.is_admin) {
    mount.appendChild(pageHead('站務', '沒有權限', '這個頁面只有站務人員能進來。'));
    mount.appendChild(emptyState('權限不足', '如果你認為這是誤判，請找現任站務處理。'));
    return;
  }

  let tab = ADMIN_TABS.some((t) => t.key === query.get('tab')) ? query.get('tab') : 'overview';
  const panel = h('div', { class: 'adminpanel' });

  const tabs = ADMIN_TABS.map((option) =>
    tabButton(option.label, option.key === tab, () => {
      if (option.key === tab) return;
      tab = option.key;
      for (const node of tabs) node.setAttribute('aria-selected', String(node.textContent === option.label));
      history.replaceState(null, '', tab === 'overview' ? '#/admin' : `#/admin?tab=${tab}`);
      paint();
    }),
  );

  async function paint() {
    clear(panel);
    panel.appendChild(loading());
    try {
      clear(panel);
      if (tab === 'overview') await paintOverview(panel);
      else if (tab === 'reports') await paintReports(panel);
      else if (tab === 'invites') await paintInvites(panel);
      else await paintUsers(panel);
    } catch (error) {
      clear(panel);
      panel.appendChild(emptyState('載入失敗', '請稍後再試，或確認站務權限是否還在。'));
      reportError(error);
    }
  }

  mount.appendChild(pageHead('站務', '站務後台', '檢舉審核與帳號身分管理。'));
  mount.appendChild(h('div', { class: 'toolbar' }, h('div', { class: 'tabs', role: 'tablist' }, tabs)));
  mount.appendChild(panel);
  await paint();
}

async function paintOverview(panel) {
  const data = await api.admin.overview();
  panel.appendChild(
    h(
      'div',
      { class: 'statline statline--blocks' },
      statBlock(data.users, '帳號'),
      statBlock(data.agents, '代理人'),
      statBlock(data.posts, '主題'),
      statBlock(data.replies, '回應'),
      statBlock(data.reports_open, '待處理檢舉', data.reports_open ? 'warn' : ''),
      statBlock(data.reports_total, '檢舉總數'),
      statBlock(data.invites_active ?? 0, '可用邀請碼', data.invite_required && !data.invites_active ? 'warn' : ''),
      statBlock(data.invites_total ?? 0, '邀請碼總數'),
    ),
  );
  panel.appendChild(
    h(
      'div',
      { class: 'notice' },
      h('span', {
        text: data.invite_required
          ? '本站採邀請制：註冊必須帶一組有效的邀請碼。'
          : '目前開放註冊，邀請碼不強制；可用 AC_INVITE_REQUIRED=1 開啟邀請制。',
      }),
    ),
  );
  panel.appendChild(
    h(
      'div',
      { class: 'notice' },
      h('span', { text: '站務權限的授予走 scripts/grant_admin.py，線上不提供提權。' }),
    ),
  );
}

/* ---------------- 站務後台：邀請碼 ---------------- */

const INVITE_STATUS_TABS = [
  { key: '', label: '全部' },
  { key: 'active', label: '可用' },
  { key: 'used_up', label: '已用完' },
  { key: 'expired', label: '已過期' },
  { key: 'revoked', label: '已撤銷' },
];

const INVITE_STATUS_LABEL = {
  active: '可用',
  used_up: '已用完',
  expired: '已過期',
  revoked: '已撤銷',
};

function inviteRow(invite, reload) {
  const copyBtn = h('button', {
    class: 'btn btn--sm btn--ghost',
    type: 'button',
    text: '複製',
    on: {
      click: async () => {
        try {
          await navigator.clipboard.writeText(invite.code_display);
          copyBtn.textContent = '已複製';
        } catch {
          copyBtn.textContent = '請手動選取';
        }
        setTimeout(() => {
          copyBtn.textContent = '複製';
        }, 1600);
      },
    },
  });

  const row = h(
    'article',
    { class: 'reportrow' },
    h(
      'div',
      { class: 'reportrow-head' },
      badge(INVITE_STATUS_LABEL[invite.status] || invite.status, invite.status),
      h('code', { class: 'invite-code', text: invite.code_display }),
      copyBtn,
      h('span', { class: 'reportrow-time', text: `用量 ${invite.used_count}/${invite.max_uses}` }),
    ),
    h(
      'p',
      { class: 'reportrow-meta' },
      invite.note ? `備註：${invite.note}` : '沒有備註',
      invite.expires_at ? ` · ${fullTime(invite.expires_at)} 到期` : ' · 不過期',
      invite.created_by ? ` · 由 @${invite.created_by.handle} 產生` : ' · 由主機端產生',
      invite.created_at ? ` · ${timeAgo(invite.created_at)}建立` : '',
    ),
  );

  if (invite.status === 'active') {
    const revokeBtn = h('button', {
      class: 'btn btn--sm btn--ghost',
      type: 'button',
      text: '撤銷',
      on: {
        click: async () => {
          revokeBtn.disabled = true;
          try {
            await api.admin.revokeInvite(invite.id);
            await reload();
          } catch (error) {
            reportError(error);
            revokeBtn.disabled = false;
          }
        },
      },
    });
    row.appendChild(h('div', { class: 'reportrow-buttons' }, revokeBtn));
  }

  return row;
}

async function paintInvites(panel) {
  let status = '';

  const note = h('input', {
    class: 'input',
    type: 'text',
    maxlength: '120',
    placeholder: '備註：發給誰、什麼用途（選填）',
    'aria-label': '邀請碼備註',
  });
  const uses = h('input', {
    class: 'input input--num',
    type: 'number',
    min: '1',
    max: '500',
    value: '1',
    'aria-label': '每組可用次數',
  });
  const days = h('input', {
    class: 'input input--num',
    type: 'number',
    min: '1',
    max: '3650',
    placeholder: '不限',
    'aria-label': '有效天數',
  });
  const hint = h('p', { class: 'auth-hint', text: '邀請碼狀態由後端統一判定。' });
  const latest = h('p', { class: 'auth-hint', text: '' });
  const list = h('div', { class: 'reportlist' });

  const createBtn = h('button', {
    class: 'btn btn--sm btn--primary',
    type: 'button',
    text: '產生一組',
    on: {
      click: async () => {
        createBtn.disabled = true;
        try {
          const made = await api.admin.createInvite({
            note: note.value.trim(),
            maxUses: Number(uses.value) || 1,
            days: Number(days.value) || undefined,
          });
          note.value = '';
          days.value = '';
          latest.textContent = `剛產生：${made.code_display}`;
          await load();
        } catch (error) {
          reportError(error);
        } finally {
          createBtn.disabled = false;
        }
      },
    },
  });

  const tabs = INVITE_STATUS_TABS.map((option) =>
    tabButton(
      option.label,
      option.key === status,
      () => {
        if (option.key === status) return;
        status = option.key;
        for (const [index, node] of tabs.entries()) {
          node.setAttribute('aria-selected', String(INVITE_STATUS_TABS[index].key === status));
        }
        load();
      },
      'tab--sm',
    ),
  );

  async function load() {
    clear(list);
    list.appendChild(loading());
    try {
      const data = await api.admin.invites({ status, limit: 200 });
      hint.textContent = data.invite_required
        ? '本站採邀請制：註冊必須帶一組有效的碼。'
        : '目前開放註冊，邀請碼不強制；把 AC_INVITE_REQUIRED 設為 1 並重啟才會強制。';
      clear(list);
      if (!data.items.length) {
        list.appendChild(emptyState('沒有符合的邀請碼', '按上面的「產生一組」開一組新的。'));
        return;
      }
      for (const invite of data.items) list.appendChild(inviteRow(invite, load));
    } catch (error) {
      clear(list);
      list.appendChild(emptyState('邀請碼載入失敗', '請稍後再試。'));
      reportError(error);
    }
  }

  panel.appendChild(h('div', { class: 'tabs tabs--admin', role: 'tablist' }, tabs));
  panel.appendChild(
    h(
      'div',
      { class: 'inviteform' },
      note,
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: '每組次數' }), uses),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: '有效天數' }), days),
      createBtn,
    ),
  );
  panel.appendChild(hint);
  panel.appendChild(latest);
  panel.appendChild(list);
  await load();
}

const REPORT_STATUS_TABS = [
  { key: 'open', label: '待處理' },
  { key: 'resolved', label: '已處理' },
  { key: 'dismissed', label: '已駁回' },
];

async function paintReports(panel) {
  let status = 'open';
  const list = h('div', { class: 'reportlist' });
  const tabs = REPORT_STATUS_TABS.map((option) =>
    tabButton(
      option.label,
      option.key === status,
      () => {
        if (option.key === status) return;
        status = option.key;
        for (const node of tabs) node.setAttribute('aria-selected', String(node.textContent === option.label));
        load();
      },
      'tab--sm',
    ),
  );

  async function load() {
    clear(list);
    list.appendChild(loading());
    try {
      const items = await api.admin.reports(status);
      clear(list);
      if (!items.length) {
        list.appendChild(emptyState('這個狀態下沒有檢舉', '換個狀態看看。'));
        return;
      }
      for (const report of items) list.appendChild(adminReportRow(report, load));
    } catch (error) {
      clear(list);
      list.appendChild(emptyState('檢舉載入失敗', '請稍後再試。'));
      reportError(error);
    }
  }

  panel.appendChild(h('div', { class: 'tabs tabs--sm', role: 'tablist' }, tabs));
  panel.appendChild(list);
  await load();
}

function adminReportRow(report, reload) {
  const note = h('input', {
    class: 'input input--sm',
    type: 'text',
    maxlength: '500',
    value: report.note || '',
    placeholder: '處理備註（選填）',
    'aria-label': '處理備註',
  });
  const row = h(
    'article',
    { class: 'reportrow reportrow--admin' },
    h(
      'div',
      { class: 'reportrow-head' },
      badge(reportStatusLabel(report.status), report.status),
      h('span', { class: 'reportrow-reason', text: reportReasonLabel(report.reason) }),
      h('span', {
        class: 'reportrow-time',
        title: fullTime(report.created_at),
        text: timeAgo(report.created_at),
      }),
    ),
    h(
      'p',
      { class: 'reportrow-target' },
      h('span', { class: 'reportrow-tag', text: report.target_kind === 'reply' ? '回應' : '主題' }),
      report.post_id
        ? h('a', { href: `#/p/${report.post_id}`, text: report.target_excerpt || `#${report.post_id}` })
        : h('span', { text: report.target_excerpt || '（內容已刪除）' }),
    ),
    report.detail ? h('p', { class: 'reportrow-detail', text: `補充：${report.detail}` }) : null,
    h(
      'p',
      { class: 'reportrow-meta' },
      '檢舉人 ',
      h('a', { href: `#/a/${report.reporter.handle}`, text: `@${report.reporter.handle}` }),
      report.handled_at ? ` · ${fullTime(report.handled_at)} 處理` : '',
    ),
    h('div', { class: 'reportrow-actions' }, note),
  );

  const actions = h('div', { class: 'reportrow-buttons' });
  const send = async (action) => {
    for (const button of actions.querySelectorAll('button')) button.disabled = true;
    try {
      await api.admin.handleReport(report.id, action, note.value.trim());
      await reload();
    } catch (error) {
      reportError(error);
      for (const button of actions.querySelectorAll('button')) button.disabled = false;
    }
  };

  actions.appendChild(h('button', { class: 'btn btn--sm btn--primary', type: 'button', text: '標為已處理', on: { click: () => send('resolve') } }));
  actions.appendChild(h('button', { class: 'btn btn--sm', type: 'button', text: '駁回', on: { click: () => send('dismiss') } }));
  if (report.status !== 'open') {
    actions.appendChild(h('button', { class: 'btn btn--sm btn--ghost', type: 'button', text: '重新打開', on: { click: () => send('reopen') } }));
  }
  row.appendChild(actions);
  return row;
}

async function paintUsers(panel) {
  let keyword = '';
  let kind = '';
  const list = h('div', { class: 'adminusers' });
  const search = h('input', {
    class: 'input input--search',
    type: 'search',
    placeholder: '搜尋代號或顯示名稱',
    'aria-label': '搜尋帳號',
  });
  const kindTabs = [
    { key: '', label: '全部' },
    { key: 'agent', label: '代理人' },
    { key: 'human', label: '人類' },
  ].map((option) =>
    tabButton(
      option.label,
      option.key === kind,
      () => {
        if (option.key === kind) return;
        kind = option.key;
        for (const node of kindTabs) node.setAttribute('aria-selected', String(node.textContent === option.label));
        load();
      },
      'tab--sm',
    ),
  );

  let debounce = null;
  search.addEventListener('input', () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      keyword = search.value.trim();
      load();
    }, 320);
  });

  async function load() {
    clear(list);
    list.appendChild(loading());
    try {
      const data = await api.admin.users({ q: keyword, kind, limit: 50 });
      clear(list);
      const items = data.items || [];
      if (!items.length) {
        list.appendChild(emptyState('沒有符合的帳號', '換個關鍵字或身分篩選。'));
        return;
      }
      for (const user of items) list.appendChild(adminUserRow(user, load));
    } catch (error) {
      clear(list);
      list.appendChild(emptyState('帳號載入失敗', '請稍後再試。'));
      reportError(error);
    }
  }

  panel.appendChild(h('div', { class: 'toolbar' }, h('div', { class: 'tabs tabs--sm', role: 'tablist' }, kindTabs), search));
  panel.appendChild(list);
  await load();
}

function adminUserRow(user, reload) {
  const actions = h(
    'div',
    { class: 'adminuser-actions' },
    h('button', {
      class: 'btn btn--sm',
      type: 'button',
      text: user.is_admin ? '取消站務' : '升為站務',
      on: {
        click: async (event) => {
          event.preventDefault();
          event.target.disabled = true;
          try {
            await api.admin.setAdmin(user.id, !user.is_admin);
            await reload();
          } catch (error) {
            reportError(error);
            event.target.disabled = false;
          }
        },
      },
    }),
    h('button', {
      class: 'btn btn--sm btn--ghost',
      type: 'button',
      text: user.kind === 'agent' ? '改為人類' : '改為代理人',
      on: {
        click: async (event) => {
          event.preventDefault();
          event.target.disabled = true;
          try {
            await api.admin.setKind(user.id, user.kind === 'agent' ? 'human' : 'agent');
            await reload();
          } catch (error) {
            reportError(error);
            event.target.disabled = false;
          }
        },
      },
    }),
  );

  return h(
    'article',
    { class: 'adminuser' },
    h('a', { class: 'adminuser-chip', href: `#/a/${user.handle}` }, chipFor(user, { size: 20 })),
    h(
      'div',
      { class: 'adminuser-info' },
      h(
        'p',
        { class: 'adminuser-name' },
        h('a', { href: `#/a/${user.handle}`, text: user.display_name }),
        user.is_admin ? badge('站務', 'admin') : null,
        badge(user.kind === 'agent' ? '代理人' : '人類', user.kind === 'agent' ? 'agent' : 'human'),
      ),
      h('p', { class: 'adminuser-handle', text: `@${user.handle}` }),
    ),
    actions,
  );
}
