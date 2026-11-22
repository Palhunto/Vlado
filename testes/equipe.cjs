'use strict';
// Equipe (W09; docs/design/componentes.md#equipe): a tabela da redação e os cartões do celular, mudar o papel (com a senha quando há dono no meio), Gerenciar
// (apurações, teto mensal, acesso), o gasto da redação e a atividade recente, com uma frase para cada tipo de evento que o servidor grava.
const test = require('node:test');
const assert = require('node:assert/strict');
const {abrir, esperar, texto, digitar, mudar, botaoPorTexto, dialogo, dados, recusa, equipeListar, pessoa, ID, ALFA, BETA, GAMA, DELTA, tecla} = require('./contas_apoio.cjs');

const ANA = () => pessoa(ID.ana, 'Ana Lima', 'dono');
const RUI = (extra = {}) => pessoa(ID.rui, 'Rui Castro', 'reporter', {casos: ['alfa', 'beta', 'gama', 'delta'], responsavel_de: ['alfa'], ...extra});
const CORA = (extra = {}) => pessoa(ID.cora, 'Cora Dias', 'convidado', {casos: ['alfa'], ...extra});
const linhas = mesa => [...mesa.doc.querySelectorAll('.equipe-tabela tbody tr')].filter(l => l.dataset.conta);
const linhaDe = (mesa, id) => linhas(mesa).find(l => l.dataset.conta === id);
const celulas = linha => [...linha.querySelectorAll('td')];
const estado = mesa => mesa.doc.querySelector('.conta-estado');
const acoesDoDialogo = mesa => [...dialogo(mesa).querySelectorAll('.dialogo-acoes button')];
const painelEquipe = mesa => mesa.$('conta-painel-equipe');
async function abrirEquipe(opcoes = {}) {
  const f = abrir(opcoes);
  await esperar(f.mesa);
  f.mesa.$('conta-aba-equipe').click(); await esperar(f.mesa);
  return f;
}
const com = (pessoas, extra = {}) => ({api: op => (op === 'equipe-listar' ? equipeListar(pessoas, extra) : undefined)});

test('a aba Equipe só existe para quem tem equipe-listar; o título é o nome da redação, com a contagem', async () => {
  const {mesa} = await abrirEquipe(com([ANA(), RUI(), CORA()]));
  assert.ok(!mesa.$('conta-aba-equipe').hidden); assert.equal(mesa.$('conta-aba-equipe').getAttribute('aria-pressed'), 'true');
  assert.equal(mesa.$('area-titulo').textContent, 'Redação Serena'); assert.equal(mesa.$('area-descricao').textContent, '3 pessoas');
  const reporter = abrir({papel: 'reporter'}); await esperar(reporter.mesa);
  assert.ok(reporter.mesa.$('conta-aba-equipe').hidden, 'a Mesa decide pela capacidade, não pelo nome do papel');
  const sozinho = await abrirEquipe(com([ANA()]));
  assert.equal(sozinho.mesa.$('area-descricao').textContent, '1 pessoa');
});

test('a tabela: Pessoa, Papel, Apurações, Uso no mês e a ação; "(você)", e-mail ou login, e a situação da conta com sinal e texto', async () => {
  const f = await abrirEquipe(com([ANA(), RUI({situacao: 'desativada', ativa: false}), CORA({email: null, login: 'cora.dias', situacao: 'aguardando_senha', ativacao_vencida: true}),
    pessoa(ID.davi, 'Davi Melo', 'editor', {situacao: 'aguardando_senha'})]));
  const mesa = f.mesa;
  assert.deepEqual([...mesa.doc.querySelectorAll('.equipe-tabela th')].map(th => th.textContent), ['Pessoa', 'Papel', 'Apurações', 'Uso no mês', 'Ações']);
  assert.equal([...mesa.doc.querySelectorAll('.equipe-tabela th')].at(-1).querySelector('.sr-only').textContent, 'Ações', 'a coluna da ação tem rótulo só para leitor de tela');
  const ana = texto(celulas(linhaDe(mesa, ID.ana))[0]);
  assert.ok(ana.startsWith('Ana Lima (você)') && ana.includes('ana@redacao.org'));
  assert.ok(texto(celulas(linhaDe(mesa, ID.rui))[0]).includes('○ Desativada'));
  const cora = texto(celulas(linhaDe(mesa, ID.cora))[0]);
  assert.ok(cora.includes('login cora.dias') && cora.includes('◐ Link de ativação vencido'));
  assert.ok(texto(celulas(linhaDe(mesa, ID.davi))[0]).includes('◐ Aguardando a senha'));
  assert.equal(celulas(linhaDe(mesa, ID.ana))[0].querySelector('.equipe-pessoa-nome span').getAttribute('translate'), 'no', 'o nome é dado: não se traduz');
});

