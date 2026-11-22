'use strict';
// Estados de tela da Mesa (interface/estados.js, docs/design/componentes.md#estados; W11 regras 1 a 6 e 9). DOM sintético (dom_minimo).
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento, PILHA} = require('./dom_minimo.cjs');

const HTML = '<!doctype html><html><head></head><body data-idioma-padrao="pt"><main id="conteudo"><div id="alvo"></div><form id="f"><label>Nome <input id="campo" type="text"></label></form><button id="botao" type="button">Enviar</button></main></body></html>';
// O relógio é manual: o esqueleto só aparece depois do atraso.
function abrir() {
  const relogio = [];
  const mesa = criarMesa({scripts: ['i18n_en.js', 'i18n.js', 'estados.js'], html: HTML,
    preparar: janela => {
      janela.setTimeout = (funcao, ms) => { const item = {funcao, ms, vivo: true}; relogio.push(item); return item; };
      janela.clearTimeout = item => { if (item) item.vivo = false; };
    }});
  mesa.avancar = () => { for (const item of relogio.splice(0)) if (item.vivo) item.funcao(); };
  return mesa;
}

test('vazio: diz o que é a coisa e traz uma ação que funciona (regra 1)', () => {
  const mesa = abrir();
  let cliques = 0;
  const bloco = mesa.janela.Estados.vazio(mesa.$('alvo'), {titulo: 'Nenhuma hipótese ainda', texto: 'Uma hipótese é uma afirmação.', acao: {rotulo: 'Fazer uma pergunta', aoClicar: () => cliques++}});
  assert.equal(bloco.dataset.estado, 'vazio');
  assert.equal(bloco.getAttribute('role'), 'status');
  assert.equal(bloco.querySelector('.estado-titulo').textContent, 'Nenhuma hipótese ainda');
  assert.equal(bloco.querySelector('.estado-texto').textContent, 'Uma hipótese é uma afirmação.');
  const botao = bloco.querySelector('button');
  assert.equal(botao.textContent, 'Fazer uma pergunta');
  botao.click();
  assert.equal(cliques, 1);
});

test('esqueleto: não aparece em espera curta; passando do atraso mostra três barras; aria-busy sempre', () => {
  const mesa = abrir(), alvo = mesa.$('alvo');
  const espera = mesa.janela.Estados.esqueleto(alvo, {rotulo: 'Carregando…'});
  assert.equal(alvo.getAttribute('aria-busy'), 'true');
  assert.equal(alvo.querySelector('[role="status"]').textContent, 'Carregando…', 'leitor de tela ouve a espera');
  assert.equal(alvo.querySelector('.estado-esqueleto'), null, 'antes do atraso não há esqueleto');
  mesa.avancar();
  assert.equal(alvo.querySelector('.estado-esqueleto').children.length, 3);
  espera.parar();
  assert.equal(alvo.getAttribute('aria-busy'), null);
  assert.equal(alvo.childNodes.length, 0);
});

test('esqueleto: se o conteúdo chega antes do atraso, o esqueleto nunca aparece e o aria-busy sai', () => {
  const mesa = abrir(), alvo = mesa.$('alvo');
  mesa.janela.Estados.esqueleto(alvo);
  alvo.replaceChildren('conteúdo pronto');   // quem carrega troca os filhos do alvo
  mesa.avancar();
  assert.equal(alvo.querySelector('.estado-esqueleto'), null);
  assert.equal(alvo.getAttribute('aria-busy'), null);
  assert.equal(alvo.textContent, 'conteúdo pronto');
});

test('espera longa: etapa por extenso, barra com valor, aviso de que pode sair e Cancelar (regras 2 e 3)', () => {
  const mesa = abrir();
  let cancelou = 0;
  const espera = mesa.janela.Estados.espera(mesa.$('alvo'), {etapa: 'Lendo a página 1 de 5', aoCancelar: () => cancelou++});
  const bloco = espera.bloco;
  assert.equal(bloco.getAttribute('aria-busy'), 'true');
  assert.equal(bloco.getAttribute('role'), 'status');
  espera.etapa('Lendo a página 2 de 5', 0.4);
  assert.equal(bloco.querySelector('.estado-titulo').textContent, 'Lendo a página 2 de 5');
  assert.equal(bloco.querySelector('[role="progressbar"]').getAttribute('aria-valuenow'), '40');
  assert.match(bloco.textContent, /Você pode sair desta tela/);
  bloco.querySelector('button').click();
  assert.equal(cancelou, 1);
  espera.parar();
  assert.equal(bloco.getAttribute('aria-busy'), null);
});

