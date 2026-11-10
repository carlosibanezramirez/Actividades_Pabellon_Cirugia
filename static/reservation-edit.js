(() => {
  const dialog = document.getElementById('reservation-edit-dialog');
  if (!dialog) return;
  const content = dialog.querySelector('[data-reservation-edit-content]');
  let controller;
  function error(message) {
    content.replaceChildren();
    const text = document.createElement('p');
    text.className = 'message error';
    text.setAttribute('role', 'alert');
    text.textContent = message;
    content.append(text);
  }
  async function load(url) {
    controller?.abort();
    controller = new AbortController();
    content.textContent = 'Cargando reserva…';
    dialog.showModal();
    try {
      const response = await fetch(url, {signal: controller.signal});
      if (response.redirected) { window.location.assign(response.url); return; }
      if (!response.ok) throw new Error();
      content.innerHTML = await response.text();
      content.querySelector('input:not([type=hidden]), select')?.focus();
    } catch (failure) {
      if (failure.name !== 'AbortError') error('No se pudo abrir la reserva. Cierre el cuadro e inténtelo nuevamente.');
    }
  }
  document.querySelectorAll('[data-edit-url]').forEach(block => {
    block.addEventListener('click', () => load(block.dataset.editUrl));
  });
  dialog.addEventListener('click', event => {
    if (event.target.closest('[data-close-reservation-edit]')) dialog.close();
  });
  dialog.addEventListener('close', () => controller?.abort());
  dialog.addEventListener('submit', async event => {
    const form = event.target.closest('[data-reservation-edit-form]');
    if (!form) return;
    event.preventDefault();
    const button = form.querySelector('[type=submit]');
    button.disabled = true;
    controller = new AbortController();
    try {
      const response = await fetch(form.action, {method: 'POST', body: new FormData(form), signal: controller.signal});
      if (response.redirected) { window.location.assign(response.url); return; }
      if (response.ok && response.headers.get('content-type')?.includes('application/json')) {
        const data = await response.json();
        window.location.assign(data.redirect_url);
      } else if (response.status === 422) {
        content.innerHTML = await response.text();
        content.querySelector('.errorlist')?.setAttribute('role', 'alert');
        content.querySelector('input:not([type=hidden]), select')?.focus();
      } else {
        error('No se pudo confirmar el cambio. Cierre el cuadro y consulte la agenda antes de intentarlo nuevamente.');
      }
    } catch (failure) {
      if (failure.name !== 'AbortError') error('No se pudo confirmar el cambio. Consulte la agenda para comprobar el estado de la reserva.');
    } finally {
      button.disabled = false;
    }
  });
})();
