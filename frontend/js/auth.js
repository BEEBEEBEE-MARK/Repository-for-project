/**
 * 登录态管理
 * - token 与用户名保存在 localStorage
 * - 供 api.js（注入 token / 401 清理）与各业务页（路由守卫）调用
 */

const TOKEN_KEY = 'travel_token';
const USERNAME_KEY = 'travel_username';

/** 读取 token，未登录返回空字符串 */
function getToken() {
  return localStorage.getItem(TOKEN_KEY) || '';
}

/** 读取当前用户名 */
function getUsername() {
  return localStorage.getItem(USERNAME_KEY) || '';
}

/** 登录成功后保存登录态 */
function setAuth(token, username) {
  localStorage.setItem(TOKEN_KEY, token);
  if (username) localStorage.setItem(USERNAME_KEY, username);
}

/** 更新本地用户名（如接口返回更准确的值） */
function setUsername(username) {
  if (username) localStorage.setItem(USERNAME_KEY, username);
}

/** 清除登录态（退出登录 / token 失效） */
function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USERNAME_KEY);
}

/** 已登录则跳转主页（用于登录页：已登录访问登录页自动跳主页） */
function redirectIfAuthed() {
  if (getToken()) {
    location.replace('index.html');
  }
}

/** 路由守卫：未登录跳转登录页（用于除登录页外的所有页面） */
function requireAuth() {
  if (!getToken()) {
    location.replace('login.html');
  }
}

/** 退出登录：清除登录态并回登录页 */
function logout() {
  clearAuth();
  location.replace('login.html');
}
