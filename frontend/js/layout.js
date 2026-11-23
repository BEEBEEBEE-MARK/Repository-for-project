/**
 * 全站公共布局
 * - mountTopbar()：注入顶部栏（应用名 + 用户名 + 退出登录）
 * - setTopbarUser()：更新顶部栏显示的用户名
 *
 * 依赖：auth.js（getUsername / logout）
 * 使用：在 body 末尾、DOM 就绪后调用 mountTopbar()
 */

/** 顶部栏所需的图标（随顶部栏一起注入，页面无需重复定义） */
const TOPBAR_SYMBOLS = `
<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
  <symbol id="ic-logo" viewBox="0 0 24 24"><circle cx="17.2" cy="6.8" r="2.3"/><path d="M2.5 19.5l6-8 3.6 4.4 2.6-3.2 7.3 6.8"/><path d="M2 19.5h20"/></symbol>
  <symbol id="ic-logout" viewBox="0 0 24 24"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></symbol>
</defs></svg>
`;

/** 注入顶部栏并绑定交互 */
function mountTopbar() {
  document.body.insertAdjacentHTML(
    'afterbegin',
    // symbols 必须放在 header 之前，确保 <use> 引用可立即解析
    TOPBAR_SYMBOLS +
    `
    <header class="topbar">
      <button type="button" class="topbar__brand" id="topbar-brand">
        <span class="brand-mark"><svg class="icon"><use href="#ic-logo"/></svg></span>
        <span class="topbar__title">旅梦规划助手</span>
      </button>
      <div class="topbar__user">
        <span class="avatar" id="topbar-avatar"></span>
        <span class="topbar__name" id="topbar-name"></span>
        <span class="topbar__divider"></span>
        <button type="button" class="topbar__logout" id="topbar-logout">
          <svg class="icon icon--sm"><use href="#ic-logout"/></svg>退出登录
        </button>
      </div>
    </header>
    `
  );

  setTopbarUser(getUsername());

  // 点击应用名回到主页
  document.getElementById('topbar-brand').addEventListener('click', () => {
    if (!canLeavePage()) return;
    location.href = 'index.html';
  });

  // 退出登录：清除登录态并跳转登录页（主页面 PRD §4 #3）
  document.getElementById('topbar-logout').addEventListener('click', () => {
    if (!canLeavePage()) return;
    logout();
  });
}

/**
 * 离开页面守卫：页面可定义 window.beforeLeavePage() 返回 false 以阻止跳转
 * （用于生成页「生成中离开需确认」，生成 PRD §3.2）
 */
function canLeavePage() {
  if (typeof window.beforeLeavePage !== 'function') return true;
  return window.beforeLeavePage();
}

/** 更新顶部栏用户名与头像首字母 */
function setTopbarUser(username) {
  const nameEl = document.getElementById('topbar-name');
  const avatarEl = document.getElementById('topbar-avatar');
  if (!nameEl || !avatarEl) return;

  const name = username || '';
  nameEl.textContent = name;
  avatarEl.textContent = name ? name.charAt(0).toUpperCase() : '?';
}
