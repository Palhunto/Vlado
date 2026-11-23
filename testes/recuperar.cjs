'use strict';
// Recuperar o acesso de outra pessoa pela Equipe (E3; docs/design/componentes.md#recuperar): o botão no bloco Acesso do Gerenciar, o diálogo com senha com texto por caso, o que a
// tela faz em cada resposta de equipe-recuperar e de equipe-recuperar-confirmar, e o cartão "Recuperações à espera de confirmação".
const test = require('node:test');
const assert = require('node:assert/strict');
const {abrir, esperar, texto, digitar, botaoPorTexto, dialogo, dados, tecla, recusa, equipeListar, pessoa, sessaoDe, ID, DIA} = require('./contas_apoio.cjs');

const ANA = () => pessoa(ID.ana, 'Ana Lima', 'dono');
const RUI = (extra = {}) => pessoa(ID.rui, 'Rui Castro', 'reporter', {casos: ['alfa'], ...extra});
const DAVI = (extra = {}) => pessoa(ID.davi, 'Davi Melo', 'dono', extra);
const estado = mesa => mesa.doc.querySelector('.conta-estado');
const acoes = mesa => [...dialogo(mesa).querySelectorAll('.dialogo-acoes button')];
const celulas = linha => [...linha.querySelectorAll('td')];
const linhaDe = (mesa, id) => [...mesa.doc.querySelectorAll('.equipe-tabela tbody tr')].find(l => l.dataset.conta === id);
const painel = (mesa, id) => mesa.$(`equipe-gerenciar-${id}`);
const sessaoInstalada = () => ({...sessaoDe('dono'), modo: 'local-contas'});
async function abrirEquipe(opcoes = {}) {
  const f = abrir(opcoes);
  await esperar(f.mesa);
  f.mesa.$('conta-aba-equipe').click(); await esperar(f.mesa);
  return f;
}
const com = (pessoas, extra = {}, resto = {}) => ({...resto, api: (op, d) => (op === 'equipe-listar' ? equipeListar(pessoas, extra) : resto.api?.(op, d))});
async function abrirDialogo(f, id) {
  if (!painel(f.mesa, id)) { celulas(linhaDe(f.mesa, id))[4].querySelector('button').click(); await esperar(f.mesa); }
  botaoPorTexto(painel(f.mesa, id), 'Recuperar acesso').click(); await esperar(f.mesa);
}
const pedido = (extra = {}) => ({id: 'f'.repeat(16), conta: ID.rui, conta_nome: 'Rui Castro', pedida_por: ID.davi, pedida_por_nome: 'Davi Melo', pedida_em: new Date(Date.now() - 3 * 3600000).toISOString(),
  expira_em: new Date(Date.now() + 21 * 3600000).toISOString(), estado: 'pendente', ...extra});

test('"Recuperar acesso" é um botão secundário no bloco Acesso, ao lado de Desativar e Remover, só para conta ativa; o apoio ganha as frases (e a do dono)', async () => {
  const f = await abrirEquipe(com([ANA(), RUI(), DAVI(), pessoa(ID.cora, 'Cora Dias', 'leitor', {situacao: 'desativada', ativa: false})]));
  celulas(linhaDe(f.mesa, ID.rui))[4].querySelector('button').click(); await esperar(f.mesa);
  const acesso = painel(f.mesa, ID.rui);
  assert.deepEqual([...acesso.querySelectorAll('.conta-acoes')].at(-1).querySelectorAll('button').length, 3);
  const botao = botaoPorTexto(acesso, 'Recuperar acesso');
  assert.ok(botao && botao.className.includes('secondary'), 'secundário');
  assert.deepEqual([...[...acesso.querySelectorAll('.conta-acoes')].at(-1).querySelectorAll('button')].map(b => b.textContent), ['Desativar', 'Recuperar acesso', 'Remover da redação']);
  assert.ok(texto(acesso).includes('Recuperar manda à pessoa um link para criar uma senha nova; nada muda na conta até ela usar o link.'));
  assert.ok(!texto(acesso).includes('Para um dono, outro dono precisa confirmar'), 'só para dono');
  celulas(linhaDe(f.mesa, ID.davi))[4].querySelector('button').click(); await esperar(f.mesa);
  assert.ok(texto(painel(f.mesa, ID.davi)).includes('Para um dono, outro dono precisa confirmar em até 24 horas.'));
  celulas(linhaDe(f.mesa, ID.cora))[4].querySelector('button').click(); await esperar(f.mesa);
  assert.equal(botaoPorTexto(painel(f.mesa, ID.cora), 'Recuperar acesso'), undefined, 'conta desativada: reativa-se antes');
  assert.ok(!texto(painel(f.mesa, ID.cora)).includes('Recuperar manda'));
  const sem = await abrirEquipe({...com([ANA(), RUI()]), sessao: {...sessaoDe('dono'), capacidades: ['conta-ver', 'equipe-listar', 'equipe-atividade']}});
  celulas(linhaDe(sem.mesa, ID.rui))[4].querySelector('button').click(); await esperar(sem.mesa);
  assert.equal(botaoPorTexto(painel(sem.mesa, ID.rui), 'Recuperar acesso'), undefined, 'sem a capacidade, sem o botão');
});

