(() => {
  const dialog = document.getElementById('day-reservations-dialog');
  if (!dialog) return;
  const content = dialog.querySelector('[data-day-reservations-content]');
  let controller;
  document.querySelectorAll('[data-day-reservations-url]').forEach(button => {
    button.addEventListener('click', async () => {
      controller?.abort();
      controller = new AbortController();
      content.textContent = 'Cargando reservas…';
      dialog.showModal();
      try {
        const response = await fetch(button.dataset.dayReservationsUrl, {signal: controller.signal});
        if (response.redirected) { window.location.assign(response.url); return; }
        if (!response.ok) throw new Error();
        content.innerHTML = await response.text();
      } catch (failure) {
        if (failure.name !== 'AbortError') content.textContent = 'No se pudieron cargar las reservas. Cierre el cuadro e inténtelo nuevamente.';
      }
    });
  });
  dialog.querySelector('[data-close-day-reservations]').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => controller?.abort());
})();
