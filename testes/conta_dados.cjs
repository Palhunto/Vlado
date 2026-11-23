'use strict';
// Seus dados em Minha conta (E4b; docs/design/componentes.md#minha-conta e #excluir-conta): os termos de uso, "Exportar meus dados" (o JSON de conta-exportar, com o nome que o servidor manda)
// e "Excluir a conta" (o diálogo com senha, com o nome antes). Os formatos são os da proposta da entrega 4b do contrato (CONTRATO_CONTAS.md).
const test = require('node:test');
const assert = require('node:assert/strict');
const {abrir, esperar, texto, digitar, botaoPorTexto, dialogo, recusa, contaVer} = require('./contas_apoio.cjs');

const cartao = mesa => mesa.doc.querySelector('[data-cartao="dados"]');
const estado = mesa => mesa.doc.querySelector('.conta-estado');
const acoes = mesa => [...dialogo(mesa).querySelectorAll('.dialogo-acoes button')];
const TERMOS = {termos: {versao: '2026-12-01', aceito_em: '2026-11-22T15:00:00+00:00'}, termos_vigente: {versao: '2026-12-01', endereco: 'https://vlado.example/termos'}};
const comTermos = (extra = {}) => op => (op === 'conta-ver' ? {...contaVer('dono'), ...TERMOS, ...extra} : undefined);

// A resposta de conta-exportar como o navegador a recebe: arquivo (blob) e cabeçalhos.
const arquivo = (corpo, cabecalho = 'attachment; filename="vlado-meus-dados-2026-11-23.json"') => ({ok: true, headers: {get: nome => (/content-disposition/i.test(nome) ? cabecalho : null)},
  blob: async () => ({text: async () => JSON.stringify(corpo)}), json: async () => corpo});
function pedirArquivo(f, resposta) {
  const baixados = [], pedidos = [], nomes = [];
  f.mesa.janela.fetch = async endereco => { pedidos.push(String(endereco)); return String(endereco) === '/api/sessao' ? {ok: true, json: async () => ({csrf: 'x'})} : resposta; };
  f.mesa.janela.URL.createObjectURL = blob => { baixados.push(blob); return 'blob:teste'; };
  const criar = f.mesa.doc.createElement.bind(f.mesa.doc);
  f.mesa.doc.createElement = nome => { const no = criar(nome); if (nome === 'a') no.click = () => nomes.push(no.download); return no; };
  return {baixados, pedidos, nomes};
}

test('Seus dados, com versão vigente: "Termos de uso: versão … aceita em …" e o link "Ler os termos" em outra aba', async () => {
  const f = abrir({api: comTermos()}); await esperar(f.mesa);
  const linha = cartao(f.mesa).querySelector('.conta-termos');
  assert.ok(linha, 'a linha dos termos'); assert.ok(texto(linha).startsWith('Termos de uso: versão 2026-12-01, aceita em 22 de nov.'), texto(linha));
  const ler = linha.querySelector('a'); assert.equal(ler.textContent, 'Ler os termos'); assert.equal(ler.getAttribute('href'), 'https://vlado.example/termos');
  assert.equal(ler.getAttribute('target'), '_blank'); assert.ok(/noopener/.test(ler.getAttribute('rel')));
});

test('sem versão vigente (a Mesa instalada) não há linha de termos; endereço que não é https:// não vira link', async () => {
  const sem = abrir(); await esperar(sem.mesa);
  assert.equal(cartao(sem.mesa).querySelector('.conta-termos'), null);
  const mau = abrir({api: comTermos({termos_vigente: {versao: '2026-12-01', endereco: 'javascript:alert(1)'}})}); await esperar(mau.mesa);
  assert.ok(texto(cartao(mau.mesa).querySelector('.conta-termos')).startsWith('Termos de uso: versão 2026-12-01'));
  assert.equal(cartao(mau.mesa).querySelector('.conta-termos a'), null, 'nenhum link');
});

test('o cartão fica em todas as contas: o texto do que se leva e os botões Exportar meus dados (secundário) e Excluir a conta (destrutivo)', async () => {
  for (const papel of ['dono', 'reporter']) {
    const f = abrir({papel}); await esperar(f.mesa);
    const caixa = cartao(f.mesa);
    assert.ok(texto(caixa).includes('Baixe um arquivo com o que o Vlado guarda sobre você: perfil, aceites dos termos, sessões, participações e a atividade dos últimos 90 dias. O conteúdo das apurações é da redação e não entra.'));
    const exportar = botaoPorTexto(caixa, 'Exportar meus dados'), excluir = botaoPorTexto(caixa, 'Excluir a conta');
    assert.ok(exportar && exportar.className.includes('secondary'), papel); assert.ok(excluir && excluir.className.includes('danger'), papel);
  }
});

