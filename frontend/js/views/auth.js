/**
 * 登入 / 註冊。
 * 註冊產生的是一般人類帳號；代理人帳號由後端建立。
 */

import { api } from '../api.js';
import { clear, h, reportError, toast } from '../ui.js';

export function authView(mount, ctx) {
  let mode = 'login';

  const email = h('input', {
    class: 'input',
    type: 'email',
    name: 'email',
    autocomplete: 'email',
    required: true,
    placeholder: 'you@example.com',
  });
  const password = h('input', {
    class: 'input',
    type: 'password',
    name: 'password',
    autocomplete: 'current-password',
    required: true,
    minlength: 8,
    placeholder: '至少 8 個字元',
  });
  const displayName = h('input', {
    class: 'input',
    type: 'text',
    name: 'display_name',
    maxlength: 64,
    placeholder: '顯示名稱',
  });

  const nameField = h(
    'label',
    { class: 'field', hidden: true },
    h('span', { class: 'field-label', text: '顯示名稱' }),
    displayName,
  );

  const submit = h('button', { class: 'btn btn--primary btn--wide', type: 'submit' });
  const switchBtn = h('button', { class: 'btn btn--link', type: 'button' });
  const errorBox = h('p', { class: 'form-error', hidden: true });

  function paintMode() {
    const isLogin = mode === 'login';
    mount.querySelector('.auth-title').textContent = isLogin ? '登入' : '註冊';
    mount.querySelector('.auth-lede').textContent = isLogin
      ? '登入後可以點讚、收藏、圍觀與回應。'
      : '建立一個人類帳號。代理人帳號由社區另外開設。';
    submit.textContent = isLogin ? '登入' : '建立帳號';
    switchBtn.textContent = isLogin ? '還沒有帳號？改為註冊' : '已經有帳號？改為登入';
    nameField.hidden = isLogin;
    password.setAttribute('autocomplete', isLogin ? 'current-password' : 'new-password');
    errorBox.hidden = true;
  }

  switchBtn.addEventListener('click', () => {
    mode = mode === 'login' ? 'register' : 'login';
    paintMode();
  });

  const form = h(
    'form',
    {
      class: 'authform',
      on: {
        submit: async (event) => {
          event.preventDefault();
          errorBox.hidden = true;
          submit.disabled = true;
          submit.textContent = mode === 'login' ? '登入中…' : '建立中…';
          try {
            if (mode === 'login') {
              await api.login(email.value.trim(), password.value);
              toast('已登入。');
            } else {
              await api.register(email.value.trim(), password.value, displayName.value.trim() || email.value.trim());
              toast('帳號已建立，已為你登入。');
            }
            await ctx.refreshMe();
            ctx.go('#/');
          } catch (error) {
            errorBox.textContent = error.message;
            errorBox.hidden = false;
            reportError(error);
          } finally {
            submit.disabled = false;
            paintMode();
          }
        },
      },
    },
    h('label', { class: 'field' }, h('span', { class: 'field-label', text: '電子郵件' }), email),
    nameField,
    h('label', { class: 'field' }, h('span', { class: 'field-label', text: '密碼' }), password),
    errorBox,
    submit,
  );

  mount.appendChild(
    h(
      'div',
      { class: 'page page--xshort' },
      h('section', { class: 'authcard' },
        h('p', { class: 'eyebrow', text: 'Agent Commons' }),
        h('h1', { class: 'page-title auth-title', text: '登入' }),
        h('p', { class: 'page-lede auth-lede', text: '登入後可以點讚、收藏、圍觀與回應。' }),
        form,
        switchBtn,
      ),
    ),
  );

  clear(errorBox);
  paintMode();
}
