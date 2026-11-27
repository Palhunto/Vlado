'use strict';
// Formulários de criar e editar dos quadros (componentes.md#formularios-quadros; interface/formularios.js), com dados sintéticos (Vila Serena,
// Construtora Alfa, Marta Reis) e o servidor simulado: cada salvamento é registrado com o corpo que o servidor receberia.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento, PILHA} = require('./dom_minimo.cjs');

const ALFA = 'P' + 'a'.repeat(32), MARTA = 'P' + 'b'.repeat(32);
const referencia = n => ({tipo: 'ia', caso_id: 'alpha', rodada: 'R002', revisao: 'r3_sintese', registros_sha256: '7'.repeat(64), evidencia_id: `E00${n}`});
const IA = (extra = {}) => ({rodada: 'R002', revisao: 'r3_sintese', registros_sha256: '7'.repeat(64), achado_id: 'A002', versao: 1, papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', destino: 'incluido', ...extra});
const RESULTADO = {origem: 'ia', tipo_fonte: 'achado_ia', texto: 'Marta Reis é sócia-administradora da Construtora Alfa.', trecho: 'Marta Reis, sócia-administradora…',
  documento: {documento_id: 'D002', nome: 'contrato_social_alfa.pdf'}, localizador: {legivel: 'D002 · página PDF 1 · linhas 12–14', pagina_pdf: 1},
  achado: {id: 'A002', versao: 1, destino: 'incluido'}, revisao_ia: IA(), conferencia_humana: null, estado: 'conferida',
  vinculo_sugerido: {referencia: referencia(3), papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', justificativa: 'O contrato social lista Marta Reis.'}, ja_ligado: false};
const TIPOS = {assinatura: 'Data de assinatura', fato: 'Data do fato (ocorrência)'};
const vinculoSalvo = (extra = {}) => ({referencia: referencia(3), papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', justificativa: 'Já ligada.', documento_id: 'D002', estado: 'conferida',
  evidencia: {documento: {documento_id: 'D002', nome: 'contrato_social_alfa.pdf'}, trecho: 'Marta Reis, sócia-administradora…', localizador: {legivel: 'D002 · p. 1', pagina_pdf: 1}}, localizador: {legivel: 'D002 · p. 1'},
  revisao_ia: IA(), preenchimento_ia: {papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', destino: 'incluido'}, alteracoes: {}, conferencia_humana: null, ...extra});
const HIP = id => ({id, enunciado: 'A dispensa seguiu o rito legal.', situacao: 'em_aberto', condicao: 'pendencia', natureza: null, situacao_sem_base: false, sustentam: [], contrariam: [], faltam: [], contexto: [], indisponiveis: []});

function montar({permissao = true, sugestoes = [], detalhe = {}, busca = [RESULTADO], entradas = []} = {}) {
  const salvos = [];
  const m = criarMesa({scripts: [...PILHA, 'quadros.js', 'sugestoes.js', 'formularios.js', 'analise.js', 'indicador_salvamento.js'], desktop: true,
    api: (operacao, dados) => {
      if (operacao === 'hipoteses-quadro') return {caso: 'alpha', total: 1, divergentes: [], aviso: '', hipoteses: [HIP('H' + '1'.repeat(32))]};
      if (operacao === 'linha-tempo-listar') return {caso: 'alpha', total: 0, divergencias: [], fontes_indisponiveis: [], divergentes: [], tipos_data: TIPOS, aviso: '', entradas};
      if (operacao === 'mapa-ver') return {caso: 'alpha', aviso: '', homonimos: [], relacoes: [], entidades: [
        {id: ALFA, nome: 'Construtora Alfa Ltda.', tipo: 'organizacao', situacao: 'com_evidencia', identificadores: []}, {id: MARTA, nome: 'Marta Reis', tipo: 'pessoa', situacao: 'com_evidencia', identificadores: []}]};
      if (operacao === 'sugestoes-listar') return {caso: 'alpha', quadro: dados.quadro, contagem: {}, sugestoes: sugestoes.filter(s => s.quadro === dados.quadro)};
      if (operacao === 'evidencia-buscar') return {caso: 'alpha', analise: {rodada: 'R002', em_utc: '2026-11-26T17:32:00+00:00', pergunta: 'Quem são os sócios?'}, analises: [], total: busca.length, resultados: busca};
      if (operacao.endsWith('-detalhe')) return detalhe[operacao];
      if (/-(criar|atualizar)$|^sugestoes-corrigir$/.test(operacao)) { salvos.push({operacao, dados}); return {id: 'X', sha256: 'f'.repeat(64)}; }
      return {};
    },
    preparar: janela => {
      const original = janela.fetch;
      janela.fetch = async (rota, opcoes) => String(rota) === '/api/integracao' ? {ok: true, json: async () => ({quadros_evidencia: true})} : original(rota, opcoes);
    }});
  m.avaliar('window.contextoCaso = () => "alpha";');
  if (!permissao) m.avaliar('window.Sessao = {pode: () => false, pronta: Promise.resolve()};');
  return {...m, salvos};
}
const espera = async m => { await new Promise(r => setTimeout(r, 12)); await m.esperar(10); };
const texto = no => no.textContent.replace(/\s+/g, ' ').trim();
async function abrirAba(m, aba) { m.$('ver-quadros').click(); await espera(m); m.$(`quadros-aba-${aba}`).click(); await espera(m); }
const por = (raiz, seletor, rotulo) => [...raiz.querySelectorAll(seletor)].find(b => texto(b) === rotulo);
const digitar = (no, valor) => { no.value = valor; no.dispatchEvent(new Evento('input', {bubbles: true})); };
const clicar = async (m, no) => { no.click(); await espera(m); };
async function ligarEvidencia(m, painel) {
  await clicar(m, por(painel, 'button', '+ Ligar evidência'));
  assert.ok(painel.querySelector('.seletor-evidencia'), 'seletor aberto no lugar do formulário');
  await clicar(m, painel.querySelector('.seletor-resultado'));
  await clicar(m, por(painel, '.seletor-aberto button', 'Ligar'));
  assert.ok(painel.querySelector('.form-quadro'), 'de volta ao formulário');
}

test('nova hipótese: abre no painel, exige o enunciado, bloqueia Sustentada sem evidência e salva por hipoteses-criar', async () => {
  const m = montar(); await abrirAba(m, 'hipoteses');
  const painel = m.$('quadros-hipoteses');
  await clicar(m, por(painel, 'button', '+ Nova hipótese'));
  assert.equal(texto(painel.querySelector('.form-titulo')), 'Nova hipótese');
  const radios = [...painel.querySelectorAll('input[type=radio]')];
  assert.equal(radios.find(r => r.value === 'sustentada').disabled, true, 'Sustentada pede evidência sustentada e documental');
  assert.match(texto(painel), /Sustentada pede ao menos uma evidência de suporte sustentada e documental\./);
  assert.equal(radios.find(r => r.value === 'em_aberto').checked, true);
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.match(texto(painel.querySelector('.form-erro-geral')), /Escreva a hipótese\./);
  assert.equal(m.salvos.length, 0);
  digitar(painel.querySelector('textarea'), 'A sócia assinou como testemunha.');
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.salvos.length, 1);
  const {operacao, dados} = m.salvos[0];
  assert.equal(operacao, 'hipoteses-criar'); assert.equal(dados.caso, 'alpha');
  assert.match(dados.requisicao_id, /^[0-9a-f]{32}$/);
  assert.equal(dados.enunciado, 'A sócia assinou como testemunha.'); assert.equal(dados.situacao, 'em_aberto');
  assert.equal(JSON.stringify(dados.lacunas), '[]'); assert.equal(JSON.stringify(dados.evidencias), '[]');
  assert.ok(!painel.querySelector('.form-quadro'), 'o quadro recarregou');
  assert.deepEqual(m.erros, []);
});

test('sem permissão de criar e atualizar o quadro: nenhum botão "Nova" nem "Editar"', async () => {
  const m = montar({permissao: false}); await abrirAba(m, 'hipoteses');
  assert.equal(m.$('quadros-hipoteses').querySelector('.quadro-novo'), null);
  assert.equal(m.$('quadros-hipoteses').querySelector('.quadro-editar'), null);
});

test('seletor dentro do formulário: a evidência liga com papel, suporte e natureza da revisão da IA, e o acontecimento salva com a data e a fonte', async () => {
  const m = montar(); await abrirAba(m, 'tempo');
  const painel = m.$('quadros-tempo');
  await clicar(m, por(painel, 'button', '+ Novo acontecimento'));
  digitar(painel.querySelector('textarea'), 'Assinatura do Contrato 041/2025');
  await ligarEvidencia(m, painel);
  const cartao = painel.querySelector('.vinculo-cartao');
  assert.match(texto(cartao), /Achado da IA/);
  assert.match(texto(cartao), /Da revisão da IA: IA · sustentado declaração documental/);
  assert.match(texto(cartao), /Marta Reis, sócia-administradora…/);
  assert.ok(!/alterado por/i.test(texto(cartao)), 'nada mudado ainda');
  assert.match(texto(m.$('quadros-anuncio')), /Evidência ligada\./);
  const campos = [...painel.querySelectorAll('.form-data input[type=text]')];
  digitar(campos[0], '03/03/2025');
  assert.match(texto(painel.querySelector('.form-precisao')), /Precisão: dia/);
  const fonte = [...painel.querySelectorAll('.form-data select')].pop();
  fonte.value = '0'; fonte.dispatchEvent(new Evento('change', {bubbles: true}));
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.salvos.length, 1, texto(painel.querySelector('.form-erro-geral') || painel));
  const {operacao, dados} = m.salvos[0];
  assert.equal(operacao, 'linha-tempo-criar');
  assert.equal(dados.descricao, 'Assinatura do Contrato 041/2025');
  assert.equal(JSON.stringify(dados.datas), JSON.stringify([{tipo: 'fato', valor: '2025-03-03', aproximada: false, fonte: 0, observacao: ''}]));
  assert.equal(JSON.stringify(dados.evidencias), JSON.stringify([{referencia: referencia(3), achado_id: 'A002', papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', justificativa: 'O contrato social lista Marta Reis.'}]));
});

test('acontecimento sem evidência de suporte não sai: a mensagem do Design fica no formulário', async () => {
  const m = montar(); await abrirAba(m, 'tempo');
  const painel = m.$('quadros-tempo');
  await clicar(m, por(painel, 'button', '+ Novo acontecimento'));
  digitar(painel.querySelector('textarea'), 'Pagamento');
  digitar([...painel.querySelectorAll('.form-data input[type=text]')][0], '2025');
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.salvos.length, 0);
  assert.match(texto(painel.querySelector('.form-erro-geral')), /Falta a evidência\. Ligue ao menos um documento que registre o acontecimento\./);
});

test('o que uma pessoa muda no vínculo ganha "alterado por você" e "Voltar ao da IA" desfaz; contexto fixa o suporte e pendência tira Sustentado', async () => {
  const m = montar(); await abrirAba(m, 'tempo');
  const painel = m.$('quadros-tempo');
  await clicar(m, por(painel, 'button', '+ Novo acontecimento'));
  await ligarEvidencia(m, painel);
  const suporte = () => [...painel.querySelectorAll('.vinculo-cartao select')][0];
  suporte().value = 'parcial'; suporte().dispatchEvent(new Evento('change', {bubbles: true})); await espera(m);
  assert.match(texto(painel.querySelector('.vinculo-cartao')), /alterado por você/);
  assert.match(texto(painel.querySelector('.vinculo-cabeca')), /Alterado por você/);
  assert.match(texto(painel.querySelector('.vinculo-cartao')), /Da revisão da IA: IA · sustentado/, 'o valor da IA não some');
  await clicar(m, por(painel, '.vinculo-voltar', 'Voltar ao da IA'));
  assert.equal(suporte().value, 'sustentado');
  assert.ok(!/alterado por/i.test(texto(painel.querySelector('.vinculo-cartao'))));
  const contexto = [...painel.querySelectorAll('.vinculo-cartao .form-segmento')].find(b => b.dataset.valor === 'contexto');
  await clicar(m, contexto);
  assert.equal(suporte().disabled, true);
  assert.match(texto(painel.querySelector('.vinculo-cartao')), /Evidência de contexto não recebe suporte\./);
  assert.equal(suporte().value, 'nao_revisado');
});

test('entidade: CPF com 11 dígitos e CNPJ com 14; salva por mapa-entidade-criar com o identificador pela fonte', async () => {
  const m = montar(); await abrirAba(m, 'mapa');
  const painel = m.$('quadros-mapa');
  await clicar(m, por(painel, 'button', '+ Nova entidade'));
  const campos = () => [...painel.querySelectorAll('.form-quadro input[type=text]')];
  digitar(campos()[0], 'Carlos Prado');
  await ligarEvidencia(m, painel);
  await clicar(m, por(painel, 'button', '+ Identificador'));
  const valor = [...painel.querySelectorAll('.form-identificador input[type=text]')][0];
  digitar(valor, '123');
  const fonte = [...painel.querySelectorAll('.form-identificador select')].pop(); fonte.value = '0'; fonte.dispatchEvent(new Evento('change', {bubbles: true}));
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.match(texto(painel.querySelector('.form-identificador')), /CPF tem 11 dígitos\. Confira o número no documento\./);
  assert.equal(m.salvos.length, 0);
  digitar(valor, '123.456.789-09');
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.salvos.length, 1, texto(painel.querySelector('.form-erro-geral') || painel));
  const {operacao, dados} = m.salvos[0];
  assert.equal(operacao, 'mapa-entidade-criar');
  assert.equal(dados.nome, 'Carlos Prado'); assert.equal(dados.tipo, 'pessoa');
  assert.equal(JSON.stringify(dados.identificadores), JSON.stringify([{tipo: 'cpf', valor: '123.456.789-09', fonte: 0}]));
});

test('ligação: as duas pontas diferentes, tipo e ao menos uma evidência de suporte; salva por mapa-relacao-criar', async () => {
  const m = montar(); await abrirAba(m, 'mapa');
  const painel = m.$('quadros-mapa');
  await clicar(m, por(painel, 'button', '+ Nova ligação'));
  const selects = () => [...painel.querySelectorAll('.form-quadro > .form-campo select')];
  const escolher = (sel, v) => { sel.value = v; sel.dispatchEvent(new Evento('change', {bubbles: true})); };
  escolher(selects()[0], MARTA); escolher(selects()[1], MARTA);
  digitar(painel.querySelectorAll('.form-quadro input[type=text]')[0], 'sócia');
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.match(texto(painel), /A ligação precisa de duas entidades diferentes\. Troque uma das pontas\./);
  escolher(selects()[1], ALFA);
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.salvos.length, 0, 'sem evidência de suporte');
  assert.match(texto(painel.querySelector('.form-erro-geral')), /Falta a evidência/);
  await ligarEvidencia(m, painel);
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.salvos.length, 1);
  const {operacao, dados} = m.salvos[0];
  assert.equal(operacao, 'mapa-relacao-criar');
  assert.equal(dados.origem, MARTA); assert.equal(dados.destino, ALFA); assert.equal(dados.tipo, 'sócia');
});

test('editar uma hipótese: abre com os dados do servidor, avisa do vínculo e salva por hipoteses-atualizar com anterior_sha256', async () => {
  const id = 'H' + '1'.repeat(32), sha = 'c'.repeat(64);
  const detalhe = {'hipoteses-detalhe': {id, sha256: sha, estado: {enunciado: 'A dispensa seguiu o rito legal.', situacao: 'em_aberto', lacunas: [{descricao: 'Parecer jurídico.', diligencia_id: null}]},
    evidencias: [vinculoSalvo({alteracoes: {suporte: {anterior: 'sustentado', valor: 'parcial', por: 'Ana Lima', em_utc: '2026-11-26T19:10:00+00:00'}}, suporte: 'parcial'})]}};
  const m = montar({detalhe}); await abrirAba(m, 'hipoteses');
  const painel = m.$('quadros-hipoteses');
  await clicar(m, por(painel, '.quadro-editar', 'Editar'));
  assert.equal(texto(painel.querySelector('.form-titulo')), 'Editar hipótese');
  assert.equal(painel.querySelector('textarea').value, 'A dispensa seguiu o rito legal.');
  assert.match(texto(painel.querySelector('.vinculo-cartao')), /alterado por Ana Lima/);
  assert.match(texto(painel.querySelector('.vinculo-cartao')), /Alterado por pessoa/);
  digitar(painel.querySelector('textarea'), 'A dispensa seguiu o rito legal e foi publicada.');
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.salvos.length, 1);
  const {operacao, dados} = m.salvos[0];
  assert.equal(operacao, 'hipoteses-atualizar'); assert.equal(dados.id, id); assert.equal(dados.anterior_sha256, sha);
  assert.equal(dados.lacunas[0].descricao, 'Parecer jurídico.');
  assert.equal(dados.evidencias[0].suporte, 'parcial');
});

test('desligar ou voltar ao da IA numa revisão humana salva pede o diálogo "Apagar a revisão de …?"; sem revisão humana, não pede', async () => {
  const id = 'H' + '1'.repeat(32);
  const alt = {suporte: {anterior: 'sustentado', valor: 'parcial', por: 'Ana Lima', em_utc: '2026-11-26T19:10:00+00:00'}};
  const detalhe = {'hipoteses-detalhe': {id, sha256: 'c'.repeat(64), estado: {enunciado: 'H', situacao: 'em_aberto', lacunas: []},
    evidencias: [vinculoSalvo({alteracoes: alt, suporte: 'parcial'}), vinculoSalvo({referencia: referencia(4)})]}};
  const m = montar({detalhe}); await abrirAba(m, 'hipoteses');
  const painel = m.$('quadros-hipoteses');
  const pedidos = [];
  m.janela.Dialogo.confirmar = async opcoes => { pedidos.push(opcoes); return false; };
  await clicar(m, por(painel, '.quadro-editar', 'Editar'));
  const cartoes = () => [...painel.querySelectorAll('.vinculo-cartao')];
  await clicar(m, cartoes()[1].querySelector('.vinculo-desligar'));
  assert.equal(pedidos.length, 0, 'sem revisão humana, desligar não pede confirmação');
  assert.equal(cartoes().length, 1, 'o vínculo saiu');
  await clicar(m, cartoes()[0].querySelector('.vinculo-desligar'));
  assert.equal(pedidos.length, 1);
  assert.equal(pedidos[0].variante, 'destrutivo');
  assert.equal(pedidos[0].titulo, 'Apagar a revisão de Ana Lima?');
  assert.equal(pedidos[0].rubrica, 'Apagar revisão');
  assert.match(pedidos[0].texto, /Ana Lima mudou o suporte de “sustentado” \(da revisão da IA\) para “parcial” em \d\d\/\d\d, às \d+h\d\d\. O vínculo volta ao que a revisão da IA disse\./);
  assert.equal(pedidos[0].acao, 'Apagar a revisão');
  assert.equal(cartoes().length, 1, 'cancelou: o vínculo continua');
});

test('Corrigir uma sugestão da IA: o formulário chega preenchido, mostra a revisão da IA e salva por sugestoes-corrigir', async () => {
  const SID = 'S' + '1'.repeat(32);
  const sug = {id: SID, tipo: 'pessoa', quadro: 'mapa', campos: {tipo: 'pessoa', nome: 'Marta Reis', variantes: ['M. Reis'], identificadores: [], evidencias: [{referencia: referencia(3), papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', justificativa: 'Sócia.'}]},
    evidencias: [{referencia: referencia(3), estado: 'conferida', documento: {documento_id: 'D002', nome: 'contrato_social_alfa.pdf'}, localizador: {legivel: 'D002 · p. 1'}, trecho: 'Marta Reis, sócia…', revisao_ia: IA(), conferencia_humana: null}],
    achado: {id: 'A002', versao: 1, destino: 'incluido'}, analise: {em_utc: '2026-11-26T17:32:00+00:00', pergunta: 'Quem?'}, estado: 'aberta', decisao: null, descartada_antes: null, bloqueio: null, avisos: []};
  const m = montar({sugestoes: [sug]}); await abrirAba(m, 'mapa');
  const painel = m.$('quadros-mapa');
  await clicar(m, painel.querySelector('.mapa-no.is-sugestao .mapa-cartao'));
  await clicar(m, por(painel, '.sugestao-acoes button', 'Corrigir'));
  assert.equal(texto(painel.querySelector('.form-titulo')), 'Corrigir sugestão da IA');
  assert.ok(painel.querySelector('.quadro-principal .mapa-no'), 'o mapa continua à vista enquanto a pessoa corrige');
  assert.ok(painel.querySelector('.quadro-lateral .form-quadro'), 'o formulário está no painel da direita');
  assert.equal(painel.querySelector('.form-quadro input[type=text]').value, 'Marta Reis');
  assert.match(texto(painel.querySelector('.vinculo-cartao')), /Da revisão da IA: IA · sustentado/);
  digitar(painel.querySelector('.form-quadro input[type=text]'), 'Marta Reis Lima');
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.salvos.length, 1);
  const {operacao, dados} = m.salvos[0];
  assert.equal(operacao, 'sugestoes-corrigir'); assert.equal(dados.id, SID);
  assert.match(dados.requisicao_id, /^[0-9a-f]{32}$/);
  assert.equal(dados.campos.nome, 'Marta Reis Lima'); assert.equal(dados.campos.variantes[0], 'M. Reis');
  assert.equal(dados.campos.evidencias[0].achado_id, 'A002');
});

test('cancelar sem mexer volta ao quadro; com alterações pede "Descartar alterações?"', async () => {
  const m = montar(); await abrirAba(m, 'hipoteses');
  const painel = m.$('quadros-hipoteses');
  await clicar(m, por(painel, 'button', '+ Nova hipótese'));
  await clicar(m, por(painel, 'button', 'Cancelar'));
  assert.ok(!painel.querySelector('.form-quadro'), 'sem alterações, volta direto');
  await clicar(m, por(painel, 'button', '+ Nova hipótese'));
  digitar(painel.querySelector('textarea'), 'Algo');
  const pedidos = []; m.janela.Dialogo.confirmar = async o => { pedidos.push(o); return false; };
  await clicar(m, por(painel, 'button', 'Cancelar'));
  assert.equal(pedidos.length, 1); assert.equal(pedidos[0].titulo, 'Descartar alterações?'); assert.equal(pedidos[0].variante, 'destrutivo');
  assert.ok(painel.querySelector('.form-quadro'), 'a pessoa ficou no formulário');
  m.janela.Dialogo.confirmar = async () => true;
  await clicar(m, por(painel, 'button', 'Cancelar'));
  assert.ok(!painel.querySelector('.form-quadro'));
});

test('R2: "conferido" só vem de conferida_no_original; resultado indisponível não é ligável e o ligado já está marcado', async () => {
  const com = (estado, extra = {}) => ({...RESULTADO, conferencia_humana: estado === null ? null : {estado, por: 'Ana Lima', em_utc: '2026-11-26T19:10:00+00:00'}, ...extra});
  const busca = [com('conferida_no_original'), com('precisa_de_ajuste'), com('sem_suporte_suficiente'), com('pendente'), com('trecho_localizado_no_texto_autorizado'), com(null),
    com(null, {estado: 'indisponivel'}), com(null, {ja_ligado: true})];
  const m = montar({busca}); await abrirAba(m, 'hipoteses');
  m.avaliar(`window.Quadros.buscaEvidencias('alpha')({texto: '', origem: 'tudo', analise: null}).then(r => { window.__r = JSON.stringify(r.resultados.map(x => [x.conferencia, x.indisponivel, x.ligada])); })`);
  await espera(m);
  assert.equal(m.janela.__r, JSON.stringify([['conferido', false, false], ['a_conferir', false, false], ['a_conferir', false, false], ['a_conferir', false, false], ['a_conferir', false, false],
    ['a_conferir', false, false], ['a_conferir', true, false], ['a_conferir', false, true]]));
  // No seletor aberto pelo formulário, o indisponível não tem botão e o conferido por pessoa leva a marca humana.
  await clicar(m, por(m.$('quadros-hipoteses'), 'button', '+ Nova hipótese'));
  await clicar(m, por(m.$('quadros-hipoteses'), 'button', '+ Ligar evidência'));
  const cartoes = [...m.$('quadros-hipoteses').querySelectorAll('.seletor-resultado')];
  assert.equal(cartoes.length, 8);
  assert.match(texto(cartoes[0]), /✓ Conferido no original/);
  for (const c of cartoes.slice(1, 6)) assert.match(texto(c), /○ A conferir/);
  assert.equal(cartoes[6].tagName, 'DIV'); assert.match(texto(cartoes[6]), /A evidência não está mais disponível\./);
  assert.equal(cartoes[7].tagName, 'DIV'); assert.match(texto(cartoes[7]), /Já ligada a este item/);
});

test('Retirar…: o motivo é obrigatório, a ação só se habilita com ele e salva por linha-tempo-atualizar com retirado e o motivo', async () => {
  const id = 'T' + '9'.repeat(32), sha = 'e'.repeat(64);
  const entrada = {evento_id: id, sha256: sha, descricao: 'Assinatura do Contrato 041/2025', data: {tipo: 'assinatura', valor: '2025-03-03', precisao: 'dia', aproximada: false, fonte: 0, observacao: '', rotulo: 'Data de assinatura'},
    fonte_da_data: null, fonte_conferida: false, evidencias: [], divergente: false, divergencia: null, retirado: false, motivo_retirada: ''};
  const detalhe = {'linha-tempo-detalhe': {id, sha256: sha, estado: {descricao: 'Assinatura do Contrato 041/2025', datas: [{tipo: 'assinatura', valor: '2025-03-03', precisao: 'dia', aproximada: false, fonte: 0, observacao: ''}]}, evidencias: [vinculoSalvo()]}};
  const m = montar({entradas: [entrada], detalhe}); await abrirAba(m, 'tempo');
  const painel = m.$('quadros-tempo');
  await clicar(m, por(painel, '.quadro-editar', 'Editar'));
  await clicar(m, por(painel, 'button', 'Retirar…'));
  const bloco = painel.querySelector('.form-retirada');
  assert.ok(bloco, 'pergunta de retirada');
  assert.match(texto(bloco.querySelector('h4')), /^Retirar “Assinatura do Contrato 041\/2025” da linha do tempo\?$/);
  const retirar = por(bloco, 'button', 'Retirar');
  assert.ok(retirar.disabled === true, 'sem motivo, a ação não habilita');
  digitar(bloco.querySelector('textarea'), 'Fonte duplicada.');
  assert.ok(retirar.disabled === false);
  await clicar(m, retirar);
  assert.equal(m.salvos.length, 1);
  const {operacao, dados} = m.salvos[0];
  assert.equal(operacao, 'linha-tempo-atualizar'); assert.equal(dados.id, id); assert.equal(dados.anterior_sha256, sha);
  assert.equal(dados.retirado, true); assert.equal(dados.motivo_retirada, 'Fonte duplicada.');
  assert.match(texto(m.$('quadros-anuncio')), /Retirado\. O item fica no registro, com o motivo\./);
});

test('B1 da Coruja: o vínculo reenvia o achado_id que o seletor traz em vinculo_sugerido (a mesma E-ID pode estar em dois achados)', async () => {
  const doisAchados = {...RESULTADO, vinculo_sugerido: {...RESULTADO.vinculo_sugerido, achado_id: 'A009'}};
  const m = montar({busca: [doisAchados]}); await abrirAba(m, 'hipoteses');
  const painel = m.$('quadros-hipoteses');
  await clicar(m, por(painel, 'button', '+ Nova hipótese'));
  digitar(painel.querySelector('textarea'), 'Hipótese com evidência de um achado específico.');
  await ligarEvidencia(m, painel);
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.salvos.length, 1);
  assert.equal(m.salvos[0].dados.evidencias[0].achado_id, 'A009', 'vale o de vinculo_sugerido, não o do resultado');
});

test('Corrigir e Cancelar volta à sugestão intacta, no mesmo painel da direita', async () => {
  const SID = 'S' + '2'.repeat(32);
  const sug = {id: SID, tipo: 'pessoa', quadro: 'mapa', campos: {tipo: 'pessoa', nome: 'Carlos Prado', variantes: [], identificadores: [], evidencias: [{referencia: referencia(3), papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', justificativa: ''}]},
    evidencias: [{referencia: referencia(3), estado: 'conferida', documento: {documento_id: 'D002', nome: 'contrato_social_alfa.pdf'}, localizador: {legivel: 'D002 · p. 1'}, trecho: 'Carlos Prado.', revisao_ia: IA(), conferencia_humana: null}],
    achado: {id: 'A002', versao: 1, destino: 'incluido'}, analise: {em_utc: '2026-11-26T17:32:00+00:00', pergunta: 'Quem?'}, estado: 'aberta', decisao: null, descartada_antes: null, bloqueio: null, avisos: []};
  const m = montar({sugestoes: [sug]}); await abrirAba(m, 'mapa');
  const painel = m.$('quadros-mapa');
  await clicar(m, painel.querySelector('.mapa-no.is-sugestao .mapa-cartao'));
  await clicar(m, por(painel, '.sugestao-acoes button', 'Corrigir'));
  assert.ok(!painel.querySelector('.quadro-lateral .sugestao-painel'), 'o formulário ocupa o lugar do painel da sugestão');
  await clicar(m, por(painel, 'button', 'Cancelar'));
  const lateral = painel.querySelector('.quadro-lateral');
  assert.equal(lateral.hidden, false, 'continua aberto');
  assert.match(texto(lateral.querySelector('.sugestao-titulo')), /^Carlos Prado · pessoa$/, 'voltou à sugestão');
  assert.equal(m.salvos.length, 0);
  await clicar(m, lateral.querySelector('.quadro-lateral-voltar'));
  assert.equal(lateral.hidden, true, '"Voltar" fecha o painel');
});

test('Editar entidade: abre com o registro sem máscara (mapa-entidade-detalhe), mantém o identificador e salva por mapa-entidade-atualizar', async () => {
  const sha = 'a'.repeat(64);
  const detalhe = {'mapa-entidade-detalhe': {id: MARTA, sha256: sha, estado: {tipo: 'pessoa', nome: 'Marta Reis', variantes: ['M. Reis'], identificadores: [{tipo: 'cpf', valor: '12345678909', fonte: 0}], conferencias: [], retirado: false, motivo_retirada: ''},
    evidencias: [vinculoSalvo()]}};
  const m = montar({detalhe}); await abrirAba(m, 'mapa');
  const painel = m.$('quadros-mapa');
  const editar = [...painel.querySelectorAll('.quadro-editar')].find(b => /Marta Reis/.test(b.getAttribute('aria-label')));
  await clicar(m, editar);
  assert.equal(texto(painel.querySelector('.form-titulo')), 'Editar entidade');
  assert.equal([...painel.querySelectorAll('.form-quadro input[type=text]')].find(i => i.value === '12345678909') !== undefined, true, 'o valor salvo, sem máscara');
  const segmentos = [...painel.querySelector('.form-segmentado').querySelectorAll('.form-segmento')];
  assert.ok(segmentos.every(b => b.disabled), 'o tipo da entidade não muda');
  digitar(painel.querySelector('.form-quadro input[type=text]'), 'Marta Reis Lima');
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.salvos.length, 1, texto(painel.querySelector('.form-erro-geral') || painel));
  const {operacao, dados} = m.salvos[0];
  assert.equal(operacao, 'mapa-entidade-atualizar'); assert.equal(dados.id, MARTA); assert.equal(dados.anterior_sha256, sha);
  assert.equal(dados.nome, 'Marta Reis Lima');
  assert.equal(dados.identificadores[0].valor, '12345678909'); assert.equal(dados.identificadores[0].fonte, 0);
});

test('R2: "Ligar a versão nova" avisa, em uma linha de status, que trocou as mudanças desta edição ainda não salvas', async () => {
  const id = 'H' + '1'.repeat(32);
  const nova = {referencia: referencia(5), achado_id: 'A002', versao: 2, revisao_ia: IA({versao: 2, suporte: 'sustentado'}), preenchimento: {papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', destino: 'incluido'}};
  const detalhe = {'hipoteses-detalhe': {id, sha256: 'c'.repeat(64), estado: {enunciado: 'H', situacao: 'em_aberto', lacunas: []}, evidencias: [vinculoSalvo({versao_nova: nova})]}};
  const m = montar({detalhe}); await abrirAba(m, 'hipoteses');
  const painel = m.$('quadros-hipoteses');
  await clicar(m, por(painel, '.quadro-editar', 'Editar'));
  const suporte = () => painel.querySelector('.vinculo-cartao select');
  suporte().value = 'parcial'; suporte().dispatchEvent(new Evento('change', {bubbles: true})); await espera(m);
  assert.match(texto(painel.querySelector('.vinculo-cartao')), /alterado por você/);
  await clicar(m, por(painel, '.vinculo-versao-nova', 'Ligar a versão nova'));
  const aviso = painel.querySelector('.vinculo-cartao .vinculo-aviso[role=status]');
  assert.ok([...painel.querySelectorAll('.vinculo-cartao .vinculo-aviso')].some(a => /Ligar a versão nova trocou as mudanças desta edição ainda não salvas \(suporte\)/.test(texto(a))), 'linha de status do R2');
  assert.ok(!/alterado por/i.test(texto(painel.querySelector('.vinculo-cartao'))), 'o valor volta ao da revisão da versão nova');
});

test('B1 da Coruja: "Voltar ao da IA" manda o preenchimento da P47, nunca o valor anterior da marca, e o diálogo mostra o valor da IA', async () => {
  const id = 'H' + '1'.repeat(32);
  const alt = {suporte: {anterior: 'parcial', valor: 'nao_sustentado', por: 'Ana Lima', em_utc: '2026-11-26T19:10:00+00:00'}};
  const detalhe = {'hipoteses-detalhe': {id, sha256: 'c'.repeat(64), estado: {enunciado: 'H', situacao: 'em_aberto', lacunas: []}, evidencias: [vinculoSalvo({alteracoes: alt, suporte: 'nao_sustentado'})]}};
  const m = montar({detalhe}); await abrirAba(m, 'hipoteses');
  const painel = m.$('quadros-hipoteses'), pedidos = [];
  m.janela.Dialogo.confirmar = async o => { pedidos.push(o); return true; };
  await clicar(m, por(painel, '.quadro-editar', 'Editar'));
  await clicar(m, [...painel.querySelectorAll('.vinculo-voltar')].find(b => /suporte/.test(b.getAttribute('aria-label'))));
  assert.match(pedidos[0].texto, /Ana Lima mudou o suporte de “sustentado” \(da revisão da IA\) para “não sustentado” em/);
  assert.doesNotMatch(pedidos[0].texto, /“parcial”/, 'o valor anterior da marca não é o da IA');
  assert.equal(painel.querySelector('.vinculo-cartao select').value, 'sustentado');
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.salvos[0].dados.evidencias[0].suporte, 'sustentado');
});

test('B1 da Coruja: "Voltar ao da IA" só aparece com o preenchimento que o servidor entrega (vínculo antigo: sem a ação)', async () => {
  const id = 'H' + '1'.repeat(32);
  const alt = {suporte: {anterior: 'sustentado', valor: 'parcial', por: 'Ana Lima', em_utc: '2026-11-26T19:10:00+00:00'}};
  const detalhe = {'hipoteses-detalhe': {id, sha256: 'c'.repeat(64), estado: {enunciado: 'H', situacao: 'em_aberto', lacunas: []}, evidencias: [vinculoSalvo({alteracoes: alt, suporte: 'parcial', preenchimento_ia: null, revisao_ia: null})]}};
  const m = montar({detalhe}); await abrirAba(m, 'hipoteses');
  const painel = m.$('quadros-hipoteses');
  await clicar(m, por(painel, '.quadro-editar', 'Editar'));
  assert.match(texto(painel.querySelector('.vinculo-cartao')), /alterado por Ana Lima/);
  assert.equal(painel.querySelector('.vinculo-voltar'), null, 'a tela não deduz o valor da IA');
});

test('B1 da Coruja: "Ligar a versão nova" usa o preenchimento da versão nova como vem (retirada: não revisado, nunca o sustentado cru da revisão)', async () => {
  const id = 'H' + '1'.repeat(32);
  const nova = {referencia: referencia(5), achado_id: 'A003', versao: 2, revisao_ia: IA({versao: 2, suporte: 'sustentado', destino: 'retirado'}),
    preenchimento: {papel: 'suporte', suporte: 'nao_revisado', natureza: 'declaracao_documental', destino: 'retirado'}};
  const detalhe = {'hipoteses-detalhe': {id, sha256: 'c'.repeat(64), estado: {enunciado: 'H', situacao: 'em_aberto', lacunas: []}, evidencias: [vinculoSalvo({versao_nova: nova})]}};
  const m = montar({detalhe}); await abrirAba(m, 'hipoteses');
  const painel = m.$('quadros-hipoteses');
  await clicar(m, por(painel, '.quadro-editar', 'Editar'));
  await clicar(m, por(painel, '.vinculo-versao-nova', 'Ligar a versão nova'));
  assert.equal(painel.querySelector('.vinculo-cartao select').value, 'nao_revisado');
  assert.match(texto(painel.querySelector('.vinculo-cartao')), /retirado/);
  await clicar(m, por(painel, 'button', 'Salvar'));
  const ev = m.salvos[0].dados.evidencias[0];
  assert.equal(JSON.stringify(ev.referencia), JSON.stringify(referencia(5))); assert.equal(ev.achado_id, 'A003');
  assert.equal(ev.suporte, 'nao_revisado'); assert.equal(ev.papel, 'suporte'); assert.equal(ev.natureza, 'declaracao_documental');
});
