(() => {
  const monitors = Array.from(document.querySelectorAll('[data-preparation-room]'));
  if (!monitors.length) return;
  const endpoint = document.currentScript.dataset.statusUrl;
  let serverTime = Date.parse(monitors[0].dataset.serverNow);
  let sampleTime = performance.now();
  const now = () => serverTime + performance.now() - sampleTime;
  function render() {
    monitors.forEach(element => {
      const start = Date.parse(element.dataset.startedAt);
      element.hidden = !Number.isFinite(start);
      if (element.hidden) return;
      const elapsed = Math.max(0, (now() - start) / 1000);
      const maximum = Number(element.dataset.maximum);
      const exceeded = elapsed > maximum * 60;
      element.classList.toggle('is-exceeded', exceeded);
      const title = exceeded ? '⚠ Tiempo máximo de preparación excedido' : 'Preparación en curso';
      const node = element.querySelector('.preparation-alarm-title');
      if (node.textContent !== title) node.textContent = title;
      const seconds = Math.floor(elapsed);
      const parts = [Math.floor(seconds / 3600), Math.floor(seconds % 3600 / 60), seconds % 60];
      element.querySelector('.preparation-clock').textContent = parts.map(value => String(value).padStart(2, '0')).join(':');
      element.querySelector('.preparation-maximum').textContent = maximum;
    });
  }
  let updating = false;
  async function refresh() {
    if (updating || document.hidden) return;
    updating = true;
    try {
      const response = await fetch(endpoint, {credentials: 'same-origin', cache: 'no-store'});
      if (!response.ok || response.redirected || !response.headers.get('content-type')?.includes('application/json')) throw Error('Estado no disponible');
      const body = await response.json();
      serverTime = Date.parse(body.now); sampleTime = performance.now();
      let phaseChanged = false;
      monitors.forEach(element => {
        const match = body.active.find(item => String(item.room_id) === element.dataset.preparationRoom &&
          (!element.dataset.preparationIntervention || String(item.intervention_id) === element.dataset.preparationIntervention));
        if (Boolean(element.dataset.startedAt) !== Boolean(match) ||
            (match && String(match.intervention_id) !== element.dataset.renderedIntervention)) phaseChanged = true;
        element.dataset.startedAt = match ? match.started_at : '';
        element.dataset.maximum = body.maximum_minutes;
        element.querySelector('.preparation-stale').hidden = true;
      });
      if (phaseChanged) { window.location.reload(); return; }
      render();
    } catch (_) {
      monitors.forEach(element => { element.querySelector('.preparation-stale').hidden = false; });
    } finally { updating = false; }
  }
  render(); refresh();
  setInterval(render, 1000);
  setInterval(refresh, 15000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
})();
