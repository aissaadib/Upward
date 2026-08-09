(function () {
  'use strict';

  /* ─────────────────────────────────────────────────────────────
     UPWARD — Premium Motion System
     Philosophy: motion communicates state, not decoration.
     Library: Anime.js (loaded via CDN before this file).
     Timing guide:
       micro  120-180ms   buttons, inputs
       cards  200-250ms
       panels 250ms
       page   280ms
       hero   400ms max
     Easing: easeOutCubic / easeOutQuart / easeOutExpo
     Springs only for organic feel (stiffness 280-420, damping 26-34)
  ───────────────────────────────────────────────────────────── */

  /* ── 0. Reduced motion gate ───────────────────────────────── */
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ── 1. Wait for anime.js ─────────────────────────────────── */
  function ready(fn) {
    if (typeof anime !== 'undefined') { fn(); return; }
    var t = setInterval(function () {
      if (typeof anime !== 'undefined') { clearInterval(t); fn(); }
    }, 20);
  }

  /* ── 2. Util: clamp, noop ─────────────────────────────────── */
  function noop() {}
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  /* ── 3. Core fade-rise (the foundational reveal) ─────────── */
  /*
     Every reveal: opacity 0→1 + translateY dist→0.
     Stagger children for hierarchy.
     Never fly from sides.
  */
  function fadeRise(els, opts) {
    if (reduced) return;
    opts = opts || {};
    if (!els || !els.length) return;
    var dur   = opts.duration || 280;
    var delay = opts.delay    || 40;
    var dist  = opts.distance || 14;
    var ease  = opts.easing   || 'easeOutCubic';
    var nodes = Array.prototype.slice.call(els).filter(function (el) {
      return el && !el.dataset._animDone && el.offsetParent !== null;
    });
    nodes.forEach(function (el) {
      el.dataset._animDone = '1';
      el.style.opacity = '0';
      el.style.transform = 'translateY(' + dist + 'px)';
    });
    if (!nodes.length) return;
    anime({
      targets:      nodes,
      opacity:      [0, 1],
      translateY:   [dist, 0],
      duration:     dur,
      delay:        anime.stagger(delay, { easing: 'easeOutQuad' }),
      easing:       ease
    });
  }


  /* ── 4. Page entrance ─────────────────────────────────────── */
  /*
     On every page load: the main content area fades in,
     moves up 10px, and de-blurs from 3px → 0.
     Duration 280ms — users perceive it as snappy, not sluggish.
  */
  function pageEntrance() {
    if (reduced) return;
    var page = document.querySelector('main') ||
               document.querySelector('.container') ||
               document.querySelector('.page') ||
               document.querySelector('.chat-container');
    if (!page || page === document.body) return;
    anime({
      targets:  page,
      opacity:  [0, 1],
      translateY: [10, 0],
      filter:   ['blur(3px)', 'blur(0px)'],
      duration: 280,
      easing:   'easeOutCubic'
    });
  }

  /* ── 5. Scroll-reveal (IntersectionObserver) ──────────────── */
  /*
     Elements with [data-reveal] or matching .reveal selector
     animate in once when they enter the viewport.
     Never replay. Never fly from sides.
  */
  var REVEAL_SEL = [
    '.feature', '.outcome', '.phase', '.highlight',
    '.card', '.course-card', '.lesson-card', '.path-card',
    '.resource', '.section-block', '.pinned-plan',
    '[data-reveal]'
  ].join(',');

  /* Elements owned by the GSAP layer (brand.js) must never be touched
     here — otherwise they flash visible, get re-hidden, then replayed. */
  function isGsapOwned(el) {
    return !!(el && el.closest &&
      el.closest('[data-reveal],[data-reveal-stagger],[data-reveal-lines]'));
  }

  function initScrollReveal() {
    if (reduced) return;
    if (!window.IntersectionObserver) return;
    var candidates = Array.prototype.slice.call(
      document.querySelectorAll(REVEAL_SEL)
    ).filter(function (el) { return !isGsapOwned(el); });
    if (!candidates.length) return;

    var io = new IntersectionObserver(function (entries) {
      var visible = [];
      entries.forEach(function (e) {
        if (e.isIntersecting && !e.target.dataset._animDone) {
          visible.push(e.target);
          io.unobserve(e.target);
        }
      });
      if (visible.length) fadeRise(visible, { duration: 260, delay: 35, distance: 16 });
    }, { threshold: 0.08, rootMargin: '0px 0px -32px 0px' });

    candidates.forEach(function (el) {
      if (!el.dataset._animDone) {
        el.style.opacity = '0';
        el.style.transform = 'translateY(16px)';
        io.observe(el);
      }
    });
  }

  /* ── 6. MutationObserver — animate dynamically injected DOM ─ */
  var DYNAMIC_SEL = [
    '.card', '.phase', '.highlight', '.path-card', '.detail-content',
    '.result-item', '.feature', '.pinned-plan', '.resource',
    '.outcome', '.lesson-card', '.course-card', '.section-block',
    '.bubble.assistant'
  ].join(',');

  var domObserver = new MutationObserver(function (muts) {
    if (reduced) return;
    var targets = [];
    muts.forEach(function (mut) {
      Array.prototype.slice.call(mut.addedNodes).forEach(function (node) {
        if (node.nodeType !== 1) return;
        if (isGsapOwned(node)) return;
        if (node.matches && node.matches(DYNAMIC_SEL) && !isGsapOwned(node)) targets.push(node);
        if (node.querySelectorAll) {
          Array.prototype.slice.call(node.querySelectorAll(DYNAMIC_SEL))
            .forEach(function (n) { if (!isGsapOwned(n)) targets.push(n); });
        }
      });
    });
    if (targets.length) fadeRise(targets, { duration: 240, delay: 30, distance: 12 });
  });
  domObserver.observe(document.documentElement, { childList: true, subtree: true });


  /* ── 7. Button micro-interactions ────────────────────────── */
  /*
     Press: scale 0.97, 80ms easeOutQuad
     Release: scale 1.0, 150ms easeOutCubic
     Hover: translateY -1px, handled in CSS (GPU, no JS overhead)
  */
  document.addEventListener('pointerdown', function (e) {
    if (reduced) return;
    var btn = e.target.closest(
      '.btn, button, [type="submit"], [type="button"], .send-btn, .btn-next, .option-btn, .tab'
    );
    if (!btn || btn.dataset.noAnim || btn.disabled) return;
    ready(function () {
      anime({ targets: btn, scale: 0.97, duration: 80, easing: 'easeOutQuad' });
    });
  }, { passive: true });

  document.addEventListener('pointerup', function (e) {
    if (reduced) return;
    var btn = e.target.closest(
      '.btn, button, [type="submit"], [type="button"], .send-btn, .btn-next, .option-btn, .tab'
    );
    if (!btn || btn.dataset.noAnim) return;
    ready(function () {
      anime({ targets: btn, scale: 1, duration: 150, easing: 'easeOutCubic' });
    });
  }, { passive: true });

  /* Release on pointer-leave so scale doesn't get stuck */
  document.addEventListener('pointerleave', function (e) {
    if (reduced) return;
    var btn = e.target.closest(
      '.btn, button, [type="submit"], [type="button"], .send-btn, .btn-next, .option-btn, .tab'
    );
    if (!btn || btn.dataset.noAnim) return;
    ready(function () {
      anime({ targets: btn, scale: 1, duration: 150, easing: 'easeOutCubic' });
    });
  }, { passive: true, capture: true });

  /* ── 8. Input focus ring ──────────────────────────────────── */
  /*
     The CSS handles border-color + box-shadow transition.
     We add a subtle label-lift effect on inputs with labels.
  */
  document.addEventListener('focusin', function (e) {
    if (reduced) return;
    var inp = e.target;
    if (!inp.matches || !inp.matches('input, textarea, select')) return;
    var group = inp.closest('.form-group');
    if (!group) return;
    var lbl = group.querySelector('label');
    if (!lbl || lbl.dataset._animDone) return;
    ready(function () {
      anime({ targets: lbl, color: ['var(--text-secondary)', 'var(--accent)'],
        duration: 180, easing: 'easeOutCubic' });
    });
  }, { passive: true });

  document.addEventListener('focusout', function (e) {
    if (reduced) return;
    var inp = e.target;
    if (!inp.matches || !inp.matches('input, textarea, select')) return;
    var group = inp.closest('.form-group');
    if (!group) return;
    var lbl = group.querySelector('label');
    if (!lbl) return;
    ready(function () {
      anime({ targets: lbl, color: ['var(--accent)', 'var(--text-secondary)'],
        duration: 180, easing: 'easeOutCubic' });
    });
  }, { passive: true });


  /* ── 9. Toast system ──────────────────────────────────────── */
  /*
     Appears top-right. Fades + slides down 8px.
     Progress bar shrinks over 3.2s.
     Exit: fade + slide up. Clean, no bounce.
  */
  window.showToast = function (message, type) {
    if (!message) return;
    type = type || 'info';
    var colors = { error: '#ff5460', success: '#41dc65', info: '#23273c', warning: '#f59e0b' };
    var bg = colors[type] || colors.info;

    var c = document.getElementById('toast-container');
    if (!c) {
      c = document.createElement('div');
      c.id = 'toast-container';
      c.style.cssText = [
        'position:fixed', 'top:20px', 'right:20px', 'z-index:99999',
        'display:flex', 'flex-direction:column', 'gap:8px', 'pointer-events:none',
        'max-width:340px'
      ].join(';');
      document.body.appendChild(c);
    }

    var t = document.createElement('div');
    t.setAttribute('role', 'status');
    t.setAttribute('aria-live', 'polite');
    t.style.cssText = [
      'background:' + bg,
      'color:#fff',
      'padding:12px 18px',
      'border-radius:10px',
      'font-weight:600',
      'font-size:.875rem',
      'pointer-events:auto',
      'opacity:0',
      'transform:translateY(-8px)',
      'will-change:opacity,transform',
      'line-height:1.5'
    ].join(';');
    t.textContent = message;

    var bar = document.createElement('div');
    bar.style.cssText = 'height:2px;background:rgba(255,255,255,.35);border-radius:1px;margin-top:8px;transform-origin:left;';
    t.appendChild(bar);
    c.appendChild(t);

    ready(function () {
      anime({ targets: t, opacity: [0, 1], translateY: [-8, 0],
        duration: 240, easing: 'easeOutCubic',
        complete: function () {
          anime({ targets: bar, scaleX: [1, 0], duration: 3200, easing: 'linear',
            complete: function () {
              anime({ targets: t, opacity: [1, 0], translateY: [0, -6],
                duration: 200, easing: 'easeInCubic',
                complete: function () { if (t.parentNode) t.parentNode.removeChild(t); }
              });
            }
          });
        }
      });
    });
  };

  document.addEventListener('toast', function (e) {
    if (e.detail && e.detail.message) window.showToast(e.detail.message, e.detail.type);
  });

  /* ── 10. Modal open/close ─────────────────────────────────── */
  /*
     Backdrop fades in. Modal: opacity + scale 0.97→1 + translateY 8→0.
     Close reverses naturally.
  */
  window.openModal = function (modal) {
    if (!modal) return;
    modal.style.display = 'flex';
    modal.setAttribute('aria-hidden', 'false');
    var content = modal.querySelector('.modal-inner, .modal-content, .modal-box');
    var backdrop = modal.querySelector('.modal-bg, .modal-backdrop');
    ready(function () {
      if (backdrop) anime({ targets: backdrop, opacity: [0, 1], duration: 200, easing: 'easeOutQuad' });
      if (content) {
        anime({ targets: content, opacity: [0, 1], scale: [0.97, 1],
          translateY: [8, 0], duration: 250, easing: 'easeOutCubic' });
      } else {
        anime({ targets: modal, opacity: [0, 1], scale: [0.97, 1],
          translateY: [8, 0], duration: 250, easing: 'easeOutCubic' });
      }
    });
  };

  window.closeModal = function (modal) {
    if (!modal) return;
    var content = modal.querySelector('.modal-inner, .modal-content, .modal-box');
    var backdrop = modal.querySelector('.modal-bg, .modal-backdrop');
    ready(function () {
      if (backdrop) anime({ targets: backdrop, opacity: [1, 0], duration: 180, easing: 'easeInQuad' });
      var target = content || modal;
      anime({ targets: target, opacity: [1, 0], scale: [1, 0.97], translateY: [0, 6],
        duration: 180, easing: 'easeInCubic',
        complete: function () {
          modal.style.display = 'none';
          modal.setAttribute('aria-hidden', 'true');
        }
      });
    });
  };


  /* ── 11. Dropdown open ────────────────────────────────────── */
  /*
     Scale from 0.97 + fade. 160ms. No slide across screen.
  */
  window.openDropdown = function (menu) {
    if (!menu || reduced) return;
    menu.style.display = 'block';
    ready(function () {
      anime({ targets: menu, opacity: [0, 1], scale: [0.97, 1],
        translateY: [-4, 0], duration: 160, easing: 'easeOutCubic' });
    });
  };
  window.closeDropdown = function (menu) {
    if (!menu || reduced) return;
    ready(function () {
      anime({ targets: menu, opacity: [1, 0], scale: [1, 0.97], translateY: [0, -4],
        duration: 120, easing: 'easeInCubic',
        complete: function () { menu.style.display = 'none'; }
      });
    });
  };

  /* ── 12. Progress bar smooth fill ────────────────────────── */
  window.animateProgress = function (el, toPercent, duration) {
    if (!el) return;
    duration = duration || 350;
    var from = parseFloat(el.style.width) || 0;
    if (reduced) { el.style.width = toPercent + '%'; return; }
    ready(function () {
      anime({ targets: el, width: [from + '%', toPercent + '%'],
        duration: duration, easing: 'easeOutCubic' });
    });
  };

  /* ── 13. Number counter (admin stats, metrics) ────────────── */
  window.countUp = function (el, to, duration) {
    if (!el) return;
    if (reduced) { el.textContent = to; return; }
    var from = parseFloat(el.textContent) || 0;
    duration = duration || 800;
    ready(function () {
      var obj = { v: from };
      anime({ targets: obj, v: [from, to],
        duration: duration, easing: 'easeOutCubic', round: 1,
        update: function () { el.textContent = Math.round(obj.v); }
      });
    });
  };

  /* ── 14. Skeleton shimmer trigger ────────────────────────── */
  /*
     CSS class .skeleton handles the shimmer via @keyframes.
     JS only adds/removes the class when state changes.
  */
  window.showSkeleton = function (container) {
    if (!container) return;
    container.classList.add('skeleton-active');
  };
  window.hideSkeleton = function (container) {
    if (!container) return;
    container.classList.remove('skeleton-active');
  };

  /* ── 15. Stagger reveal for path/detail panel ─────────────── */
  /*
     Called by advice.js after detail panel is injected.
     Staggers steps, risks, resources in sequence.
  */
  window.revealDetail = function (container) {
    if (!container || reduced) return;
    var groups = [
      container.querySelectorAll('.outcome'),
      container.querySelectorAll('.step'),
      container.querySelectorAll('.risk'),
      container.querySelectorAll('.resource')
    ];
    var baseDelay = 0;
    ready(function () {
      groups.forEach(function (group) {
        if (!group.length) return;
        Array.prototype.slice.call(group).forEach(function (el, i) {
          el.style.opacity = '0';
          el.style.transform = 'translateY(10px)';
          anime({ targets: el, opacity: [0, 1], translateY: [10, 0],
            duration: 220, delay: baseDelay + i * 30, easing: 'easeOutCubic' });
        });
        baseDelay += group.length * 30 + 20;
      });
    });
  };


  /* ── 16. Onboarding question transitions ─────────────────── */
  /*
     Between questions: current screen fades out + moves up 8px,
     next screen fades in from 8px below. 220ms each.
     Called by onboarding render() before/after DOM swap.
  */
  window.transitionOut = function (el, cb) {
    if (!el) { if (cb) cb(); return; }
    if (reduced) { el.style.display = 'none'; if (cb) cb(); return; }
    ready(function () {
      anime({ targets: el, opacity: [1, 0], translateY: [0, -8],
        duration: 160, easing: 'easeInCubic',
        complete: function () {
          el.style.opacity = '0';
          el.style.transform = '';
          if (cb) cb();
        }
      });
    });
  };

  window.transitionIn = function (el) {
    if (!el) return;
    if (reduced) { el.style.opacity = '1'; return; }
    el.style.opacity = '0';
    el.style.transform = 'translateY(8px)';
    ready(function () {
      anime({ targets: el, opacity: [0, 1], translateY: [8, 0],
        duration: 220, easing: 'easeOutCubic' });
    });
  };

  /* ── 17. Chat bubble entrance ────────────────────────────── */
  /*
     New bubbles slide up 6px + fade. 180ms.
     User bubbles from right, assistant from left (translateX).
  */
  window.animateBubble = function (bubble) {
    if (!bubble || reduced) return;
    var isUser = bubble.classList.contains('user');
    var tx = isUser ? 6 : -6;
    bubble.style.opacity = '0';
    bubble.style.transform = 'translateY(6px) translateX(' + tx + 'px)';
    ready(function () {
      anime({ targets: bubble, opacity: [0, 1], translateY: [6, 0],
        translateX: [tx, 0], duration: 200, easing: 'easeOutCubic' });
    });
  };

  /* ── 18. Tab indicator slide ─────────────────────────────── */
  /*
     The active tab underline slides horizontally to the new tab.
     CSS transition handles the visual; this positions the indicator.
  */
  window.updateTabIndicator = function (indicator, activeTab) {
    if (!indicator || !activeTab) return;
    var left = activeTab.offsetLeft;
    var width = activeTab.offsetWidth;
    if (reduced) {
      indicator.style.left = left + 'px';
      indicator.style.width = width + 'px';
      return;
    }
    ready(function () {
      anime({ targets: indicator, left: [indicator.offsetLeft, left],
        width: [indicator.offsetWidth, width], duration: 200, easing: 'easeOutCubic' });
    });
  };

  /* ── 19. Payment success check reveal ───────────────────── */
  /*
     Circle pops in: scale 0→1 with a spring-like feel.
     Runs once on payment_success.html load.
  */
  window.animateCheck = function (el) {
    if (!el || reduced) return;
    el.style.transform = 'scale(0)';
    el.style.opacity = '0';
    ready(function () {
      anime({ targets: el, scale: [0, 1], opacity: [0, 1],
        duration: 400, easing: 'spring(1, 80, 12, 0)' });
    });
  };

  /* ── 20. Advice overlay (loading state) ──────────────────── */
  /*
     When generating suggestions: overlay fades + blurs in.
     Spinner text has a soft pulse.
  */
  window.showAdviceOverlay = function (overlay) {
    if (!overlay) return;
    overlay.style.display = 'flex';
    if (reduced) return;
    overlay.style.opacity = '0';
    overlay.style.backdropFilter = 'blur(0px)';
    ready(function () {
      anime({ targets: overlay, opacity: [0, 1], duration: 250, easing: 'easeOutCubic' });
    });
  };
  window.hideAdviceOverlay = function (overlay) {
    if (!overlay) return;
    if (reduced) { overlay.style.display = 'none'; return; }
    ready(function () {
      anime({ targets: overlay, opacity: [1, 0], duration: 200, easing: 'easeInCubic',
        complete: function () { overlay.style.display = 'none'; }
      });
    });
  };


  /* ── 21. Course card filter animation ───────────────────── */
  /*
     When search filters cards, hidden cards fade out first,
     visible cards then fade back in with a brief stagger.
  */
  window.animateCardFilter = function (grid) {
    if (!grid || reduced) return;
    var visible = Array.prototype.slice.call(grid.querySelectorAll('.course-card:not(.hidden)'));
    if (!visible.length) return;
    visible.forEach(function (el) { el.style.opacity = '0'; el.style.transform = 'translateY(8px)'; });
    ready(function () {
      anime({ targets: visible, opacity: [0, 1], translateY: [8, 0],
        duration: 220, delay: anime.stagger(20, { easing: 'easeOutQuad' }),
        easing: 'easeOutCubic' });
    });
  };

  /* ── 22. Autocomplete dropdown (tag search) ──────────────── */
  window.openAutocomplete = function (el) {
    if (!el || reduced) return;
    el.classList.add('open');
    ready(function () {
      anime({ targets: el, opacity: [0, 1], translateY: [-4, 0], scale: [0.98, 1],
        duration: 150, easing: 'easeOutCubic' });
    });
  };
  window.closeAutocomplete = function (el) {
    if (!el) return;
    el.classList.remove('open');
    if (!reduced) {
      ready(function () {
        anime({ targets: el, opacity: [1, 0], translateY: [0, -4],
          duration: 100, easing: 'easeInCubic' });
      });
    }
  };

  /* ── 23. Plan section reveal (plan_extend.html) ──────────── */
  /*
     When renderPlan() injects content, stagger all major sections
     in sequence: overview → highlight → phases → skills → links.
  */
  window.revealPlan = function (contentEl) {
    if (!contentEl || reduced) return;
    var sections = contentEl.querySelectorAll(
      '.section-title, .highlight, .phase, .pill-row, .resource, .risk, p, h3'
    );
    ready(function () {
      var nodes = Array.prototype.slice.call(sections);
      nodes.forEach(function (el) { el.style.opacity = '0'; el.style.transform = 'translateY(12px)'; });
      anime({ targets: nodes, opacity: [0, 1], translateY: [12, 0],
        duration: 260, delay: anime.stagger(18, { easing: 'easeOutQuad' }),
        easing: 'easeOutCubic' });
    });
  };

  /* ── 24. Initialisation on DOMContentLoaded ──────────────── */
  function init() {
    ready(function () {
      pageEntrance();
      initScrollReveal();

      /* Animate elements already visible on load */
      var onLoad = Array.prototype.slice.call(document.querySelectorAll(REVEAL_SEL))
        .filter(function (el) { return !el.dataset._animDone && el.offsetParent !== null; })
        .filter(function (el) { return !isGsapOwned(el); });
      if (onLoad.length) {
        onLoad.forEach(function (el) {
          el.style.opacity = '0';
          el.style.transform = 'translateY(16px)';
        });
        anime({ targets: onLoad, opacity: [0, 1], translateY: [16, 0],
          duration: 280, delay: anime.stagger(35, { easing: 'easeOutQuad' }),
          easing: 'easeOutCubic',
          complete: function () {
            onLoad.forEach(function (el) { el.dataset._animDone = '1'; });
          }
        });
      }

      /* Progress bars declared with data-width */
      Array.prototype.slice.call(document.querySelectorAll('[data-anim-progress]')).forEach(function (el) {
        var w = el.getAttribute('data-width') || '0%';
        el.style.width = '0%';
        anime({ targets: el, width: w, duration: 500, easing: 'easeOutCubic' });
      });

      /* Admin stat counters */
      Array.prototype.slice.call(document.querySelectorAll('[data-count-to]')).forEach(function (el) {
        var to = parseFloat(el.getAttribute('data-count-to')) || 0;
        window.countUp(el, to, 900);
      });

      /* Payment success check */
      var checkEl = document.querySelector('.check, .success-icon');
      if (checkEl) window.animateCheck(checkEl);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
