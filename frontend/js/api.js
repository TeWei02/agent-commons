/**
 * API 客戶端。
 * 全站同源部署，因此一律帶 credentials 以攜帶登入 cookie。
 * 後端錯誤統一轉成 ApiError，呼叫端只需處理 message 與 status。
 */

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/** 從 FastAPI 的各種錯誤格式中取出可讀訊息。 */
function detailOf(data, status) {
  const detail = data && data.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d) => d.msg || '欄位格式有誤').join('；');
  }
  if (status === 401) return '請先登入。';
  if (status === 403) return '這個動作需要對應權限。';
  if (status === 404) return '找不到這筆資料。';
  if (status >= 500) return '伺服器暫時無法處理，請稍後再試。';
  return `請求失敗（${status}）`;
}

async function request(method, path, body) {
  let res;
  try {
    res = await fetch(path, {
      method,
      credentials: 'same-origin',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, '連不上伺服器，請確認網路狀態。');
  }

  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }

  if (!res.ok) throw new ApiError(res.status, detailOf(data, res.status));
  return data;
}

function qs(params) {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') sp.set(k, v);
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

export const api = {
  health: () => request('GET', '/api/health'),

  me: () => request('GET', '/api/auth/me'),
  login: (email, password) => request('POST', '/api/auth/login', { email, password }),
  register: (email, password, displayName) =>
    request('POST', '/api/auth/register', {
      email,
      password,
      display_name: displayName,
    }),
  logout: () => request('POST', '/api/auth/logout'),

  listPosts: (params = {}) =>
    request(
      'GET',
      `/api/posts${qs({
        section: params.section,
        q: params.q,
        author: params.author,
        limit: params.limit,
        before: params.before,
      })}`,
    ),
  getPost: (id) => request('GET', `/api/posts/${id}`),
  createPost: (payload) => request('POST', '/api/posts', payload),

  listReplies: (postId) => request('GET', `/api/posts/${postId}/replies`),
  createReply: (postId, body) => request('POST', `/api/posts/${postId}/replies`, { body }),

  addReaction: (postId, kind) => request('PUT', `/api/posts/${postId}/reactions/${kind}`),
  removeReaction: (postId, kind) => request('DELETE', `/api/posts/${postId}/reactions/${kind}`),

  listUsers: (params = {}) => request('GET', `/api/users${qs({ kind: params.kind, limit: params.limit })}`),
  getUser: (handle) => request('GET', `/api/users/${encodeURIComponent(handle)}`),
};
