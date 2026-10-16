/**
 * Main Application Logic for Standard Japanese Cognitive Reader
 */

(function () {
  // State
  let lessonsData = [];
  let exemplarsData = [];
  let grammarDeep = null;      // data/grammar_deep.json（缺失时为 null，自动回退旧渲染）
  let grammarDeepIndex = {};   // id -> entry，供关联条目跳转
  // data/romaji.json：全 48 课罗马音（由假名注音重新生成）。
  // lessons.json 自带的 romaji / title_romaji 是 pykakasi 产物，读起来是错的
  // （李→sumomo、は→ha、へ→he），只在取不到新数据时才回落。
  let romajiData = null;
  let currentLessonNum = 1;
  let activeFilter = '';
  let toastTimer = null;
  const renderedXraySlots = new Set();  // 已懒渲染过的例句透视图槽位

  /** 极简 Markdown：**加粗** → <strong>。讲义正文里用来点睛。 */
  function md(str) {
    return esc(str || '')
      // 内容里混用了 ASCII 直引号，中文排版里很刺眼，统一成弯引号
      .replace(/"([^"\n]*)"/g, '“$1”')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  }

  /** HTML 转义。jp_ruby 这类本来就是标记的字段不要走这里。 */
  function esc(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  /* ====================================================================
     罗马音取值：优先 data/romaji.json（引擎从假名注音重生成），
     取不到才回落 lessons.json 的旧字段（pykakasi 产物，读音有错）。
     句子的 ruby 也优先用重生成的那一份——教材注音层有 4 处修订
     （晴れ 的 ほ、後で 的 ご、五種類・一度 漏注音），修订过的句子才带 ruby。
     ==================================================================== */
  function romajiForSentence(s) {
    if (!s) return '';
    const entry = romajiData && romajiData.sentences && romajiData.sentences[s.jp_raw];
    return (entry && entry.romaji) || s.romaji || '';
  }

  function rubyForSentence(s) {
    if (!s) return '';
    const entry = romajiData && romajiData.sentences && romajiData.sentences[s.jp_raw];
    return (entry && entry.ruby) || s.jp_ruby || s.jp_clean || '';
  }

  function romajiForWord(w) {
    if (!w) return '';
    const hit = romajiData && romajiData.words && romajiData.words[w.word_clean];
    return hit || w.romaji || '';
  }

  function romajiForLessonTitle(lesson) {
    if (!lesson) return '';
    const hit = romajiData && romajiData.titles && romajiData.titles[lesson.title_clean];
    return hit || lesson.title_romaji || '';
  }

  /** 朗读用正文：修订过的句子（教材注音错字等）用修订版，否则用教材原文。 */
  function cleanForSentence(s) {
    if (!s) return '';
    const entry = romajiData && romajiData.sentences && romajiData.sentences[s.jp_raw];
    return (entry && entry.clean) || s.jp_clean || '';
  }

  function showToast(msg) {
    let toast = document.getElementById('app_toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'app_toast';
      toast.style.cssText = `
        position: fixed;
        bottom: 24px;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(26, 26, 26, 0.92);
        color: #f5f5f5;
        border: 1px solid rgba(255, 255, 255, 0.15);
        padding: 0.5rem 1.2rem;
        border-radius: 20px;
        font-size: 0.88rem;
        box-shadow: 0 8px 24px rgba(0,0,0,0.4);
        backdrop-filter: blur(8px);
        z-index: 1000;
        pointer-events: none;
        transition: opacity 0.25s ease, transform 0.25s ease;
      `;
      document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.style.opacity = '1';
    toast.style.transform = 'translateX(-50%) translateY(0)';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(-50%) translateY(10px)';
    }, 1800);
  }

  const STATE = {
    theme: localStorage.getItem('xbr_theme') || 'dark', // 'dark' (video screenshot) or 'paper'
    furigana: localStorage.getItem('xbr_furigana') !== 'false',
    romaji: localStorage.getItem('xbr_romaji') === 'true', // default subtle off or on
    translation: localStorage.getItem('xbr_trans') !== 'false',
    xray: localStorage.getItem('xbr_xray') !== 'false'
  };

  async function init() {
    setupEventListeners();
    applyStateToDOM();

    try {
      // Load datasets
      // grammar_deep.json 是可选的：没跑构建脚本或课程未覆盖时回退到教材原始笔记
      // 两个会随构建变化的数据文件用 no-store，避免开发期读到旧缓存；
      // lessons.json 体积大且极少变动，沿用浏览器缓存。
      const [resLessons, resExemplars, resGrammar, resRomaji] = await Promise.all([
        fetch('data/lessons.json'),
        fetch('data/exemplars.json', { cache: 'no-store' }),
        fetch('data/grammar_deep.json', { cache: 'no-store' }).catch(() => null),
        fetch('data/romaji.json', { cache: 'no-store' }).catch(() => null)
      ]);

      lessonsData = await resLessons.json();
      exemplarsData = await resExemplars.json();
      window.exemplarsData = exemplarsData;

      if (resRomaji && resRomaji.ok) {
        try {
          romajiData = await resRomaji.json();
        } catch (e) {
          console.warn('romaji.json 解析失败，回退到 lessons.json 里的旧罗马音', e);
          romajiData = null;
        }
      }

      if (resGrammar && resGrammar.ok) {
        try {
          grammarDeep = await resGrammar.json();
          grammarDeepIndex = {};
          (grammarDeep.entries || []).forEach(e => { grammarDeepIndex[e.id] = e; });
        } catch (e) {
          console.warn('grammar_deep.json 解析失败，回退到教材原始笔记', e);
          grammarDeep = null;
        }
      }

      // Populate Drawer
      renderDrawerList();

      // Check URL hash for direct lesson jump e.g. #lesson-4 or #showcase
      const hash = window.location.hash;
      if (hash && hash.startsWith('#lesson-')) {
        const num = parseInt(hash.replace('#lesson-', ''), 10);
        if (num >= 1 && num <= 48) {
          currentLessonNum = num;
        }
      }

      // Render current lesson
      renderLesson(currentLessonNum);

    } catch (err) {
      console.error('Failed to load lesson data:', err);
      document.getElementById('lesson_content_root').innerHTML = `
        <div style="text-align:center; padding: 4rem 1rem; color: var(--text-muted);">
          <p>加载数据失败，请确保本地服务器正常运行或刷新页面重试。</p>
          <p style="font-size:0.85rem; margin-top:0.5rem;">${err.message}</p>
        </div>
      `;
    }
  }

  function applyStateToDOM() {
    // Theme
    if (STATE.theme === 'paper') {
      document.body.classList.add('theme-paper');
    } else {
      document.body.classList.remove('theme-paper');
    }
    updateToggleBtn('theme_toggle', STATE.theme === 'paper', STATE.theme === 'paper' ? '书卷纸白' : '视频黑板');

    // Furigana
    document.body.classList.toggle('hide-furigana', !STATE.furigana);
    updateToggleBtn('furi_toggle', STATE.furigana);

    // Romaji
    document.body.classList.toggle('hide-romaji', !STATE.romaji);
    updateToggleBtn('romaji_toggle', STATE.romaji);

    // Translation
    document.body.classList.toggle('hide-translation', !STATE.translation);
    updateToggleBtn('trans_toggle', STATE.translation);

    // X-Ray
    document.body.classList.toggle('hide-xray', !STATE.xray);
    updateToggleBtn('xray_toggle', STATE.xray);
  }

  function updateToggleBtn(id, isActive, textOverride) {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.classList.toggle('active', isActive);
    if (textOverride) {
      const label = btn.querySelector('.btn-label');
      if (label) label.textContent = textOverride;
    }
  }

  function setupEventListeners() {
    // Top bar toggles
    document.getElementById('furi_toggle')?.addEventListener('click', () => {
      STATE.furigana = !STATE.furigana;
      localStorage.setItem('xbr_furigana', STATE.furigana);
      applyStateToDOM();
    });

    document.getElementById('romaji_toggle')?.addEventListener('click', () => {
      STATE.romaji = !STATE.romaji;
      localStorage.setItem('xbr_romaji', STATE.romaji);
      applyStateToDOM();
    });

    document.getElementById('trans_toggle')?.addEventListener('click', () => {
      STATE.translation = !STATE.translation;
      localStorage.setItem('xbr_trans', STATE.translation);
      applyStateToDOM();
    });

    document.getElementById('xray_toggle')?.addEventListener('click', () => {
      STATE.xray = !STATE.xray;
      localStorage.setItem('xbr_xray', STATE.xray);
      applyStateToDOM();
      if (STATE.xray) {
        setTimeout(() => GrammarDiagram.updateAllArrows(), 100);
      }
    });

    document.getElementById('theme_toggle')?.addEventListener('click', () => {
      STATE.theme = STATE.theme === 'dark' ? 'paper' : 'dark';
      localStorage.setItem('xbr_theme', STATE.theme);
      applyStateToDOM();
      setTimeout(() => GrammarDiagram.updateAllArrows(), 100);
    });

    // Voice & speed selection
    const voiceSelect = document.getElementById('voice_select');
    if (voiceSelect) {
      const curVoice = JapaneseTTS.getVoice();
      for (let opt of voiceSelect.options) {
        if (opt.value === curVoice) opt.selected = true;
      }
      voiceSelect.addEventListener('change', (e) => {
        JapaneseTTS.setVoice(e.target.value);
        showToast(e.target.value.includes('Keita') ? '🎙️ 已切换为：庆太 (男声)' : '🎙️ 已切换为：七海 (女声)');
      });
    }

    const speedSelect = document.getElementById('speed_select');
    if (speedSelect) {
      const curRate = JapaneseTTS.getRate();
      for (let opt of speedSelect.options) {
        if (Math.abs(parseFloat(opt.value) - curRate) < 0.05) opt.selected = true;
      }
      speedSelect.addEventListener('change', (e) => {
        const rate = parseFloat(e.target.value);
        JapaneseTTS.setRate(rate);
        showToast(`⚡ 语速已调整为：${rate}x`);
      });
    }

    // Drawer openers & closers
    document.getElementById('open_drawer_btn')?.addEventListener('click', openDrawer);
    document.getElementById('close_drawer_btn')?.addEventListener('click', closeDrawer);
    document.getElementById('drawer_backdrop')?.addEventListener('click', (e) => {
      if (e.target.id === 'drawer_backdrop') closeDrawer();
    });

    // Search inside drawer
    document.getElementById('drawer_search_input')?.addEventListener('input', (e) => {
      activeFilter = e.target.value.trim().toLowerCase();
      renderDrawerList();
    });

    // Keyboard shortcuts
    window.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      if (e.key === 'f' || e.key === 'F') {
        document.getElementById('furi_toggle')?.click();
      } else if (e.key === 'r' || e.key === 'R') {
        document.getElementById('romaji_toggle')?.click();
      } else if (e.key === 't' || e.key === 'T') {
        document.getElementById('trans_toggle')?.click();
      } else if (e.key === 'x' || e.key === 'X') {
        document.getElementById('xray_toggle')?.click();
      } else if (e.key === 'm' || e.key === 'M') {
        document.getElementById('theme_toggle')?.click();
      }
    });
  }

  function openDrawer() {
    const backdrop = document.getElementById('drawer_backdrop');
    if (backdrop) backdrop.classList.add('open');
  }

  function closeDrawer() {
    const backdrop = document.getElementById('drawer_backdrop');
    if (backdrop) backdrop.classList.remove('open');
  }

  function renderDrawerList() {
    const listEl = document.getElementById('drawer_list');
    if (!listEl) return;

    const filtered = lessonsData.filter(l => {
      if (!activeFilter) return true;
      const t = (l.title_clean + l.contitlet + `第${l.number}课`).toLowerCase();
      return t.includes(activeFilter);
    });

    listEl.innerHTML = filtered.map(l => `
      <div class="drawer-item ${l.number === currentLessonNum ? 'active' : ''}" 
           onclick="App.selectLesson(${l.number})">
        <div class="drawer-item-title">第${l.number}课：${l.title_clean}</div>
        <div class="drawer-item-sub">${l.contitle || ''} ${l.contitlet ? `(${l.contitlet})` : ''}</div>
      </div>
    `).join('');
  }

  function selectLesson(num) {
    currentLessonNum = num;
    window.location.hash = `#lesson-${num}`;
    closeDrawer();
    renderLesson(num);
    renderDrawerList();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  /**
   * 初学者图例：怎么读一张「语法透视图」
   *
   * 存在的理由：用户是零起点初学者。透视图里的每个视觉元素（彩色方框、下划线、
   * 内嵌连接框、淡色 Ø が、折叠的直译行）对我们是常识，对他是天书。
   * 没有这张图例，他就只能靠猜——而猜错一次就会把错误的句法结构记进脑子。
   *
   * 密度控制：全站只出现一次（每课顶部），看过之后自动折叠（localStorage），
   * 不违背"高密度视觉元素不得逐句常驻"的原则。
   */
  const LEGEND_ROWS = [
    {
      sample: `<span class="particle-box blue-box">は</span>
               <span class="particle-box red-box">が</span>
               <span class="particle-box orange-box">を</span>
               <span class="particle-box purple-box">に</span>
               <span class="particle-box magenta-box">へ</span>
               <span class="particle-box yellow-box">と</span>
               <span class="particle-box teal-box">の</span>
               <span class="particle-box pink-box">も</span>`,
      title: '彩色方框 = 助词，颜色永远不变',
      body: '蓝=は（话题）、红=が（主语）、橙=を（宾语）、紫=に（地点/时间）、洋红=へ（方向）、黄=と（和/并列）、青=の（的）、粉=も（也）。认颜色比认字快，看多了不用想。'
    },
    {
      sample: `<div class="syntax-chunk-unit legend-demo-chunk">
                 <div class="chunk-jp-wrapper"><span class="chunk-text">李さん</span><span class="particle-box blue-box">は</span></div>
                 <div class="chunk-underline-bar blue-line"></div>
                 <div class="chunk-gloss-box"><span class="gloss-main">小李</span><span class="gloss-sub">名词</span></div>
               </div>`,
      title: '彩色横线 = 这个助词管到哪个词',
      body: '横线盖住的词 + 方框里的助词，合起来才是一个完整成分。词下面的小字是中文意思和词性，汉字头上的假名是读音。'
    },
    {
      sample: `<div class="syntax-chunk-unit legend-demo-chunk">
                 <div class="chunk-jp-wrapper"><span class="chunk-text">駅<span class="particle-box teal-box inner-connector">の</span>外</span><span class="particle-box purple-box">に</span></div>
                 <div class="chunk-underline-bar purple-line"></div>
                 <div class="chunk-gloss-box"><span class="gloss-main">车站的外面</span><span class="gloss-sub">名词短语</span></div>
               </div>`,
      title: '词块内部的小方框 = 这几层是一个整体，不能拆',
      body: '「駅の外」是"车站的外面"这<em>一个</em>地点，不是"车站"和"外面"两个并列的东西。所以整条紫色下划线只画一次，画在整个短语底下。同理「机といす」是"桌子和椅子"一个整体。'
    },
    {
      sample: `<span class="zero-badge red-box legend-demo-zero" type="button">Ø が</span>
               <span class="zero-hint">隐性主语 · 悬停查看</span>`,
      title: '淡红色小圆片 Ø が = 日语没说出口的主语',
      body: '日语只要语境清楚就不说主语，但语法上它一直在。这个圆片平时缩成很淡的一小点，不吵你；鼠标移上去（手机点一下）就展开，告诉你"是谁在做这个动作"。'
    },
    {
      sample: `<span class="literal-toggle-btn legend-demo-btn" type="button"><span class="lit-toggle-arrow">▸</span> 看日语语序（逐词直译）</span>`,
      title: '这个按钮点开 = 按日语原顺序的逐词中文',
      body: '用来对照"日语和中文的语序差在哪"。比如日语说「至于 小李 中国人 是」，中文说"小李是中国人"。不点它不影响你看懂句子。'
    }
  ];

  function renderDiagramLegend() {
    // 第一次进来完整展开，渲染的同时就记一笔；从下一课起默认折叠，
    // 需要时一键展开。不让"看过很多遍的说明"长期占着屏幕。
    const seen = localStorage.getItem('xbr_legend_seen') === '1';
    if (!seen) localStorage.setItem('xbr_legend_seen', '1');
    const rows = LEGEND_ROWS.map(r => `
      <div class="legend-row">
        <div class="legend-sample">${r.sample}</div>
        <div class="legend-text">
          <div class="legend-row-title">${r.title}</div>
          <div class="legend-row-body">${r.body}</div>
        </div>
      </div>`).join('');

    return `
      <section class="diagram-legend ${seen ? 'legend-collapsed' : ''}" id="diagram_legend">
        <button class="legend-head" type="button" onclick="App.toggleDiagramLegend()">
          <span class="legend-arrow">${seen ? '▸' : '▾'}</span>
          <span class="legend-title">怎么读这张「语法透视图」</span>
          <span class="legend-sub">${seen ? '忘了符号意思时点开' : '第一次用请先看这 30 秒'}</span>
        </button>
        <div class="legend-body" id="diagram_legend_body" ${seen ? 'style="display:none;"' : ''}>
          ${rows}
          <div class="legend-steps">
            <div class="legend-row-title">读任何一句日语，都按这三步</div>
            <ol>
              <li><strong>先看句尾</strong>：日语的谓语（动词・です・形容词）永远在最后，它决定整句是"断言"、"存在"还是"动作"。</li>
              <li><strong>再问一句"谁？"</strong>：句尾落定后回头找主语——要么带红框 が，要么带蓝框 は，要么就是那个淡红的 Ø が。</li>
              <li><strong>顺着彩色框往回拆</strong>：每个方框＋它底下的横线就是一个成分，把它们逐个翻译成中文，句子就散了。</li>
            </ol>
          </div>
        </div>
      </section>
    `;
  }

  function toggleDiagramLegend(force) {
    const box = document.getElementById('diagram_legend');
    const body = document.getElementById('diagram_legend_body');
    if (!box || !body) return;
    const open = force !== undefined ? force : box.classList.contains('legend-collapsed');
    box.classList.toggle('legend-collapsed', !open);
    body.style.display = open ? '' : 'none';
    const arrow = box.querySelector('.legend-arrow');
    const sub = box.querySelector('.legend-sub');
    if (arrow) arrow.textContent = open ? '▾' : '▸';
    if (sub) sub.textContent = open ? '符号速查 · 点一下收起' : '忘了符号意思时点开';
  }

  /**
   * Main Lesson Renderer
   */
  function renderLesson(num) {
    const lesson = lessonsData.find(l => l.number === num);
    const root = document.getElementById('lesson_content_root');
    if (!lesson || !root) return;

    // 整页重渲染会销毁已挂载的透视图 DOM，
    // 懒渲染记录必须一并清空，否则回到同一课时槽位会一直是空的。
    renderedXraySlots.clear();

    // Check if there is a featured exemplar to display at top
    // For Lesson 1, we also show the 1:1 Video Exemplar (`今日は雨だから傘を持っていく`) as the opening pedagogical showcase!
    const videoShowcaseExemplar = exemplarsData.find(e => e.id === 'screenshot_showcase');
    const isLessonOne = num === 1;

    let html = `
      <!-- 课文卷头 -->
      <header class="chapter-header">
        <div class="chapter-number">標準日本語 · 第 ${lesson.number} 課</div>
        <h1 class="chapter-title jp-text">${lesson.title_ruby || lesson.title_clean}</h1>
        <div class="chapter-romaji">${romajiForLessonTitle(lesson)}</div>
      </header>
      ${renderDiagramLegend()}
    `;

    // If Lesson 1, render the 1:1 Video Screenshot Showcase as the Master Demonstration
    if (isLessonOne && videoShowcaseExemplar) {
      html += `
        <section class="textbook-section">
          <div class="section-editorial-title">
            <span class="num-kanji">★</span>
            <span>B站原片 1:1 语法透视复刻</span>
            <span class="sub-en">Masterclass Video Screenshot Exemplar</span>
          </div>
          <div style="margin-bottom: 1.2rem; font-size: 0.95rem; color: var(--text-muted); line-height: 1.7;">
            本模块 1:1 复刻原片的视觉系统：<strong>「Ø が 隐性主语红框与弧形箭头」</strong>、
            <strong>「[は][から][を] 彩色助词框」</strong>、<strong>「词下形态拆解」</strong>与<strong>「逻辑小句直译」</strong>。
            鼠标悬停任一助词或直译词，即可触发全句关联高亮与心法提示。
            词注一律改用中文——原片是英文词注，但对中文学习者而言那是一道多余的坎，故只复刻视效、不复刻语种。
          </div>
          ${GrammarDiagram.render(videoShowcaseExemplar, { id: 'showcase_embed' })}
        </section>
      `;
    }

    // Section 1: 基本课文 (Basic 4 Sentences)
    html += `
      <section class="textbook-section">
        <div class="section-editorial-title">
          <span class="num-kanji">一、</span>
          <span>基本課文</span>
          <span class="sub-en">Core Syntactic Patterns</span>
        </div>
        <div class="basic-sentences-list">
          ${lesson.basic4.map((b4, idx) => renderBasicSentence(b4, idx, num)).join('')}
        </div>
      </section>
    `;

    // Section 2: 核心语法讲义（有深度讲义数据时用卡片，否则回退教材原始笔记）
    html += renderGrammarSection(lesson, num);

    // Section 3: 基础对话 (A, B, C, D Dialogues)
    if (lesson.basicc && lesson.basicc.length > 0) {
      html += `
        <section class="textbook-section">
          <div class="section-editorial-title">
            <span class="num-kanji">三、</span>
            <span>会話演習</span>
            <span class="sub-en">Basic Conversational Exchanges</span>
          </div>
          <div class="dialogue-exchanges-container">
            ${renderBasicDialogues(lesson.basicc, num)}
          </div>
        </section>
      `;
    }

    // Section 4: 应用课文 (Full Applied Dialogue Story)
    if (lesson.context_sections && lesson.context_sections.length > 0) {
      html += `
        <section class="textbook-section">
          <div class="section-editorial-title">
            <span class="num-kanji">四、</span>
            <span>応用本文</span>
            <span class="sub-en">${lesson.contitle || '本课情景对话'} ${lesson.contitlet ? `(${lesson.contitlet})` : ''}</span>
          </div>
          <div class="applied-story-container">
            ${renderAppliedStory(lesson.context_sections, num)}
          </div>
        </section>
      `;
    }

    // Section 5: 词汇表 (Vocabulary List)
    if (lesson.words && lesson.words.length > 0) {
      html += `
        <section class="textbook-section">
          <div class="section-editorial-title">
            <span class="num-kanji">五、</span>
            <span>単語リスト</span>
            <span class="sub-en">Vocabulary &amp; Pitch Accents</span>
          </div>
          <div class="words-editorial-grid">
            ${lesson.words.map(w => `
              <div class="word-card-item" onclick="JapaneseTTS.speak('${escapeQuotes(w.word_clean)}')">
                <div class="word-top-row">
                  <span class="word-jp jp-text">${w.word_ruby || w.word_clean}</span>
                  ${w.pitch ? `<span class="word-pitch">⓪${w.pitch}</span>` : ''}
                </div>
                <div class="word-bottom-row">
                  ${w.pos ? `<span class="word-pos">${w.pos}</span>` : ''}
                  <span class="word-zh">${w.desc}</span>
                  <span class="word-romaji">${romajiForWord(w)}</span>
                </div>
              </div>
            `).join('')}
          </div>
        </section>
      `;
    }

    // Bottom Lesson Navigation Bar
    html += `
      <div style="margin-top: 4rem; padding-top: 2rem; border-top: 1px solid var(--border-hairline); display: flex; justify-content: space-between; align-items: center;">
        ${num > 1 ? `
          <button class="lesson-selector-btn" onclick="App.selectLesson(${num - 1})">
            ← 上一课 (第${num - 1}课)
          </button>
        ` : '<div></div>'}
        <span style="font-size:0.85rem; color:var(--text-muted);">第 ${num} 课 / 共 48 课</span>
        ${num < 48 ? `
          <button class="lesson-selector-btn" onclick="App.selectLesson(${num + 1})">
            下一课 (第${num + 1}课) →
          </button>
        ` : '<div></div>'}
      </div>
    `;

    root.innerHTML = html;

    // After DOM insertion, calculate and draw SVG arrows
    setTimeout(() => {
      GrammarDiagram.updateAllArrows();
    }, 120);
  }

  function renderBasicSentence(b4, idx, lessonNum) {
    // Check if there is an exemplar corresponding to this sentence
    const cleanJp = b4.jp_clean.replace(/[。！？\s]/g, '');
    const matchedExemplar = exemplarsData.find(e => {
      const eClean = e.sentence_raw.replace(/[。！？\s]/g, '');
      return e.lesson === lessonNum && (eClean === cleanJp || e.id === `l${lessonNum}_b${idx+1}`);
    });

    const hasExemplar = !!matchedExemplar;
    const slotId = `b4_slot_${lessonNum}_${idx+1}`;

    return `
      <div class="basic-sentence-item">
        <div class="basic-main-row">
          <div class="basic-left">
            <span class="basic-index">${idx + 1}.</span>
            <span class="basic-jp jp-text">${rubyForSentence(b4)}</span>
          </div>
          <div class="sentence-tools">
            <button class="icon-btn" title="朗读" onclick="JapaneseTTS.speak('${escapeQuotes(cleanForSentence(b4))}', this)">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
                <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
              </svg>
            </button>
            ${hasExemplar ? `
              <button class="icon-btn" style="color: var(--accent-gold);" title="切换语法透视图" onclick="App.toggleSentenceXray('${slotId}', '${matchedExemplar.id}')">
                ✦ 语法透视
              </button>
            ` : ''}
          </div>
        </div>
        <div class="basic-romaji">${romajiForSentence(b4)}</div>
        <div class="basic-zh">${b4.zh}</div>

        <!-- Inline Visual Breakdown Container -->
        ${hasExemplar ? `
          <div class="xray-embed-slot" id="${slotId}">
            ${GrammarDiagram.render(matchedExemplar, { id: `embed_${matchedExemplar.id}` })}
          </div>
        ` : ''}
      </div>
    `;
  }

  function toggleSentenceXray(slotId, exemplarId) {
    const slot = document.getElementById(slotId);
    if (!slot) return;
    const isHidden = slot.style.display === 'none';
    slot.style.display = isHidden ? 'block' : 'none';
    if (isHidden) {
      setTimeout(() => GrammarDiagram.updateAllArrows(), 80);
    }
  }

  /* ====================================================================
     课文「简单透视图」
     会话课文（basicc）与应用课文（context_sections 的对白）每句一个折叠按钮，
     默认折叠；展开后只画「词块 ＋ 助词框（含块内连接框 jp_units）＋ 振假名」
     ——不画词下词义小字、不画逐词直译行、不画认知心法、不画 Ø が 红框。
     数据里没有 simple 条目时：不渲染按钮、不留空容器，整段输出与改动前一致。
     ==================================================================== */

  /** 句面规范化：抹掉句读与空白（含全角空格）后再比，只认汉字假名本身。 */
  function normalizeSentence(s) {
    if (!s) return '';
    return String(s).replace(/[。．！？，、,.\s]/g, '');
  }

  /**
   * 取一句课文对应的 simple 条目，按协议优先级：
   *   1. 先按 id：会话 l{课}_c{i}（i 从 1 起）／应用 l{课}_x{段}_{j}（段从 0 起，j 从 1 起）；
   *   2. 再退回「课号相等 且 规范化句面相等」。
   * 只认 simple: true 的条目——其余条目的 schema 里没有对白句，命中也渲染不出词块。
   */
  function findSimpleExemplar(lessonNum, id, jpClean) {
    if (!exemplarsData || !exemplarsData.length) return null;

    const byId = exemplarsData.find(e => e.simple && e.id === id);
    if (byId) return byId;

    const target = normalizeSentence(jpClean);
    if (!target) return null;
    return exemplarsData.find(e => {
      return e.simple && e.lesson === lessonNum && normalizeSentence(e.sentence_raw) === target;
    }) || null;
  }

  /** 对白日文行：命中 simple 条目才在句尾挂一个折叠按钮，未命中就原样输出。 */
  function renderDialogueJp(line, simpleEx, slotId) {
    const jpLine = `
      <div class="dlg-jp jp-text" onclick="JapaneseTTS.speak('${escapeQuotes(cleanForSentence(line))}', this)">
        ${rubyForSentence(line)}
      </div>`;

    if (!simpleEx) return jpLine;

    return `
      <div class="dlg-jp-line">
        ${jpLine}
        <div class="sentence-tools">
          <button class="icon-btn simple-xray-btn" type="button" id="${slotId}_btn"
                  aria-expanded="false" aria-controls="${slotId}"
                  title="展开词块透视：只画词块、助词框与振假名"
                  onclick="App.toggleSimpleXray('${slotId}', '${simpleEx.id}', this)">
            <span class="simple-xray-arrow" aria-hidden="true">▸</span><span>词块透视</span>
          </button>
        </div>
      </div>`;
  }

  /** 简单透视图槽位：默认折叠、零高度；未命中条目时连容器都不输出。 */
  function renderSimpleXraySlot(simpleEx, slotId) {
    if (!simpleEx) return '';
    return `<div class="xray-embed-slot simple-xray-slot" id="${slotId}"></div>`;
  }

  function renderBasicDialogues(basiccList, lessonNum) {
    let currentGroup = '';
    let html = '';

    basiccList.forEach((line, idx) => {
      if (line.group && line.group !== currentGroup) {
        if (currentGroup !== '') html += `</div>`;
        currentGroup = line.group;
        html += `
          <div class="dialogue-group">
            <div class="dialogue-group-header">【对话场景 ${currentGroup}】</div>
        `;
      }

      // 会话课文 id：l{课}_c{i}，i 从 1 起
      const simpleEx = findSimpleExemplar(lessonNum, `l${lessonNum}_c${idx + 1}`, line.jp_clean);
      const slotId = `c_slot_${lessonNum}_${idx + 1}`;

      html += `
        <div class="dialogue-bubble-row">
          <div class="speaker-tag">${line.speaker || '•'}</div>
          <div class="dlg-content">
            ${renderDialogueJp(line, simpleEx, slotId)}
            <div class="dlg-romaji">${romajiForSentence(line)}</div>
            <div class="dlg-zh">${line.zh}</div>
            ${renderSimpleXraySlot(simpleEx, slotId)}
          </div>
        </div>
      `;
    });

    if (currentGroup !== '') html += `</div>`;
    return html;
  }

  function renderAppliedStory(sections, lessonNum) {
    return sections.map((sec, secIdx) => {
      let dlgNo = 0;   // 段内对白序号，从 1 起；旁白不计数（协议只给 dialogue 配简单透视）

      const body = sec.map(item => {
        if (item.type === 'narration') {
          return `<div class="narration-line">${item.zh}</div>`;
        }
        dlgNo += 1;
        // 应用课文 id：l{课}_x{段号}_{段内对白序号}，段号从 0 起
        const simpleEx = findSimpleExemplar(lessonNum, `l${lessonNum}_x${secIdx}_${dlgNo}`, item.jp_clean);
        const slotId = `x_slot_${lessonNum}_${secIdx}_${dlgNo}`;

        return `
          <div class="dialogue-bubble-row">
            <div class="speaker-tag">${item.speaker || '•'}</div>
            <div class="dlg-content">
              ${renderDialogueJp(item, simpleEx, slotId)}
              <div class="dlg-romaji">${romajiForSentence(item)}</div>
              <div class="dlg-zh">${item.zh}</div>
              ${renderSimpleXraySlot(simpleEx, slotId)}
            </div>
          </div>
        `;
      }).join('');

      return `
        <div style="margin-bottom: 2rem;">
          ${body}
          ${secIdx < sections.length - 1 ? `<div style="margin: 1.5rem 0; border-bottom: 1px dashed var(--border-hairline);"></div>` : ''}
        </div>
      `;
    }).join('');
  }

  /* ====================================================================
     深度语法讲义渲染
     有 grammar_deep 数据 → 折叠式卡片（本质 / 公式 / 认知理据 / 课文原句 /
     易错对照 / 辨析表 / 变形表 / 自检题 / 关联条目）
     无数据 → 回退到教材原始笔记，保证第5～48课不空窗
     ==================================================================== */
  function deepEntriesFor(lessonNum) {
    if (!grammarDeep || !Array.isArray(grammarDeep.entries)) return [];
    // 注意：order 可以是 0（认知地基），不能用 || 兜底，否则 0 会被当成 99 排到最后
    return grammarDeep.entries
      .filter(e => e.lesson === lessonNum)
      .sort((a, b) => (a.order === undefined ? 99 : a.order) - (b.order === undefined ? 99 : b.order));
  }

  function renderGrammarSection(lesson, num) {
    const deep = deepEntriesFor(num);

    if (!deep.length) {
      // 回退：教材原始笔记（第5课以后尚未撰写深度讲义）
      if (!lesson.grammar || !lesson.grammar.length) return '';
      return `
        <section class="textbook-section">
          <div class="section-editorial-title">
            <span class="num-kanji">二、</span>
            <span>文法ノート</span>
            <span class="sub-en">Grammar Notes (Textbook Original)</span>
          </div>
          <div class="gdeep-coverage">
            本课的深度讲义尚未撰写，以下是教材原始语法笔记。
            第 ${(grammarDeep && grammarDeep.meta && grammarDeep.meta.coverage || []).join('、') || '1～4'} 课已完成七层拆解，可先去看那几课。
          </div>
          <div class="grammar-notes-flow">
            ${lesson.grammar.map(gn => `
              <div class="grammar-note-item">
                <div class="gn-header">
                  <span class="gn-exp jp-text">${esc(gn.expression)}</span>
                  ${gn.shortexplain ? `<span class="gn-short">${esc(gn.shortexplain)}</span>` : ''}
                </div>
                <div class="gn-body">${formatGrammarExplanation(gn.explanation)}</div>
              </div>
            `).join('')}
          </div>
        </section>
      `;
    }

    const exCount = deep.reduce((n, e) => n + (e.examples || []).length, 0);
    const pitCount = deep.reduce((n, e) => n + (e.pitfalls || []).length, 0);
    const grammarCount = deep.filter(e => !e.concept).length;
    const conceptCount = deep.length - grammarCount;
    const minOrder = Math.min.apply(null, deep.map(e => e.order === undefined ? 99 : e.order));

    return `
      <section class="textbook-section">
        <div class="section-editorial-title">
          <span class="num-kanji">二、</span>
          <span>文法ノート</span>
          <span class="sub-en">Deep Grammar &amp; Cognitive Models</span>
          <button class="lesson-selector-btn" style="margin-left:auto;"
                  onclick="App.toggleAllGrammarCards(${num}, this)">展开全部</button>
        </div>
        <div class="gdeep-coverage">
          本课 ${grammarCount} 个语法点${conceptCount ? `＋${conceptCount} 条认知地基` : ''}已做七层拆解：一句话本质 → 结构公式 → 为什么日语这样想 →
          课文原句（可点读、可开透视图）→ 中文母语者的坑 → 近义辨析 → 自检题。
          共 ${exCount} 条例句、${pitCount} 组错对对照。点击任意一条展开。
        </div>
        <div class="gdeep-list" id="gdeep_list_${num}" data-open-order="${minOrder}">
          ${deep.map(e => renderDeepCard(e, num, minOrder)).join('')}
        </div>
      </section>
    `;
  }

  function renderDeepCard(e, lessonNum, minOrder) {
    const cardId = 'gdc_' + e.id;
    // 只展开排序最靠前的一条（通常是认知地基或第一条句型），
    // 让页面一进来就能看到讲义长什么样，其余保持可扫读的折叠态。
    const isOpen = (e.order === undefined ? 99 : e.order) === minOrder;

    return `
      <article class="gdeep-card ${isOpen ? 'open' : ''}" id="${cardId}" data-lesson="${lessonNum}">
        <div class="gdeep-head" onclick="App.toggleGrammarCard('${e.id}')">
          <div class="gdeep-pattern-row">
            ${e.category ? `<span class="gdeep-cat">${esc(e.category)}</span>` : ''}
            <h3 class="gdeep-pattern jp-text">${esc(e.pattern)}</h3>
          </div>
          <button class="gdeep-chevron" tabindex="-1" aria-label="展开或收起">▾</button>
          <div class="gdeep-essence">${md(e.essence)}</div>
        </div>

        <div class="gdeep-body">
          ${e.formula ? renderFormula(e.formula) : ''}
          ${e.why && e.why.length ? renderWhy(e.why) : ''}
          ${e.key_points && e.key_points.length ? renderKeyPoints(e.key_points) : ''}
          ${e.examples && e.examples.length ? renderExamples(e.examples, cardId) : ''}
          ${e.pitfalls && e.pitfalls.length ? renderPitfalls(e.pitfalls) : ''}
          ${e.contrast ? renderContrast(e.contrast) : ''}
          ${e.conjugation ? renderConjugation(e.conjugation) : ''}
          ${e.self_check && e.self_check.length ? renderQuiz(e) : ''}
          ${renderRelated(e)}
          ${renderLegacy(e)}
        </div>
      </article>
    `;
  }

  function renderFormula(f) {
    return `
      <div class="gd-sec">
        <div class="gd-sec-title">结构公式</div>
        <div class="gd-formula jp-text">${esc(f.template)}</div>
        ${f.slots && f.slots.length ? `
          <table class="gd-table">
            <thead><tr><th>成分</th><th>角色</th><th>说明</th></tr></thead>
            <tbody>
              ${f.slots.map(s => `
                <tr>
                  <td class="jp-text">${esc(s.t)}</td>
                  <td>${esc(s.r)}</td>
                  <td>${md(s.n)}</td>
                </tr>`).join('')}
            </tbody>
          </table>` : ''}
      </div>
    `;
  }

  function renderWhy(paras) {
    return `
      <div class="gd-sec">
        <div class="gd-sec-title">为什么日语这样想</div>
        ${paras.map(p => `<p class="gd-prose">${md(p)}</p>`).join('')}
      </div>
    `;
  }

  function renderKeyPoints(points) {
    return `
      <div class="gd-sec">
        <div class="gd-sec-title">要点</div>
        <ul class="gd-list">${points.map(p => `<li>${md(p)}</li>`).join('')}</ul>
      </div>
    `;
  }

  function renderExamples(examples, cardId) {
    return `
      <div class="gd-sec">
        <div class="gd-sec-title">课文原句</div>
        ${examples.map((x, i) => {
          const slotId = `${cardId}_ex${i}_xray`;
          const hasXray = !!x.xid && exemplarsData.some(e => e.id === x.xid);
          return `
            <div class="gd-example">
              <div class="gd-ex-top">
                <span class="gd-ex-jp jp-text" onclick="JapaneseTTS.speak('${escapeQuotes(x.jp)}', this)"
                      title="点击朗读">${x.jp_ruby || esc(x.jp)}</span>
                <button class="icon-btn" title="朗读这句" onclick="JapaneseTTS.speak('${escapeQuotes(x.jp)}', this)">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
                    <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
                  </svg>
                </button>
                ${hasXray ? `
                  <button class="icon-btn" style="color: var(--accent-gold);" title="打开这句的语法透视图"
                          onclick="App.toggleExampleXray('${slotId}', '${esc(x.xid)}')">✦ 语法透视</button>` : ''}
                ${x.src ? `<span class="gd-ex-src">${esc(x.src)}</span>` : ''}
              </div>
              ${x.romaji ? `<div class="gd-ex-rm">${esc(x.romaji)}</div>` : ''}
              ${x.lit ? `<div class="gd-ex-lit"><span class="lit-label">逐词直译</span>${esc(x.lit)}</div>` : ''}
              ${x.zh ? `<div class="gd-ex-zh">${esc(x.zh)}</div>` : ''}
              ${x.note ? `<div class="gd-ex-note">${md(x.note)}</div>` : ''}
              ${hasXray ? `<div class="gd-xray-slot" id="${slotId}"></div>` : ''}
            </div>
          `;
        }).join('')}
      </div>
    `;
  }

  function renderPitfalls(pitfalls) {
    return `
      <div class="gd-sec">
        <div class="gd-sec-title">中文母语者的坑</div>
        ${pitfalls.map(p => `
          <div class="gd-pitfall">
            <span class="gd-wrong jp-text">${esc(p.wrong)}</span>
            <span class="gd-right jp-text">${esc(p.right)}</span>
            ${p.why ? `<div class="gd-pit-why">${md(p.why)}</div>` : ''}
          </div>`).join('')}
      </div>
    `;
  }

  function renderContrast(c) {
    return `
      <div class="gd-sec">
        <div class="gd-sec-title">${esc(c.title || '近义辨析')}</div>
        ${renderTable(c)}
        ${c.note ? `<div class="gd-note">${md(c.note)}</div>` : ''}
      </div>
    `;
  }

  function renderConjugation(c) {
    return `
      <div class="gd-sec">
        <div class="gd-sec-title">${esc(c.title || '变形表')}</div>
        ${renderTable(c)}
        ${c.note ? `<div class="gd-note">${md(c.note)}</div>` : ''}
      </div>
    `;
  }

  function renderTable(spec) {
    if (!spec || !spec.rows || !spec.rows.length) return '';
    const cols = spec.cols || [];
    return `
      <table class="gd-table">
        ${cols.length ? `<thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead>` : ''}
        <tbody>
          ${spec.rows.map(r => `<tr>${r.map((cell, ci) => `
            <${ci === 0 ? 'th' : 'td'}${ci === 0 ? ' scope="row"' : ''}>${md(cell)}</${ci === 0 ? 'th' : 'td'}>`).join('')}
          </tr>`).join('')}
        </tbody>
      </table>
    `;
  }

  function renderQuiz(e) {
    const qs = e.self_check || [];
    const as = e.answers || [];
    return `
      <div class="gd-sec">
        <div class="gd-sec-title">自检（点击看答案）</div>
        ${qs.map((q, i) => `
          <div class="gd-quiz" id="${e.id}_q${i}">
            <div class="gd-q" onclick="App.toggleQuiz('${e.id}_q${i}')">
              <span class="gd-q-num">Q${i + 1}</span>
              <span>${md(q)}</span>
            </div>
            ${as[i] ? `<div class="gd-a">${md(as[i])}</div>` : ''}
          </div>`).join('')}
      </div>
    `;
  }

  function renderRelated(e) {
    const rel = e.related_resolved || [];
    if (!rel.length) return '';
    return `
      <div class="gd-related">
        <span class="gd-related-label">关联条目</span>
        ${rel.map(r => r.pending
          ? `<span class="gd-rel-chip pending" title="该条目在后续课程，尚未撰写">${esc(r.label)}</span>`
          : `<button class="gd-rel-chip" onclick="App.gotoGrammar('${esc(r.id)}')"
                    title="跳到第${r.lesson}课">${esc(r.label)}<span style="opacity:.5;font-size:.8em;">　第${r.lesson}课</span></button>`
        ).join('')}
      </div>
    `;
  }

  function renderLegacy(e) {
    if (e.legacy_missing) {
      return `
        <details class="gd-legacy">
          <summary>原教材笔记</summary>
          <div class="gd-legacy-body gd-legacy-empty">
            教材此条笔记为空——原数据抓下来时就没有任何解释。上面的讲义是从零补写的。
          </div>
        </details>
      `;
    }
    if (!e.legacy) return '';
    return `
      <details class="gd-legacy">
        <summary>原教材笔记（对照用）</summary>
        <div class="gd-legacy-body">${formatGrammarExplanation(e.legacy)}</div>
      </details>
    `;
  }

  /* ---------------- 交互 ---------------- */

  function toggleGrammarCard(id, forceOpen) {
    const card = document.getElementById('gdc_' + id);
    if (!card) return false;
    const open = (forceOpen === undefined) ? !card.classList.contains('open') : !!forceOpen;
    card.classList.toggle('open', open);
    // 展开后透视图槽位的几何位置会变，箭头需要重算
    if (open) setTimeout(() => GrammarDiagram.updateAllArrows(), 80);
    return open;
  }

  function toggleAllGrammarCards(lessonNum, btn) {
    const list = document.getElementById('gdeep_list_' + lessonNum);
    if (!list) return;
    const cards = list.querySelectorAll('.gdeep-card');
    const allOpen = Array.prototype.every.call(cards, c => c.classList.contains('open'));
    cards.forEach(c => c.classList.toggle('open', !allOpen));
    if (btn) btn.textContent = allOpen ? '展开全部' : '收起全部';
    if (!allOpen) setTimeout(() => GrammarDiagram.updateAllArrows(), 120);
  }

  function toggleQuiz(qid) {
    const el = document.getElementById(qid);
    if (el) el.classList.toggle('open');
  }

  /** 例句的透视图按需渲染：77 条例句若一次性铺满会拖慢首屏。 */
  function toggleExampleXray(slotId, xid) {
    const slot = document.getElementById(slotId);
    if (!slot) return;
    const willOpen = !slot.classList.contains('open');
    slot.classList.toggle('open', willOpen);
    if (!willOpen) return;

    const containerId = slotId + '_dg';
    if (!renderedXraySlots.has(slotId)) {
      const ex = exemplarsData.find(e => e.id === xid);
      if (!ex) return;
      slot.innerHTML = GrammarDiagram.render(ex, { id: containerId });
      renderedXraySlots.add(slotId);
    }
    setTimeout(() => GrammarDiagram.updateArrows(containerId), 60);
  }

  /**
   * 课文「简单透视图」的折叠开关（会话课文／应用课文每句一个）。
   * 与 toggleExampleXray 同一套 slot + .open 机制：默认折叠、首次展开才挂图，
   * 所以整课重渲染时槽位天然回到空且折叠。简单模式不画 Ø が，无需重算箭头几何。
   * 按钮自身同步 .open 与 aria-expanded，键盘焦点环由 CSS :focus-visible 提供。
   */
  function toggleSimpleXray(slotId, exemplarId, btn) {
    const slot = document.getElementById(slotId);
    if (!slot) return;

    const willOpen = !slot.classList.contains('open');
    slot.classList.toggle('open', willOpen);

    const button = btn || document.getElementById(`${slotId}_btn`);
    if (button) {
      button.classList.toggle('open', willOpen);
      button.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
    }
    if (!willOpen) return;

    if (!renderedXraySlots.has(slotId)) {
      const ex = exemplarsData.find(e => e.id === exemplarId);
      if (!ex) return;
      slot.innerHTML = GrammarDiagram.render(ex, { id: `${slotId}_dg`, simple: true });
      renderedXraySlots.add(slotId);
    }
  }

  /** 关联条目跳转：可能跨课，需要先切课再展开、滚动、闪一下 */
  function gotoGrammar(id) {
    const entry = grammarDeepIndex[id];
    if (!entry) {
      showToast('该条目还没撰写');
      return;
    }
    const reveal = () => {
      toggleGrammarCard(id, true);
      const el = document.getElementById('gdc_' + id);
      if (!el) return;
      setTimeout(() => {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        el.classList.remove('flash');
        void el.offsetWidth;   // 强制重排，让动画可以重播
        el.classList.add('flash');
      }, 60);
    };
    if (entry.lesson !== currentLessonNum) {
      selectLesson(entry.lesson);
      setTimeout(reveal, 160);
    } else {
      reveal();
    }
  }

  function formatGrammarExplanation(exp) {
    if (!exp) return '';
    // Highlight brackets [名], [动], ～は, etc.
    return exp
      .replace(/\[([^\]]+)\]/g, '<span style="color:var(--accent-gold); font-weight:600;">[$1]</span>')
      .replace(/“([^”]+)”/g, '<span style="font-weight:600;">“$1”</span>');
  }

  function escapeQuotes(str) {
    if (!str) return '';
    return str.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  // Public API
  window.App = {
    init: init,
    selectLesson: selectLesson,
    toggleSentenceXray: toggleSentenceXray,
    toggleSimpleXray: toggleSimpleXray,
    toggleGrammarCard: toggleGrammarCard,
    toggleAllGrammarCards: toggleAllGrammarCards,
    toggleQuiz: toggleQuiz,
    toggleExampleXray: toggleExampleXray,
    toggleDiagramLegend: toggleDiagramLegend,
    gotoGrammar: gotoGrammar
  };

  // Launch on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