test('o diálogo com senha tem o texto de cada caso: não dono hospedado, Mesa instalada (P33) e dono', async () => {
  const hospedado = await abrirEquipe(com([ANA(), RUI(), DAVI()]));
  await abrirDialogo(hospedado, ID.rui);
  assert.equal(dialogo(hospedado.mesa).querySelector('.dialogo-titulo').textContent, 'Recuperar o acesso de Rui Castro?');
  assert.ok(texto(dialogo(hospedado.mesa)).includes('Rui Castro recebe por e-mail um link para criar uma senha nova. O link vale 24 horas. Nada muda na conta até ele ser usado.'));
  assert.equal(acoes(hospedado.mesa)[1].textContent, 'Recuperar acesso'); assert.ok(acoes(hospedado.mesa)[1].disabled, 'a ação espera a senha');
  assert.equal(dialogo(hospedado.mesa).querySelector('input').autocomplete, 'current-password');
  acoes(hospedado.mesa)[0].click(); await esperar(hospedado.mesa);
  const instalada = await abrirEquipe({...com([ANA(), RUI()]), sessao: sessaoInstalada()});
  await abrirDialogo(instalada, ID.rui);
  assert.ok(texto(dialogo(instalada.mesa)).includes('A Mesa mostra a você um link para Rui Castro criar uma senha nova. Entregue por um canal seguro. O link vale 24 horas.'));
  acoes(instalada.mesa)[0].click(); await esperar(instalada.mesa);
  await abrirDialogo(hospedado, ID.davi);
  assert.ok(texto(dialogo(hospedado.mesa)).includes('Davi Melo é dono. O pedido espera até 24 horas que outro dono, que não seja você, o confirme. Só então sai o link.'));
});

async function recuperar(f, id, resposta, senha = 'minha-senha') {
  await abrirDialogo(f, id);
  digitar(dialogo(f.mesa).querySelector('input'), senha); acoes(f.mesa)[1].click(); await esperar(f.mesa);
}

test('enviada por e-mail: o diálogo fecha e a linha de estado diz "Link de recuperação enviado … Vale 24 horas."; a senha vai em `senha`', async () => {
  const f = await abrirEquipe(com([ANA(), RUI()], {}, {api: op => (op === 'equipe-recuperar' ? {estado: 'enviada', conta: ID.rui, envio: 'enviado'} : undefined)}));
  await recuperar(f, ID.rui);
  assert.equal(dialogo(f.mesa), null);
  assert.deepEqual(dados(f.mesa.chamadas.find(c => c.operacao === 'equipe-recuperar').dados), {conta: ID.rui, senha: 'minha-senha'});
  assert.equal(texto(estado(f.mesa)), '✓ Link de recuperação enviado para Rui Castro. Vale 24 horas.');
});

test('enviada com falha de e-mail: linha de estado em cores de aviso, role=status', async () => {
  const f = await abrirEquipe(com([ANA(), RUI()], {}, {api: op => (op === 'equipe-recuperar' ? {estado: 'enviada', conta: ID.rui, envio: 'falha'} : undefined)}));
  await recuperar(f, ID.rui);
  assert.equal(texto(estado(f.mesa)), '! O e-mail para Rui Castro não saiu. Peça de novo em alguns minutos.');
  assert.equal(estado(f.mesa).dataset.tom, 'aviso'); assert.equal(estado(f.mesa).getAttribute('role'), 'status');
});