test('erro: três partes, role=alert, cores de erro por classe e código interno só em Detalhes (regras 4, 6 e 9)', () => {
  const mesa = abrir();
  let tentou = 0;
  const bloco = mesa.janela.Estados.erro(mesa.$('alvo'), {titulo: 'Não deu para ler o arquivo.', texto: 'Confira o formato e tente de novo.',
    preservado: 'O original ficou guardado.', acoes: [{rotulo: 'Tentar de novo', aoClicar: () => tentou++}, {rotulo: 'O que fazer'}], detalhes: 'extracao_falhou'});
  assert.equal(bloco.getAttribute('role'), 'alert');
  assert.ok(bloco.className.includes('estado-erro'));
  assert.match(bloco.querySelector('.estado-titulo').textContent, /Não deu para ler o arquivo\./);
  assert.ok(bloco.querySelector('svg.estado-sinal'), 'sinal de erro em SVG, não um caractere');
  assert.equal(bloco.querySelector('svg').getAttribute('aria-hidden'), 'true');
  const [principal, secundario] = bloco.querySelectorAll('button');
  assert.equal(principal.className, '');
  assert.equal(secundario.className, 'secondary');
  principal.click();
  assert.equal(tentou, 1);
  assert.doesNotMatch(bloco.querySelector('.estado-titulo').textContent + bloco.querySelector('.estado-texto').textContent, /extracao_falhou/);
  assert.equal(bloco.querySelector('details code').textContent, 'extracao_falhou');
});

test('erro de campo: mensagem junto ao campo, aria-invalid, aria-describedby e foco; some ao digitar (regra 5)', () => {
  const mesa = abrir(), campo = mesa.$('campo');
  campo.setAttribute('aria-describedby', 'ajuda');
  const aviso = mesa.janela.Estados.erroCampo(campo, 'Escreva a pergunta antes de enviar.');
  assert.equal(campo.getAttribute('aria-invalid'), 'true');
  assert.ok(campo.nextSibling === aviso, 'a mensagem fica logo depois do campo');
  assert.equal(aviso.textContent, 'Escreva a pergunta antes de enviar.');
  assert.equal(campo.getAttribute('aria-describedby'), `ajuda ${aviso.id}`);
  assert.ok(mesa.doc.activeElement === campo, 'o foco vai para o campo');
  // Um segundo erro troca a mensagem em vez de empilhar.
  const outro = mesa.janela.Estados.erroCampo(campo, 'Escreva uma pergunta com mais de uma palavra.');
  assert.equal(mesa.doc.querySelectorAll('.campo-erro').length, 1);
  assert.equal(campo.getAttribute('aria-describedby'), `ajuda ${outro.id}`);
  campo.dispatchEvent(new Evento('input', {bubbles: true}));
  assert.equal(campo.getAttribute('aria-invalid'), null);
  assert.equal(campo.getAttribute('aria-describedby'), 'ajuda');
  assert.equal(mesa.doc.querySelectorAll('.campo-erro').length, 0);
});

test('botão ocupado: gerúndio, aria-busy e aria-disabled, ignora novos cliques e restaura o rótulo', () => {
  const mesa = abrir(), botao = mesa.$('botao');
  let cliques = 0;
  // No navegador o ouvinte de captura do próprio botão roda antes dos demais; o DOM sintético só o ordena antes dos de quem está acima.
  mesa.$('conteudo').addEventListener('click', () => cliques++);
  const restaurar = mesa.janela.Estados.ocupado(botao, 'Enviando…');
  assert.equal(botao.textContent, 'Enviando…');
  assert.equal(botao.getAttribute('aria-busy'), 'true');
  assert.equal(botao.getAttribute('aria-disabled'), 'true');
  assert.equal(botao.disabled, false, 'o foco não se perde: aria-disabled, não disabled');
  botao.click();
  assert.equal(cliques, 0, 'clique durante a espera é ignorado');
  restaurar();
  assert.equal(botao.textContent, 'Enviar');
  assert.equal(botao.getAttribute('aria-busy'), null);
  assert.equal(botao.getAttribute('aria-disabled'), null);
  botao.click();
  assert.equal(cliques, 1);
});

test('Perguntar: pergunta em branco mostra o erro junto ao campo, com aria-invalid e foco, e não envia', async () => {
  const mesa = criarMesa({scripts: PILHA, desktop: true, modo: 'local', url: 'http://127.0.0.1:8765/?area=codex&caso=alfa',
    catalogo: [{id: 'alfa', titulo: 'Pauta Alfa', rodadas: []}],
    api: operacao => ({'codex-listar': {conversas: []}, 'codex-status': {autenticado: true, provedor: 'anthropic', modelo: 'm'}}[operacao] || {})});
  await mesa.esperar(12);
  const campo = mesa.$('codex-pergunta');
  campo.value = '   ';
  mesa.$('codex-form').dispatchEvent(new Evento('submit', {bubbles: true, cancelable: true}));
  await mesa.esperar(2);
  assert.equal(campo.getAttribute('aria-invalid'), 'true');
  assert.equal(campo.nextSibling.textContent, 'Escreva a pergunta antes de enviar.');
  assert.ok(mesa.doc.activeElement === campo);
  assert.equal(mesa.chamadas.filter(c => c.operacao === 'codex-perguntar').length, 0, 'nada foi enviado');
  // O evento "invalid" do navegador (campo vazio com required) também cai aqui, sem a bolha nativa.
  campo.value = '';
  const invalido = new Evento('invalid', {cancelable: true});
  campo.dispatchEvent(invalido);
  assert.equal(invalido.defaultPrevented, true);
  assert.equal(campo.getAttribute('aria-invalid'), 'true');
});
