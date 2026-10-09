// Animation engine — cinematic scroll for hotel landing page
(function() {
  const section = document.getElementById('cinema');
  if (!section) return;
  const html = document.documentElement;
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const track = document.getElementById('sights-track');
  const controls = document.getElementById('sights-controls');
  const prevBtn = document.querySelector('.sight-prev');
  const nextBtn = document.querySelector('.sight-next');
  const sightCards = [];
  let originalSightCount = 0;
  let activeSight = 0;
  let targetMouseX = 0, mouseX = 0, targetMouseY = 0, mouseY = 0;
  let targetScroll = 0, smoothScroll = 0, initialized = false;
  let rafPending = false;

  function clamp(v, min = 0, max = 1) { return Math.min(max, Math.max(min, v)); }
  function smoothstep(e0, e1, v) {
    const x = clamp((v - e0) / (e1 - e0));
    return x * x * (3 - 2 * x);
  }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function segmentInOut(s, a, b, c, d) {
    const enter = smoothstep(a, b, s), exit = smoothstep(c, d, s);
    return { enter, exit, active: enter * (1 - exit) };
  }
  function getScrollDistance() {
    return clamp(-section.getBoundingClientRect().top, 0, section.offsetHeight - window.innerHeight);
  }

  function update() {
    rafPending = false;
    targetScroll = getScrollDistance();
    if (!initialized || reduceMotion.matches) { smoothScroll = targetScroll; initialized = true; }
    else { smoothScroll = lerp(smoothScroll, targetScroll, 0.14); }
    if (Math.abs(smoothScroll - targetScroll) < 0.08) smoothScroll = targetScroll;

    mouseX = lerp(mouseX, targetMouseX, 0.12);
    mouseY = lerp(mouseY, targetMouseY, 0.12);

    const frame2 = segmentInOut(smoothScroll, 560, 900, 1300, 1620);
    const frame3 = segmentInOut(smoothScroll, 1760, 2140, 2540, 2700);
    const progress = clamp(smoothScroll / 2700);
    const introExit = smoothstep(90, 650, smoothScroll);
    const sightsEnterRaw = smoothstep(2760, 3560, smoothScroll);
    const sightsEnter = Math.pow(sightsEnterRaw, 1.55);
    const sightsControlsEnter = smoothstep(3360, 3660, smoothScroll);
    const blurActive = clamp(frame2.active + frame3.active);
    const frame2Opacity = frame2.active * (1 - frame3.enter);
    const splitDrift = Math.pow(frame2.enter, 1.5);
    const panel2Opacity = frame2.active * (1 - frame2.exit);
    const panel3Opacity = frame3.active * (1 - frame3.exit);
    const backScale = 0.76 + progress * 0.2 + frame2.enter * 0.18 + frame3.enter * 0.16;
    const sharedHeroY = progress * -74;
    const sharedHeroScale = progress * 0.23;

    const sightsScreenTop = Math.min(220, Math.max(112, window.innerHeight * 0.19)) - 50;
    const sightsParentTop = window.innerHeight - (window.innerHeight - sightsScreenTop) / backScale;

    html.style.setProperty('--mx', (reduceMotion.matches ? 0 : mouseX).toFixed(4));
    html.style.setProperty('--my', (reduceMotion.matches ? 0 : mouseY).toFixed(4));
    html.style.setProperty('--back-opacity', (1 - frame2.active * 0.06).toFixed(3));
    html.style.setProperty('--back-x', `${mouseX * -12}px`);
    html.style.setProperty('--back-y', `${mouseY * -4}px`);
    html.style.setProperty('--back-scale', backScale.toFixed(3));
    html.style.setProperty('--four-y', `${10 + progress * 10}vh`);
    html.style.setProperty('--four-scale', (0.78 + progress * 0.16).toFixed(3));
    html.style.setProperty('--bazaar-y', `${20 - progress * 8}vh`);
    html.style.setProperty('--blur-px', `${blurActive * 14}px`);
    html.style.setProperty('--back-brightness', (1 - blurActive * 0.255).toFixed(3));
    html.style.setProperty('--bazaar-blur-px', `${frame2.active * 14}px`);
    html.style.setProperty('--bazaar-brightness', (1 - frame2.active * 0.255 - frame3.active * 0.06).toFixed(3));
    html.style.setProperty('--bazaar-saturation', (1 + frame3.active * 0.18).toFixed(3));
    html.style.setProperty('--shade-opacity', "1");
    html.style.setProperty('--shade-z', frame2.active > 0.02 ? "2" : "0");
    html.style.setProperty('--shade-top-alpha', (blurActive * 0.465).toFixed(3));
    html.style.setProperty('--shade-mid-alpha', (blurActive * 0.42).toFixed(3));
    html.style.setProperty('--shade-bottom-alpha', (blurActive * 0.51).toFixed(3));
    html.style.setProperty('--title-y', `${introExit * -210}px`);
    html.style.setProperty('--title-scale', (1 - introExit * 0.08).toFixed(3));
    html.style.setProperty('--title-opacity', (1 - introExit).toFixed(3));
    html.style.setProperty('--bridge-x', `calc(-50% + ${mouseX * 18}px)`);
    html.style.setProperty('--bridge-y', `${mouseY * 8 + sharedHeroY - frame2.exit * 760}px`);
    html.style.setProperty('--bridge-bottom', `${5 - frame2.enter * 13}vh`);
    html.style.setProperty('--bridge-width', `${67.2 + frame2.enter * 37.8}vw`);
    html.style.setProperty('--bridge-scale', (1.02 + sharedHeroScale + frame2.exit * 0.46).toFixed(3));
    html.style.setProperty('--split-left-x', `calc(-50% + ${-splitDrift * 46}vw + ${mouseX * 22}px)`);
    html.style.setProperty('--split-left-y', `${mouseY * 10 + sharedHeroY - splitDrift * 180}px`);
    html.style.setProperty('--split-left-scale', (1 + sharedHeroScale + frame2.enter * 0.74).toFixed(3));
    html.style.setProperty('--split-right-x', `calc(-50% + ${splitDrift * 46}vw + ${mouseX * 22}px)`);
    html.style.setProperty('--split-right-y', `${mouseY * 10 + sharedHeroY - splitDrift * 180}px`);
    html.style.setProperty('--split-right-scale', (1 + sharedHeroScale + frame2.enter * 0.74).toFixed(3));
    html.style.setProperty('--frame2-opacity', frame2Opacity.toFixed(3));
    html.style.setProperty('--frame2-x', `calc(-50% + ${mouseX * 10}px)`);
    html.style.setProperty('--frame2-y', `calc(-50% + ${mouseY * 8 - frame2.exit * 150}px)`);
    html.style.setProperty('--frame2-scale', (1.06 + frame2.enter * 0.08 + frame2.exit * 0.08).toFixed(3));
    html.style.setProperty('--intro-copy-y', `${introExit * 90}px`);
    html.style.setProperty('--intro-copy-opacity', (1 - introExit).toFixed(3));
    html.style.setProperty('--panel2-opacity', panel2Opacity.toFixed(3));
    html.style.setProperty('--panel2-y', `calc(-50% + ${-frame2.exit * 86 + (1 - frame2.enter) * 58}px)`);
    html.style.setProperty('--panel3-opacity', panel3Opacity.toFixed(3));
    html.style.setProperty('--panel3-y', `calc(-50% + ${-frame3.exit * 86 + (1 - frame3.enter) * 58}px)`);
    html.style.setProperty('--sights-opacity', sightsEnter.toFixed(3));
    html.style.setProperty('--sights-controls-opacity', sightsControlsEnter.toFixed(3));
    controls.classList.toggle('is-ready', sightsControlsEnter > 0.98);
    html.style.setProperty('--sights-visibility', sightsEnter > 0.01 ? 'visible' : 'hidden');
    html.style.setProperty('--sights-y', '0px');
    html.style.setProperty('--sights-enter-x', `${(1 - sightsEnter) * 420}vw`);
    html.style.setProperty('--sights-scale', (1 / backScale).toFixed(3));
    html.style.setProperty('--sights-top', `${sightsParentTop}px`);
    html.style.setProperty('--sights-screen-top', `${sightsScreenTop}px`);

    if (Math.abs(smoothScroll - targetScroll) > 0.08 || Math.abs(mouseX - targetMouseX) > 0.001 || Math.abs(mouseY - targetMouseY) > 0.001) {
      requestTick();
    }
  }

  function requestTick() {
    if (!rafPending) { rafPending = true; requestAnimationFrame(update); }
  }

  // Sight slider
  function setupSightSlider() {
    if (!track) return;
    track.replaceChildren();
    const cards = Array.from(document.querySelectorAll('.sight-card'));
    if (!cards.length) return;
    originalSightCount = cards.length;
    activeSight = originalSightCount;
    for (let set = 0; set < 3; set++) {
      for (let i = 0; i < cards.length; i++) {
        const clone = cards[i].cloneNode(true);
        clone.dataset.sightIndex = set * originalSightCount + i;
        clone.addEventListener('click', () => selectSightCard(clone));
        clone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectSightCard(clone); } });
        track.appendChild(clone);
      }
    }
  }
  function updateSightSlider() {
    if (!track || !track.children.length) return;
    const cardWidth = track.children[0].offsetWidth;
    const style = getComputedStyle(track);
    const gap = parseFloat(style.columnGap || '0');
    html.style.setProperty('--sights-shift', `${-(cardWidth + gap) * activeSight}px`);
    Array.from(track.children).forEach(c => c.classList.toggle('is-active', Number(c.dataset.sightIndex) === activeSight));
  }
  function moveSightSlider(dir) { activeSight += dir; updateSightSlider(); }
  function selectSightCard(card) {
    const idx = Number(card.dataset.sightIndex);
    if (Number.isFinite(idx)) { activeSight = idx; updateSightSlider(); }
  }
  function jumpSightSlider(i) {
    track.classList.add('is-jumping');
    activeSight = i;
    updateSightSlider();
    requestAnimationFrame(() => requestAnimationFrame(() => track.classList.remove('is-jumping')));
  }
  function normalizeSightSlider() {
    if (activeSight >= originalSightCount * 2) jumpSightSlider(activeSight - originalSightCount);
    else if (activeSight < originalSightCount) jumpSightSlider(activeSight + originalSightCount);
  }

  // Events
  window.addEventListener('scroll', () => { requestTick(); }, { passive: true });
  window.addEventListener('resize', () => { setupSightSlider(); updateSightSlider(); requestTick(); });
  window.addEventListener('pointermove', e => {
    targetMouseX = e.clientX / window.innerWidth - 0.5;
    targetMouseY = e.clientY / window.innerHeight - 0.5;
    requestTick();
  }, { passive: true });

  if (prevBtn) prevBtn.addEventListener('click', () => moveSightSlider(-1));
  if (nextBtn) nextBtn.addEventListener('click', () => moveSightSlider(1));
  if (track) track.addEventListener('transitionend', () => normalizeSightSlider());

  // Init
  setupSightSlider();
  updateSightSlider();
  requestTick();
})();
