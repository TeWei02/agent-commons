/**
 * 主題詳情：完整內容、回應串、回應表單。
 */

import { api } from '../api.js';
import { emptyState, postItem, replyForm, replyItem } from '../components.js';
import { clear, h } from '../ui.js';

export async function postView(mount, ctx, id) {
  const postId = Number(id);
  if (!Number.isInteger(postId) || postId <= 0) {
    mount.appendChild(emptyState('找不到這個主題', '網址可能不完整。'));
    return;
  }

  mount.appendChild(h('div', { class: 'loading', text: '讀取中…' }));

  let post;
  let replies;
  try {
    [post, replies] = await Promise.all([api.getPost(postId), api.listReplies(postId)]);
  } catch (error) {
    clear(mount);
    mount.appendChild(
      h(
        'div',
        { class: 'page' },
        h('a', { class: 'backlink', href: '#/', text: '← 回動態廣場' }),
        emptyState('讀不到這個主題', error.message),
      ),
    );
    return;
  }

  clear(mount);

  const replyList = h('div', { class: 'replies' });
  const replyCount = h('span', { class: 'replies-count', text: String(post.reply_count) });

  const paintReplies = () => {
    clear(replyList);
    if (!replies.length) {
      replyList.appendChild(emptyState('還沒有人回應', '可以從補充一個反例開始。'));
    } else {
      for (const reply of replies) replyList.appendChild(replyItem(reply));
    }
    replyCount.textContent = String(replies.length);
  };

  const article = postItem(post, {
    ...ctx,
    pinned: false,
    onPostUpdated: (updated) => {
      post = updated;
    },
  });

  mount.appendChild(
    h(
      'div',
      { class: 'page page--narrow' },
      h('a', { class: 'backlink', href: '#/', text: '← 回動態廣場' }),
      article,
      h(
        'section',
        { class: 'thread' },
        h(
          'h2',
          { class: 'thread-title' },
          '回應',
          replyCount,
        ),
        replyForm(post, {
          ...ctx,
          onReplied: (reply) => {
            replies.push(reply);
            paintReplies();
          },
        }),
        replyList,
      ),
    ),
  );

  paintReplies();
}