test('Papel: a própria linha é só texto; as outras têm caixa com Dono, Editor, Repórter e Leitor; o perfil antigo aparece selecionado e indisponível', async () => {
  const {mesa} = await abrirEquipe(com([ANA(), RUI(), CORA()]));
  assert.equal(celulas(linhaDe(mesa, ID.ana))[1].querySelector('select'), null); assert.equal(texto(celulas(linhaDe(mesa, ID.ana))[1]), 'Dono');
  const rui = celulas(linhaDe(mesa, ID.rui))[1].querySelector('select');
  assert.deepEqual([...rui.querySelectorAll('option')].map(o => o.textContent), ['Dono', 'Editor', 'Repórter', 'Leitor']); assert.equal(rui.value, 'reporter');
  assert.equal(rui.getAttribute('aria-label'), 'Papel de Rui Castro');
  const cora = celulas(linhaDe(mesa, ID.cora))[1].querySelector('select');
  assert.equal(cora.value, 'convidado'); assert.equal(cora.querySelector('option').textContent, 'Convidado (perfil antigo)'); assert.ok(cora.querySelector('option').disabled);
  const aviso = painelEquipe(mesa).querySelector('.notice');
  assert.ok(aviso && aviso.getAttribute('role') === 'status');
  assert.equal(texto(aviso), '1 pessoa ainda tem o perfil antigo de convidado: pergunta só nas apurações liberadas e vê só as próprias conversas. Escolha um papel para ela ou remova da redação.');
  const dois = await abrirEquipe(com([ANA(), CORA(), pessoa(ID.davi, 'Davi Melo', 'convidado')]));
  assert.ok(texto(painelEquipe(dois.mesa).querySelector('.notice')).startsWith('2 pessoas ainda têm o perfil antigo de convidado'));
  const sem = await abrirEquipe(com([ANA(), RUI()]));
  assert.equal(painelEquipe(sem.mesa).querySelector('.notice'), null, 'sem convidado, sem aviso');
});

test('Apurações e Uso no mês: "Todas" para dono; até três títulos e "e mais N"; "Nenhuma"; valores em reais, teto próprio e esgotada com "!"', async () => {
  const {mesa} = await abrirEquipe(com([ANA(), RUI({teto_mensal_brl: '30.00'}), pessoa(ID.davi, 'Davi Melo', 'editor', {gasto: null}),
    pessoa(ID.eva, 'Eva Rosa', 'leitor', {gasto: {mes: '2026-11', gasto_brl: '50.00', teto_brl: '50.00', saldo_brl: '0.00', esgotada: true}})]));
  assert.equal(texto(celulas(linhaDe(mesa, ID.ana))[2]), 'Todas');
  assert.equal(texto(celulas(linhaDe(mesa, ID.rui))[2]), 'Pauta Alfa, Campo Verde, Pauta Gama e mais 1');
  assert.equal(texto(celulas(linhaDe(mesa, ID.davi))[2]), 'Nenhuma');
  assert.equal(texto(celulas(linhaDe(mesa, ID.ana))[3]), 'R$ 18,40');
  assert.equal(texto(celulas(linhaDe(mesa, ID.rui))[3]), 'R$ 18,40teto R$ 30');
  assert.equal(texto(celulas(linhaDe(mesa, ID.davi))[3]), '—', 'sem o gasto, um traço');
  assert.equal(texto(celulas(linhaDe(mesa, ID.eva))[3]), '! R$ 50,00 · esgotada', 'esgotado: sinal e texto, não só a cor');
});

test('mudar o papel sem dono no meio vai direto, com a caixa indisponível enquanto corre, e a linha de estado diz que vale na próxima ação', async () => {
  let pessoas = [ANA(), RUI()];
  const {mesa} = await abrirEquipe({api: (op, d) => {
    if (op === 'equipe-listar') return equipeListar(pessoas);
    if (op === 'equipe-papel') { pessoas = [ANA(), RUI({papel: d.papel})]; return {conta: pessoas[1]}; }
    return undefined;
  }});
  mudar(celulas(linhaDe(mesa, ID.rui))[1].querySelector('select'), 'editor'); await esperar(mesa);
  assert.equal(dialogo(mesa), null, 'sem dono no meio, sem diálogo');
  assert.deepEqual(dados(mesa.chamadas.find(c => c.operacao === 'equipe-papel').dados), {conta: ID.rui, papel: 'editor'});
  assert.equal(texto(estado(mesa)), '✓ Rui Castro agora é Editor. Vale na próxima ação.');
  assert.equal(celulas(linhaDe(mesa, ID.rui))[1].querySelector('select').value, 'editor');
});

