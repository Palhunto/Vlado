'use strict';
// Provider and API key panel. The key is write-only: the server only returns
// whether a key exists and its last four characters.
(() => {
  const form = document.getElementById('ia-config');
  if (!form) return;
  const t = (texto, vars) => (window.I18N ? window.I18N.t(texto, vars) : texto);
  let estado = null, ocupado = false;

  function mensagem(texto = '') { $('ia-config-mensagem').textContent = texto; }
  function render() {
    if (!estado) return;
    const provedor = $('ia-provedor').value;
    $('ia-modelo').placeholder = `Padrão: ${estado.modelos_padrao[provedor]}`;
    const chave = estado.chaves[provedor] || {};
    $('ia-chave-estado').textContent = !chave.configurada ? 'Nenhuma chave configurada.'
      : chave.origem === 'ambiente' ? `Chave do ambiente do servidor · termina em ${chave.final}`
      : `Chave salva · termina em ${chave.final}`;
    $('ia-remover').hidden = !(chave.configurada && chave.origem === 'salva');
  }
  function aplicar(dados) {
    estado = dados;
    $('ia-provedor').value = dados.provedor;
    $('ia-modelo').value = dados.modelo_preferido || '';
    render();
  }
  async function carregar() {
    try {
      aplicar(await api('ia-config', {}));
    } catch (error) {
      form.hidden = error.result && error.result.estado === 'proibido';
      mensagem(error.message);
    }
  }
  async function enviar(extra) {
    if (ocupado) return;
    ocupado = true;
    $('ia-salvar').disabled = true; $('ia-remover').disabled = true;
    mensagem(t('Salvando…'));
    const chave = $('ia-chave').value.trim();
    const dados = {provedor: $('ia-provedor').value, modelo_preferido: $('ia-modelo').value.trim() || null, ...extra};
    if (chave && !extra.remover_chave) dados.chave = chave;
    try {
      aplicar(await api('ia-config-salvar', dados));
      $('ia-chave').value = '';
      mensagem(t(extra.remover_chave ? 'Chave removida.' : 'Configuração salva.'));
      document.getElementById('codex-conectar')?.click();
    } catch (error) {
      mensagem(error.message);
    } finally {
      ocupado = false;
      $('ia-salvar').disabled = false; $('ia-remover').disabled = false;
    }
  }
  form.addEventListener('submit', event => { event.preventDefault(); enviar({}); });
  $('ia-remover').addEventListener('click', () => enviar({remover_chave: true}));
  $('ia-provedor').addEventListener('change', render);
  carregar();
})();
