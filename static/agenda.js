(() => {
  const form = document.querySelector('#reservation-form');
  if (!form) return;
  const boxes = Array.from(form.querySelectorAll('input[name="slots"]'));
  const summary = document.querySelector('#selection-summary');
  const selected = () => boxes.filter(box => box.checked && !box.disabled);
  function update() {
    const picks = selected().sort((a, b) => Number(a.dataset.index) - Number(b.dataset.index));
    boxes.forEach(box => box.setCustomValidity(''));
    if (!picks.length) {
      summary.textContent = 'Selecciona una o más horas consecutivas en las tarjetas de un pabellón.';
      return;
    }
    const sameRoom = picks.every(box => box.dataset.room === picks[0].dataset.room);
    const contiguous = picks.every((box, i) => Number(box.dataset.index) === Number(picks[0].dataset.index) + i);
    if (!sameRoom || !contiguous) {
      summary.textContent = 'Selecciona únicamente horas consecutivas de un mismo pabellón.';
      picks[0].setCustomValidity('Las horas deben ser consecutivas y del mismo pabellón.');
      return;
    }
    const first = picks[0].dataset.label.split(' – ')[0];
    const last = picks[picks.length - 1].dataset.label.split(' – ')[1];
    summary.textContent = `${picks[0].dataset.roomName}: ${first} – ${last} · ${picks.length} hora(s), incluida la preparación.`;
  }
  boxes.forEach(box => box.addEventListener('change', () => {
    if (box.checked) boxes.forEach(other => {
      if (other.dataset.room !== box.dataset.room) other.checked = false;
    });
    update();
  }));
  form.addEventListener('submit', event => {
    update();
    if (!selected().length) {
      event.preventDefault();
      summary.textContent = 'Debes seleccionar al menos una hora disponible.';
      summary.scrollIntoView({block: 'center'});
    } else if (!form.reportValidity()) event.preventDefault();
  });
  update();
})();