test('tornar dono pede a senha no diálogo, com o texto do desenho; a senha vai em `senha`; cancelar devolve a caixa ao papel anterior', async () => {
  let pessoas = [ANA(), RUI()];
  const {mesa} = await abrirEquipe({api: (op, d) => {
    if (op === 'equipe-listar') return equipeListar(pessoas);
    if (op === 'equipe-papel') { pessoas = [ANA(), RUI({papel: 'dono', casos: null})]; return {conta: pessoas[1]}; }
    return undefined;
  }});
  let caixa = celulas(linhaDe(mesa, ID.rui))[1].querySelector('select');
  mudar(caixa, 'dono'); await esperar(mesa);
  assert.equal(dialogo(mesa).querySelector('.dialogo-titulo').textContent, 'Tornar Rui Castro dono da redação?');
  assert.ok(texto(dialogo(mesa)).includes('Dono vê todas as apurações da redação, administra a equipe e apaga de vez. Vale na próxima ação de Rui Castro.'));
  assert.equal(dialogo(mesa).dataset.variante, 'simples'); assert.equal(acoesDoDialogo(mesa)[1].textContent, 'Tornar dono');
  assert.equal(mesa.chamadas.filter(c => c.operacao === 'equipe-papel').length, 0, 'nada foi enviado antes da senha');
  acoesDoDialogo(mesa)[0].click(); await esperar(mesa);
  assert.equal(celulas(linhaDe(mesa, ID.rui))[1].querySelector('select').value, 'reporter', 'cancelar devolve o papel anterior');
  caixa = celulas(linhaDe(mesa, ID.rui))[1].querySelector('select');
  mudar(caixa, 'dono'); await esperar(mesa);
  digitar(dialogo(mesa).querySelector('input'), 'minha-senha');
  acoesDoDialogo(mesa)[1].click(); await esperar(mesa);
  assert.deepEqual(dados(mesa.chamadas.find(c => c.operacao === 'equipe-papel').dados), {conta: ID.rui, papel: 'dono', senha: 'minha-senha'});
  assert.equal(texto(estado(mesa)), '✓ Rui Castro agora é Dono. Vale na próxima ação.');
});

test('rebaixar um dono: diálogo destrutivo com senha; o último dono é recusado com o texto do servidor no diálogo, e a lista é relida ao fechar', async () => {
  const OUTRO = pessoa(ID.davi, 'Davi Melo', 'dono');
  let listagens = 0;
  const {mesa} = await abrirEquipe({api: (op) => {
    if (op === 'equipe-listar') { listagens += 1; return equipeListar([ANA(), OUTRO]); }
    if (op === 'equipe-papel') return recusa('ultimo_dono', 'A redação precisa de ao menos um dono ativo.');
    return undefined;
  }});
  mudar(celulas(linhaDe(mesa, ID.davi))[1].querySelector('select'), 'editor'); await esperar(mesa);
  assert.equal(dialogo(mesa).querySelector('.dialogo-titulo').textContent, 'Mudar o papel de Davi Melo para Editor?');
  assert.equal(dialogo(mesa).dataset.variante, 'destrutivo'); assert.equal(acoesDoDialogo(mesa)[1].textContent, 'Mudar papel');
  assert.ok(texto(dialogo(mesa)).includes('Davi Melo deixa de administrar a redação e passa a ver só as apurações de que participa. Vale na próxima ação.'));
  digitar(dialogo(mesa).querySelector('input'), 'senha'); acoesDoDialogo(mesa)[1].click(); await esperar(mesa);
  assert.equal(texto(dialogo(mesa).querySelector('.dialogo-erro[role="alert"]')), 'A redação precisa de ao menos um dono ativo.');
  const antes = listagens;
  acoesDoDialogo(mesa)[0].click(); await esperar(mesa);
  assert.ok(listagens > antes, 'ao fechar, a lista recarrega');
  assert.equal(celulas(linhaDe(mesa, ID.davi))[1].querySelector('select').value, 'dono');
});

test('mudar o papel sem dono, recusado pelo servidor: o texto vai à linha de estado, em tom de erro e role=alert, e a caixa volta ao papel anterior', async () => {
  const {mesa} = await abrirEquipe({api: (op) => {
    if (op === 'equipe-listar') return equipeListar([ANA(), RUI()]);
    if (op === 'equipe-papel') return recusa('papel_invalido', 'Papel de acesso inválido.');
    return undefined;
  }});
  mudar(celulas(linhaDe(mesa, ID.rui))[1].querySelector('select'), 'leitor'); await esperar(mesa);
  assert.equal(texto(estado(mesa)), 'Papel de acesso inválido.'); assert.equal(estado(mesa).getAttribute('role'), 'alert'); assert.equal(estado(mesa).dataset.tom, 'erro');
  assert.equal(celulas(linhaDe(mesa, ID.rui))[1].querySelector('select').value, 'reporter'); assert.ok(!celulas(linhaDe(mesa, ID.rui))[1].querySelector('select').disabled);
});

