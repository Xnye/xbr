/**
 * JapaneseTTS.js - High Fidelity Japanese Audio Engine (v2.0)
 * 1. Microsoft Edge Neural Audio via local /api/tts endpoint
 *    - 🎙️ ja-JP-NanamiNeural (Female, Tokyo NHK announcer quality, pitch-accent accurate)
 *    - 🎙️ ja-JP-KeitaNeural (Male, warm Tokyo natural tone)
 * 2. Instant Memory Cache (0ms on repeat clicks)
 * 3. Robust HTML5 PlaybackRate Engine (respects 0.7x, 0.85x, 1.0x, 1.25x in real-time)
 * 4. Immediate Voice Switching without reload
 * 5. Fallback to Web Speech API
 */

const JapaneseTTS = (function () {
  let currentAudio = null;
  let activeVoice = localStorage.getItem('xbr_voice') || 'ja-JP-NanamiNeural';
  let speechRate = parseFloat(localStorage.getItem('xbr_rate') || '1.0');
  let currentPlayingBtn = null;

  // In-memory audio instance cache for instant re-play without re-fetching
  const memoryAudioCache = new Map();

  function setVoice(v) {
    if (activeVoice !== v) {
      activeVoice = v;
      localStorage.setItem('xbr_voice', v);
      // Stop current playback if voice changes
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

  /**
   * Main speech playback function
   * @param {string} rawText The sentence or word to speak
   * @param {HTMLElement} btnElement The clicked button or container for feedback
   */
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

    // Stop currently playing audio
    stop();

    // Visual loading feedback immediately (0ms)
    if (btnElement) {
      currentPlayingBtn = btnElement;
      btnElement.classList.add('audio-loading');
    }

    const cacheKey = `${activeVoice}_${cleanText}`;
    const audioUrl = `/api/tts?text=${encodeURIComponent(cleanText)}&voice=${encodeURIComponent(activeVoice)}`;

    // Check memory cache first
    let audio = memoryAudioCache.get(cacheKey);

    if (!audio) {
      audio = new Audio(audioUrl);
      // Preload metadata
      audio.preload = 'auto';
      memoryAudioCache.set(cacheKey, audio);
    }

    currentAudio = audio;

    // Ensure playback rate is applied across all lifecycle events
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
      console.warn('Audio endpoint error, falling back to Web Speech API:', err);
      resetActiveBtn();
      audio.removeEventListener('play', onPlayHandler);
      audio.removeEventListener('ended', onEndedHandler);
      audio.removeEventListener('error', onErrorHandler);
      speakWebSpeech(cleanText, btnElement);
    };

    audio.addEventListener('play', onPlayHandler);
    audio.addEventListener('canplay', () => applyPlaybackRate(audio, speechRate));
    audio.addEventListener('loadedmetadata', () => applyPlaybackRate(audio, speechRate));
    audio.addEventListener('ended', onEndedHandler);
    audio.addEventListener('error', onErrorHandler);

    // Reset playback position
    audio.currentTime = 0;

    const playPromise = audio.play();
    if (playPromise !== undefined) {
      playPromise.catch(err => {
        console.warn('Audio play() promise rejected:', err);
        resetActiveBtn();
        // Fallback if network blocked
        speakWebSpeech(cleanText, btnElement);
      });
    }
  }

  /**
   * Fallback using browser Web Speech API
   */
  function speakWebSpeech(text, btnElement) {
    if (!('speechSynthesis' in window)) {
      resetActiveBtn();
      return;
    }

    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = 'ja-JP';
    utter.rate = speechRate;

    // Prioritize natural voices
    const voices = window.speechSynthesis.getVoices();
    const isMale = activeVoice.includes('Keita');
    const matchedVoice = voices.find(v => {
      const matchLang = v.lang.startsWith('ja') || v.lang.includes('JP');
      if (!matchLang) return false;
      if (isMale) return v.name.includes('Keita') || v.name.includes('Male') || v.name.includes('Ichiro');
      return v.name.includes('Nanami') || v.name.includes('Ayumi') || v.name.includes('Haruka') || v.name.includes('Female');
    }) || voices.find(v => v.lang.startsWith('ja') || v.lang.includes('JP'));

    if (matchedVoice) utter.voice = matchedVoice;

    if (btnElement) {
      currentPlayingBtn = btnElement;
      btnElement.classList.add('audio-playing');
    }

    utter.onend = resetActiveBtn;
    utter.onerror = resetActiveBtn;

    window.speechSynthesis.speak(utter);
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
    getRate: getRate
  };
})();

if (typeof window !== 'undefined') {
  window.JapaneseTTS = JapaneseTTS;
}
