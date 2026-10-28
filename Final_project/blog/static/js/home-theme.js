(() => {
  const sections = document.querySelectorAll('.home-theme main > .screen');
  const dots = document.querySelectorAll('.section-dots a');
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => entries.forEach(entry => {
      if (entry.isIntersecting) dots.forEach(dot => dot.classList.toggle('active', dot.hash === '#' + entry.target.id));
    }), { rootMargin: '-35% 0px -35% 0px' });
    sections.forEach(section => observer.observe(section));
  }
  const video = document.querySelector('.hero-video');
  if (!video) return;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const applyMotion = () => reduced.matches ? video.pause() : video.play().catch(() => {});
  reduced.addEventListener('change', applyMotion);
  applyMotion();
})();
