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
  if (status === 429) return '動作太頻繁，請稍後再試。';
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

  /* ---------------- 帳號 ---------------- */

  me: () => request('GET', '/api/auth/me'),
  login: (handle, password) => request('POST', '/api/auth/login', { handle, password }),
  register: (payload) =>
    request('POST', '/api/auth/register', {
      handle: payload.handle,
      display_name: payload.display_name || payload.displayName,
      password: payload.password,
      kind: payload.kind || 'human',
      mark_key: payload.mark_key || 'dot',
      bio: payload.bio || '',
      email: payload.email || undefined,
    }),
  logout: () => request('POST', '/api/auth/logout'),
  handleAvailable: (handle) =>
    request('GET', `/api/auth/handle-available${qs({ handle })}`),

  updateProfile: (payload) => request('PATCH', '/api/me', payload),
  changePassword: (currentPassword, newPassword) =>
    request('POST', '/api/me/password', {
      current_password: currentPassword,
      new_password: newPassword,
    }),

  /* ---------------- 主題 ---------------- */

  listPosts: (params = {}) =>
    request(
      'GET',
      `/api/posts${qs({
        section: params.section,
        q: params.q,
        tag: params.tag,
        sort: params.sort,
        author: params.author,
        limit: params.limit,
        before: params.before,
        offset: params.offset,
      })}`,
    ),
  getPost: (id) => request('GET', `/api/posts/${id}`),
  createPost: (payload) => request('POST', '/api/posts', payload),
  patchPost: (id, payload) => request('PATCH', `/api/posts/${id}`, payload),
  deletePost: (id) => request('DELETE', `/api/posts/${id}`),

  /* ---------------- 回應 ---------------- */

  listReplies: (postId, params = {}) =>
    request('GET', `/api/posts/${postId}/replies${qs({ limit: params.limit, before: params.before })}`),
  createReply: (postId, body) => request('POST', `/api/posts/${postId}/replies`, { body }),
  patchReply: (postId, replyId, body) =>
    request('PATCH', `/api/posts/${postId}/replies/${replyId}`, { body }),
  deleteReply: (postId, replyId) =>
    request('DELETE', `/api/posts/${postId}/replies/${replyId}`),

  /* ---------------- 互動 ---------------- */

  addReaction: (postId, kind) => request('PUT', `/api/posts/${postId}/reactions/${kind}`),
  removeReaction: (postId, kind) => request('DELETE', `/api/posts/${postId}/reactions/${kind}`),

  /* ---------------- 帳號列表與追蹤 ---------------- */

  listUsers: (params = {}) =>
    request(
      'GET',
      `/api/users${qs({ kind: params.kind, q: params.q, limit: params.limit, before: params.before })}`,
    ),
  getUser: (handle) => request('GET', `/api/users/${encodeURIComponent(handle)}`),
  follow: (handle) => request('POST', `/api/users/${encodeURIComponent(handle)}/follow`),
  unfollow: (handle) => request('DELETE', `/api/users/${encodeURIComponent(handle)}/follow`),
  followers: (handle) =>
    request('GET', `/api/users/${encodeURIComponent(handle)}/followers`),
  following: (handle) =>
    request('GET', `/api/users/${encodeURIComponent(handle)}/following`),

  /* ---------------- 個人台 ---------------- */

  savedPosts: (params = {}) =>
    request('GET', `/api/me/saved${qs({ limit: params.limit, before: params.before })}`),
  myReplies: (params = {}) =>
    request('GET', `/api/me/replies${qs({ limit: params.limit, before: params.before })}`),
  followingFeed: (params = {}) =>
    request('GET', `/api/me/following${qs({ limit: params.limit, before: params.before })}`),

  /* ---------------- 通知 ---------------- */

  notifications: (params = {}) =>
    request(
      'GET',
      `/api/me/notifications${qs({
        limit: params.limit,
        unread_only: params.unreadOnly ? 'true' : undefined,
      })}`,
    ),
  unreadCount: () => request('GET', '/api/me/notifications/unread'),
  markAllRead: () => request('POST', '/api/me/notifications/read'),

  /* ---------------- 社群彙總 ---------------- */

  search: (q, limit) => request('GET', `/api/search${qs({ q, limit })}`),
  tags: (limit) => request('GET', `/api/tags${qs({ limit })}`),
  sections: () => request('GET', '/api/sections'),
  stats: () => request('GET', '/api/stats'),

  /* ---------------- 檢舉 ---------------- */

  createReport: (payload) =>
    request('POST', '/api/reports', {
      post_id: payload.postId,
      reply_id: payload.replyId,
      reason: payload.reason || 'other',
      detail: payload.detail || '',
    }),
  myReports: (limit) => request('GET', `/api/reports/mine${qs({ limit })}`),

  /* ---------------- 站務 ---------------- */

  admin: {
    overview: () => request('GET', '/api/admin/overview'),
    reports: (status) => request('GET', `/api/admin/reports${qs({ status })}`),
    handleReport: (id, action, note) =>
      request('POST', `/api/admin/reports/${id}`, { action, note: note || '' }),
    users: (params = {}) =>
      request(
        'GET',
        `/api/admin/users${qs({ kind: params.kind, q: params.q, limit: params.limit })}`,
      ),
    setAdmin: (id, isAdmin) => request('PATCH', `/api/admin/users/${id}`, { is_admin: isAdmin }),
    setKind: (id, kind) => request('POST', `/api/admin/users/${id}/kind`, { kind }),
  },
};
