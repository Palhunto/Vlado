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
  function travar(travado) { $('ia-salvar').disabled = travado; $('ia-remover').disabled = travado; }
  // Onde há contas, salvar ou remover a chave pede a senha de quem faz (contrato de contas, 5.15): o pedido segue primeiro e, se o servidor responder
  // 403 senha_necessaria, o diálogo pede "Sua senha" e reenvia o mesmo pedido com ela. Os botões só ficam travados enquanto um pedido está no ar,
  // para o foco voltar a eles quando o diálogo fecha. Sem contas (modo local) o servidor não pede e o diálogo nem abre.
  async function enviar(extra, gatilho) {
    if (ocupado) return;
    ocupado = true;
    mensagem(t('Salvando…'));
    const chave = $('ia-chave').value.trim();
    const dados = {provedor: $('ia-provedor').value, modelo_preferido: $('ia-modelo').value.trim() || null, ...extra};
    if (chave && !extra.remover_chave) dados.chave = chave;
    const remover = !!extra.remover_chave;
    try {
      const resposta = await window.Dialogo.comSenha({operacao: 'ia-config-salvar', dados, pedirAntes: false, gatilho,
        enviar: async (nome, corpo) => { travar(true); try { return await api(nome, corpo); } finally { travar(false); } },
        dialogo: remover
          ? {titulo: 'Remover a chave de IA?', texto: 'A Mesa deixa de usar a chave salva. A senha confirma que é você quem muda a conexão com a IA.', acao: 'Remover chave', destrutiva: true}
          : {titulo: 'Salvar a configuração da IA?', texto: 'A senha confirma que é você quem muda a conexão com a IA.', acao: 'Salvar'}});
      if (resposta === null) { mensagem(''); return; }   // a pessoa cancelou o diálogo: nada foi enviado
      aplicar(resposta);
      $('ia-chave').value = '';
      mensagem(t(remover ? 'Chave removida.' : 'Configuração salva.'));
      document.getElementById('codex-conectar')?.click();
    } catch (error) {
      mensagem(error.message);
    } finally {
      ocupado = false;
      travar(false);
    }
  }
  form.addEventListener('submit', event => { event.preventDefault(); enviar({}, $('ia-salvar')); });
  $('ia-remover').addEventListener('click', () => enviar({remover_chave: true}, $('ia-remover')));
  $('ia-provedor').addEventListener('change', render);
  carregar();
})();
