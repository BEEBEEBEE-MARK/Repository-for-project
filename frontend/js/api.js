/**
 * 统一请求封装
 * - 开发环境指向 localhost:8000，生产环境走同源相对路径（部署零改代码）
 * - 自动注入 token、解析 { code, message, data }
 * - 401 自动清理登录态并跳转登录页（登录类接口可关闭）
 *
 * 用法：
 *   const res = await apiRequest('/api/auth/login', {
 *     method: 'POST',
 *     body: { account, password, remember_me },
 *     withToken: false,
 *     onUnauthorized: false,
 *   });
 *   if (res.code === 0) { ... } else { toast(res.message); }
 */

const API_BASE = ['localhost', '127.0.0.1'].includes(location.hostname)
  ? 'http://localhost:8000'
  : '';

const DEFAULT_TIMEOUT = 30000;

// file:// 直接打开时无法调用接口，给出明确提示（开发期便利）
if (location.protocol === 'file:') {
  console.warn('[api] 请用本地静态服务器打开页面（file:// 协议无法调用后端接口）');
}

/**
 * @param {string} path 接口路径，如 '/api/auth/login'
 * @param {object} options
 * @param {string} [options.method='GET']
 * @param {object|null} [options.body=null] 请求体（JSON）
 * @param {boolean} [options.withToken=true] 是否携带 token
 * @param {boolean} [options.onUnauthorized=withToken] 401 时是否清理登录态并跳转
 * @param {number} [options.timeout=30000] 超时毫秒数
 * @returns {Promise<{code:number,message:string,data:any}>}
 */
async function apiRequest(path, options = {}) {
  const {
    method = 'GET',
    body = null,
    withToken = true,
    onUnauthorized = withToken,
    timeout = DEFAULT_TIMEOUT,
  } = options;

  const headers = {};
  if (body) headers['Content-Type'] = 'application/json';
  if (withToken) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(API_BASE + path, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    const result = await response.json().catch(() => null);

    // 后端未返回统一格式（如网关错误页），按服务器异常处理
    if (!result || typeof result.code === 'undefined') {
      return { code: 500, message: '网络异常，请稍后重试', data: null };
    }

    if (result.code === 401 && onUnauthorized) {
      clearAuth();
      location.replace('login.html');
    }

    return result;
  } catch (error) {
    if (error.name === 'AbortError') {
      return { code: 504, message: '请求超时，请重试', data: null };
    }
    return { code: -1, message: '网络异常，请稍后重试', data: null };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * 文件下载（PDF 导出）
 * 成功时接口返回二进制流，失败时返回 JSON，故需区分处理。
 * @returns {Promise<{ok:boolean, blob?:Blob, filename?:string, message?:string}>}
 */
async function apiDownload(path, timeout = 35000) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(API_BASE + path, { headers, signal: controller.signal });
    const contentType = response.headers.get('Content-Type') || '';

    if (!response.ok || contentType.includes('application/json')) {
      const result = await response.json().catch(() => null);
      if (result && result.code === 401) {
        clearAuth();
        location.replace('login.html');
      }
      return { ok: false, message: (result && result.message) || '导出失败，请重试' };
    }

    const blob = await response.blob();
    return {
      ok: true,
      blob,
      filename: parseFilename(response.headers.get('Content-Disposition')),
    };
  } catch (error) {
    if (error.name === 'AbortError') return { ok: false, message: '导出超时，请重试' };
    return { ok: false, message: '网络异常，请稍后重试' };
  } finally {
    clearTimeout(timer);
  }
}

/** 解析 Content-Disposition 中的文件名（优先 RFC 5987 的 filename*） */
function parseFilename(disposition) {
  if (!disposition) return '旅行计划.pdf';

  const utf8Match = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (utf8Match) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch (error) {
      /* 解析失败则走下面的普通 filename */
    }
  }

  const plainMatch = /filename="?([^";]+)"?/i.exec(disposition);
  return plainMatch ? plainMatch[1] : '旅行计划.pdf';
}

/** 触发浏览器下载 */
function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
