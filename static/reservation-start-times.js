(() => {
  const clock = document.querySelector('[data-start-times-url]');
  if (!clock) return;
  const form = clock.closest('form');
  const day = form.querySelector('[name=fecha]');
  let controller;
  async function refresh() {
    controller?.abort();
    controller = new AbortController();
    const request = controller;
    const selected = clock.value;
    clock.disabled = true;
    try {
      if (!day.value) { clock.replaceChildren(new Option('Seleccione primero una fecha', '')); return; }
      const url = new URL(clock.dataset.startTimesUrl, location.origin);
      url.searchParams.set('fecha', day.value);
      const response = await fetch(url, {signal: request.signal});
      if (!response.ok) throw new Error();
      const data = await response.json();
      clock.replaceChildren(new Option(data.times.length ? 'Seleccione hora de inicio' : 'Sin horarios disponibles', ''));
      data.times.forEach(value => clock.add(new Option(value, value)));
      if (data.times.includes(selected)) clock.value = selected;
    } catch (error) {
      if (error.name !== 'AbortError') clock.replaceChildren(new Option('No se pudieron actualizar las horas. Reintente cambiando la fecha.', ''));
    } finally {
      if (controller === request) clock.disabled = false;
    }
  }
  day.addEventListener('change', refresh);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  setInterval(refresh, 60000);
  refresh();
})();
