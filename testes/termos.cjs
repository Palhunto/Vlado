'use strict';
// A pendência de termos novos (E4b-1; docs/design/componentes.md#pendencia-termos): a página /conta/termos, no cartão do Entrar. Aceitar, o que falta marcar, os termos que mudaram
// enquanto se lia, e os dois links dos dados, que só existem sem a pendência do segundo fator (B1 da Coruja sobre b7eee49).
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa} = require('./dom_minimo.cjs');
const {esperar, texto, botaoPorTexto, digitar, recusa, contaVer} = require('./contas_apoio.cjs');

const VIGENTE = {versao: '2026-12-01', endereco: 'https://vlado.example/termos'};
const comTermos = (extra = {}) => ({...contaVer('dono'), termos: null, termos_vigente: VIGENTE, ...extra});

function pagina({api = () => undefined, pendencias = ['termos'], idioma = 'pt', semLista = false} = {}) {
  const sair = [], abrir = [], pedidos = [];
  const mesa = criarMesa({scripts: ['i18n_en.js', 'i18n.js', 'estados.js', 'dialogo.js', 'dados_conta.js', 'termos.js'], idioma, armazenamento: idioma === 'en' ? {'vlado-idioma': 'en'} : {}, api: () => ({})});
  const alvo = mesa.doc.createElement('div'); mesa.doc.body.append(alvo);
  const chamar = async (operacao, dados) => {
    pedidos.push([operacao, dados]);
    const r = api(operacao, dados);
    if (r instanceof Error) throw r;
    if (r !== undefined) return r;
    return operacao === 'conta-ver' ? comTermos() : {};
  };
  mesa.janela.Termos.pagina(alvo, {chamar, ...(semLista ? {} : {pendencias}), sair: () => sair.push(1), abrirMesa: () => abrir.push(1)});
  return {mesa, alvo, sair, abrir, pedidos};
}
const caixa = p => p.alvo.querySelector('input[type="checkbox"]');
const marcar = p => { caixa(p).checked = true; caixa(p).dispatchEvent(new p.mesa.janela.Event('change')); };

test('sem aceite anterior: rubrica, "Aceite os termos de uso", o texto com a versão, "Ler os termos" em outra aba, a caixa e a ação grande', async () => {
  const p = pagina(); await esperar(p.mesa);
  assert.equal(texto(p.alvo.querySelector('.fator-rubrica-pagina')), 'ANTES DE CONTINUAR'); assert.equal(texto(p.alvo.querySelector('h1')), 'Aceite os termos de uso');
  assert.ok(texto(p.alvo).includes('Para continuar usando o Vlado, leia e aceite os termos de uso e a política de privacidade do teste (versão 2026-12-01).'));
  const ler = p.alvo.querySelector('a'); assert.equal(ler.textContent, 'Ler os termos'); assert.equal(ler.getAttribute('href'), VIGENTE.endereco);
  assert.equal(ler.getAttribute('target'), '_blank'); assert.ok(/noopener/.test(ler.getAttribute('rel')));
  assert.ok(texto(p.alvo).includes('Li e aceito os termos de uso e a política de privacidade do teste.')); assert.ok(caixa(p) && !caixa(p).checked);
  assert.ok(botaoPorTexto(p.alvo, 'Aceitar e abrir a Mesa')); assert.ok(botaoPorTexto(p.alvo.querySelector('.fator-rodape'), 'Sair'));
});

test('com aceite anterior o título é "Os termos de uso mudaram"; sem versão vigente não há o que aceitar e a Mesa abre', async () => {
  const p = pagina({api: op => (op === 'conta-ver' ? comTermos({termos: {versao: '2026-06-01', aceito_em: '2026-06-02T10:00:00+00:00'}}) : undefined)}); await esperar(p.mesa);
  assert.equal(texto(p.alvo.querySelector('h1')), 'Os termos de uso mudaram');
  const nada = pagina({api: op => (op === 'conta-ver' ? comTermos({termos_vigente: null}) : undefined)}); await esperar(nada.mesa);
  assert.equal(nada.abrir.length, 1);
});

test('endereço dos termos que não é https:// não vira link', async () => {
  const p = pagina({api: op => (op === 'conta-ver' ? comTermos({termos_vigente: {versao: '2026-12-01', endereco: 'javascript:alert(1)'}}) : undefined)}); await esperar(p.mesa);
  assert.equal(p.alvo.querySelector('a'), null);
});

test('enviar sem marcar: "Falta aceitar os termos. Marque a caixa para continuar." junto à caixa, sem pedido', async () => {
  const p = pagina(); await esperar(p.mesa);
  botaoPorTexto(p.alvo, 'Aceitar e abrir a Mesa').click(); await esperar(p.mesa);
  const erro = p.alvo.querySelector('.termos-erro'); assert.ok(erro && !erro.hidden && texto(erro) === 'Falta aceitar os termos. Marque a caixa para continuar.');
  assert.equal(caixa(p).getAttribute('aria-invalid'), 'true'); assert.ok(!p.pedidos.some(([op]) => op === 'conta-termos-aceitar'));
  marcar(p); assert.ok(erro.hidden, 'marcar tira o erro');
});

test('aceitar: envia a versão vigente, sem senha, e abre a Mesa (o servidor manda à pendência seguinte)', async () => {
  const p = pagina(); await esperar(p.mesa); marcar(p);
  botaoPorTexto(p.alvo, 'Aceitar e abrir a Mesa').click(); await esperar(p.mesa); await esperar(p.mesa);
  assert.deepEqual(JSON.parse(JSON.stringify(p.pedidos.filter(([op]) => op === 'conta-termos-aceitar'))), [['conta-termos-aceitar', {versao: '2026-12-01'}]]);
  assert.equal(p.abrir.length, 1);
});