test('o perfil antigo: converter pergunta antes, com o texto do desenho, e só então envia o papel (princípio 9)', async () => {
  const {mesa} = await abrirEquipe({api: (op, d) => {
    if (op === 'equipe-listar') return equipeListar([ANA(), CORA()]);
    if (op === 'equipe-papel') return {conta: CORA({papel: d.papel})};
    return undefined;
  }});
  mudar(celulas(linhaDe(mesa, ID.cora))[1].querySelector('select'), 'leitor'); await esperar(mesa);
  assert.equal(dialogo(mesa).querySelector('.dialogo-titulo').textContent, 'Converter Cora Dias em Leitor?');
  assert.ok(texto(dialogo(mesa)).includes('Leitor lê também o caderno, os achados e o texto das apurações de que participa.'));
  assert.equal(acoesDoDialogo(mesa)[1].textContent, 'Converter'); assert.equal(dialogo(mesa).querySelector('input'), null, 'sem senha: leitor não é dono');
  assert.equal(mesa.chamadas.filter(c => c.operacao === 'equipe-papel').length, 0);
  acoesDoDialogo(mesa)[1].click(); await esperar(mesa);
  assert.deepEqual(dados(mesa.chamadas.find(c => c.operacao === 'equipe-papel').dados), {conta: ID.cora, papel: 'leitor'});
  assert.equal(texto(estado(mesa)), '✓ Cora Dias agora é Leitor. Vale na próxima ação.');
});

test('Gerenciar: botão com aria-expanded e aria-controls, só nas outras linhas; abre três blocos; apurações com "responsável" sem Retirar, Retirar e Incluir', async () => {
  let rui = RUI({casos: ['alfa', 'beta']});
  const {mesa} = await abrirEquipe({api: (op, d) => {
    if (op === 'equipe-listar') return equipeListar([ANA(), rui]);
    if (op === 'caso-retirar') { rui = RUI({casos: ['alfa'] }); return {};}
    if (op === 'caso-incluir') { rui = RUI({casos: ['alfa', 'beta', d.caso]}); return {}; }
    return undefined;
  }});
  assert.equal(botaoPorTexto(celulas(linhaDe(mesa, ID.ana))[4], 'Gerenciar'), undefined, 'a própria linha não tem Gerenciar');
  let gerenciar = celulas(linhaDe(mesa, ID.rui))[4].querySelector('button');
  assert.equal(gerenciar.getAttribute('aria-expanded'), 'false');
  gerenciar.click(); await esperar(mesa);
  gerenciar = celulas(linhaDe(mesa, ID.rui))[4].querySelector('button');
  assert.equal(gerenciar.getAttribute('aria-expanded'), 'true');
  const painel = mesa.$(gerenciar.getAttribute('aria-controls')); assert.ok(painel);
  assert.deepEqual([...painel.querySelectorAll('.equipe-bloco-titulo')].map(h => h.textContent), ['APURAÇÕES', 'TETO MENSAL', 'ACESSO']);
  const casos = [...painel.querySelectorAll('.equipe-caso')];
  assert.equal(casos.length, 2);
  assert.ok(texto(casos[0]).includes('Pauta Alfa') && texto(casos[0]).includes('responsável') && casos[0].querySelector('button') === null, 'o responsável não sai por aqui');
  assert.ok(texto(painel).includes('Quem é responsável não sai da apuração por aqui.'));
  botaoPorTexto(casos[1], 'Retirar').click(); await esperar(mesa);
  assert.deepEqual(dados(mesa.chamadas.find(c => c.operacao === 'caso-retirar').dados), {caso: 'beta', conta: ID.rui});
  assert.equal(texto(estado(mesa)), '✓ Rui Castro não participa mais de Campo Verde.');
  const incluirEm = mesa.$(gerenciar.getAttribute('aria-controls')).querySelector('select');
  assert.deepEqual([...incluirEm.querySelectorAll('option')].map(o => o.value), ['beta', 'gama', 'delta'], 'só as apurações em que a pessoa ainda não está');
  incluirEm.value = 'gama';
  botaoPorTexto(mesa.$(gerenciar.getAttribute('aria-controls')), 'Incluir').click(); await esperar(mesa);
  assert.deepEqual(dados(mesa.chamadas.find(c => c.operacao === 'caso-incluir').dados), {caso: 'gama', conta: ID.rui});
  assert.equal(texto(estado(mesa)), '✓ Rui Castro agora participa de Pauta Gama.');
});

test('Gerenciar um dono: "Todas as apurações da redação." e nada de Retirar nem Incluir', async () => {
  const {mesa} = await abrirEquipe(com([ANA(), pessoa(ID.davi, 'Davi Melo', 'dono')]));
  celulas(linhaDe(mesa, ID.davi))[4].querySelector('button').click(); await esperar(mesa);
  const painel = mesa.$(`equipe-gerenciar-${ID.davi}`);
  assert.ok(texto(painel).includes('Todas as apurações da redação.'));
  assert.equal(botaoPorTexto(painel, 'Retirar'), undefined); assert.equal(botaoPorTexto(painel, 'Incluir'), undefined);
});

