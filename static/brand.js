/* ============================================================
   UPWARD — Motion layer
   GSAP ScrollTrigger reveals. Falls back silently if CDNs
   are unreachable.
   ============================================================ */

(function(){
    'use strict';

    var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce){ return; }

    function initGsap(){
        if (typeof gsap === 'undefined'){ setTimeout(initGsap, 60); return; }
        if (typeof ScrollTrigger !== 'undefined'){ gsap.registerPlugin(ScrollTrigger); }

        /* Single elements: fade + rise */
        gsap.utils.toArray('[data-reveal]').forEach(function(el){
            gsap.fromTo(el,
                {opacity: 0, y: 60},
                {
                    opacity: 1,
                    y: 0,
                    duration: 1.1,
                    ease: 'power3.out',
                    delay: parseFloat(el.getAttribute('data-delay') || 0),
                    scrollTrigger: { trigger: el, start: 'top 86%' }
                }
            );
        });

        /* Groups: children stagger in one after another */
        gsap.utils.toArray('[data-reveal-stagger]').forEach(function(grp){
            var items = Array.prototype.filter.call(grp.children, function(c){
                return c.nodeType === 1 && !c.hasAttribute('data-reveal');
            });
            if (!items.length){ return; }
            gsap.fromTo(items,
                {opacity: 0, y: 70},
                {
                    opacity: 1,
                    y: 0,
                    duration: 1,
                    ease: 'power3.out',
                    stagger: parseFloat(grp.getAttribute('data-stagger') || 0.14),
                    scrollTrigger: { trigger: grp, start: 'top 85%' }
                }
            );
        });

        /* Masked line reveals for oversized headlines */
        gsap.utils.toArray('[data-reveal-lines]').forEach(function(el){
            var lines = el.querySelectorAll('span');
            if (!lines.length){ return; }
            gsap.fromTo(lines,
                {yPercent: 115},
                {
                    yPercent: 0,
                    duration: 1.3,
                    ease: 'power4.out',
                    stagger: 0.12,
                    scrollTrigger: { trigger: el, start: 'top 88%' }
                }
            );
        });

        /* Subtle parallax drift */
        gsap.utils.toArray('[data-parallax]').forEach(function(el){
            var speed = parseFloat(el.getAttribute('data-parallax') || 0.15);
            gsap.to(el, {
                yPercent: speed * 100,
                ease: 'none',
                scrollTrigger: { trigger: el, start: 'top bottom', end: 'bottom top', scrub: true }
            });
        });
    }
    initGsap();
})();
