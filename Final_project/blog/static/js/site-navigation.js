(() => {
  const header = document.getElementById('site-nav');
  const mobile = document.getElementById('mobile-menu');
  const mobileButton = document.getElementById('mobile-menu-button');
  if (mobile?.classList.contains('hidden')) { mobile.classList.remove('hidden'); mobile.hidden = true; }
  const account = document.getElementById('account-menu');
  const accountButton = document.getElementById('account-button');
  function setOpen(button, panel, open) {
    if (!button || !panel) return;
    panel.hidden = !open;
    button.setAttribute('aria-expanded', String(open));
  }
  mobileButton?.addEventListener('click', () => setOpen(mobileButton, mobile, mobile.hidden));
  accountButton?.addEventListener('click', () => setOpen(accountButton, account, account.hidden));
  document.addEventListener('click', event => {
    if (!event.target.closest('header, #mobile-menu')) {
      setOpen(mobileButton, mobile, false);
      setOpen(accountButton, account, false);
    }
  });
  mobile?.querySelectorAll('a').forEach(link => link.addEventListener('click', () => setOpen(mobileButton, mobile, false)));
  const updateHeader = () => header?.classList.toggle('scrolled', scrollY > 50);
  addEventListener('scroll', updateHeader, { passive: true });
  updateHeader();

  const modal = document.getElementById('check-in-modal');
  const form = document.getElementById('daily-check-in-form');
  const message = document.getElementById('check-in-message');
  let previousFocus;
  const toggleModal = open => {
    if (!modal) return;
    if (open) previousFocus = document.activeElement;
    modal.classList.toggle('hidden', !open);
    if (open) document.getElementById('close-modal')?.focus();
    else previousFocus?.focus();
  };
  document.querySelectorAll('#check-in-trigger, [data-open-checkin]').forEach(button => button.addEventListener('click', () => {
    setOpen(mobileButton, mobile, false);
    toggleModal(true);
  }));
  ['close-modal', 'cancel-modal'].forEach(id => document.getElementById(id)?.addEventListener('click', () => toggleModal(false)));
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    setOpen(mobileButton, mobile, false);
    setOpen(accountButton, account, false);
    if (modal && !modal.classList.contains('hidden')) toggleModal(false);
  });
  let sending = false;
  form?.addEventListener('submit', async event => {
    event.preventDefault();
    if (sending) return;
    sending = true;
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    message.classList.add('hidden');
    try {
      // Preserve the existing endpoint, CSRF field and success/error contract.
      const response = await fetch(form.action, {
        method: 'POST', body: new FormData(form),
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      });
      const data = await response.json();
      message.className = 'mb-4 text-sm font-medium ' + (response.ok ? 'text-green-600' : 'text-red-600');
      message.textContent = response.ok ? 'Check-in successful! You earned 10 points' : (data.error || 'Check-in failed. Please try again.');
      if (response.ok) setTimeout(() => toggleModal(false), 2000);
    } catch {
      message.className = 'mb-4 text-sm font-medium text-red-600';
      message.textContent = 'Unable to check in. Please try again.';
    } finally {
      sending = false;
      button.disabled = false;
    }
  });
})();