test('confirmada com link (Mesa instalada): o diálogo troca o formulário pelo link, uma vez, com "Copiar link" e "Já enviei" e sem Cancelar; o link sai da página ao fechar', async () => {
  const LINK = 'http://127.0.0.1:8765/redefinir/' + 'k'.repeat(43);
  const f = await abrirEquipe({...com([ANA(), RUI()], {}, {api: op => (op === 'equipe-recuperar' ? {estado: 'confirmada', conta: ID.rui, link: LINK} : undefined)}), sessao: sessaoInstalada()});
  const copiados = [];
  f.mesa.janela.navigator.clipboard.writeText = async valor => { copiados.push(valor); };
  await recuperar(f, ID.rui);
  const caixa = dialogo(f.mesa);
  assert.ok(caixa, 'o diálogo segue aberto');
  assert.equal(caixa.querySelector('.dialogo-titulo').textContent, 'Entregue o link a Rui Castro');
  assert.ok(texto(caixa).includes('Mande por um canal seguro. O link vale 24 horas, uma única vez, e não será mostrado de novo. Nada muda na conta até ele ser usado.'));
  assert.equal(caixa.querySelector('.convite-link').value, LINK); assert.ok(caixa.querySelector('.convite-link').readOnly);
  assert.deepEqual(acoes(f.mesa).filter(b => !b.hidden).map(b => b.textContent), ['Já enviei']);
  botaoPorTexto(caixa, 'Copiar link').click(); await esperar(f.mesa);
  assert.deepEqual(copiados, [LINK]);
  acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.equal(dialogo(f.mesa), null); assert.ok(!f.mesa.doc.body.textContent.includes('k'.repeat(43)), 'o link não fica na página');
});

test('dono: aguardando_confirmacao fecha o diálogo e diz até quando outro dono precisa confirmar; o pedido aparece no cartão', async () => {
  const expira = new Date(Date.now() + DIA).toISOString();
  let registrado = false;
  const f = await abrirEquipe({api: (op, d) => {
    if (op === 'equipe-listar') return equipeListar([ANA(), DAVI(), pessoa(ID.eva, 'Eva Rosa', 'dono')], {recuperacoes: registrado ? [pedido({conta: ID.davi, conta_nome: 'Davi Melo', pedida_por: ID.ana, pedida_por_nome: 'Ana Lima', expira_em: expira})] : []});
    if (op === 'equipe-recuperar') { registrado = true; return {estado: 'aguardando_confirmacao', recuperacao: pedido({conta: ID.davi, conta_nome: 'Davi Melo', pedida_por: ID.ana, expira_em: expira})}; }
    return undefined;
  }});
  await recuperar(f, ID.davi);
  assert.equal(dialogo(f.mesa), null);
  assert.equal(texto(estado(f.mesa)), `✓ Pedido registrado. Outro dono precisa confirmar a recuperação de Davi Melo até ${f.mesa.janela.Conta.data(expira)}.`);
  const cartao = f.mesa.doc.querySelector('.equipe-recuperacoes');
  assert.ok(cartao && !cartao.hidden, 'o pedido aparece no cartão');
});

test('recuperacao_pelo_operador: o texto do servidor no erro do diálogo, a ação indisponível e só "Cancelar"; as outras recusas ficam no erro, com a ação disponível', async () => {
  let resposta = recusa('recuperacao_pelo_operador', 'Essa recuperação é feita pelo operador do serviço, pelo terminal.');
  const f = await abrirEquipe(com([ANA(), RUI()], {}, {api: op => (op === 'equipe-recuperar' ? resposta : undefined)}));
  await recuperar(f, ID.rui);
  assert.equal(texto(dialogo(f.mesa).querySelector('.dialogo-erro[role="alert"]')), 'Essa recuperação é feita pelo operador do serviço, pelo terminal.');
  assert.ok(acoes(f.mesa)[1].disabled); digitar(dialogo(f.mesa).querySelector('input'), 'outra'); assert.ok(acoes(f.mesa)[1].disabled, 'nem digitando de novo');
  acoes(f.mesa)[0].click(); await esperar(f.mesa);
  resposta = recusa('requisicao_invalida', 'Um link de recuperação acabou de ser enviado a essa pessoa. Espere alguns minutos.');
  await recuperar(f, ID.rui);
  assert.equal(texto(dialogo(f.mesa).querySelector('.dialogo-erro[role="alert"]')), 'Um link de recuperação acabou de ser enviado a essa pessoa. Espere alguns minutos.');
  digitar(dialogo(f.mesa).querySelector('input'), 'de-novo'); assert.ok(!acoes(f.mesa)[1].disabled, 'a pessoa pode tentar de novo');
  acoes(f.mesa)[0].click(); await esperar(f.mesa);
});