test('termos_desatualizados: relê a página com a versão nova, desmarcada, e diz que os termos mudaram enquanto se lia', async () => {
  let lidos = 0;
  const p = pagina({api: op => {
    if (op === 'conta-ver') return comTermos({termos_vigente: {...VIGENTE, versao: lidos++ ? '2027-01-10' : '2026-12-01'}});
    if (op === 'conta-termos-aceitar') return recusa('termos_desatualizados', 'Os termos mudaram.', 'invalido');
    return undefined;
  }}); await esperar(p.mesa); marcar(p);
  botaoPorTexto(p.alvo, 'Aceitar e abrir a Mesa').click(); await esperar(p.mesa); await esperar(p.mesa); await esperar(p.mesa);
  assert.ok(texto(p.alvo).includes('(versão 2027-01-10)'), texto(p.alvo));
  assert.ok(texto(p.alvo).includes('Os termos mudaram enquanto você lia. Confira a versão nova e marque de novo.')); assert.ok(!caixa(p).checked); assert.equal(p.abrir.length, 0);
});

test('outra recusa vai à caixa de aviso da página e a ação volta', async () => {
  const p = pagina({api: op => (op === 'conta-termos-aceitar' ? recusa('erro', 'Não deu para registrar o aceite.', 'erro') : undefined)}); await esperar(p.mesa); marcar(p);
  const acao = botaoPorTexto(p.alvo, 'Aceitar e abrir a Mesa'); acao.click(); await esperar(p.mesa); await esperar(p.mesa);
  assert.ok(texto(p.alvo.querySelector('.termos-aviso')).includes('Não deu para registrar o aceite.')); assert.ok(!acao.disabled); assert.equal(p.abrir.length, 0);
});

test('"Prefere não aceitar?": sem a pendência do fator, os links "baixar seus dados" e "excluir a conta"; o segundo abre o diálogo de excluir', async () => {
  const p = pagina(); await esperar(p.mesa);
  const frase = p.alvo.querySelector('.termos-nao-aceitar');
  assert.equal(texto(frase), 'Prefere não aceitar? Você pode baixar seus dados ou excluir a conta.');
  const [baixar, excluir] = [...frase.querySelectorAll('button')]; assert.equal(baixar.textContent, 'baixar seus dados'); assert.equal(excluir.textContent, 'excluir a conta');
  excluir.click(); await esperar(p.mesa);
  const caixaDeExcluir = p.mesa.doc.querySelector('dialog.dialogo'); assert.ok(caixaDeExcluir, 'o diálogo de excluir');
  assert.ok(texto(caixaDeExcluir).includes('Excluir a sua conta?') && texto(caixaDeExcluir).includes('Digite o seu nome, «Ana Lima», para confirmar'), texto(caixaDeExcluir));
  botaoPorTexto(caixaDeExcluir, 'Cancelar').click(); await esperar(p.mesa);
});

test('com a pendência do fator também aberta, no lugar dos links fica "Depois de cadastrar o segundo fator, ..." e nenhum botão de dados', async () => {
  const p = pagina({pendencias: ['termos', 'segundo_fator']}); await esperar(p.mesa);
  assert.equal(botaoPorTexto(p.alvo, 'baixar seus dados'), undefined); assert.equal(botaoPorTexto(p.alvo, 'excluir a conta'), undefined);
  assert.ok(texto(p.alvo).includes('Depois de cadastrar o segundo fator, você poderá baixar seus dados ou excluir a conta.'));
  assert.ok(!texto(p.alvo).includes('Prefere não aceitar?'));
  assert.deepEqual(p.alvo.querySelectorAll('.termos-nao-aceitar button').length, 0);
});

test('chamada sem a lista de pendências: lado seguro, sem os links de dados e com a frase de depois do fator (V1 da Coruja)', async () => {
  const p = pagina({semLista: true}); await esperar(p.mesa);
  assert.equal(p.alvo.querySelectorAll('.termos-nao-aceitar button').length, 0); assert.equal(botaoPorTexto(p.alvo, 'excluir a conta'), undefined);
  assert.ok(texto(p.alvo).includes('Depois de cadastrar o segundo fator, você poderá baixar seus dados ou excluir a conta.'));
  assert.ok(!texto(p.alvo).includes('Prefere não aceitar?'));
});

test('"Sair" chama sessao-sair e a saída', async () => {
  const p = pagina(); await esperar(p.mesa);
  botaoPorTexto(p.alvo.querySelector('.fator-rodape'), 'Sair').click(); await esperar(p.mesa); await esperar(p.mesa);
  assert.ok(p.pedidos.some(([op]) => op === 'sessao-sair')); assert.equal(p.sair.length, 1);
});

test('em inglês: título, caixa, ação e a frase dos links', async () => {
  const p = pagina({idioma: 'en'}); await esperar(p.mesa);
  assert.equal(texto(p.alvo.querySelector('h1')), 'Accept the terms of use');
  assert.ok(texto(p.alvo).includes('I have read and accept the terms of use and the privacy policy of the test.'));
  assert.ok(botaoPorTexto(p.alvo, 'Accept and open the Mesa'));
  assert.equal(texto(p.alvo.querySelector('.termos-nao-aceitar')), 'Prefer not to accept? You can download your data or delete the account.');
  const fator = pagina({idioma: 'en', pendencias: ['termos', 'segundo_fator']}); await esperar(fator.mesa);
  assert.ok(texto(fator.alvo).includes('After you set up the second factor, you will be able to download your data or delete the account.'));
});
