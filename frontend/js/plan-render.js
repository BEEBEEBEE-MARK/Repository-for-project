/**
 * 旅行计划内容渲染（生成结果页 / 计划详情页共用）
 * - PlanRender.render(planContent, meta, activeDay)：返回完整结果 HTML
 * - PlanRender.buildCopyText(planContent, meta)：复制分享用的纯文本
 *
 * meta 字段：departure / destination / days / people / budget_per_person / used_guide
 */

const PlanRender = (function () {
  const PERIOD_LABELS = { morning: '上午', afternoon: '下午', evening: '晚间' };
  const MARKER_LABELS = {
    fact: '以实际为准',
    src: '参考来源',
    cat: '品类建议',
    feedback: '来自旅行者反馈',
  };
  const TIP_LABELS = {
    reservation: '预约',
    duration: '建议时长',
    best_time: '最佳时段',
    ticket: '门票',
    gear: '装备',
  };

  function esc(value) {
    return String(value ?? '').replace(/[&<>"]/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]
    ));
  }

  function money(value) {
    if (typeof value === 'string' && /[¥￥]/.test(value)) return value;
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    return '¥' + n.toLocaleString('zh-CN');
  }

  function markerHtml(code) {
    if (!code || !MARKER_LABELS[code]) return '';
    return `<span class="mk mk--${code}">${MARKER_LABELS[code]}</span>`;
  }

  /* ---------- 各模块 ---------- */

  function legendHtml() {
    return `<div class="legend">
      <span class="legend__title">信息标注</span>
      <span class="legend__item"><span class="mk mk--fact">以实际为准</span>实时性事实，出行前核实</span>
      <span class="legend__item"><span class="mk mk--src">参考来源</span>有攻略依据</span>
      <span class="legend__item"><span class="mk mk--feedback">来自旅行者反馈</span>踩坑帖提炼</span>
      <span class="legend__item"><span class="mk mk--cat">品类建议</span>无门店依据，不编造店名</span>
    </div>`;
  }

  function overviewHtml(content, meta) {
    const overview = content.overview || {};
    const theme = overview.theme || '';

    return `<div class="card">
      <h3><svg class="icon"><use href="#ic-map"/></svg>行程概览</h3>
      <div class="stat-grid">
        <div class="stat">
          <div class="stat__label"><svg class="icon"><use href="#ic-pin"/></svg>目的地</div>
          <div class="stat__value">${esc(meta.destination || '—')}</div>
        </div>
        <div class="stat">
          <div class="stat__label"><svg class="icon"><use href="#ic-calendar"/></svg>出行天数</div>
          <div class="stat__value">${esc(meta.days ?? '—')}<small>天</small></div>
        </div>
        <div class="stat">
          <div class="stat__label"><svg class="icon"><use href="#ic-users"/></svg>出行人数</div>
          <div class="stat__value">${esc(meta.people ?? '—')}<small>人</small></div>
        </div>
        <div class="stat">
          <div class="stat__label"><svg class="icon"><use href="#ic-yuan"/></svg>人均预算</div>
          <div class="stat__value">${money(meta.budget_per_person)}</div>
        </div>
      </div>
      ${theme ? `<div class="theme-line">
        <svg class="icon"><use href="#ic-sparkles"/></svg>
        <span><b>主题建议：</b>${esc(theme)}</span>
      </div>` : ''}
    </div>`;
  }

  function longDistanceHtml(content) {
    const data = content.long_distance_transport;
    if (!data) return '';

    const segments = [];
    if (data.outbound) segments.push({ tag: '去程', segment: data.outbound });
    if (data.return) segments.push({ tag: '返程', segment: data.return });
    (data.intercity || []).forEach((segment, index) => {
      segments.push({ tag: `城际 ${index + 1}`, segment });
    });
    if (!segments.length) return '';

    const items = segments.map(({ tag, segment }) => `
      <div class="journey">
        <div class="journey__head">
          <span class="journey__tag">${esc(tag)}</span>
          <span class="journey__route">${esc(segment.from || '')} → ${esc(segment.to || '')}</span>
          ${markerHtml(segment.marker)}
        </div>
        <div class="journey__options">
          ${(segment.options || []).map((option) => `
            <span class="journey__option">
              <b>${esc(option.way || '')}</b>${esc(option.duration || '')} · ${esc(option.cost || '')}
            </span>`).join('')}
        </div>
        ${segment.recommendation
          ? `<div class="journey__rec">推荐：${esc(segment.recommendation)}</div>`
          : ''}
      </div>`).join('');

    return `<div class="card">
      <h3><svg class="icon"><use href="#ic-bus"/></svg>交通信息
        <span class="card__sub">往返与城际交通 · 价格为估算</span>
      </h3>
      <div class="journey-list">${items}</div>
    </div>`;
  }

  function dailyHtml(content, activeDay) {
    const daily = content.daily || [];
    if (!daily.length) return '';

    const activeIndex = daily[activeDay] ? activeDay : 0;
    const day = daily[activeIndex];

    const tabs = daily.map((item, index) => (
      `<button type="button" class="daytab ${index === activeIndex ? 'daytab--active' : ''}" data-day="${index}">第 ${esc(item.day ?? index + 1)} 天</button>`
    )).join('');

    const blocks = (day.blocks || []).map(blockHtml).join('');

    const alternatives = (day.alternatives || []).length
      ? `<div class="day-alt">
          <h4><svg class="icon"><use href="#ic-list"/></svg>当日备选 · 遇排队 / 闭馆 / 天气不适时替换</h4>
          <ul>${day.alternatives.map((text) => `<li>${esc(text)}</li>`).join('')}</ul>
        </div>`
      : '';

    return `<div class="card">
      <h3><svg class="icon"><use href="#ic-calendar"/></svg>每日安排
        <span class="card__sub">景点提示 / 交通方式对比 / 附近美食 · 当日备选见每天末尾</span>
      </h3>
      <div class="daytabs">${tabs}</div>
      <div class="timeline">${blocks || '<p class="hint">本日暂无安排</p>'}</div>
      ${alternatives}
    </div>`;
  }

  function blockHtml(block) {
    const tips = block.spot_tips ? tipChipsHtml(block.spot_tips) : '';
    const transport = block.transport ? transportHtml(block.transport) : '';
    const food = block.nearby_food ? foodHtml(block.nearby_food) : '';

    return `<div class="timeline__item">
      <div class="block">
        <div class="block__head">
          <span class="block__time">${esc(PERIOD_LABELS[block.period] || block.period || '')}</span>
          <span class="block__place">${esc(block.place || '')}</span>
        </div>
        ${tips ? `<div class="block__section">
          <div class="block__section-title"><svg class="icon"><use href="#ic-info"/></svg>景点提示</div>
          <div class="tip-chips">${tips}</div>
        </div>` : ''}
        ${transport}
        ${food}
        <div class="block__meta">
          <span><svg class="icon"><use href="#ic-food"/></svg>餐饮 ${esc(block.meal || '—')}</span>
          <span><svg class="icon"><use href="#ic-wallet"/></svg>分项预算 ${money(block.cost)}</span>
        </div>
        ${block.note ? `<div class="block__note">备注：${esc(block.note)}</div>` : ''}
        ${block.pitfall ? `<div class="pitfall">
          <svg class="icon"><use href="#ic-alert"/></svg>
          <span>${esc(block.pitfall)} ${markerHtml('feedback')}</span>
        </div>` : ''}
      </div>
    </div>`;
  }

  function tipChipsHtml(tips) {
    return Object.entries(TIP_LABELS).map(([key, label]) => {
      const value = tips[key];
      if (!value) return '';
      const marker = tips.markers ? tips.markers[key] : null;
      return `<span class="tip-chip"><b>${label}</b>${esc(value)}${markerHtml(marker)}</span>`;
    }).join('');
  }

  function transportHtml(transport) {
    const options = (transport.options || []).map((option) => `
      <div class="transport__option">
        <div class="transport__way">${esc(option.way || '')}</div>
        <div class="transport__detail">
          <span>时长</span> ${esc(option.duration || '—')}<br />
          <span>费用</span> ${esc(option.cost || '—')}
        </div>
      </div>`).join('');

    return `<div class="block__section">
      <div class="block__section-title"><svg class="icon"><use href="#ic-bus"/></svg>交通方式对比</div>
      <div class="transport__grid">${options}</div>
      ${transport.recommendation ? `<div class="transport__recommend">
        <svg class="icon"><use href="#ic-check"/></svg>
        <span>${esc(transport.recommendation)} ${markerHtml(transport.marker)}</span>
      </div>` : ''}
    </div>`;
  }

  function foodHtml(nearby) {
    const items = (nearby.items || []).map((item) => `
      <div class="food-item">
        <span class="food-item__name">${esc(item.name || '')}</span>
        <span class="food-item__desc">${esc(item.desc || '')}</span>
        <span class="food-item__price">${esc(item.price || '')}</span>
      </div>`).join('');

    return `<div class="block__section">
      <div class="block__section-title">
        <svg class="icon"><use href="#ic-food"/></svg>附近美食 ${markerHtml(nearby.marker)}
      </div>
      <div class="food-list">${items}</div>
    </div>`;
  }

  function accommodationsHtml(content) {
    const items = content.accommodations || [];
    if (!items.length) return '';

    const rows = items.map((item, index) => `
      <div class="stay-item">
        <span class="stay-item__rank">${esc(item.rank || index + 1)}</span>
        <div class="stay-item__body">
          <div class="stay-item__head">
            <span class="stay-item__name">${esc(item.area || '')}${item.name ? ' · ' + esc(item.name) : ''}</span>
            ${item.level ? `<span class="stay-item__level">${esc(item.level)}</span>` : ''}
            ${markerHtml(item.marker)}
          </div>
          ${item.reason ? `<div class="stay-item__reason">${esc(item.reason)}</div>` : ''}
        </div>
        ${item.price ? `<span class="stay-item__price">${esc(item.price)}</span>` : ''}
      </div>`).join('');

    return `<div class="card">
      <h3><svg class="icon"><use href="#ic-hotel"/></svg>住宿推荐
        <span class="card__sub">按推荐优先级排序 · 价格为估算</span>
      </h3>
      <div class="stay-list">${rows}</div>
    </div>`;
  }

  function budgetHtml(content) {
    const budget = content.budget || {};
    const items = budget.items || [];
    if (!items.length) return '';

    const maxAmount = Math.max(...items.map((item) => Number(item.amount) || 0), 1);
    const total = budget.total != null
      ? budget.total
      : items.reduce((sum, item) => sum + (Number(item.amount) || 0), 0);

    const rows = items.map((item) => {
      const amount = Number(item.amount) || 0;
      const width = Math.max(6, Math.round((amount / maxAmount) * 100));
      return `<div class="budget-row">
        <div class="budget-row__name">${esc(item.name || '')}</div>
        <div class="budget-row__bar"><i style="width:${width}%"></i></div>
        <div class="budget-row__value">${money(amount)}</div>
      </div>`;
    }).join('');

    return `<div class="card">
      <h3><svg class="icon"><use href="#ic-wallet"/></svg>预算估算 <span class="card__sub">人均 · 元</span></h3>
      ${rows}
      <div class="budget-total"><span>人均合计（估算）</span><b>${money(total)}</b></div>
    </div>`;
  }

  function noticesHtml(content) {
    const notices = content.notices || [];
    if (!notices.length) return '';

    const items = notices.map((notice) => {
      const text = typeof notice === 'string' ? notice : notice.text;
      const marker = typeof notice === 'string' ? null : notice.marker;
      return `<li>${esc(text)} ${markerHtml(marker)}</li>`;
    }).join('');

    return `<div class="card">
      <h3><svg class="icon"><use href="#ic-info"/></svg>注意事项
        <span class="card__sub">目的地通用层 · 景点专属提示已下沉至对应条目</span>
      </h3>
      <ul class="bullets">${items}</ul>
    </div>`;
  }

  function alternativesHtml(content) {
    const alternatives = content.alternatives || [];
    if (!alternatives.length) return '';

    return `<div class="card">
      <h3><svg class="icon"><use href="#ic-list"/></svg>备选建议
        <span class="card__sub">全局层 · 当日替换见各天安排</span>
      </h3>
      <ul class="bullets">${alternatives.map((text) => `<li>${esc(text)}</li>`).join('')}</ul>
    </div>`;
  }

  function sourcesHtml(content) {
    const sources = content.sources || [];
    if (!sources.length) return '';

    const items = sources.map((source) => {
      const label = source.url || source.label || source.t || '';
      const type = source.type === 'link' || source.st
        ? (source.st || '分享链接')
        : '参与生成';
      return `<div class="src-item">
        <svg class="icon"><use href="#ic-map"/></svg>
        <span class="src-item__label">${esc(label)}</span>
        <span class="src-item__type">${esc(type)}</span>
      </div>`;
    }).join('');

    return `<div class="card">
      <h3><svg class="icon"><use href="#ic-map"/></svg>参考来源
        <span class="card__sub">链接仅作来源记录，不做内容抓取</span>
      </h3>
      <div class="src-list">${items}</div>
    </div>`;
  }

  function disclaimerHtml(usedGuide) {
    let text = '行程与价格均为 AI 估算，信息非实时，出行前请自行核实。';
    if (usedGuide) {
      text += '参考内容来自公开分享，可能过时或夸大，仅供灵感参考。';
    }
    return `<div class="disclaimer">
      <svg class="icon"><use href="#ic-info"/></svg>
      <span>${esc(text)}</span>
    </div>`;
  }

  /* ---------- 对外接口 ---------- */

  function render(content, meta, activeDay) {
    const planContent = content || {};
    const planMeta = meta || {};
    return [
      legendHtml(),
      overviewHtml(planContent, planMeta),
      longDistanceHtml(planContent),
      dailyHtml(planContent, activeDay || 0),
      accommodationsHtml(planContent),
      budgetHtml(planContent),
      noticesHtml(planContent),
      alternativesHtml(planContent),
      sourcesHtml(planContent),
      disclaimerHtml(planMeta.used_guide),
    ].join('');
  }

  /** 复制分享文本：行程概览 + 每日安排 + 免责声明（不含任何用户隐私） */
  function buildCopyText(content, meta) {
    const planContent = content || {};
    const planMeta = meta || {};
    const lines = [];

    lines.push('【行程概览】');
    if (planMeta.departure) lines.push(`出发地：${planMeta.departure}`);
    lines.push(`目的地：${planMeta.destination || ''}`);
    lines.push(`天数：${planMeta.days || ''} 天`);
    lines.push(`人数：${planMeta.people || ''} 人`);
    lines.push(`人均预算：${money(planMeta.budget_per_person)}`);

    const theme = planContent.overview && planContent.overview.theme;
    if (theme) lines.push(`主题：${theme}`);
    lines.push('');

    lines.push('【每日安排】');
    (planContent.daily || []).forEach((day) => {
      lines.push(`第 ${day.day} 天`);
      (day.blocks || []).forEach((block) => {
        lines.push(`  ${PERIOD_LABELS[block.period] || ''} · ${block.place || ''}`);
        if (block.meal) lines.push(`    餐饮：${block.meal}`);
      });
      if ((day.alternatives || []).length) {
        lines.push(`  当日备选：${day.alternatives.join('；')}`);
      }
      lines.push('');
    });

    lines.push('行程与价格均为 AI 估算，信息非实时，出行前请自行核实。');
    return lines.join('\n');
  }

  return { render, buildCopyText, esc, money, markerHtml };
})();