test('senha incorreta vai ao campo da senha; bloqueio deixa só Cancelar', async () => {
  let resposta = recusa('senha_atual_incorreta', 'Senha incorreta.', 'proibido');
  const f = await abrirEquipe(com([ANA(), RUI()], {}, {api: op => (op === 'equipe-recuperar' ? resposta : undefined)}));
  await recuperar(f, ID.rui, null, 'errada');
  assert.equal(texto(dialogo(f.mesa).querySelector('.dialogo-erro-campo')), 'Senha incorreta. Confira e tente de novo.');
  resposta = recusa('bloqueado', 'Muitas tentativas.', 'bloqueado');
  digitar(dialogo(f.mesa).querySelector('input'), 'x'); acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.ok(texto(dialogo(f.mesa).querySelector('.dialogo-erro[role="alert"]')).startsWith('Muitas senhas erradas seguidas.')); assert.ok(acoes(f.mesa)[1].disabled);
  acoes(f.mesa)[0].click(); await esperar(f.mesa);
});

test('cartão "Recuperações à espera de confirmação": acima da tabela, só com pedidos; Confirmar só para um terceiro dono; quem pediu e a própria pessoa veem "Aguardando outro dono"', async () => {
  const pedidos = [pedido(), pedido({id: 'e'.repeat(16), conta: ID.davi, conta_nome: 'Davi Melo', pedida_por: ID.eva, pedida_por_nome: 'Eva Rosa'}),
    pedido({id: 'd'.repeat(16), conta: ID.ana, conta_nome: 'Ana Lima', pedida_por: ID.davi, pedida_por_nome: 'Davi Melo'}), pedido({id: 'c'.repeat(16), conta: ID.cora, conta_nome: 'Cora Dias', pedida_por: ID.ana, pedida_por_nome: 'Ana Lima'})];
  const f = await abrirEquipe(com([ANA(), RUI(), DAVI(), pessoa(ID.eva, 'Eva Rosa', 'dono'), pessoa(ID.cora, 'Cora Dias', 'leitor')], {recuperacoes: pedidos}));
  const cartao = f.mesa.doc.querySelector('.equipe-recuperacoes');
  assert.ok(!cartao.hidden); assert.equal(texto(cartao.querySelector('h2')), 'Recuperações à espera de confirmação');
  const painelEquipe = f.mesa.$('conta-painel-equipe');
  const filhos = [...painelEquipe.children];
  assert.ok(filhos.indexOf(cartao) < filhos.indexOf(painelEquipe.querySelector('.conta-cartao-tabela')), 'o cartão vem antes da tabela');
  const linhas = [...cartao.querySelectorAll('li')];
  assert.equal(linhas.length, 4);
  const quando = iso => f.mesa.janela.Conta.data(iso);
  assert.equal(texto(linhas[0].querySelector('.conta-rotulo')), `Rui Castropedido por Davi Melo em ${quando(pedidos[0].pedida_em)} · vence em ${quando(pedidos[0].expira_em)}`);
  assert.ok(botaoPorTexto(linhas[0], 'Confirmar'), 'a Ana não pediu e não é a pessoa: pode confirmar');
  assert.ok(botaoPorTexto(linhas[1], 'Confirmar'));
  assert.equal(botaoPorTexto(linhas[2], 'Confirmar'), undefined, 'a Ana é a própria pessoa do pedido'); assert.ok(texto(linhas[2]).includes('Aguardando outro dono'));
  assert.equal(botaoPorTexto(linhas[3], 'Confirmar'), undefined, 'a Ana foi quem pediu'); assert.ok(texto(linhas[3]).includes('Aguardando outro dono'));
  const vazio = await abrirEquipe(com([ANA(), RUI()], {recuperacoes: []}));
  assert.ok(vazio.mesa.doc.querySelector('.equipe-recuperacoes').hidden, 'sem pedidos, sem cartão');
});