test('Teto mensal: aceita 30 e 30,50 e envia texto com ponto; "Usar o padrão" envia null; a recusa do servidor fica abaixo do campo', async () => {
  let rui = RUI();
  let recusar = false;
  const {mesa} = await abrirEquipe({api: (op, d) => {
    if (op === 'equipe-listar') return equipeListar([ANA(), rui]);
    if (op === 'equipe-teto') { if (recusar) return recusa('requisicao_invalida', 'O teto por pessoa não pode passar do teto da redação (R$ 150,00).'); rui = RUI({teto_mensal_brl: d.teto_brl}); return {conta: rui}; }
    return undefined;
  }});
  celulas(linhaDe(mesa, ID.rui))[4].querySelector('button').click(); await esperar(mesa);
  const painel = () => mesa.$(`equipe-gerenciar-${ID.rui}`);
  const campo = () => painel().querySelector('.equipe-teto-campo');
  assert.equal(campo().getAttribute('inputmode'), 'decimal');
  assert.ok(texto(painel()).includes('Padrão da redação: R$ 50. Não passa do teto da redação.'));
  assert.equal(botaoPorTexto(painel(), 'Usar o padrão'), undefined, 'sem teto próprio, sem "Usar o padrão"');
  digitar(campo(), '30,50'); botaoPorTexto(painel(), 'Salvar').click(); await esperar(mesa);
  assert.deepEqual(dados(mesa.chamadas.find(c => c.operacao === 'equipe-teto').dados), {conta: ID.rui, teto_brl: '30.50'});
  assert.equal(typeof mesa.chamadas.find(c => c.operacao === 'equipe-teto').dados.teto_brl, 'string', 'nunca como número');
  assert.equal(texto(estado(mesa)), '✓ Teto de Rui Castro salvo.');
  assert.ok(botaoPorTexto(painel(), 'Usar o padrão'), 'com teto próprio, o link aparece');
  assert.equal(campo().value, '30,50', 'o campo mostra o valor guardado');
  botaoPorTexto(painel(), 'Usar o padrão').click(); await esperar(mesa);
  const ultima = mesa.chamadas.filter(c => c.operacao === 'equipe-teto').at(-1);
  assert.deepEqual(dados(ultima.dados), {conta: ID.rui, teto_brl: null});
  digitar(campo(), ''); botaoPorTexto(painel(), 'Salvar').click(); await esperar(mesa);
  assert.equal(texto(painel().querySelector('.campo-erro')), 'Falta o teto. Escreva o valor em reais ou use o padrão.');
  recusar = true; digitar(campo(), '999'); botaoPorTexto(painel(), 'Salvar').click(); await esperar(mesa);
  assert.equal(texto(painel().querySelector('.campo-erro')), 'O teto por pessoa não pode passar do teto da redação (R$ 150,00).');
});

