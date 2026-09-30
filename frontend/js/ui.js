/**
 * DOM 建構與格式化工具。
 * 全站一律以 DOM API 組裝節點、以 textContent 寫入使用者資料，不使用 innerHTML。
 */

export function h(tag, props = null, ...children) {
  const el = document.createElement(tag);

  if (props) {
    for (const [key, value] of Object.entries(props)) {
      if (value === null || value === undefined || value === false) continue;
      if (key === 'class') el.className = value;
      else if (key === 'text') el.textContent = value;
      else if (key === 'dataset') Object.assign(el.dataset, value);
      else if (key === 'on') {
        for (const [event, handler] of Object.entries(value)) el.addEventListener(event, handler);
      } else if (key in el && key !== 'list') el[key] = value;
      else el.setAttribute(key, value);
    }
  }

  append(el, children);
  return el;
}

export function append(parent, children) {
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    if (Array.isArray(child)) append(parent, child);
    else if (child instanceof Node) parent.appendChild(child);
    else parent.appendChild(document.createTextNode(String(child)));
  }
  return parent;
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

export function frag(...children) {
  const f = document.createDocumentFragment();
  append(f, children);
  return f;
}

/* ---------------- 主題分區 ---------------- */

export const SECTIONS = [
  { key: 'all', label: '全部' },
  { key: 'field-notes', label: '現場筆記' },
  { key: 'bug-report', label: '疑難排查' },
  { key: 'prompt', label: '指令提示' },
  { key: 'tooling', label: '工具編排' },
  { key: 'general', label: '綜合討論' },
];

const SECTION_MAP = new Map(SECTIONS.map((s) => [s.key, s.label]));

export function sectionLabel(key) {
  return SECTION_MAP.get(key) || key;
}

/* ---------------- 排序與檢舉理由 ---------------- */

export const SORTS = [
  { key: 'new', label: '最新' },
  { key: 'hot', label: '熱門' },
  { key: 'discussed', label: '討論最多' },
];

export const REPORT_REASONS = [
  { key: 'spam', label: '廣告或洗版' },
  { key: 'abuse', label: '攻擊性內容' },
  { key: 'offtopic', label: '離題／分區不符' },
  { key: 'other', label: '其他' },
];

const REPORT_REASON_MAP = new Map(REPORT_REASONS.map((r) => [r.key, r.label]));

export function reportReasonLabel(key) {
  return REPORT_REASON_MAP.get(key) || key;
}

export const NOTIFICATION_KINDS = {
  reply: '回應了你的主題',
  like: '對你的主題按讚',
  follow: '開始追蹤你',
  suspend: '帳號狀態變更',
};

export function notificationLabel(kind) {
  return NOTIFICATION_KINDS[kind] || '有新動態';
}

const REPORT_STATUS = {
  open: '待處理',
  resolved: '已處理',
  dismissed: '已駁回',
};

export function reportStatusLabel(status) {
  return REPORT_STATUS[status] || status;
}

/* ---------------- 時間 ---------------- */

/** 後端回傳的是不帶時區的 UTC 時間，需補上 Z 再解析。 */
export function parseDate(iso) {
  if (!iso) return new Date();
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
  return new Date(hasZone ? iso : `${iso}Z`);
}

export function timeAgo(iso) {
  const then = parseDate(iso);
  const secs = Math.max(0, Math.round((Date.now() - then.getTime()) / 1000));
  if (secs < 60) return '剛剛';
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins} 分鐘前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小時前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  return then.toLocaleDateString('zh-Hant', { year: 'numeric', month: 'numeric', day: 'numeric' });
}

export function fullTime(iso) {
  return parseDate(iso).toLocaleString('zh-Hant', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/* ---------------- 提示訊息 ---------------- */

let toastTimer = null;

export function toast(message, kind = 'info') {
  const node = document.getElementById('toast');
  if (!node) return;
  node.textContent = message;
  node.dataset.kind = kind;
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    node.hidden = true;
  }, kind === 'error' ? 5200 : 3200);
}

/** 把非預期錯誤收斂成一句可讀訊息，同時保留主控台線索。 */
export function reportError(error) {
  console.error(error);
  toast(error && error.message ? error.message : '發生未預期的錯誤。', 'error');
}

/* ---------------- 對話方塊 ---------------- */

/**
 * 需要使用者點頭的動作（刪除、覆寫、下架…）。
 * 不用 window.confirm：它會擋住整個主執行緒，也無法顯示脈絡。
 * @returns {Promise<boolean>}
 */
export function confirmDialog({
  title,
  body = '',
  confirmText = '確定',
  cancelText = '取消',
  danger = false,
} = {}) {
  return new Promise((resolve) => {
    let settled = false;
    const close = (value) => {
      if (settled) return;
      settled = true;
      document.removeEventListener('keydown', onKey);
      veil.remove();
      resolve(value);
    };
    const onKey = (event) => {
      if (event.key === 'Escape') close(false);
      if (event.key === 'Enter') close(true);
    };

    const ok = h('button', {
      class: `btn ${danger ? 'btn--danger' : 'btn--primary'}`,
      type: 'button',
      text: confirmText,
      on: { click: () => close(true) },
    });

    const veil = h(
      'div',
      {
        class: 'modal-veil',
        role: 'dialog',
        'aria-modal': 'true',
        'aria-label': title,
        on: {
          click: (event) => {
            if (event.target === veil) close(false);
          },
        },
      },
      h(
        'div',
        { class: 'modal' },
        h('h3', { class: 'modal-title', text: title }),
        body ? h('p', { class: 'modal-body', text: body }) : null,
        h(
          'div',
          { class: 'modal-actions' },
          h('button', {
            class: 'btn',
            type: 'button',
            text: cancelText,
            on: { click: () => close(false) },
          }),
          ok,
        ),
      ),
    );

    document.body.appendChild(veil);
    document.addEventListener('keydown', onKey);
    ok.focus();
  });
}

/** 徽章：未讀數、站務、身分標記都用它。 */
export function badge(text, kind = '') {
  return h('span', { class: `badge${kind ? ` badge--${kind}` : ''}`, text: String(text) });
}
