/**
 * JapaneseTTS.js - Japanese audio engine
 * 1. Microsoft Edge Neural Audio via local /api/tts endpoint
 * 2. Instant memory cache
 * 3. Playback rate control
 * 4. Graceful fallback to Web Speech with explicit user feedback
 */
const JapaneseTTS = (function () {
  const TTS_API = 'api/tts';
  const HEALTH_API = 'api/health';

  let currentAudio = null;
  let activeVoice = localStorage.getItem('xbr_voice') || 'ja-JP-NanamiNeural';
  let speechRate = parseFloat(localStorage.getItem('xbr_rate') || '1.0');
  let currentPlayingBtn = null;
  let backendAvailable = null;       // null = 尚未探测
  let probePromise = null;
  let systemVoiceNoticeShown = false;
  let fallbackNoticeShown = false;
  let errorNoticeShown = false;
  let systemVoicesPending = false;   // 是否已在等 voiceschanged 补全声线列表
  const memoryAudioCache = new Map();

  function notify(msg) {
    if (window.App && typeof window.App.showToast === 'function') {
      window.App.showToast(msg);
    }
  }

  function probeBackend(force) {
    // force 时必须真的重发请求：旧实现把 resolved 的 Promise 直接返回，
    // 重试探测永远是上一次的结果（后端起起来后 UI 一直停在降级态）。
    if (probePromise && !force) return probePromise;
    probePromise = fetch(HEALTH_API, { cache: 'no-store' })
      .then(r => {
        backendAvailable = r.ok;
        document.dispatchEvent(new CustomEvent('xbr:tts-status', {
          detail: { available: r.ok }
        }));
        return r.ok;
      })
      .catch(() => {
        backendAvailable = false;
        document.dispatchEvent(new CustomEvent('xbr:tts-status', {
          detail: { available: false }
        }));
        return false;
      });
    return probePromise;
  }

  function isBackendAvailable() {
    return backendAvailable;
  }

  function setVoice(v) {
    if (activeVoice !== v) {
      activeVoice = v;
      localStorage.setItem('xbr_voice', v);
      stop();
    }
  }

  function getVoice() {
    return activeVoice;
  }

  /**
   * 语速档位。value 是播放倍率；rate 是送给神经语音的合成语速百分比。
   *
   * 为什么不直接用 playbackRate：浏览器变速是时间拉伸，会把频谱涂糊。
   * 实测同一句 0.5x：服务端原生合成谱质心 1513Hz，客户端拉伸只剩 1240Hz，
   * 而且发闷、辅音粘连。所以慢速必须交给服务端做，playbackRate 只留 1.0。
   *
   * Edge 的语速下限实测是 -50%（再低不生效），故最慢档就是 -50%。
   */
  const RATE_STEPS = [
    { value: 0.5,  rate: -50, label: '0.5x', note: '极慢' },
    { value: 0.6,  rate: -40, label: '0.6x', note: '很慢' },
    { value: 0.75, rate: -25, label: '0.75x', note: '慢速' },
    { value: 0.85, rate: -15, label: '0.85x', note: '稍慢' },
    { value: 1.0,  rate: -4,  label: '1.0x', note: '常速' },
    { value: 1.2,  rate: 20,  label: '1.2x', note: '较快' },
    { value: 1.5,  rate: 50,  label: '1.5x', note: '高速' }
  ];

  /** 顶栏下拉里用短标签（窄屏放得下），提示和 toast 用长描述。 */
  function labelOf(step, withNote) {
    if (!step) return '';
    return withNote ? `${step.label} ${step.note}` : step.label;
  }

  function rateForSpeed(value) {
    const v = parseFloat(value);
    const hit = RATE_STEPS.find(s => Math.abs(s.value - v) < 0.01);
    if (hit) return hit.rate;
    // 非预设档位（例如旧存档里的 1.25）按倍率线性折算
    return Math.round((v - 1) * 100);
  }

  function getRateSteps() {
    return RATE_STEPS.slice();
  }

  function setRate(r) {
    const v = parseFloat(r);
    speechRate = Math.max(0.5, Math.min(2.0, isFinite(v) ? v : 1.0));
    localStorage.setItem('xbr_rate', speechRate);
    // 语速变了，已缓存的 Audio 元素就是旧速率的产物，必须失效
    memoryAudioCache.clear();
    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
      resetActiveBtn();
    }
  }

  function getRate() {
    return speechRate;
  }

  function speak(rawText, btnElement) {
    if (!rawText) return;

    // 只清标记和空白；标点必须保留，Edge TTS 靠 。，！？ 来生成句读停顿
    const cleanText = rawText
      .replace(/<rt[^>]*>.*?<\/rt>/gi, '')
      .replace(/<[^>]*>/g, '')
      .replace(/^\*\s*/, '')
      .replace(/[\s　]+/g, '')
      .trim();

    if (!cleanText) return;

    stop();

    if (btnElement) {
      currentPlayingBtn = btnElement;
      btnElement.classList.add('audio-loading');
    }

    // 已经确认没有本地 TTS 服务：直接走系统语音，避免每次点都等一遍 404
    if (backendAvailable === false) {
      speakWebSpeech(cleanText, btnElement, true);
      return;
    }

    // 语速由服务端合成，缓存键要带上它，否则换档会播到上一档的音频
    const synthRate = rateForSpeed(speechRate);
    const cacheKey = `${activeVoice}_${synthRate}_${cleanText}`;
    const audioUrl = `${TTS_API}?text=${encodeURIComponent(cleanText)}`
      + `&voice=${encodeURIComponent(activeVoice)}&rate=${synthRate}`;

    let audio = memoryAudioCache.get(cacheKey);
    if (!audio) {
      audio = new Audio(audioUrl);
      audio.preload = 'auto';
      memoryAudioCache.set(cacheKey, audio);
    }

    let fallbackStarted = false;
    const fallback = (err) => {
      if (fallbackStarted) return;
      fallbackStarted = true;
      console.warn('Audio endpoint error, falling back to Web Speech API:', err);
      // 失败的 Audio 元素会卡在 error 状态；删掉缓存，下次点击重新请求
      memoryAudioCache.delete(cacheKey);
      resetActiveBtn();
      if (btnElement) {
        currentPlayingBtn = btnElement;
        btnElement.classList.add('audio-loading');
      }
      speakWebSpeech(cleanText, btnElement, true);
    };

    currentAudio = audio;
    // 音频已经是目标语速，播放保持 1.0，不再二次变速
    audio.playbackRate = 1.0;

    const onPlayHandler = function () {
      audio.playbackRate = 1.0;
      if (currentPlayingBtn) {
        currentPlayingBtn.classList.remove('audio-loading');
        currentPlayingBtn.classList.add('audio-playing');
      }
    };

    const onEndedHandler = function () {
      resetActiveBtn();
      if (currentAudio === audio) {
        currentAudio = null;
      }
      audio.removeEventListener('play', onPlayHandler);
      audio.removeEventListener('ended', onEndedHandler);
      audio.removeEventListener('error', onErrorHandler);
    };

    const onErrorHandler = function (err) {
      audio.removeEventListener('play', onPlayHandler);
      audio.removeEventListener('ended', onEndedHandler);
      audio.removeEventListener('error', onErrorHandler);
      fallback(err);
    };

    audio.addEventListener('play', onPlayHandler);
    audio.addEventListener('ended', onEndedHandler);
    audio.addEventListener('error', onErrorHandler);

    audio.currentTime = 0;

    const playPromise = audio.play();
    if (playPromise !== undefined) {
      playPromise.catch(err => {
        // play() 与 error 事件可能同时失败，fallback 内部保证只执行一次
        fallback(err);
      });
    }
  }

  function getJapaneseVoices() {
    if (!('speechSynthesis' in window)) return [];
    return window.speechSynthesis.getVoices().filter(v => {
      return (v.lang || '').toLowerCase().startsWith('ja');
    });
  }

  function pickJapaneseVoice(voices) {
    const isMale = activeVoice.includes('Keita');
    if (isMale) {
      return voices.find(v => /Keita|Male|Ichiro|Takumi/i.test(v.name)) || voices[0];
    }
    return voices.find(v => /Nanami|Ayumi|Haruka|Female|Kyoko/i.test(v.name)) || voices[0];
  }

  /**
   * 暴露系统日语声线的真实名字，供 UI 如实显示「当前听到的到底是谁」。
   * 浏览器首次 getVoices() 常为空、随后靠 voiceschanged 补齐，所以这里
   * 顺手注册一次刷新回调，让已经渲染出来的「系统语音」文案能变成真名。
   */
  function getSystemVoiceNames() {
    const names = getJapaneseVoices().map(v => v.name);
    if (!names.length && 'speechSynthesis' in window && !systemVoicesPending) {
      systemVoicesPending = true;
      const onChange = () => {
        if (!getJapaneseVoices().length) return;
        window.speechSynthesis.removeEventListener('voiceschanged', onChange);
        document.dispatchEvent(new CustomEvent('xbr:tts-status', {
          detail: { available: backendAvailable }
        }));
      };
      window.speechSynthesis.addEventListener('voiceschanged', onChange);
    }
    return names;
  }

  /**
   * Web Speech 回退。浏览器首次 getVoices() 可能为空，要等 voiceschanged。
   * 没有日语声线时不假装播放，明确告诉用户。
   */
  function speakWebSpeech(text, btnElement, fromFallback) {
    if (!('speechSynthesis' in window)) {
      notify('当前浏览器不支持朗读。');
      resetActiveBtn();
      return;
    }

    const run = (voices) => {
      if (fromFallback && backendAvailable !== false && !fallbackNoticeShown) {
        fallbackNoticeShown = true;
        notify('网络发音失败，已切换为系统语音。');
      } else if (fromFallback && backendAvailable === false && !systemVoiceNoticeShown) {
        systemVoiceNoticeShown = true;
        notify('当前为静态页面，使用系统语音朗读。');
      }

      window.speechSynthesis.cancel();
      const utter = new SpeechSynthesisUtterance(text);
      utter.lang = 'ja-JP';
      utter.rate = speechRate;
      utter.voice = pickJapaneseVoice(voices);
      // 系统语音没有服务端可调，只能靠 SpeechSynthesisUtterance.rate；
      // 它本身是原生韵律放慢，不像 media playbackRate 那样涂抹频谱。
      utter.pitch = 1;

      if (btnElement) {
        currentPlayingBtn = btnElement;
        btnElement.classList.remove('audio-loading');
        btnElement.classList.add('audio-playing');
      }

      const reset = () => resetActiveBtn();
      utter.onend = reset;
      utter.onerror = () => {
        reset();
        if (!errorNoticeShown) {
          errorNoticeShown = true;
          notify('朗读失败，请稍后重试。');
        }
      };

      window.speechSynthesis.speak(utter);
    };

    const voices = getJapaneseVoices();
    if (voices.length) {
      run(voices);
      return;
    }

    let settled = false;
    const onVoices = () => {
      if (settled) return;
      const list = getJapaneseVoices();
      if (!list.length) return;
      settled = true;
      window.speechSynthesis.removeEventListener('voiceschanged', onVoices);
      run(list);
    };
    window.speechSynthesis.addEventListener('voiceschanged', onVoices);
    setTimeout(() => {
      if (settled) return;
      settled = true;
      window.speechSynthesis.removeEventListener('voiceschanged', onVoices);
      const list = getJapaneseVoices();
      if (list.length) {
        run(list);
      } else {
        resetActiveBtn();
        if (!errorNoticeShown) {
          errorNoticeShown = true;
          notify('当前环境没有日语语音，朗读不可用。');
        }
      }
    }, 900);
  }

  function stop() {
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
      currentAudio = null;
    }
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    resetActiveBtn();
  }

  function resetActiveBtn() {
    if (currentPlayingBtn) {
      currentPlayingBtn.classList.remove('audio-loading');
      currentPlayingBtn.classList.remove('audio-playing');
      currentPlayingBtn = null;
    }
    document.querySelectorAll('.audio-loading, .audio-playing').forEach(el => {
      el.classList.remove('audio-loading', 'audio-playing');
    });
  }

  return {
    speak: speak,
    stop: stop,
    setVoice: setVoice,
    getVoice: getVoice,
    setRate: setRate,
    getRate: getRate,
    getRateSteps: getRateSteps,
    probeBackend: probeBackend,
    isBackendAvailable: isBackendAvailable,
    getSystemVoiceNames: getSystemVoiceNames
  };
})();

if (typeof window !== 'undefined') {
  window.JapaneseTTS = JapaneseTTS;
}