test('Exportar meus dados: baixa o JSON com o nome do servidor e diz "Arquivo baixado."', async () => {
  const f = abrir(); await esperar(f.mesa);
  const baixa = pedirArquivo(f, arquivo({incompleto: []}));
  botaoPorTexto(cartao(f.mesa), 'Exportar meus dados').click(); await esperar(f.mesa); await esperar(f.mesa);
  assert.ok(baixa.pedidos.includes('/api/conta-exportar')); assert.equal(baixa.baixados.length, 1);
  assert.deepEqual(baixa.nomes, ['vlado-meus-dados-2026-11-23.json']);
  assert.ok(texto(estado(f.mesa)).includes('Arquivo baixado.'), texto(estado(f.mesa)));
});

test('Exportar: com o arquivo `incompleto`, a linha de estado acrescenta "Ainda não traz: …"', async () => {
  const f = abrir(); await esperar(f.mesa);
  pedirArquivo(f, arquivo({incompleto: ['itens_criados', 'registro_de_acesso']}));
  botaoPorTexto(cartao(f.mesa), 'Exportar meus dados').click(); await esperar(f.mesa); await esperar(f.mesa);
  assert.ok(texto(estado(f.mesa)).includes('Arquivo baixado.'), texto(estado(f.mesa)));
  assert.ok(texto(estado(f.mesa)).includes('Ainda não traz: notas, revisões e conversas que você criou; acessos do registro de auditoria.'), texto(estado(f.mesa)));
});

test('Exportar recusado: o texto do servidor vai à linha de estado e o botão volta', async () => {
  const f = abrir(); await esperar(f.mesa);
  pedirArquivo(f, {ok: false, json: async () => ({estado: 'erro', codigo: 'erro', erro: 'Não deu para preparar o arquivo.'})});
  const botao = botaoPorTexto(cartao(f.mesa), 'Exportar meus dados');
  botao.click(); await esperar(f.mesa); await esperar(f.mesa);
  assert.ok(texto(estado(f.mesa)).includes('Não deu para preparar o arquivo.'), texto(estado(f.mesa)));
  assert.ok(!botao.disabled, 'o botão volta');
});

test('o nome do arquivo vem de Content-Disposition (filename* e filename), sem caminho, e há um nome padrão', () => {
  const {mesa} = abrir();
  const nome = mesa.janela.DadosConta.nomeDoArquivo;
  assert.equal(nome('attachment; filename="a.json"'), 'a.json');
  assert.equal(nome("attachment; filename*=UTF-8''vlado%20dados.json"), 'vlado dados.json');
  assert.equal(nome('attachment; filename="../../etc/passwd"'), 'passwd');
  assert.equal(nome(null), 'vlado-meus-dados.json'); assert.equal(nome('attachment'), 'vlado-meus-dados.json');
});

async function abrirExcluir(opcoes = {}) {
  const f = abrir(opcoes); await esperar(f.mesa);
  botaoPorTexto(cartao(f.mesa), 'Excluir a conta').click(); await esperar(f.mesa);
  return f;
}
const camposDoDialogo = mesa => ({nome: dialogo(mesa).querySelector('input[type="text"]'), senha: dialogo(mesa).querySelector('input[type="password"]')});

test('Excluir a conta: título, texto da decisão 10, o nome antes da senha e a ação só com os dois', async () => {
  const f = await abrirExcluir();
  const caixa = dialogo(f.mesa), c = camposDoDialogo(f.mesa);
  assert.equal(caixa.querySelector('.dialogo-titulo').textContent, 'Excluir a sua conta?');
  assert.ok(texto(caixa).includes('Você sai da Mesa agora e não entra mais com esta conta. Suas notas, revisões e conversas ficam com a redação, e a Mesa passa a mostrar o autor como «Conta excluída». O seu nome continua gravado nos registros já feitos e nos backups, que não podem ser reescritos.'));
  assert.ok(texto(caixa).includes('Digite o seu nome, «Ana Lima», para confirmar')); assert.ok(texto(caixa).includes('Sua senha'));
  assert.ok(c.nome && c.senha, 'os dois campos');
  assert.ok(texto(caixa).indexOf('Digite o seu nome') < texto(caixa).indexOf('Sua senha'), 'o nome vem antes da senha');
  const [cancelar, excluir] = acoes(f.mesa); assert.equal(cancelar.textContent, 'Cancelar'); assert.equal(excluir.textContent, 'Excluir a conta');
  assert.ok(excluir.className.includes('danger') && excluir.disabled, 'destrutiva e desabilitada');
  digitar(c.nome, 'Ana Lima'); assert.ok(excluir.disabled, 'só o nome: ainda espera a senha');
  digitar(c.senha, 'senha-dela'); assert.ok(!excluir.disabled);
  digitar(c.nome, 'Ana'); assert.ok(excluir.disabled, 'o nome tem de conferir');
  cancelar.click(); await esperar(f.mesa);
});

