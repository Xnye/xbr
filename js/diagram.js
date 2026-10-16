/**
 * Diagram.js - 1:1 Cure Dolly / Cognitive Grammar Visual Breakdown Engine
 * Faithfully reproduces the exact visual style from the video screenshot:
 * - Red Ø が zero-pronoun box with dynamic SVG curved arrows
 * - Color-coded particle boxes ([は] blue, [から] cyan, [を] orange, [が] red, etc.)
 * - Continuous phrase underlines
 * - Sub-word glosses with morphological notes (e.g. copula, て-form)
 * - Structured literal translation line with matching color underlines
 * - Natural idiomatic translation
 * - Interactive hover & click interlock
 */

const GrammarDiagram = (function () {
  let arrowUpdateDebounce = null;

  /**
   * Generates the HTML for a syntax breakdown component
   * @param {Object} data Exemplar data structure
   * @param {Object} options display options { id, simple } —— simple: 课文对白的「词块透视」精简模式
   */
  function render(data, options = {}) {
    const containerId = options.id || `diagram_${data.id}`;
    // 简单模式（课文对白的「词块透视」）：只画 词块 ＋ 助词框（含 jp_units 块内连接框）＋ 振假名。
    // 不画词下词义小字、不画「▸逐词直译」按钮与直译行、不画认知心法卡、不画 Ø が 红框。
    // 由 opts.simple 或条目自带的 ex.simple 触发；完整模式一行不动。
    if (options.simple || data.simple) return renderSimple(data, containerId);
    const hasZeroSubject = !!data.zero_subject;

    let html = `
      <div class="grammar-diagram-container ${hasZeroSubject ? 'zero-collapsed' : ''}" id="${containerId}" data-diagram-id="${data.id}">
        <!-- Top Action & Tag Bar -->
        <div class="diagram-meta-bar">
          <div class="meta-tag-group">
            <span class="meta-tag-pill">${data.tag || '语法透视'}</span>
            <span class="meta-lesson-title">${data.lesson_title || ''}</span>
          </div>
          <div class="meta-action-group">
            <button class="icon-btn audio-play-btn" title="听原声朗读" onclick="JapaneseTTS.speak('${escapeQuotes(data.sentence_raw)}', this)">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
                <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
                <path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>
              </svg>
              <span>朗读</span>
            </button>
            <button class="icon-btn explain-toggle-btn" title="展开/收起认知语法心法" onclick="GrammarDiagram.toggleNote('${containerId}')">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="16" x2="12" y2="12"></line>
                <line x1="12" y1="8" x2="12.01" y2="8"></line>
              </svg>
              <span>解构秘籍</span>
            </button>
          </div>
        </div>

        <!-- The 1:1 Cinematic Canvas matching the Screenshot -->
        <div class="diagram-canvas">
          <!-- Zero Pronoun Row (Top Layer) -->
          <!-- 默认收起：Ø が 只是一枚浅色小角标。悬停预览、点击固定， -->
          <!-- 才还原成红框＋弧形箭头。行高恒定 52px，展开收起不引起版面跳动，箭头几何也无需重算。 -->
          <div class="zero-subject-layer ${hasZeroSubject ? 'has-zero' : 'no-zero'}">
            ${hasZeroSubject ? `
              <div class="zero-badge-wrapper">
                <button class="zero-badge red-box" id="${containerId}_zero_badge" type="button"
                     title="隐性主语：悬停预览，点击固定展开"
                     data-tooltip="${escapeQuotes(data.zero_subject.tooltip)}"
                     onmouseenter="GrammarDiagram.revealZero('${containerId}', true); GrammarDiagram.highlightElement('${containerId}', 'zero_ga')"
                     onmouseleave="GrammarDiagram.revealZero('${containerId}', false); GrammarDiagram.clearHighlight('${containerId}')"
                     onclick="GrammarDiagram.pinZero('${containerId}')">
                  <span class="zero-sym">${data.zero_subject.symbol}</span>
                  <span class="zero-particle">${data.zero_subject.particle}</span>
                </button>
                <span class="zero-hint">隐性主语 · 悬停查看</span>
              </div>
            ` : ''}
          </div>

          ${hasZeroSubject ? `
            <!-- SVG Arrow Layer directly on diagram-canvas -->
            <svg class="diagram-arrows-svg" id="${containerId}_svg" preserveAspectRatio="none">
              <defs>
                <marker id="${containerId}_arrow_head" viewBox="0 0 10 10" refX="7" refY="5" 
                        markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#e74c3c" />
                </marker>
              </defs>
            </svg>
          ` : ''}

          <!-- Main Sentence & Particle Breakdown Row -->
          <div class="sentence-chunks-row" id="${containerId}_chunks_row">
            ${data.chunks.map(chunk => renderChunk(chunk, containerId)).join('')}
          </div>

          <!-- Structured Literal Translation Row (Cure Dolly Style) -->
          <!-- 默认折叠：初学者先看自然译文；需要观察日语语序时再点开。 -->
          <div class="literal-toggle-row">
            <button class="literal-toggle-btn" id="${containerId}_litbtn" type="button"
                    onclick="GrammarDiagram.toggleLiteral('${containerId}')">
              <span class="lit-toggle-arrow">▸</span> 看日语语序（逐词直译）
            </button>
          </div>
          <div class="literal-clause-row" id="${containerId}_literal" style="display: none;">
            ${renderLiteralStructure(data.literal_structure, containerId)}
          </div>

          <!-- Natural Idiomatic Translation Row -->
          <div class="natural-translation-row">
            <span class="zh-sentence">${data.natural_translation}</span>
          </div>
        </div>

        <!-- Cognitive Grammar Deep Explanation Accordion -->
        <div class="cognitive-note-panel" id="${containerId}_note" style="display: none;">
          <div class="note-inner">
            <div class="note-header">
              <span class="note-badge">深层认知结构剖析</span>
              <span class="note-quote">“把谓语当作列车引擎，助词是车厢连接器，隐形主语随时在后台就绪。”</span>
            </div>
            <p class="note-body">${data.cognitive_note}</p>
            <div class="particle-legend-grid">
              ${data.chunks.filter(c => c.particle).map(c => `
                <div class="legend-card ${c.particle_color}-accent">
                  <span class="legend-badge ${c.particle_color}-box">${c.particle}</span>
                  <div class="legend-text">
                    <strong>${c.particle_name || c.particle}</strong>
                    <span>${c.particle_desc || ''}</span>
                  </div>
                </div>
              `).join('')}
              ${hasZeroSubject ? `
                <div class="legend-card red-accent">
                  <span class="legend-badge red-box">${data.zero_subject.symbol} ${data.zero_subject.particle}</span>
                  <div class="legend-text">
                    <strong>零代词主语 (Zero Subject)</strong>
                    <span>${data.zero_subject.tooltip}</span>
                  </div>
                </div>
              ` : ''}
            </div>
          </div>
        </div>

        <!-- Floating Interactive Tooltip -->
        <div class="diagram-tooltip" id="${containerId}_tooltip" style="display: none;"></div>
      </div>
    `;

    return html;
  }

  /**
   * 简单模式：课文对白的「词块透视」。
   * 只输出 词块 ＋ 助词框 ＋ 振假名 三层里必要的那一层（.sentence-chunks-row），
   * 外层仍套用完整透视图的容器类名（.grammar-diagram-container / .diagram-canvas），
   * 于是主题、字号、助词配色、悬停联动全部沿用同一套 CSS。
   * 没有 zero_subject，因此不画 Ø が 红框、不生成 SVG 箭头层。
   */
  function renderSimple(data, containerId) {
    return `
      <div class="grammar-diagram-container simple-mode" id="${containerId}" data-diagram-id="${data.id}">
        <div class="diagram-canvas simple-canvas">
          <div class="sentence-chunks-row" id="${containerId}_chunks_row">
            ${data.chunks.map(chunk => renderChunk(chunk, containerId, true)).join('')}
          </div>
        </div>
      </div>
    `;
  }

  /**
   * Render single word chunk with ruby, particle box, underline, and gloss
   * @param {boolean} simple 简单模式：省略词下词义小字（词块、助词框、振假名照旧）
   */
  function renderChunk(chunk, containerId, simple) {
    const chunkId = `${containerId}_chunk_${chunk.id}`;
    const pColor = chunk.particle_color || 'none';
    const uColor = chunk.underline_color || 'none';

    let jpContent = '';
    if (chunk.jp_units && chunk.jp_units.length) {
      // 名词短语（駅の 外 / 机の 上）：の 渲染成块内连接框，
      // 表明它是把前后两个名词焊在一起的连体助词，而不是词尾格助词。
      jpContent = chunk.jp_units.map(u => {
        if (u.type === 'box') {
          return `<span class="particle-box ${u.color}-box inner-connector"
                        data-target-id="${chunk.id}"
                        onmouseenter="GrammarDiagram.highlightElement('${containerId}', '${chunk.id}', '${escapeQuotes(u.desc || '')}')"
                        onmouseleave="GrammarDiagram.clearHighlight('${containerId}')">${u.particle}</span>`;
        }
        return u.kana ? `<ruby>${u.kanji}<rt>${u.kana}</rt></ruby>` : u.kanji;
      }).join('');
    } else if (chunk.ruby_parts) {
      jpContent = chunk.ruby_parts.map(p => {
        if (p.kana) return `<ruby>${p.kanji}<rt>${p.kana}</rt></ruby>`;
        return p.kanji;
      }).join('');
    } else if (chunk.ruby) {
      jpContent = `<ruby>${chunk.text}<rt>${chunk.ruby}</rt></ruby>`;
    } else {
      jpContent = chunk.text;
    }

    const hasParticle = !!chunk.particle;
    const particleHtml = hasParticle ? `
      <span class="particle-box ${pColor}-box" 
            data-target-id="${chunk.id}"
            onmouseenter="GrammarDiagram.highlightElement('${containerId}', '${chunk.id}', '${escapeQuotes(chunk.particle_desc || '')}')"
            onmouseleave="GrammarDiagram.clearHighlight('${containerId}')">
        ${chunk.particle}
      </span>
    ` : '';

    const suffixHtml = chunk.suffix ? `<span class="chunk-suffix">${chunk.suffix}</span>` : '';

    return `
      <div class="syntax-chunk-unit" id="${chunkId}" data-chunk-id="${chunk.id}">
        <!-- Japanese Word & Particle -->
        <div class="chunk-jp-wrapper">
          <span class="chunk-text">${jpContent}</span>
          ${particleHtml}
          ${suffixHtml}
        </div>

        <!-- Underline spanning the phrase -->
        <div class="chunk-underline-bar ${uColor}-line"></div>${simple ? '' : `

        <!-- Word Gloss beneath -->
        <div class="chunk-gloss-box">
          <span class="gloss-main">${chunk.gloss_main}</span>
          ${chunk.gloss_sub ? `<span class="gloss-sub">${chunk.gloss_sub}</span>` : ''}
        </div>`}
      </div>
    `;
  }

  /**
   * Render structured literal translation
   */
  function renderLiteralStructure(structure, containerId) {
    if (!structure || !structure.length) return '';

    return structure.map((clauseObj, idx) => {
      const clauseTokens = clauseObj.tokens.map(token => {
        const uClass = token.underline ? `${token.color}-u` : '';
        const targetAttr = token.target_chunk ? `data-target-chunk="${token.target_chunk}"` : '';
        const hoverEvents = token.target_chunk ? `
          onmouseenter="GrammarDiagram.highlightElement('${containerId}', '${token.target_chunk}')"
          onmouseleave="GrammarDiagram.clearHighlight('${containerId}')"
        ` : '';

        return `
          <span class="lit-token ${uClass}" ${targetAttr} ${hoverEvents}>
            ${token.text}
          </span>
        `;
      }).join(' ');

      return `
        <div class="clause-part ${idx > 0 ? 'clause-part-break' : ''}">
          ${clauseTokens}
        </div>
      `;
    }).join(' ');
  }

  /**
   * Draw or update curved SVG arrows from Ø が to the target chunks
   */
  function updateArrows(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const diagramId = container.getAttribute('data-diagram-id');
    const svg = document.getElementById(`${containerId}_svg`);
    const zeroBadge = document.getElementById(`${containerId}_zero_badge`);

    if (!svg || !zeroBadge) return;

    // Retrieve exemplar data
    const data = (window.exemplarsData || []).find(d => d.id === diagramId);
    if (!data || !data.zero_subject || !data.zero_subject.targets) return;

    const containerRect = container.querySelector('.diagram-canvas').getBoundingClientRect();
    const zeroRect = zeroBadge.getBoundingClientRect();

    // Zero badge coordinates relative to canvas
    const zeroCenterX = (zeroRect.left + zeroRect.right) / 2 - containerRect.left;
    const zeroLeftX = zeroRect.left - containerRect.left + (zeroRect.width * 0.25);
    const zeroRightX = zeroRect.left - containerRect.left + (zeroRect.width * 0.75);
    const zeroBottomY = zeroRect.bottom - containerRect.top;

    svg.setAttribute('width', containerRect.width);
    svg.setAttribute('height', containerRect.height);

    // Remove existing paths
    const existingPaths = svg.querySelectorAll('.arrow-curve-path');
    existingPaths.forEach(p => p.remove());

    const targets = data.zero_subject.targets;
    targets.forEach((targetInfo, idx) => {
      const targetEl = document.getElementById(`${containerId}_chunk_${targetInfo.id}`);
      if (!targetEl) return;

      // Pinpoint the kanji ruby element for exact center landing
      const anchorEl = targetEl.querySelector('ruby') || targetEl;
      const targetRect = anchorEl.getBoundingClientRect();
      const targetX = (targetRect.left + targetRect.right) / 2 - containerRect.left;
      const targetTopY = targetRect.top - containerRect.top - 6; // land softly above ruby text

      // Origin point (left part for left arrow, right part for right arrow)
      const startX = idx === 0 ? zeroLeftX : zeroRightX;
      const startY = zeroBottomY + 2;

      // Calculate control point for graceful Bézier curve
      const dx = targetX - startX;
      const dy = targetTopY - startY;

      // Graceful cubic Bézier curve ensuring arrowhead points vertically down onto the kanji/ruby
      const cp1X = startX + dx * 0.15;
      const cp1Y = startY + dy * 0.35;
      const cp2X = targetX;
      const cp2Y = targetTopY - 26;

      const pathData = `M ${startX.toFixed(1)} ${startY.toFixed(1)} C ${cp1X.toFixed(1)} ${cp1Y.toFixed(1)}, ${cp2X.toFixed(1)} ${cp2Y.toFixed(1)}, ${targetX.toFixed(1)} ${targetTopY.toFixed(1)}`;

      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', pathData);
      path.setAttribute('class', 'arrow-curve-path');
      path.setAttribute('stroke', '#e74c3c');
      path.setAttribute('stroke-width', '2');
      path.setAttribute('fill', 'none');
      path.setAttribute('marker-end', `url(#${containerId}_arrow_head)`);
      path.setAttribute('data-target', targetInfo.id);

      svg.appendChild(path);
    });
  }

  /**
   * Recalculate all arrows on page
   */
  function updateAllArrows() {
    document.querySelectorAll('.grammar-diagram-container').forEach(c => {
      updateArrows(c.id);
    });
  }

  // Debounced resize listener
  window.addEventListener('resize', () => {
    clearTimeout(arrowUpdateDebounce);
    arrowUpdateDebounce = setTimeout(updateAllArrows, 120);
  });

  /**
   * Hover synchronization across Japanese chunk, zero arrow, and literal tokens
   */
  function highlightElement(containerId, targetId, tooltipText) {
    const container = document.getElementById(containerId);
    if (!container) return;

    // Highlight target chunk
    const chunkEl = document.getElementById(`${containerId}_chunk_${targetId}`);
    if (chunkEl) chunkEl.classList.add('hover-highlight');

    // Highlight zero badge and arrow if targetId is zero_ga
    if (targetId === 'zero_ga') {
      const zeroEl = document.getElementById(`${containerId}_zero_badge`);
      if (zeroEl) zeroEl.classList.add('hover-highlight');
      const paths = container.querySelectorAll('.arrow-curve-path');
      paths.forEach(p => p.classList.add('path-highlight'));
    }

    // Highlight matching path if it targets this chunk
    const path = container.querySelector(`.arrow-curve-path[data-target="${targetId}"]`);
    if (path) path.classList.add('path-highlight');

    // Highlight matching literal token
    const litTokens = container.querySelectorAll(`[data-target-chunk="${targetId}"]`);
    litTokens.forEach(t => t.classList.add('hover-highlight'));

    // Show tooltip if provided
    if (tooltipText) {
      showTooltip(containerId, tooltipText);
    }
  }

  function clearHighlight(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.querySelectorAll('.hover-highlight').forEach(el => el.classList.remove('hover-highlight'));
    container.querySelectorAll('.path-highlight').forEach(el => el.classList.remove('path-highlight'));
    hideTooltip(containerId);
  }

  function showTooltip(containerId, text) {
    const tooltip = document.getElementById(`${containerId}_tooltip`);
    if (!tooltip) return;
    tooltip.innerHTML = text;
    tooltip.style.display = 'block';
  }

  function hideTooltip(containerId) {
    const tooltip = document.getElementById(`${containerId}_tooltip`);
    if (tooltip) tooltip.style.display = 'none';
  }

  function toggleNote(containerId) {
    const note = document.getElementById(`${containerId}_note`);
    if (!note) return;
    const isHidden = note.style.display === 'none';
    note.style.display = isHidden ? 'block' : 'none';
  }

  /**
   * 零主语 Ø が 的收起/展开。
   * 默认收起（容器带 zero-collapsed：红框缩成浅色小角标、箭头隐藏）。
   * 悬停为临时预览，移开即收回；点击则固定（zero-pinned），固定后悬停离开不收回。
   * 行高恒定，所以展开收起不引起版面跳动，箭头几何也无需重算。
   */
  function revealZero(containerId, on) {
    const c = document.getElementById(containerId);
    if (!c) return;
    if (c.classList.contains('zero-pinned')) {
      c.classList.remove('zero-collapsed');
      return;
    }
    c.classList.toggle('zero-collapsed', !on);
  }

  function pinZero(containerId) {
    const c = document.getElementById(containerId);
    if (!c) return;
    const pinned = c.classList.toggle('zero-pinned');
    c.classList.toggle('zero-collapsed', !pinned);
    // 固定展开后让提示气泡停留，方便读完解释
    if (pinned) {
      const badge = document.getElementById(`${containerId}_zero_badge`);
      if (badge && badge.dataset.tooltip) showTooltip(containerId, badge.dataset.tooltip);
    } else {
      hideTooltip(containerId);
    }
  }

  /** 逐词直译行默认折叠；点开后箭头/高亮联动才需要重算几何。 */
  function toggleLiteral(containerId) {
    const row = document.getElementById(`${containerId}_literal`);
    const btn = document.getElementById(`${containerId}_litbtn`);
    if (!row) return;
    const isOpen = row.style.display !== 'none';
    row.style.display = isOpen ? 'none' : 'flex';
    if (btn) btn.classList.toggle('open', !isOpen);
  }

  function escapeQuotes(str) {
    if (!str) return '';
    return str.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  return {
    render: render,
    updateArrows: updateArrows,
    updateAllArrows: updateAllArrows,
    highlightElement: highlightElement,
    clearHighlight: clearHighlight,
    toggleNote: toggleNote,
    revealZero: revealZero,
    pinZero: pinZero,
    toggleLiteral: toggleLiteral
  };
})();

if (typeof window !== 'undefined') {
  window.GrammarDiagram = GrammarDiagram;
}