test('Confirmar: diálogo com senha, texto por caso e as respostas de recuperar; "Pedido de recuperação não encontrado." fica no diálogo e a lista recarrega ao fechar', async () => {
  let listagens = 0, resposta = {estado: 'enviada', conta: ID.rui, envio: 'enviado'};
  const f = await abrirEquipe({api: (op, d) => {
    if (op === 'equipe-listar') { listagens += 1; return equipeListar([ANA(), RUI(), DAVI()], {recuperacoes: [pedido()]}); }
    if (op === 'equipe-recuperar-confirmar') return resposta;
    return undefined;
  }});
  const confirmar = () => botaoPorTexto(f.mesa.doc.querySelector('.equipe-recuperacoes'), 'Confirmar');
  confirmar().click(); await esperar(f.mesa);
  const caixa = dialogo(f.mesa);
  assert.equal(caixa.querySelector('.dialogo-titulo').textContent, 'Confirmar a recuperação do acesso de Rui Castro?'); assert.equal(acoes(f.mesa)[1].textContent, 'Confirmar recuperação');
  const quando = f.mesa.janela.Conta.data(pedido().pedida_em);
  assert.ok(texto(caixa).includes(`Davi Melo pediu em ${quando.slice(0, 5)}`) || texto(caixa).includes('Davi Melo pediu em'));
  assert.ok(texto(caixa).includes('Ao confirmar, Rui Castro recebe por e-mail um link para criar uma senha nova, válido por 24 horas.'));
  digitar(caixa.querySelector('input'), 'minha-senha'); acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.deepEqual(dados(f.mesa.chamadas.find(c => c.operacao === 'equipe-recuperar-confirmar').dados), {recuperacao: 'f'.repeat(16), senha: 'minha-senha'});
  assert.equal(texto(estado(f.mesa)), '✓ Link de recuperação enviado para Rui Castro. Vale 24 horas.');
  resposta = recusa('requisicao_invalida', 'Pedido de recuperação não encontrado.');
  confirmar().click(); await esperar(f.mesa);
  digitar(dialogo(f.mesa).querySelector('input'), 'x'); acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.equal(texto(dialogo(f.mesa).querySelector('.dialogo-erro[role="alert"]')), 'Pedido de recuperação não encontrado.');
  const antes = listagens;
  acoes(f.mesa)[0].click(); await esperar(f.mesa);
  assert.ok(listagens > antes, 'a lista recarrega');
});

test('Confirmar na Mesa instalada: o texto diz que a Mesa mostra o link, e a resposta `confirmada` abre a vista do link', async () => {
  const f = await abrirEquipe({sessao: sessaoInstalada(), api: (op) => {
    if (op === 'equipe-listar') return equipeListar([ANA(), RUI(), DAVI()], {recuperacoes: [pedido()]});
    if (op === 'equipe-recuperar-confirmar') return {estado: 'confirmada', conta: ID.rui, link: 'http://127.0.0.1:8765/redefinir/abc'};
    return undefined;
  }});
  botaoPorTexto(f.mesa.doc.querySelector('.equipe-recuperacoes'), 'Confirmar').click(); await esperar(f.mesa);
  assert.ok(texto(dialogo(f.mesa)).includes('Ao confirmar, a Mesa mostra a você o link para entregar a Rui Castro.'));
  digitar(dialogo(f.mesa).querySelector('input'), 'x'); acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.equal(dialogo(f.mesa).querySelector('.dialogo-titulo').textContent, 'Entregue o link a Rui Castro'); assert.equal(dialogo(f.mesa).querySelector('.convite-link').value, 'http://127.0.0.1:8765/redefinir/abc');
  acoes(f.mesa)[1].click(); await esperar(f.mesa);
});

test('em inglês: botão, diálogo, cartão e linhas de estado saem em inglês', async () => {
  const f = await abrirEquipe({...com([ANA(), RUI()], {recuperacoes: [pedido()]}), idioma: 'en', api: (op) => {
    if (op === 'equipe-listar') return equipeListar([ANA(), RUI(), DAVI()], {recuperacoes: [pedido()]});
    if (op === 'equipe-recuperar') return {estado: 'enviada', conta: ID.rui, envio: 'enviado'};
    return undefined;
  }});
  await f.mesa.esperar(20);
  assert.ok(texto(f.mesa.doc.querySelector('.equipe-recuperacoes')).includes('Recoveries waiting for confirmation') && texto(f.mesa.doc.querySelector('.equipe-recuperacoes')).includes('Confirm'));
  celulas(linhaDe(f.mesa, ID.rui))[4].querySelector('button').click(); await esperar(f.mesa);
  botaoPorTexto(painel(f.mesa, ID.rui), 'Recover access').click(); await esperar(f.mesa);
  assert.equal(dialogo(f.mesa).querySelector('.dialogo-titulo').textContent, 'Recover the access of Rui Castro?');
  assert.ok(texto(dialogo(f.mesa)).includes('Rui Castro gets a link by email to create a new password. The link is valid for 24 hours. Nothing changes in the account until it is used.'));
  digitar(dialogo(f.mesa).querySelector('input'), 'x'); acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.equal(texto(estado(f.mesa)), '✓ Recovery link sent to Rui Castro. Valid for 24 hours.');
});
