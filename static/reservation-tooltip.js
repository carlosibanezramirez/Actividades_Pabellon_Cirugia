(() => {
  const blocks = document.querySelectorAll('[data-booking-tooltip]');
  if (!blocks.length) return;
  const popup = document.createElement('div');
  popup.className = 'reservation-tooltip';
  popup.id = 'reservation-tooltip';
  popup.setAttribute('role', 'tooltip');
  popup.hidden = true;
  document.body.appendChild(popup);
  let active = null;
  function hide() {
    if (active) active.removeAttribute('aria-describedby');
    active = null;
    popup.hidden = true;
  }
  function position() {
    if (!active) return;
    const rect = active.getBoundingClientRect();
    const box = popup.getBoundingClientRect();
    const left = Math.max(10, Math.min(rect.left, window.innerWidth - box.width - 10));
    let top = rect.bottom + 8;
    if (top + box.height > window.innerHeight - 10) top = rect.top - box.height - 8;
    popup.style.left = `${left}px`;
    popup.style.top = `${Math.max(10, top)}px`;
  }
  function show(block) {
    hide();
    active = block;
    popup.replaceChildren();
    const rows = [['Etapa', block.dataset.phase],
      ['Tipo de cirugía', block.dataset.surgery], ['Médico', block.dataset.doctor],
      ['Horario Tramo', block.dataset.phaseHours], ['Horario Reserva', block.dataset.hours],
      ['Duración Reserva', `${block.dataset.duration} minutos`],
      ['Tiempo Total', `${block.dataset.totalDuration} minutos`],
      ['Paciente', block.dataset.patient], ['RUT', block.dataset.rut]];
    rows.forEach(([label, value]) => {
      const row = document.createElement('p');
      const title = document.createElement('strong');
      title.textContent = `${label}: `;
      row.append(title, document.createTextNode(value || 'No registrado'));
      popup.appendChild(row);
    });
    popup.hidden = false;
    block.setAttribute('aria-describedby', popup.id);
    position();
  }
  blocks.forEach(block => {
    block.addEventListener('mouseenter', () => show(block));
    block.addEventListener('mouseleave', () => {
      if (document.activeElement !== block) hide();
    });
    block.addEventListener('focus', () => show(block));
    block.addEventListener('blur', hide);
    block.addEventListener('click', () => block.dataset.editUrl ? hide() : show(block));
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') hide(); });
  document.addEventListener('pointerdown', event => {
    if (!event.target.closest('[data-booking-tooltip]')) hide();
  });
  window.addEventListener('resize', hide);
  document.addEventListener('scroll', position, true);
})();
