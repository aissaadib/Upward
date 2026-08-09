/* ============================================================
   UPWARD — React Bits components (vanilla ports)
   Spotlight, CountUp, Tilt, Magnetic, ProgressRing.
   No dependencies, respects prefers-reduced-motion.
   ============================================================ */

(function(){
    'use strict';

    var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    /* ---------- SpotlightCard (event delegation, works for injected DOM) ---------- */
    if(!reduce){
        document.addEventListener('pointermove', function(e){
            var card = e.target.closest ? e.target.closest('.rb-spotlight') : null;
            if(!card) return;
            var rect = card.getBoundingClientRect();
            card.style.setProperty('--mx', ((e.clientX - rect.left) / rect.width * 100) + '%');
            card.style.setProperty('--my', ((e.clientY - rect.top) / rect.height * 100) + '%');
        });
    }

    /* ---------- CountUp ---------- */
    function animateCount(el){
        var target = parseFloat(el.getAttribute('data-count'));
        if(isNaN(target)) return;
        var dur = parseFloat(el.getAttribute('data-count-duration') || 1.4) * 1000;
        var decimals = parseInt(el.getAttribute('data-count-decimals') || '0', 10);
        var start = null;
        function tick(ts){
            if(start === null) start = ts;
            var t = Math.min((ts - start) / dur, 1);
            var eased = 1 - Math.pow(1 - t, 3);
            el.textContent = (target * eased).toFixed(decimals);
            if(t < 1) requestAnimationFrame(tick);
            else el.textContent = target.toFixed(decimals);
        }
        requestAnimationFrame(tick);
    }

    function initCount(){
        var els = document.querySelectorAll('[data-count]');
        if(!els.length) return;
        if(reduce || typeof IntersectionObserver === 'undefined'){
            els.forEach(function(el){ el.textContent = parseFloat(el.getAttribute('data-count')).toFixed(parseInt(el.getAttribute('data-count-decimals') || '0', 10)); });
            return;
        }
        var io = new IntersectionObserver(function(entries){
            entries.forEach(function(en){
                if(!en.isIntersecting) return;
                io.unobserve(en.target);
                animateCount(en.target);
            });
        }, {threshold: .5});
        els.forEach(function(el){
            if(el.dataset._rbCountDone){ return; }
            el.dataset._rbCountDone = '1';
            io.observe(el);
        });
    }

    /* ---------- TiltedCard ---------- */
    function initTilt(){
        var els = document.querySelectorAll('[data-tilt]');
        if(!els.length || reduce) return;
        els.forEach(function(el){
            var max = parseFloat(el.getAttribute('data-tilt-max') || 8);
            var scale = el.hasAttribute('data-tilt-scale') ? parseFloat(el.getAttribute('data-tilt-scale')) : 1.02;
            el.addEventListener('pointerenter', function(e){
                el.classList.add('rb-tilt-active');
            });
            el.addEventListener('pointermove', function(e){
                var rect = el.getBoundingClientRect();
                var px = (e.clientX - rect.left) / rect.width - .5;
                var py = (e.clientY - rect.top) / rect.height - .5;
                el.style.transform = 'perspective(900px) rotateX(' + (-py * max * 2).toFixed(2) + 'deg) rotateY(' + (px * max * 2).toFixed(2) + 'deg) scale(' + scale + ')';
            });
            el.addEventListener('pointerleave', function(){
                el.classList.remove('rb-tilt-active');
                el.style.transform = '';
            });
        });
    }

    /* ---------- MagneticButton ---------- */
    function initMagnetic(){
        var els = document.querySelectorAll('[data-magnetic]');
        if(!els.length || reduce) return;
        els.forEach(function(el){
            var strength = parseFloat(el.getAttribute('data-magnetic') || 0.35);
            el.addEventListener('pointerenter', function(){ el.classList.add('rb-magnetic-fast'); });
            el.addEventListener('pointermove', function(e){
                var rect = el.getBoundingClientRect();
                var dx = (e.clientX - rect.left - rect.width / 2) * strength;
                var dy = (e.clientY - rect.top - rect.height / 2) * strength;
                el.style.transform = 'translate(' + dx.toFixed(2) + 'px,' + dy.toFixed(2) + 'px)';
            });
            el.addEventListener('pointerleave', function(){
                el.classList.remove('rb-magnetic-fast');
                el.style.transform = '';
            });
        });
    }

    /* ---------- ProgressRing ---------- */
    function initRings(){
        var rings = document.querySelectorAll('[data-ring]');
        if(!rings.length) return;
        rings.forEach(function(ring){
            var pct = parseFloat(ring.getAttribute('data-ring'));
            if(isNaN(pct)) return;
            pct = Math.max(0, Math.min(100, pct));
            var radius = parseFloat(ring.getAttribute('data-ring-r') || 15.9155);
            var circ = 2 * Math.PI * radius;
            ring.style.setProperty('--circ', circ.toFixed(2));
            var fg = ring.querySelector('.rb-ring-fg');
            var center = ring.querySelector('.rb-ring-center');
            if(center && center.textContent === ''){
                center.textContent = Math.round(pct) + '%';
            }
            if(reduce){
                ring.style.setProperty('--rp', (pct / 100).toFixed(4));
                ring.classList.add('rb-ring-in');
                return;
            }
            var io = new IntersectionObserver(function(entries){
                entries.forEach(function(en){
                    if(!en.isIntersecting) return;
                    io.unobserve(en.target);
                    ring.style.setProperty('--rp', (pct / 100).toFixed(4));
                    ring.classList.add('rb-ring-in');
                });
            }, {threshold: .4});
            io.observe(ring);
        });
    }

    /* ---------- Public refresh (re-scan injected DOM) ---------- */
    window.RB = {
        refresh: function(){
            initCount();
            initTilt();
            initMagnetic();
            initRings();
        }
    };

    if(document.readyState === 'loading'){
        document.addEventListener('DOMContentLoaded', RB.refresh);
    }else{
        RB.refresh();
    }
})();