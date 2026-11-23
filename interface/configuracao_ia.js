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
  // Em Perguntar > Conexão e opções fica só a linha que diz o que está em uso (o formulário mora em Configurações): provedor e modelo, ou o modelo padrão.
  function resumir() {
    const rotulo = $('ia-resumo');
    if (!rotulo || !estado) return;
    const provedor = $('ia-provedor').selectedOptions?.[0]?.textContent || $('ia-provedor').value;
    rotulo.textContent = `IA: ${provedor}, ${estado.modelo_preferido ? `modelo ${estado.modelo_preferido}` : 'modelo padrão'}.`;
  }
  function aplicar(dados) {
    estado = dados;
    $('ia-provedor').value = dados.provedor;
    $('ia-modelo').value = dados.modelo_preferido || '';
    render();
    resumir();
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
  // Onde há contas, salvar ou remover a chave pede a senha de quem faz (contrato de contas, 5.15): o diálogo abre antes e o pedido vai uma vez, com a senha.
  // Os botões só ficam travados enquanto um pedido está no ar, para o foco voltar a eles quando o diálogo fecha. Sem contas (modo local) o diálogo nem abre.
  // Onde há contas (tudo menos o modo local sem login) o servidor pede a senha: a Mesa a pede ANTES de enviar, para a chave viajar uma vez só, e não
  // primeiro sem senha, para ser recusada, e de novo com ela.
  const comContas = () => document.body.dataset.modo !== 'local';
  async function enviar(extra, gatilho) {
    if (ocupado) return;
    ocupado = true;
    mensagem(t('Salvando…'));
    const chave = $('ia-chave').value.trim();
    const dados = {provedor: $('ia-provedor').value, modelo_preferido: $('ia-modelo').value.trim() || null, ...extra};
    if (chave && !extra.remover_chave) dados.chave = chave;
    const remover = !!extra.remover_chave;
    try {
      const resposta = await window.Dialogo.comSenha({operacao: 'ia-config-salvar', dados, pedirAntes: comContas(), gatilho,
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
