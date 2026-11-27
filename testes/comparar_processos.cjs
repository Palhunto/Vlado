'use strict';
// Comparação entre processos (L9; componentes.md#comparar-processos; interface/processos.js), com dados sintéticos no formato de CONTRATO_QUADROS_ONDA4.md, seção 5
// (Vila Serena, Contrato 041/2025, Procuradoria). A diferença de desfecho não é aviso nem erro; a conferência vem na forma da P20a; sem os campos, a vista fica vazia.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento, PILHA} = require('./dom_minimo.cjs');

const ref = n => ({tipo: 'ia', caso_id: 'alpha', rodada: 'R002', revisao: 'r3_sintese', registros_sha256: '7'.repeat(64), evidencia_id: `E0${n}`});
const evid = (n, trecho, extra = {}) => ({referencia: ref(n), estado: 'conferida', documento: {documento_id: 'D007', nome: 'parecer_12_2025.pdf'}, localizador: {legivel: 'D007 · página PDF 2', pagina_pdf: 2}, trecho,
  achado_id: 'A004', justificativa_ia: `Trecho do parecer na evidência E0${n}.`, revisao_ia: {suporte: 'sustentado', natureza: 'declaracao_documental', destino: 'incluido'}, conferencia_humana: null,
  preenchimento: {papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', destino: 'incluido'}, ...extra});
const COMPARACAO = (extra = {}) => ({achado: {id: 'A004', versao: 1, destino: 'incluido', redacao: 'O parecer foi usado nos dois processos.'},
  chave: {identificador: 'Parecer jurídico nº 12/2025', data: '2025-02-10', emissor: 'Procuradoria de Vila Serena', versao: 'única'},
  lados: [{processo: 'Processo 2025/118 · Contrato 041/2025', fundamento: evid(7, 'A dispensa é cabível nos termos do art. 75.'), questao: 'Validade da dispensa', fase: 'primeira instância', desfecho: 'Dispensa considerada regular', desfecho_evidencia: evid(8, 'Julgo regular a dispensa.')},
    {processo: 'Processo 2025/201 · Contrato 052/2025', fundamento: evid(9, 'A dispensa é cabível nos termos do art. 75, I.'), questao: 'Validade da dispensa', fase: 'recurso', desfecho: 'Dispensa anulada', desfecho_evidencia: evid(10, 'Dá-se provimento ao recurso.')}],
  conferencias: {versao: 'mesmo', data: 'mesmo', emissor: 'mesmo', trecho: 'diferente', questao: 'mesmo', fase: 'diferente'}, mesmo_arquivo: false, pendente: true,
  revisao_ia: {suporte: 'parcial', natureza: 'declaracao_documental'}, ...extra});
const IGUAIS = () => COMPARACAO({achado: {id: 'A005', versao: 1, destino: 'incluido'}, mesmo_arquivo: true, pendente: false, revisao_ia: {suporte: 'sustentado', natureza: 'declaracao_documental'},
  conferencias: {versao: 'mesmo', data: 'mesmo', emissor: 'mesmo', trecho: 'mesmo', questao: 'mesmo', fase: 'a_conferir'}});

function montar({resposta = {caso: 'alpha', estruturada: true, comparacoes: [COMPARACAO(), IGUAIS()]}, permissao = true, falha = null} = {}) {
  const salvos = [];
  const m = criarMesa({scripts: [...PILHA, 'quadros.js', 'sugestoes.js', 'formularios.js', 'processos.js', 'analise.js', 'indicador_salvamento.js'], desktop: true,
    catalogo: [{id: 'alpha', titulo: 'Alfa', rodadas: [{id: 'R001', geracoes: ['g1']}]}],
    api: (operacao, dados) => {
      if (operacao.endsWith('-criar')) {
        if ((dados.evidencias || []).some(v => !String(v.justificativa || '').trim())) throw new Error('Justificativa do vínculo: o texto não pode ser vazio.');
        salvos.push({operacao, dados}); return {id: 'H001'};
      }
      if (operacao === 'inventario') return {caso_id: 'alpha', documentos: [{id: 'D001', nome_recebido: 'a.txt', arquivo: 'a'}, {id: 'D002', nome_recebido: 'b.txt', arquivo: 'b'}]};
      if (operacao === 'comparar-processos') { if (falha) throw new Error(falha); return resposta; }
      if (operacao === 'sugestoes-listar') return {sugestoes: []};
      return {};
    },
    preparar: janela => {
      const original = janela.fetch;
      janela.fetch = async (rota, opcoes) => String(rota) === '/api/integracao' ? {ok: true, json: async () => ({quadros_evidencia: true})} : original(rota, opcoes);
    }});
  m.avaliar("window.contextoCaso = () => 'alpha'; window.abrirOriginal = async () => {};");
  m.salvos = salvos;
  if (!permissao) m.avaliar('window.Sessao = {pode: op => op === "inventario", pronta: Promise.resolve()};');
  return m;
}
const espera = async m => { await new Promise(r => setTimeout(r, 12)); await m.esperar(10); };
const texto = no => no.textContent.replace(/\s+/g, ' ').trim();
async function abrirProcessos(m) {
  m.$('ver-quadros').click(); await espera(m); m.$('quadros-aba-comparador').click(); await espera(m);
  const modos = [...m.$('quadros-comparador').querySelectorAll('.comparar-modos button')];
  assert.deepEqual(modos.map(b => b.textContent), ['Documentos', 'Processos']);
  assert.equal(modos[0].getAttribute('aria-pressed'), 'true');
  modos[1].click(); await espera(m);
  return {modos, vista: m.$('quadros-comparador').querySelector('.processos-vista')};
}

test('seletor "Documentos | Processos": Documentos continua o comparador de sempre e Processos abre a vista', async () => {
  const m = montar(); const {modos, vista} = await abrirProcessos(m);
  assert.equal(modos[1].getAttribute('aria-pressed'), 'true'); assert.equal(modos[0].getAttribute('aria-pressed'), 'false');
  assert.ok(vista, 'vista dos processos');
  assert.equal(m.$('quadros-comparador').querySelector('.comparar-docs').hidden, true);
  modos[0].click(); await espera(m);
  assert.equal(m.$('quadros-comparador').querySelector('.comparar-docs').hidden, false, 'Documentos volta');
});

test('topo, fundamento comum, os dois processos, "O que muda" e a conferência, sem as cores de erro', async () => {
  const m = montar(); const {vista} = await abrirProcessos(m);
  assert.match(texto(vista.querySelector('.processos-titulo')), /^Comparação entre processos$/);
  assert.match(texto(vista.querySelector('.processos-conta')), /2 comparações · 1 pendente · 1\/2/);
  const fund = vista.querySelector('.processo-fundamento');
  assert.match(texto(fund), /FUNDAMENTO COMUM|Fundamento comum/);
  assert.match(texto(fund), /Parecer jurídico nº 12\/2025/);
  assert.match(texto(fund.querySelector('.processo-chave')), /Identificador.*Data.*Emissor.*Versão/);
  assert.match(texto(fund.querySelector('.processo-identidade')), /○ Mesmo fundamento a conferir: versões ou trechos diferentes/);
  const lados = [...vista.querySelectorAll('.processo-lado')];
  assert.equal(lados.length, 2);
  assert.match(texto(lados[0]), /Processo A.*Processo 2025\/118 · Contrato 041\/2025.*A dispensa é cabível nos termos do art\. 75\..*parecer_12_2025\.pdf, D007 · página PDF 2.*Desfecho.*Dispensa considerada regular/);
  assert.match(texto(lados[1]), /Processo B.*Dispensa anulada/);
  assert.equal(lados[0].querySelector('blockquote').getAttribute('translate'), 'no');
  const linhas = [...vista.querySelectorAll('.processo-muda tbody tr')].map(tr => texto(tr));
  assert.match(linhas[0], /Questão decidida.*Validade da dispensa.*Validade da dispensa.*= igual/);
  assert.match(linhas[1], /Fase.*primeira instância.*recurso.*≠ diferente/);
  assert.match(linhas[2], /Desfecho.*≠ diferente/);
  assert.equal(vista.querySelector('.processo-comparacao span').getAttribute('aria-hidden'), 'true', 'o sinal é decoração');
  const conf = vista.querySelector('.processo-conferencia');
  assert.ok(conf.querySelector('.support-badge.ai-support'), 'veredito da IA na forma da P20a');
  const selos = [...conf.querySelectorAll('.processo-selo')].map(s => texto(s));
  assert.deepEqual(selos, ['IA · mesma versão', 'IA · mesma data', 'IA · mesmo emissor', 'IA · trechos diferentes', 'IA · mesma questão decidida', 'IA · fases diferentes: primeira instância e recurso']);
  assert.match(texto(vista.querySelector('.processo-pe')), /A diferença de desfecho não prova irregularidade\./);
  assert.ok(vista.querySelector('.processo-comparacao-cartao').classList.contains('is-pendente'));
  assert.match(texto(vista.querySelector('.processo-pendente')), /! Comparação pendente: falta conferir que o fundamento e os desfechos são comparáveis\./);
  assert.equal(vista.querySelectorAll('.notice, [role=alert], .sugestao-erro, .form-erro').length, 0, 'nada nas cores de erro, nem aviso');
});

test('mesmo arquivo: "= Mesmo arquivo nos dois processos (mesmo hash)" e Próxima/Anterior andam entre as comparações', async () => {
  const m = montar(); const {vista} = await abrirProcessos(m);
  const [anterior, proxima] = [...vista.querySelectorAll('.processos-nav button')];
  assert.equal(anterior.disabled, true);
  proxima.click(); await espera(m);
  assert.match(texto(vista.querySelector('.processo-identidade')), /= Mesmo arquivo nos dois processos \(mesmo hash\)/);
  assert.equal(vista.querySelector('.processo-identidade span').getAttribute('aria-hidden'), 'true');
  assert.ok(!vista.querySelector('.processo-comparacao-cartao').classList.contains('is-pendente'));
  assert.equal(vista.querySelector('.processo-pendente'), null);
  assert.match(texto(vista.querySelector('.processo-conferencia')), /IA · fase a conferir/);
  assert.equal(proxima.disabled, true); assert.equal(anterior.disabled, false);
  anterior.click(); await espera(m);
  assert.match(texto(vista.querySelector('.processo-fundamento')), /○ Mesmo fundamento a conferir/);
});

test('"Criar hipótese com esta comparação" abre o formulário com as evidências dos dois lados e o preenchimento da P47', async () => {
  const m = montar(); const {vista} = await abrirProcessos(m);
  [...vista.querySelectorAll('.processo-acoes button')].find(b => b.textContent === 'Criar hipótese com esta comparação').click(); await espera(m);
  const painel = m.$('quadros-comparador');
  assert.equal(texto(painel.querySelector('.form-titulo')), 'Nova hipótese');
  assert.equal(painel.querySelector('textarea').value, '', 'enunciado em branco');
  assert.equal([...painel.querySelectorAll('input')].find(i => i.type === 'radio' && i.value === 'em_aberto').checked, true);
  const cartoes = [...painel.querySelectorAll('.vinculo-cartao')];
  assert.equal(cartoes.length, 4, 'fundamento e desfecho dos dois lados');
  assert.match(texto(cartoes[0]), /A dispensa é cabível nos termos do art\. 75\./);
  assert.match(texto(cartoes[0]), /Da revisão da IA: IA · sustentado declaração documental/);
});

test('"Criar hipótese" liga cada evidência com o achado_id e o preenchimento do servidor, sem papel nem suporte fixos (785cfec)', async () => {
  const retirada = evid(9, 'A dispensa é cabível nos termos do art. 75, I.', {achado_id: 'A009', revisao_ia: {suporte: 'sustentado', natureza: 'declaracao_documental', destino: 'retirado'},
    preenchimento: {papel: 'contexto', suporte: 'nao_revisado', natureza: 'declaracao_documental', destino: 'retirado'}});
  const comp = COMPARACAO(); comp.lados[1].fundamento = retirada;
  const m = montar({resposta: {caso: 'alpha', estruturada: true, comparacoes: [comp]}}); const {vista} = await abrirProcessos(m);
  [...vista.querySelectorAll('.processo-acoes button')].find(b => b.textContent === 'Criar hipótese com esta comparação').click(); await espera(m);
  const painel = m.$('quadros-comparador');
  const area = painel.querySelector('textarea'); area.value = 'O parecer sustenta as duas decisões.'; area.dispatchEvent(new Evento('input', {bubbles: true}));
  for (const j of painel.querySelectorAll('.vinculo-cartao textarea')) { j.value = 'Mesmo parecer nos dois processos.'; j.dispatchEvent(new Evento('input', {bubbles: true})); }
  [...painel.querySelectorAll('button')].find(b => b.textContent === 'Salvar').click(); await espera(m);
  assert.equal(m.salvos.length, 1);
  const vs = m.salvos[0].dados.evidencias;
  const deRetirada = vs.find(v => v.achado_id === 'A009');
  assert.ok(deRetirada, 'o achado_id do servidor vai no vínculo');
  assert.equal(deRetirada.papel, 'contexto'); assert.equal(deRetirada.suporte, 'nao_revisado', 'achado retirado: não revisado, não o sustentado cru');
  const normal = vs.find(v => v.achado_id === 'A004');
  assert.equal(normal.papel, 'suporte'); assert.equal(normal.suporte, 'sustentado'); assert.equal(normal.natureza, 'declaracao_documental');
  assert.deepEqual(m.erros, []);
});

test('"Criar hipótese" preenche cada cartão com a justificativa_ia da evidência e salva sem a pessoa digitar (R1 da Coruja)', async () => {
  const m = montar(); const {vista} = await abrirProcessos(m);
  [...vista.querySelectorAll('.processo-acoes button')].find(b => b.textContent === 'Criar hipótese com esta comparação').click(); await espera(m);
  const painel = m.$('quadros-comparador');
  assert.deepEqual([...painel.querySelectorAll('.vinculo-cartao textarea')].map(j => j.value), ['E07', 'E08', 'E09', 'E010'].map(e => `Trecho do parecer na evidência ${e}.`));
  const area = painel.querySelector('textarea'); area.value = 'O parecer sustenta as duas decisões.'; area.dispatchEvent(new Evento('input', {bubbles: true}));
  [...painel.querySelectorAll('button')].find(b => b.textContent === 'Salvar').click(); await espera(m);
  assert.equal(m.salvos.length, 1);
  assert.deepEqual(m.salvos[0].dados.evidencias.map(v => v.justificativa), [7, 8, 9, 10].map(n => `Trecho do parecer na evidência E0${n}.`));
  assert.deepEqual(m.erros, []);
});

test('Salvar confere a justificativa de cada cartão antes de enviar e aponta o cartão que falta, com mensagem e foco no campo (R1 da Coruja)', async () => {
  const sem = COMPARACAO(); for (const l of sem.lados) for (const e of [l.fundamento, l.desfecho_evidencia]) e.justificativa_ia = '';
  const m = montar({resposta: {caso: 'alpha', estruturada: true, comparacoes: [sem]}}); const {vista} = await abrirProcessos(m);
  [...vista.querySelectorAll('.processo-acoes button')].find(b => b.textContent === 'Criar hipótese com esta comparação').click(); await espera(m);
  const painel = m.$('quadros-comparador');
  const area = painel.querySelector('textarea'); area.value = 'O parecer sustenta as duas decisões.'; area.dispatchEvent(new Evento('input', {bubbles: true}));
  const justs = () => [...painel.querySelectorAll('.vinculo-cartao textarea')];
  assert.equal(justs().length, 4);
  justs().slice(0, 2).forEach(j => { j.value = 'Mesmo parecer.'; j.dispatchEvent(new Evento('input', {bubbles: true})); });
  const salvar = () => [...painel.querySelectorAll('button')].find(b => b.textContent === 'Salvar').click();
  salvar(); await espera(m);
  assert.equal(m.salvos.length, 0, 'nada sai com justificativa vazia');
  assert.match(texto(painel.querySelector('.form-erro-geral')), /Falta a justificativa de parecer_12_2025\.pdf, D007 · página PDF 2\./);
  const terceiro = justs()[2];
  assert.equal(terceiro.getAttribute('aria-invalid'), 'true', 'o campo do cartão que falta está marcado');
  assert.equal(m.doc.activeElement, terceiro, 'o foco vai para o campo');
  assert.equal(justs()[0].getAttribute('aria-invalid'), null);
  assert.match(texto(terceiro.parentNode), /Escreva a justificativa\./);
  justs().slice(2).forEach(j => { j.value = 'Mesmo parecer.'; j.dispatchEvent(new Evento('input', {bubbles: true})); });
  salvar(); await espera(m);
  assert.equal(m.salvos.length, 1); assert.equal(m.salvos[0].dados.evidencias.length, 4);
  assert.deepEqual(m.erros, []);
});

test('sem permissão de editar o quadro, "Criar hipótese" fica indisponível com a razão', async () => {
  const m = montar({permissao: false}); const {vista} = await abrirProcessos(m);
  const criar = [...vista.querySelectorAll('.processo-acoes button')].find(b => b.textContent === 'Criar hipótese com esta comparação');
  assert.ok(criar.disabled === true);
  assert.match(texto(m.doc.getElementById(criar.getAttribute('aria-describedby'))), /Só repórter e editor mudam os quadros\./);
});

test('sem comparações (estruturada: false): estado vazio do Design; o servidor sem a rota: bloco de erro e Documentos continua disponível', async () => {
  const vazio = montar({resposta: {caso: 'alpha', estruturada: false, comparacoes: []}}); const {vista} = await abrirProcessos(vazio);
  assert.match(texto(vista), /Nenhuma comparação entre processos/);
  assert.match(texto(vista), /A análise compara processos quando o acervo tem mais de um sobre a mesma matéria e o mesmo fundamento aparece em mais de um deles\./);
  assert.ok([...vista.querySelectorAll('button')].some(b => b.textContent === 'Fazer uma pergunta'));
  const erro = montar({falha: 'Operação desconhecida.'}); const r = await abrirProcessos(erro);
  assert.equal(r.vista.querySelector('[data-estado="erro"]').getAttribute('role'), 'alert');
  assert.match(texto(r.vista), /Não deu para abrir a comparação\./);
  r.modos[0].click(); await espera(erro);
  assert.equal(erro.$('quadros-comparador').querySelector('.comparar-docs').hidden, false);
});
