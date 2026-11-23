/**
 * 公共交互
 * 目前仅含 toast；后续页面开发时在此补充 modal / loading 等
 */

/** 显示轻提示，默认 2.2 秒自动消失 */
function toast(message, duration = 2200) {
  let el = document.getElementById('toast');

  if (!el) {
    el = document.createElement('div');
    el.id = 'toast';
    el.className = 'toast';
    el.innerHTML =
      '<svg class="icon"><use href="#ic-check"/></svg><span></span>';
    document.body.appendChild(el);
  }

  el.querySelector('span').textContent = message;
  el.classList.add('toast--show');

  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove('toast--show'), duration);
}

/** ISO 时间字符串 → 本地时间「yyyy-MM-dd HH:mm」 */
function formatDateTime(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} `
    + `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** 出发日期 + 天数 → 「2026-04-12 ~ 04-16」；未填日期时返回「5 天」 */
function formatDateRange(startDate, days) {
  const count = Math.max(1, Number(days) || 1);
  if (!startDate) return `${count} 天`;

  const start = new Date(`${startDate}T00:00:00`);
  if (Number.isNaN(start.getTime())) return `${count} 天`;

  const end = new Date(start);
  end.setDate(start.getDate() + count - 1);
  const pad = (n) => String(n).padStart(2, '0');
  return `${startDate} ~ ${pad(end.getMonth() + 1)}-${pad(end.getDate())}`;
}

/**
 * 二次确认弹窗（替换原生 confirm，样式与原型一致）
 * @returns {Promise<boolean>} 确定 true / 取消 false
 */
function showConfirm({ title, message, okText = '确定', cancelText = '取消', danger = false }) {
  return new Promise((resolve) => {
    const mask = document.createElement('div');
    mask.className = 'modal-mask';
    mask.innerHTML = `
      <div class="modal" role="dialog" aria-modal="true">
        <div class="modal__icon">
          <svg class="icon icon--lg"><use href="#ic-alert"/></svg>
        </div>
        <h3 class="modal__title"></h3>
        <p class="modal__text"></p>
        <div class="modal__foot">
          <button type="button" class="btn btn--ghost" data-modal-cancel></button>
          <button type="button" class="${danger ? 'btn btn--danger' : 'btn btn--primary'}" data-modal-ok></button>
        </div>
      </div>`;

    mask.querySelector('.modal__title').textContent = title;
    mask.querySelector('.modal__text').textContent = message;
    mask.querySelector('[data-modal-cancel]').textContent = cancelText;
    mask.querySelector('[data-modal-ok]').textContent = okText;

    document.body.appendChild(mask);
    requestAnimationFrame(() => mask.classList.add('modal-mask--show'));

    function close(result) {
      mask.remove();
      resolve(result);
    }

    mask.querySelector('[data-modal-ok]').addEventListener('click', () => close(true));
    mask.querySelector('[data-modal-cancel]').addEventListener('click', () => close(false));
    mask.addEventListener('click', (event) => {
      if (event.target === mask) close(false);
    });
  });
}

/**
 * 补充攻略弹窗（生成结果页 / 计划详情页共用）
 * @returns {Promise<Array<{type:string, content:string}>|null>} 取消返回 null
 */
function openGuideDialog({
  title = '补充参考攻略',
  description = '添加攻略后，将基于当前条件重新生成一版方案。链接仅作来源记录，粘贴的正文参与生成。',
  okText = '重新生成',
} = {}) {
  return new Promise((resolve) => {
    const mask = document.createElement('div');
    mask.className = 'modal-mask';
    mask.innerHTML = `
      <div class="modal modal--guide" role="dialog" aria-modal="true">
        <h3></h3>
        <p class="modal__desc"></p>
        <div class="guide-list" data-guide-list>
          <div class="guide-item">
            <select>
              <option value="link">链接</option>
              <option value="text">文本</option>
            </select>
            <input placeholder="粘贴链接或攻略正文（文本 ≤500 字）" />
            <button type="button" class="guide-item__remove" data-guide-remove aria-label="删除这条参考攻略">
              <svg class="icon icon--sm"><use href="#ic-close"/></svg>
            </button>
          </div>
        </div>
        <button type="button" class="btn btn--ghost btn--sm" data-guide-add>
          <svg class="icon icon--sm"><use href="#ic-plus"/></svg>添加一条
        </button>
        <div class="modal__foot">
          <button type="button" class="btn btn--ghost" data-modal-cancel>取消</button>
          <button type="button" class="btn btn--primary" data-modal-ok></button>
        </div>
      </div>`;

    mask.querySelector('h3').textContent = title;
    mask.querySelector('.modal__desc').textContent = description;
    mask.querySelector('[data-modal-ok]').textContent = okText;

    document.body.appendChild(mask);
    requestAnimationFrame(() => mask.classList.add('modal-mask--show'));

    const list = mask.querySelector('[data-guide-list]');

    function buildItem() {
      const item = document.createElement('div');
      item.className = 'guide-item';
      item.innerHTML = `
        <select>
          <option value="link">链接</option>
          <option value="text">文本</option>
        </select>
        <input placeholder="粘贴链接或攻略正文（文本 ≤500 字）" />
        <button type="button" class="guide-item__remove" data-guide-remove aria-label="删除这条参考攻略">
          <svg class="icon icon--sm"><use href="#ic-close"/></svg>
        </button>`;
      return item;
    }

    mask.querySelector('[data-guide-add]').addEventListener('click', () => {
      if (list.querySelectorAll('.guide-item').length >= 3) {
        toast('参考攻略最多 3 条，每条文本不超过 500 字');
        return;
      }
      list.appendChild(buildItem());
    });

    list.addEventListener('click', (event) => {
      const removeButton = event.target.closest('[data-guide-remove]');
      if (!removeButton) return;

      const items = list.querySelectorAll('.guide-item');
      if (items.length <= 1) {
        removeButton.closest('.guide-item').querySelector('input').value = '';
        return;
      }
      removeButton.closest('.guide-item').remove();
    });

    list.addEventListener('input', (event) => {
      const input = event.target.closest('input');
      if (!input) return;

      const select = input.parentElement.querySelector('select');
      if (select && select.value === 'text' && input.value.length > 500) {
        input.value = input.value.slice(0, 500);
        toast('参考攻略最多 3 条，每条文本不超过 500 字');
      }
    });

    function close(result) {
      mask.remove();
      resolve(result);
    }

    mask.querySelector('[data-modal-cancel]').addEventListener('click', () => close(null));

    mask.querySelector('[data-modal-ok]').addEventListener('click', () => {
      const guides = Array.from(list.querySelectorAll('.guide-item'))
        .map((item) => ({
          type: item.querySelector('select').value,
          content: item.querySelector('input').value.trim(),
        }))
        .filter((guide) => guide.content);

      if (!guides.length) {
        toast('请至少填写一条参考攻略');
        return;
      }
      close(guides);
    });

    mask.addEventListener('click', (event) => {
      if (event.target === mask) close(null);
    });
  });
}

/**
 * 复制文本到剪贴板
 * http 非安全上下文下 navigator.clipboard 不可用，回退 execCommand（部署约定 §6）
 * @returns {Promise<boolean>}
 */
async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (error) {
    /* 继续走降级方案 */
  }

  try {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.top = '-9999px';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    const ok = document.execCommand('copy');
    textarea.remove();
    return ok;
  } catch (error) {
    return false;
  }
}