test('Acesso: desativar sem ser dono é a destrutiva sem senha; desativar um dono e remover pedem a senha; reativar é direto', async () => {
  let pessoas = [ANA(), RUI(), pessoa(ID.davi, 'Davi Melo', 'dono'), CORA({papel: 'leitor', situacao: 'desativada', ativa: false})];
  const {mesa} = await abrirEquipe({api: (op, d) => {
    if (op === 'equipe-listar') return equipeListar(pessoas);
    if (op === 'equipe-desativar' || op === 'equipe-remover') return {conta: {id: d.conta}};
    if (op === 'equipe-reativar') { pessoas = pessoas.map(p => (p.id === d.conta ? {...p, ativa: true, situacao: 'ativa'} : p)); return {conta: {id: d.conta}}; }
    return undefined;
  }});
  const abrirGerenciar = async id => {
    if (!mesa.$(`equipe-gerenciar-${id}`)) { celulas(linhaDe(mesa, id))[4].querySelector('button').click(); await esperar(mesa); }
    return mesa.$(`equipe-gerenciar-${id}`);
  };
  let painel = await abrirGerenciar(ID.rui);
  assert.ok(texto(painel).includes('Desativar encerra as sessões e para as perguntas em curso; as apurações ficam. Remover exclui a conta.'));
  botaoPorTexto(painel, 'Desativar').click(); await esperar(mesa);
  assert.equal(dialogo(mesa).querySelector('.dialogo-titulo').textContent, 'Desativar a conta de Rui Castro?'); assert.equal(dialogo(mesa).dataset.variante, 'destrutivo');
  assert.equal(dialogo(mesa).querySelector('input'), null, 'sem ser dono, sem senha');
  assert.ok(texto(dialogo(mesa)).includes('A pessoa sai na próxima ação e as perguntas em curso dessa conta param.'));
  assert.equal(acoesDoDialogo(mesa)[0].textContent, 'Cancelar'); assert.ok(mesa.doc.activeElement === acoesDoDialogo(mesa)[0], 'o foco inicial da destrutiva fica em Cancelar');
  acoesDoDialogo(mesa)[1].click(); await esperar(mesa);
  assert.deepEqual(dados(mesa.chamadas.find(c => c.operacao === 'equipe-desativar').dados), {conta: ID.rui});
  assert.equal(texto(estado(mesa)), '✓ A conta de Rui Castro foi desativada.');
  painel = await abrirGerenciar(ID.davi);
  botaoPorTexto(painel, 'Desativar').click(); await esperar(mesa);
  assert.ok(dialogo(mesa).querySelector('input'), 'desativar um dono pede a senha');
  digitar(dialogo(mesa).querySelector('input'), 'sx'); acoesDoDialogo(mesa)[1].click(); await esperar(mesa);
  assert.deepEqual(dados(mesa.chamadas.filter(c => c.operacao === 'equipe-desativar').at(-1).dados), {conta: ID.davi, senha: 'sx'});
  painel = await abrirGerenciar(ID.davi);
  botaoPorTexto(painel, 'Remover da redação').click(); await esperar(mesa);
  assert.equal(dialogo(mesa).querySelector('.dialogo-titulo').textContent, 'Remover Davi Melo da redação?');
  assert.ok(texto(dialogo(mesa)).includes('A conta é excluída: a pessoa perde o acesso') && texto(dialogo(mesa)).includes('que não podem ser reescritos.'));
  digitar(dialogo(mesa).querySelector('input'), 'sy'); acoesDoDialogo(mesa)[1].click(); await esperar(mesa);
  assert.deepEqual(dados(mesa.chamadas.find(c => c.operacao === 'equipe-remover').dados), {conta: ID.davi, senha: 'sy'});
  assert.equal(texto(estado(mesa)), '✓ Davi Melo foi removida da redação.');
  painel = await abrirGerenciar(ID.cora);
  assert.equal(botaoPorTexto(painel, 'Desativar'), undefined, 'conta desativada: Reativar no lugar de Desativar'); assert.ok(botaoPorTexto(painel, 'Remover da redação'));
  botaoPorTexto(painel, 'Reativar').click(); await esperar(mesa);
  assert.equal(dialogo(mesa), null, 'reativar é direto');
  assert.deepEqual(dados(mesa.chamadas.find(c => c.operacao === 'equipe-reativar').dados), {conta: ID.cora});
});

test('desativar sem ser dono, mas o servidor pede a senha mesmo assim (403 senha_necessaria): o diálogo com senha abre e reenvia', async () => {
  const {mesa} = await abrirEquipe({api: (op, d) => {
    if (op === 'equipe-listar') return equipeListar([ANA(), RUI()]);
    if (op === 'equipe-desativar') return d.senha ? {conta: {id: d.conta}} : recusa('senha_necessaria', 'Digite a sua senha para confirmar.', 'proibido');
    return undefined;
  }});
  celulas(linhaDe(mesa, ID.rui))[4].querySelector('button').click(); await esperar(mesa);
  botaoPorTexto(mesa.$(`equipe-gerenciar-${ID.rui}`), 'Desativar').click(); await esperar(mesa);
  acoesDoDialogo(mesa)[1].click(); await esperar(mesa);   // a destrutiva sem senha
  assert.ok(dialogo(mesa).querySelector('input'), 'agora com o campo da senha');
  digitar(dialogo(mesa).querySelector('input'), 'sz'); acoesDoDialogo(mesa)[1].click(); await esperar(mesa);
  const envios = mesa.chamadas.filter(c => c.operacao === 'equipe-desativar');
  assert.deepEqual(envios.map(c => dados(c.dados)), [{conta: ID.rui}, {conta: ID.rui, senha: 'sz'}]);
});

test('Gasto com IA neste mês: valor e medidor; sem o gasto da redação, o texto de apoio; o teto padrão envia null quando vazio', async () => {
  const f = await abrirEquipe(com([ANA(), RUI()]));
  const cartao = f.mesa.doc.querySelector('[data-cartao="gasto"]');
  assert.ok(texto(cartao).includes('R$ 24,50 de R$ 150')); assert.equal(cartao.querySelector('.mesa-medidor').getAttribute('aria-label'), '16% da cota usada');
  assert.ok(texto(cartao).includes('Cota da redação, definida por quem administra o serviço.'));
  const campo = cartao.querySelector('input'); assert.equal(campo.value, '50');
  digitar(campo, ''); botaoPorTexto(cartao, 'Salvar').click(); await esperar(f.mesa);
  assert.deepEqual(dados(f.mesa.chamadas.find(c => c.operacao === 'equipe-teto').dados), {teto_brl: null});
  assert.ok(texto(cartao).includes('Vazio quer dizer o teto da instalação.'));
  const nulo = await abrirEquipe(com([ANA(), RUI()], {gasto: null}));
  const cartaoNulo = nulo.mesa.doc.querySelector('[data-cartao="gasto"]');
  assert.ok(texto(cartaoNulo).includes('O gasto da redação aparece aqui quando o serviço passar a contá-lo por redação. O de cada pessoa está na tabela.'));
  assert.equal(cartaoNulo.querySelector('.mesa-medidor'), null);
});