test('Excluir a conta, sucesso: envia {senha, nome} e a Mesa vai ao Entrar com o aviso da conta excluída', async () => {
  const pedidos = [];
  const f = await abrirExcluir({api: (op, d) => { if (op === 'conta-excluir') { pedidos.push(d); return {estado: 'conta_excluida'}; } return undefined; }});
  const trocas = []; f.mesa.janela.location.replace = destino => trocas.push(destino);
  const c = camposDoDialogo(f.mesa); digitar(c.nome, 'Ana Lima'); digitar(c.senha, 'senha-dela');
  acoes(f.mesa)[1].click(); await esperar(f.mesa); await esperar(f.mesa);
  assert.deepEqual(pedidos, [{senha: 'senha-dela', nome: 'Ana Lima'}]);
  assert.deepEqual(trocas, ['/entrar?aviso=conta_excluida']);
});

test('Excluir a conta, nome que não confere: o erro do servidor vai ao campo do nome, que recebe o foco, e o diálogo fica', async () => {
  const f = await abrirExcluir({api: op => (op === 'conta-excluir' ? recusa('nome_confirmacao_divergente', 'Digite o nome exatamente como mostrado para confirmar.', 'invalido') : undefined)});
  const c = camposDoDialogo(f.mesa); digitar(c.nome, 'Ana Lima'); digitar(c.senha, 'senha-dela');
  acoes(f.mesa)[1].click(); await esperar(f.mesa); await esperar(f.mesa);
  assert.ok(dialogo(f.mesa), 'o diálogo continua');
  const erro = dialogo(f.mesa).querySelector('.dialogo-erro-nome');
  assert.ok(erro && !erro.hidden && texto(erro).includes('Digite o nome exatamente como mostrado'), 'o erro junto ao campo do nome');
  assert.ok(f.mesa.doc.activeElement === c.nome, 'o foco volta ao nome'); assert.equal(c.senha.value, 'senha-dela', 'a senha não se apaga');
  acoes(f.mesa)[0].click(); await esperar(f.mesa);
});

test('Excluir a conta, a última dona ou o último dono: a razão no diálogo, sem sair', async () => {
  const f = await abrirExcluir({api: op => (op === 'conta-excluir' ? recusa('ultimo_dono', 'A redação precisa de ao menos um dono ativo.', 'invalido') : undefined)});
  const trocas = []; f.mesa.janela.location.replace = destino => trocas.push(destino);
  const c = camposDoDialogo(f.mesa); digitar(c.nome, 'Ana Lima'); digitar(c.senha, 'x');
  acoes(f.mesa)[1].click(); await esperar(f.mesa); await esperar(f.mesa);
  assert.ok(texto(dialogo(f.mesa)).includes('A redação precisa de ao menos um dono ativo. Antes de excluir a sua conta, torne outra pessoa dono na Equipe.'));
  assert.deepEqual(trocas, []); acoes(f.mesa)[0].click(); await esperar(f.mesa);
});

test('Excluir a conta, senha errada: o diálogo fica e a mensagem vai ao campo da senha', async () => {
  const f = await abrirExcluir({api: op => (op === 'conta-excluir' ? recusa('senha_incorreta', 'Senha incorreta.', 'proibido') : undefined)});
  const c = camposDoDialogo(f.mesa); digitar(c.nome, 'Ana Lima'); digitar(c.senha, 'errada');
  acoes(f.mesa)[1].click(); await esperar(f.mesa); await esperar(f.mesa);
  assert.ok(dialogo(f.mesa), 'o diálogo continua');
  assert.ok(texto(dialogo(f.mesa)).includes('Senha incorreta.'), texto(dialogo(f.mesa)));
  acoes(f.mesa)[0].click(); await esperar(f.mesa);
});
