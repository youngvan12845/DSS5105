/* A single HTMX panel is moved between hosts; never clone or re-render on resize. */
(() => {
    const slot = document.getElementById('article-agent-slot');
    const dock = document.getElementById('article-agent-dock');
    const drawer = document.getElementById('article-agent-mobile-drawer');
    const mobileHost = document.getElementById('article-agent-mobile-slot');
    const opener = document.getElementById('article-agent-mobile-btn');
    const closer = document.getElementById('article-agent-mobile-close');
    const backdrop = document.getElementById('article-agent-mobile-backdrop');
    const layout = document.getElementById('article-layout');
    if (!slot || !dock || !drawer || !mobileHost) return;
    const wide = matchMedia('(min-width: 1024px)');
    let mobileOpen = false, collapsed = false, loading = false, loaded = false;
    let returnFocus = null;
    const setStatus = (failed) => {
        slot.replaceChildren();
        const status = document.createElement('div');
        status.className = 'assistant-load-status';
        status.setAttribute('role', failed ? 'alert' : 'status');
        status.textContent = failed ? 'Assistant failed to load. Please retry. ' : 'Loading assistant…';
        if (failed) {
            const retry = document.createElement('button');
            retry.type = 'button'; retry.textContent = 'Retry';
            retry.addEventListener('click', load);
            status.append(retry);
        }
        slot.append(status);
    };
    function load() {
        if (loaded || loading) return;
        if (!window.htmx) { setStatus(true); return; }
        loading = true;
        setStatus(false);
        htmx.process(slot);
        htmx.trigger(slot, 'assistant:load');
    }
    const backgroundNodes = () => [document.getElementById('article-page-main'), opener];
    function sync() {
        const focus = document.activeElement;
        const messages = document.getElementById('article-chat-messages');
        const scroll = messages?.scrollTop;
        const target = wide.matches ? dock : mobileHost;
        const moving = slot.parentElement !== target;
        if (moving) target.append(slot);
        const modal = !wide.matches && mobileOpen;
        drawer.classList.toggle('hidden', !modal);
        document.body.classList.toggle('assistant-drawer-open', modal);
        backgroundNodes().forEach(node => { if (node) node.inert = modal; });
        const shell = document.getElementById('article-agent-shell');
        shell?.classList.toggle('is-collapsed', wide.matches && collapsed);
        dock.classList.toggle('is-collapsed', wide.matches && collapsed);
        layout?.classList.toggle('has-agent-collapsed', wide.matches && collapsed);
        layout?.classList.toggle('has-agent-panel', !wide.matches || !collapsed);
        opener?.setAttribute('aria-expanded', String(modal));
        opener?.setAttribute('aria-controls', drawer.id);
        if (moving && focus && slot.contains(focus) && (wide.matches || modal)) focus.focus({preventScroll: true});
        if (messages && scroll !== undefined) messages.scrollTop = scroll;
        if (wide.matches && drawer.contains(document.activeElement)) shell?.querySelector('button')?.focus();
        if (wide.matches || mobileOpen) load();
    }
    function open() {
        returnFocus = document.activeElement;
        mobileOpen = true; sync(); closer?.focus();
    }
    function close() {
        mobileOpen = false; sync();
        (returnFocus?.isConnected ? returnFocus : opener)?.focus();
    }
    window.ArticleAssistantLayout = {
        collapse() { if (wide.matches) { collapsed = true; sync(); } else close(); },
        expand() { collapsed = false; sync(); }
    };
    opener?.addEventListener('click', open);
    closer?.addEventListener('click', close);
    backdrop?.addEventListener('click', close);
    wide.addEventListener('change', sync);
    drawer.addEventListener('keydown', event => {
        if (wide.matches || !mobileOpen) return;
        if (event.key === 'Escape') { event.preventDefault(); close(); return; }
        if (event.key !== 'Tab') return;
        const items = [...drawer.querySelectorAll('button:not(:disabled),a[href],textarea:not(:disabled),input:not(:disabled),select,summary,[tabindex="0"]')]
            .filter(node => node.getClientRects().length && node.tabIndex >= 0);
        const first = items[0], last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    });
    // An expired login must not insert a whole login page as an assistant panel.
    slot.addEventListener('htmx:beforeSwap', event => {
        if (event.detail.target !== slot) return;
        const html = event.detail.xhr?.responseText || '';
        if (event.detail.isError || !html.includes('id="article-agent-shell"')) {
            event.detail.shouldSwap = false;
            loading = false; setStatus(true);
        }
    });
    slot.addEventListener('htmx:afterSwap', event => {
        if (event.detail.target !== slot) return;
        loaded = !!slot.querySelector('#article-agent-shell');
        loading = false; sync();
    });
    for (const name of ['htmx:sendError', 'htmx:timeout', 'htmx:responseError']) {
        slot.addEventListener(name, event => {
            if (event.detail.elt !== slot) return;
            loading = false; setStatus(true);
        });
    }
    sync();
})();