test('Atividade recente: cinco últimas, uma frase por evento, "Mostrar mais" traz 50 pelo cursor opaco que o servidor deu', async () => {
  const evento = (n, tipo, extra = {}) => ({n, em: new Date(Date.now() - n * 3600000).toISOString(), tipo, conta: ID.rui, por: ID.ana, conta_nome: 'Rui Castro', por_nome: 'Ana Lima', ...extra});
  const primeiros = Array.from({length: 5}, (_, i) => evento(20 - i, 'papel_alterado'));
  const maisUm = Array.from({length: 3}, (_, i) => evento(10 - i, 'conta_desativada'));
  const {mesa} = await abrirEquipe({api: (op, d) => {
    if (op === 'equipe-listar') return equipeListar([ANA(), RUI()]);
    if (op === 'equipe-atividade') return d.antes === undefined ? {eventos: primeiros, proximo: 'cursor-opaco-xyz'} : {eventos: maisUm, proximo: null};
    return undefined;
  }});
  const cartao = mesa.doc.querySelector('[data-cartao="atividade"]');
  assert.equal(dados(mesa.chamadas.find(c => c.operacao === 'equipe-atividade').dados).limite, 5);
  assert.equal(cartao.querySelectorAll('.equipe-atividade-item').length, 5);
  assert.equal(texto(cartao.querySelector('.equipe-atividade-item .equipe-frase')), 'Ana Lima mudou o papel de Rui Castro');
  botaoPorTexto(cartao, 'Mostrar mais').click(); await esperar(mesa);
  const segunda = mesa.chamadas.filter(c => c.operacao === 'equipe-atividade').at(-1);
  assert.deepEqual(dados(segunda.dados), {limite: 50, antes: 'cursor-opaco-xyz'}, 'o cursor volta como veio');
  assert.equal(cartao.querySelectorAll('.equipe-atividade-item').length, 8);
  assert.equal(botaoPorTexto(cartao, 'Mostrar mais'), undefined, 'sem `proximo`, sem o botão');
});

test('Atividade: cada tipo que o servidor grava tem frase (nenhum cai em "Ação de administração"); quem não tem frase cai nela; operador, conta removida e a mesma conta', async () => {
  const TIPOS = ['papel_alterado', 'conta_desativada', 'conta_reativada', 'conta_excluida', 'conta_criada', 'participacao_incluida', 'participacao_retirada', 'responsavel_alterado',
    'teto_alterado', 'senha_trocada', 'senha_definida', 'sessao_encerrada_a_distancia', 'conta_atualizada', 'recuperacao_emitida', 'login_bloqueado', 'sessao_encerrada',
    'acesso_alterado', 'caso_atribuido', 'caso_criado', 'primeiro_admin', 'migracao_contas', 'redacao_criada', 'redacao_suspensa', 'redacao_reativada', 'redacao_encerrada'];
  const {mesa} = await abrirEquipe(com([ANA(), RUI()]));
  const {Equipe} = mesa.janela;
  const base = {conta: ID.rui, por: ID.ana, conta_nome: 'Rui Castro', por_nome: 'Ana Lima'};
  for (const tipo of TIPOS) assert.notEqual(texto(Equipe.frase({...base, tipo})), 'Ação de administração', tipo);
  assert.equal(texto(Equipe.frase({...base, tipo: 'tipo_que_ninguem_previu'})), 'Ação de administração');
  assert.equal(texto(Equipe.frase({...base, tipo: 'conta_desativada'})), 'Ana Lima desativou a conta de Rui Castro');
  assert.equal(texto(Equipe.frase({...base, tipo: 'senha_trocada', por: ID.rui, por_nome: 'Rui Castro'})), 'Rui Castro trocou a senha');
  assert.equal(texto(Equipe.frase({...base, tipo: 'conta_excluida', conta_nome: null})), 'Ana Lima removeu uma conta removida da redação');
  assert.equal(texto(Equipe.frase({...base, tipo: 'papel_alterado', por: 'operador', por_nome: null})), 'Quem administra o serviço mudou o papel de Rui Castro');
  assert.equal(texto(Equipe.frase({...base, tipo: 'conta_criada', por: null, por_nome: null})), 'Quem administra o serviço criou a conta de Rui Castro');
  assert.equal(texto(Equipe.frase({...base, tipo: 'papel_alterado', por: 'f'.repeat(16), por_nome: null})), 'uma conta removida mudou o papel de Rui Castro');
  assert.equal(texto(Equipe.frase({...base, tipo: 'caso_atribuido', conta: null, conta_nome: null, por: 'operador', por_nome: null})), 'Quem administra o serviço atribuiu uma apuração a uma pessoa');
  const hostil = Equipe.frase({...base, tipo: 'conta_criada', conta_nome: '<img src=x onerror=alert(1)>'});
  assert.equal(hostil.querySelector('img'), null, 'o nome entra como texto');
});

