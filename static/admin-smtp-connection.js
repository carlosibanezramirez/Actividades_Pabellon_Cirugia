(() => {
  function init() {
    const port = document.getElementById('id_port');
    const mode = document.getElementById('id_connection_type');
    if (!port || !mode) return;
    const summary = document.createElement('p');
    summary.className = 'help';
    summary.id = 'smtp-connection-summary';
    summary.setAttribute('role', 'status');
    mode.insertAdjacentElement('afterend', summary);
    const labels = {starttls: 'STARTTLS', tls: 'TLS / SSL implícito', plain: 'Sin SSL/TLS'};
    const byPort = {'587': 'starttls', '465': 'tls', '25': 'plain'};
    function update() {
      const resolved = mode.value === 'auto' ? byPort[port.value] : mode.value;
      summary.textContent = resolved ? `Puerto ${port.value}: ${labels[resolved]}.` :
        'Puerto no estándar: seleccione el tipo de conexión indicado por su proveedor.';
    }
    port.addEventListener('input', () => { mode.value = 'auto'; update(); });
    port.addEventListener('change', update);
    mode.addEventListener('change', update);
    update();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
