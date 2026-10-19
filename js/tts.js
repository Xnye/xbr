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
  const memoryAudioCache = new Map();

  function notify(msg) {
    if (window.App && typeof window.App.showToast === 'function') {
      window.App.showToast(msg);
    }
  }

  function probeBackend(force) {
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

  function applyPlaybackRate(audio, rate) {
    if (!audio) return;
    try {
      audio.defaultPlaybackRate = rate;
      audio.playbackRate = rate;
    } catch (e) {
      console.warn('Playback rate error:', e);
    }
  }

  function setRate(r) {
    speechRate = Math.max(0.5, Math.min(2.0, parseFloat(r)));
    localStorage.setItem('xbr_rate', speechRate);
    if (currentAudio) {
      applyPlaybackRate(currentAudio, speechRate);
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

    const cacheKey = `${activeVoice}_${cleanText}`;
    const audioUrl = `${TTS_API}?text=${encodeURIComponent(cleanText)}&voice=${encodeURIComponent(activeVoice)}`;

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
    applyPlaybackRate(audio, speechRate);

    const onPlayHandler = function () {
      applyPlaybackRate(audio, speechRate);
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
    audio.addEventListener('canplay', () => applyPlaybackRate(audio, speechRate));
    audio.addEventListener('loadedmetadata', () => applyPlaybackRate(audio, speechRate));
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
    probeBackend: probeBackend,
    isBackendAvailable: isBackendAvailable
  };
})();

if (typeof window !== 'undefined') {
  window.JapaneseTTS = JapaneseTTS;
}