test('sem atividade: "Nenhuma ação registrada ainda."; sem Convidar: só o texto da exceção abaixo da tabela, e nenhum botão de convite', async () => {
  const {mesa} = await abrirEquipe(com([ANA()]));
  assert.equal(texto(mesa.doc.querySelector('[data-cartao="atividade"] .conta-cartao-corpo')), 'Nenhuma ação registrada ainda.');
  assert.equal(texto(painelEquipe(mesa).querySelector('.equipe-convite')), 'Para incluir alguém na redação, fale com quem administra o serviço.');
  assert.ok(![...painelEquipe(mesa).querySelectorAll('button')].some(b => /convid|recuperar/i.test(b.textContent)), 'sem Convidar, Reenviar nem Recuperar acesso');
});

test('abaixo de 1024 px a tabela vira um cartão por pessoa, com "Papel" visível, apurações e uso em 14 e "Gerenciar" em largura cheia', async () => {
  const {mesa} = await abrirEquipe({...com([ANA(), RUI()]), desktop: false});
  assert.equal(mesa.doc.querySelector('.equipe-tabela'), null);
  const cartoes = [...mesa.doc.querySelectorAll('.equipe-cartao')];
  assert.equal(cartoes.length, 2);
  const rui = cartoes.find(c => c.dataset.conta === ID.rui);
  assert.ok(texto(rui).includes('Rui Castro') && texto(rui).includes('Papel') && texto(rui).includes('Apurações:') && texto(rui).includes('Uso no mês: R$ 18,40'));
  assert.ok(rui.querySelector('select')); assert.ok(rui.querySelector('button.secondary'), 'Gerenciar secundário');
  assert.equal(botaoPorTexto(cartoes.find(c => c.dataset.conta === ID.ana), 'Gerenciar'), undefined);
  botaoPorTexto(rui, 'Gerenciar').click(); await esperar(mesa);
  assert.ok(mesa.$(`equipe-gerenciar-${ID.rui}`), 'o painel abre dentro do cartão');
});

test('nomes e e-mails do servidor entram como texto: nada de HTML na tabela, e o e-mail não se traduz', async () => {
  const {mesa} = await abrirEquipe(com([ANA(), pessoa(ID.rui, '<b onmouseover=x>Rui</b>', 'reporter', {email: '"><script>alert(1)</script>@x.org'})]));
  assert.equal(mesa.doc.querySelector('.equipe-tabela b'), null); assert.equal(mesa.doc.querySelector('.equipe-tabela script'), null);
  assert.ok(texto(linhaDe(mesa, ID.rui)).includes('<b onmouseover=x>Rui</b>'));
  assert.equal(celulas(linhaDe(mesa, ID.rui))[0].querySelector('p.conta-apoio').getAttribute('translate'), 'no');
});

test('em inglês: título, cabeçalhos, estados e frases da atividade saem em inglês', async () => {
  const evento = {n: 3, em: new Date().toISOString(), tipo: 'papel_alterado', conta: ID.rui, por: ID.ana, conta_nome: 'Rui Castro', por_nome: 'Ana Lima'};
  const {mesa} = await abrirEquipe({...com([ANA(), RUI(), CORA()]), idioma: 'en', api: op => (op === 'equipe-listar' ? equipeListar([ANA(), RUI(), CORA()]) : op === 'equipe-atividade' ? {eventos: [evento], proximo: null} : undefined)});
  await mesa.esperar(30);
  assert.equal(mesa.$('area-descricao').textContent, '3 people');
  assert.deepEqual([...mesa.doc.querySelectorAll('.equipe-tabela th')].map(th => th.textContent), ['Person', 'Role', 'Investigations', 'Usage this month', 'Actions']);
  assert.ok(texto(linhaDe(mesa, ID.ana)).includes('(you)'));
  assert.ok(texto(painelEquipe(mesa)).includes('Ana Lima changed the role of Rui Castro'));
  assert.ok(texto(painelEquipe(mesa)).includes('1 person still has the old guest profile'));
  assert.equal(celulas(linhaDe(mesa, ID.cora))[1].querySelector('option').textContent, 'Guest (old profile)');
});
