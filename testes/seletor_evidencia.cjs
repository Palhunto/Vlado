'use strict';
// Seletor comum de evidência (componentes.md#seletor-evidencia, P47): busca, origem, estados e "Ligar", com dados sintéticos
// (Vila Serena, Construtora Alfa) e uma `buscar` de teste. Não usa rota nem caso real.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento, PILHA} = require('./dom_minimo.cjs');

const ACHADO = (n, extra = {}) => ({chave: `ia:R001:E00${n}`, origem: 'ia', tipo: 'Achado da IA', texto: `Marta Reis assinou o Contrato 041/2025 (${n}).`,
  localizador: 'Contrato 041/2025, p. 1, linhas 12 a 14', conferencia: 'a_conferir', suporte_ia: 'sustentado', natureza: 'declaracao_documental', destino: 'incluido',
  ligada: false, preenchimento: {papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental'}, ...extra});
const TRECHO = {chave: 'cad:N1:0', origem: 'caderno', tipo: 'Trecho do caderno', texto: 'Anotação sobre Carlos Prado.', localizador: 'Nota 3', conferencia: 'conferido',
  suporte_ia: null, natureza: null, destino: null, ligada: false, preenchimento: {papel: 'suporte', suporte: 'nao_revisado', natureza: null}};
const DADOS = {analise_atual: {id: 'R001', rotulo: '26/11, 14h32'}, analises: [{id: 'R001', rotulo: '26/11, 14h32', pergunta: 'Quem assinou?'}, {id: 'R000', rotulo: '20/11, 09h10', pergunta: 'Qual o valor?'}],
  resultados: [ACHADO(1), ACHADO(2, {destino: 'retirado', suporte_ia: 'sustentado'}), ACHADO(3, {ligada: true}), TRECHO]};

function montar(buscar) {
  const m = criarMesa({scripts: [...PILHA, 'quadros.js'], desktop: true, api: () => ({})});
  const chamadas = [];
  m.janela.__buscar = async c => { chamadas.push(c); return buscar(c); };
  const sel = m.avaliar(`window.Quadros.seletorEvidencia({buscar: window.__buscar, atraso: 0, aoVoltar: () => { window.__voltou = true; },
    aoLigar: r => { window.__ligou = r; }, aoAbrirOriginal: () => {}, limite: () => window.__limite || {atingido: false}})`);
  m.doc.body.append(sel);
  return {...m, sel, chamadas};
}
// O adiamento da busca é um setTimeout: esperar só voltas do laço não basta.
const quando = async m => { await new Promise(r => setTimeout(r, 15)); await m.esperar(6); };

test('abre com a lista da análise mais recente, sem busca digitada, e diz qual é', async () => {
  const m = montar(() => DADOS); await quando(m);
  assert.equal(m.sel.querySelector('.seletor-titulo').textContent, 'Ligar evidência');
  assert.equal(JSON.stringify(m.chamadas[0]), JSON.stringify({texto: '', origem: 'tudo', analise: null}));
  assert.match(m.sel.querySelector('.seletor-analise').textContent, /Achados da análise mais recente \(26\/11, 14h32\)/);
  assert.equal(m.sel.querySelectorAll('.seletor-resultado').length, 4);
  assert.equal(m.sel.querySelector('.seletor-avancado').hidden, false, 'há mais de uma análise');
  assert.deepEqual(m.erros, []);
});

test('duas marcas que não se confundem: conferência humana e veredito da IA; retirado e já ligada', async () => {
  const m = montar(() => DADOS); await quando(m);
  const [a1, a2, a3, c] = m.sel.querySelectorAll('.seletor-resultado');
  assert.match(a1.textContent, /○ A conferir/);
  assert.ok(a1.querySelector('.support-badge.ai-support'), 'veredito da IA com a forma da P20a');
  assert.match(a1.querySelector('.ai-support').textContent, /^IA · sustentado$/);
  assert.match(a2.querySelector('.seletor-retirado').textContent, /retirado pela revisão/);
  assert.match(a3.textContent, /Já ligada a este item/);
  assert.ok(a3.tagName === 'DIV', 'já ligada não abre');
  assert.match(c.textContent, /✓ Conferido no original/);
  assert.ok(c.querySelector('.ai-support') === null, 'trecho do caderno não leva veredito da IA');
  assert.ok(a1.querySelector('.seletor-texto').getAttribute('translate') === 'no');
});

test('filtro de origem e busca a partir do segundo caractere', async () => {
  const m = montar(c => ({...DADOS, resultados: c.texto === 'Marta' ? [ACHADO(1)] : DADOS.resultados})); await quando(m);
  const pilulas = [...m.sel.querySelectorAll('.seletor-pilula')];
  assert.deepEqual(pilulas.map(p => p.textContent), ['Tudo', 'Achados da IA', 'Caderno']);
  assert.equal(pilulas[0].getAttribute('aria-pressed'), 'true');
  pilulas[2].click(); await quando(m);
  assert.equal(m.chamadas.at(-1).origem, 'caderno');
  assert.equal(pilulas[2].getAttribute('aria-pressed'), 'true'); assert.equal(pilulas[0].getAttribute('aria-pressed'), 'false');
  const busca = m.sel.querySelector('.seletor-busca');
  busca.value = 'M'; busca.dispatchEvent(new Evento('input', {bubbles: true})); await quando(m);
  assert.equal(m.chamadas.at(-1).texto, '', 'um caractere só não busca');
  busca.value = 'Marta'; busca.dispatchEvent(new Evento('input', {bubbles: true})); await quando(m);
  assert.equal(m.chamadas.at(-1).texto, 'Marta');
  assert.equal(m.sel.querySelectorAll('.seletor-resultado').length, 1);
});

test('resultado aberto mostra o vínculo preenchido e "Ligar" entrega o resultado', async () => {
  const m = montar(() => DADOS); await quando(m);
  m.sel.querySelector('.seletor-resultado').click();
  const aberto = m.sel.querySelector('.seletor-aberto');
  assert.ok(aberto, 'cartão aberto');
  assert.match(aberto.textContent, /Papel/); assert.match(aberto.textContent, /Sustentado/); assert.match(aberto.textContent, /Declaração documental/);
  assert.ok([...aberto.querySelectorAll('button')].some(b => b.textContent === 'Abrir o original'));
  [...aberto.querySelectorAll('button')].find(b => b.textContent === 'Ligar').click();
  assert.ok(m.janela.__ligou.chave === 'ia:R001:E001');
});

test('com 100 evidências, "Ligar" fica indisponível com a razão ligada por aria-describedby', async () => {
  const m = montar(() => DADOS); await quando(m);
  m.janela.__limite = {atingido: true, razao: 'Este item já tem 100 evidências, o limite.'};
  m.sel.querySelector('.seletor-resultado').click();
  const ligar = [...m.sel.querySelectorAll('.seletor-aberto button')].find(b => b.textContent === 'Ligar');
  assert.ok(ligar.disabled === true);
  const razao = m.doc.getElementById(ligar.getAttribute('aria-describedby'));
  assert.match(razao.textContent, /100 evidências/);
});

test('vazio com busca não afirma ausência; vazio sem nada leva a Fazer uma pergunta; erro mantém a busca', async () => {
  const m = montar(() => ({...DADOS, resultados: []})); await quando(m);
  assert.match(m.sel.textContent, /Esta apuração ainda não tem achados nem trechos com fonte/);
  const busca = m.sel.querySelector('.seletor-busca');
  busca.value = 'Marta'; busca.dispatchEvent(new Evento('input', {bubbles: true})); await quando(m);
  assert.match(m.sel.textContent, /Nada encontrado para “Marta”/);
  assert.match(m.sel.textContent, /Isso não prova que não esteja nos documentos/);
  const e = montar(() => { throw new Error('Serviço fora do ar.'); }); await quando(e);
  assert.match(e.sel.textContent, /Serviço fora do ar/);
});

test('voltar chama aoVoltar', async () => {
  const m = montar(() => DADOS); await quando(m);
  m.sel.querySelector('.seletor-voltar').click();
  assert.ok(m.janela.__voltou === true);
});

test('R2: resultado indisponível não é ligável: não abre, não tem "Ligar" e diz o motivo', async () => {
  const dados = {...DADOS, resultados: [ACHADO(1, {indisponivel: true}), ACHADO(2)]};
  const m = montar(() => dados); await quando(m);
  const [indisp, normal] = m.sel.querySelectorAll('.seletor-resultado');
  assert.ok(indisp.tagName === 'DIV', 'não é botão');
  assert.match(indisp.textContent, /A evidência não está mais disponível\./);
  indisp.click();
  assert.equal(m.sel.querySelector('.seletor-aberto'), null, 'não abre');
  normal.click();
  assert.ok(m.sel.querySelector('.seletor-aberto'), 'o resultado normal abre');
});
