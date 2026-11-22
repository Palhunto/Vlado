'use strict';
// Minha conta (W08; docs/design/componentes.md#minha-conta): o perfil da barra abre a página, os cinco cartões, mudar o nome, trocar a senha no diálogo
// com senha, as sessões abertas (encerrar sem diálogo), o uso do mês em reais, idioma e tema. Os textos que vêm do servidor entram como texto, nunca como HTML.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa} = require('./dom_minimo.cjs');
const {SCRIPTS, abrir, esperar, texto, digitar, mudar, botaoPorTexto, dialogo, dados, tecla, recusa, sessaoDe, contaVer, sessaoItem, DIA} = require('./contas_apoio.cjs');

const cartao = (mesa, nome) => mesa.doc.querySelector(`[data-cartao="${nome}"]`);
const estado = mesa => mesa.doc.querySelector('.conta-estado');
const SESSOES = [sessaoItem('b'.repeat(16), 'Firefox · Linux', false), sessaoItem('s'.repeat(16), 'Edge · Windows', true, new Date().toISOString(), '127.0.0.1')];

test('o perfil da barra abre Minha conta, leva aria-current e nenhum item de área fica selecionado; sem contas (modo local) não há perfil', async () => {
  const {mesa} = abrir({url: 'http://127.0.0.1:8765/?area=inicio'});
  await esperar(mesa);
  const perfil = mesa.$('ver-configuracoes');
  assert.ok(!perfil.hidden, 'toda conta tem o perfil, não só o dono');
  assert.ok(mesa.$('area-configuracoes').hidden);
  perfil.click(); await esperar(mesa);
  assert.ok(!mesa.$('area-configuracoes').hidden);
  assert.equal(perfil.getAttribute('aria-current'), 'page');
  assert.equal(mesa.$('conta-aba-conta').getAttribute('aria-pressed'), 'true'); assert.ok(!mesa.$('conta-painel-conta').hidden);
  assert.equal(mesa.$('area-titulo').textContent, 'Minha conta');
  for (const area of ['inicio', 'codex', 'achados', 'apuracao']) assert.notEqual(mesa.$(`ver-${area}`).getAttribute('aria-current'), 'page');
  mesa.$('ver-codex').click(); await esperar(mesa);
  assert.equal(perfil.getAttribute('aria-current'), null, 'sai da página: o perfil deixa de ser a página atual');
  const local = criarMesa({modo: 'local', url: 'http://127.0.0.1:8765/?area=inicio', scripts: SCRIPTS});
  await local.esperar(10);
  assert.equal(local.janela.Conta, undefined, 'no modo local conta.js não faz nada');
});

test('o dono vê as três abas, na ordem; quem não é dono vê só Minha conta, sem a linha de abas', async () => {
  const dono = abrir(); await esperar(dono.mesa);
  const abas = [...dono.mesa.doc.querySelectorAll('.conta-abas button')].filter(b => !b.hidden).map(b => b.textContent);
  assert.deepEqual(abas, ['Minha conta', 'Equipe', 'Configurações']);
  const reporter = abrir({papel: 'reporter'}); await esperar(reporter.mesa);
  assert.ok(reporter.mesa.doc.querySelector('.conta-abas').hidden, 'sem a linha de abas');
  assert.ok(!reporter.mesa.$('area-configuracoes').hidden, 'a página abre mesmo assim: o repórter também tem Minha conta');
  assert.ok(!reporter.mesa.$('conta-painel-conta').hidden);
  assert.ok(reporter.mesa.$('conta-painel-equipe').hidden);
});

test('Perfil: nome, e-mail, papel e redação; sem e-mail, "login ana.lima"; os dados do servidor entram como texto', async () => {
  const HOSTIL = '<img src=x onerror=alert(1)> "Ana"';
  const {mesa} = abrir({api: op => (op === 'conta-ver' ? contaVer('reporter', {nome: HOSTIL}) : undefined), papel: 'reporter'});
  await esperar(mesa);
  const perfil = cartao(mesa, 'perfil');
  assert.equal(texto(perfil.querySelector('strong')), HOSTIL.replace(/\s+/g, ' '));
  assert.equal(perfil.querySelector('img'), null, 'nenhum HTML do servidor vira elemento');
  assert.ok(texto(perfil).includes('ana@redacao.org')); assert.ok(texto(perfil).includes('Repórter · Redação Serena'));
  assert.equal(perfil.querySelector('strong').getAttribute('translate'), 'no');
  const migrada = abrir({api: op => (op === 'conta-ver' ? contaVer('dono', {email: null, login: 'ana.lima'}) : undefined)});
  await esperar(migrada.mesa);
  assert.ok(texto(cartao(migrada.mesa, 'perfil')).includes('login ana.lima')); assert.ok(!texto(cartao(migrada.mesa, 'perfil')).includes('@'));
});

test('Mudar nome: campo preenchido, em branco recusa junto ao campo, salvar manda `nome` e atualiza a barra; recusa do servidor abaixo do campo', async () => {
  const {mesa} = abrir({api: (op, d) => (op === 'conta-atualizar' ? contaVer('dono', {nome: d.nome}) : undefined)});
  await esperar(mesa);
  botaoPorTexto(cartao(mesa, 'perfil'), 'Mudar nome').click();
  const campo = cartao(mesa, 'perfil').querySelector('input');
  assert.equal(campo.value, 'Ana Lima'); assert.equal(campo.maxLength, 120); assert.ok(mesa.doc.activeElement === campo);
  digitar(campo, '   ');
  botaoPorTexto(cartao(mesa, 'perfil'), 'Salvar').click(); await esperar(mesa);
  assert.equal(texto(cartao(mesa, 'perfil').querySelector('.campo-erro')), 'Falta o nome. Escreva o seu nome.');
  assert.equal(mesa.chamadas.filter(c => c.operacao === 'conta-atualizar').length, 0);
  digitar(campo, 'Ana Maria Lima');
  botaoPorTexto(cartao(mesa, 'perfil'), 'Salvar').click(); await esperar(mesa);
  assert.deepEqual(dados(mesa.chamadas.find(c => c.operacao === 'conta-atualizar').dados), {nome: 'Ana Maria Lima'});
  assert.equal(texto(cartao(mesa, 'perfil').querySelector('strong')), 'Ana Maria Lima');
  assert.equal(texto(estado(mesa)), '✓ Nome atualizado.');
  assert.equal(texto(mesa.doc.querySelector('.mesa-perfil-nome')), 'Ana Maria Lima', 'o perfil da barra acompanha');
  const recusado = abrir({api: op => (op === 'conta-atualizar' ? recusa('requisicao_invalida', 'O nome deve ter de 1 a 120 caracteres.') : undefined)});
  await esperar(recusado.mesa);
  botaoPorTexto(cartao(recusado.mesa, 'perfil'), 'Mudar nome').click();
  botaoPorTexto(cartao(recusado.mesa, 'perfil'), 'Salvar').click(); await esperar(recusado.mesa);
  assert.equal(texto(cartao(recusado.mesa, 'perfil').querySelector('.campo-erro')), 'O nome deve ter de 1 a 120 caracteres.');
  botaoPorTexto(cartao(recusado.mesa, 'perfil'), 'Cancelar').click();
  assert.ok(botaoPorTexto(cartao(recusado.mesa, 'perfil'), 'Mudar nome'), 'Cancelar volta ao nome');
});

test('Entrada e segurança: "definida há 12 dias" (ou "hoje"), só a senha, sem segundo fator nem chave de acesso', async () => {
  const {mesa} = abrir(); await esperar(mesa);
  const seguranca = cartao(mesa, 'seguranca');
  assert.ok(texto(seguranca).includes('Senha') && texto(seguranca).includes('definida há 12 dias'));
  assert.ok(botaoPorTexto(seguranca, 'Trocar senha'));
  assert.ok(!/segundo fator|autenticador|chave de acesso|códigos/i.test(texto(seguranca)), 'as linhas ainda sem servidor ficam fora (exceções declaradas)');
  const hoje = abrir({api: op => (op === 'conta-ver' ? contaVer('dono', {}, 0) : undefined)}); await esperar(hoje.mesa);
  assert.ok(texto(cartao(hoje.mesa, 'seguranca')).includes('definida hoje'));
  const ontem = abrir({api: op => (op === 'conta-ver' ? contaVer('dono', {}, 1) : undefined)}); await esperar(ontem.mesa);
  assert.ok(texto(cartao(ontem.mesa, 'seguranca')).includes('definida há 1 dia'));
});

test('Trocar senha: três campos, conferência antes de enviar, envia senha_atual e senha_nova; sucesso fecha, recarrega as sessões e diz quantas saíram', async () => {
  let sessoes = SESSOES;
  const {mesa} = abrir({api: (op, d) => {
    if (op === 'conta-sessoes') return {sessoes};
    if (op === 'conta-senha-trocar') { sessoes = [SESSOES[1]]; return {estado: 'senha_trocada', sessoes_encerradas: 1}; }
    return undefined;
  }});
  await esperar(mesa);
  botaoPorTexto(cartao(mesa, 'seguranca'), 'Trocar senha').click(); await esperar(mesa);
  const caixa = dialogo(mesa);
  assert.equal(caixa.querySelector('.dialogo-titulo').textContent, 'Trocar senha');
  assert.ok(texto(caixa).includes('As outras sessões desta conta serão encerradas. Esta continua aberta.'));
  const campos = [...caixa.querySelectorAll('input')];
  assert.deepEqual(campos.map(c => c.autocomplete), ['current-password', 'new-password', 'new-password']); assert.ok(campos.every(c => c.type === 'password'));
  assert.ok(texto(caixa).includes('De 12 a 256 caracteres. Pode colar ou usar o gerenciador de senhas.'));
  const acao = [...caixa.querySelectorAll('.dialogo-acoes button')][1];
  acao.click(); await esperar(mesa);
  const erros = () => [...caixa.querySelectorAll('.dialogo-erro-campo')].filter(p => !p.hidden).map(p => p.textContent);
  assert.deepEqual(erros(), ['Falta a senha atual. Digite a senha com que você entra hoje.', 'A senha deve ter de 12 a 256 caracteres.']);
  digitar(campos[0], 'senha-de-hoje'); digitar(campos[1], 'nova-senha-longa-1'); digitar(campos[2], 'nova-senha-longa-2');
  acao.click(); await esperar(mesa);
  assert.deepEqual(erros(), ['As duas senhas não coincidem. Digite a mesma senha nos dois campos.']);
  assert.equal(mesa.chamadas.filter(c => c.operacao === 'conta-senha-trocar').length, 0, 'nada foi enviado');
  digitar(campos[2], 'nova-senha-longa-1');
  acao.click(); await esperar(mesa);
  assert.deepEqual(dados(mesa.chamadas.find(c => c.operacao === 'conta-senha-trocar').dados), {senha_atual: 'senha-de-hoje', senha_nova: 'nova-senha-longa-1'});
  assert.equal(dialogo(mesa), null, 'o diálogo fecha');
  assert.equal(texto(estado(mesa)), '✓ Senha trocada. 1 outra sessão foi encerrada.');
  assert.equal(cartao(mesa, 'sessoes').querySelectorAll('li').length, 1, 'a lista de sessões recarrega');
});

test('Trocar senha: senha atual incorreta vai ao campo, bloqueio deixa só Cancelar, e a mensagem de "nenhuma outra sessão" e o plural', async () => {
  let resposta = recusa('senha_atual_incorreta', 'Senha incorreta.', 'proibido');
  const {mesa} = abrir({api: op => (op === 'conta-senha-trocar' ? resposta : undefined)});
  await esperar(mesa);
  const abrirDialogo = async () => { botaoPorTexto(cartao(mesa, 'seguranca'), 'Trocar senha').click(); await esperar(mesa); return [...dialogo(mesa).querySelectorAll('input')]; };
  const preencher = campos => { digitar(campos[0], 'senha-de-hoje'); digitar(campos[1], 'nova-senha-longa-1'); digitar(campos[2], 'nova-senha-longa-1'); };
  let campos = await abrirDialogo(); preencher(campos);
  [...dialogo(mesa).querySelectorAll('.dialogo-acoes button')][1].click(); await esperar(mesa);
  assert.equal(texto(dialogo(mesa).querySelector('.dialogo-erro-campo')), 'Senha atual incorreta. Confira e tente de novo.');
  assert.equal(campos[0].value, '', 'a senha atual é limpa'); assert.ok(mesa.doc.activeElement === campos[0]);
  assert.equal(campos[1].value, 'nova-senha-longa-1', 'a nova senha fica');
  resposta = recusa('bloqueado', 'Muitas tentativas.', 'bloqueado');
  digitar(campos[0], 'outra'); [...dialogo(mesa).querySelectorAll('.dialogo-acoes button')][1].click(); await esperar(mesa);
  assert.ok(texto(dialogo(mesa).querySelector('.dialogo-erro[role="alert"]')).startsWith('Muitas senhas erradas seguidas. Por 15 minutos'));
  assert.ok([...dialogo(mesa).querySelectorAll('.dialogo-acoes button')][1].disabled);
  [...dialogo(mesa).querySelectorAll('.dialogo-acoes button')][0].click(); await esperar(mesa);
  resposta = {estado: 'senha_trocada', sessoes_encerradas: 0};
  campos = await abrirDialogo(); preencher(campos);
  [...dialogo(mesa).querySelectorAll('.dialogo-acoes button')][1].click(); await esperar(mesa);
  assert.equal(texto(estado(mesa)), '✓ Senha trocada. Nenhuma outra sessão estava aberta.');
  resposta = {estado: 'senha_trocada', sessoes_encerradas: 3};
  campos = await abrirDialogo(); preencher(campos);
  [...dialogo(mesa).querySelectorAll('.dialogo-acoes button')][1].click(); await esperar(mesa);
  assert.equal(texto(estado(mesa)), '✓ Senha trocada. 3 outras sessões foram encerradas.');
});

test('Onde sua conta está aberta: a sessão em uso primeiro, sem botão; as outras com Encerrar, sem diálogo; o aparelho entra como texto', async () => {
  let lista = [sessaoItem('b'.repeat(16), '<b>Firefox</b> · Linux', false, new Date(Date.now() - DIA).toISOString()), sessaoItem('s'.repeat(16), 'Edge · Windows', true, new Date().toISOString(), '127.0.0.1')];
  const {mesa} = abrir({api: (op, d) => {
    if (op === 'conta-sessoes') return {sessoes: lista};
    if (op === 'conta-sessao-encerrar') { lista = lista.filter(s => s.id !== d.sessao); return {sessoes: lista}; }
    return undefined;
  }});
  await esperar(mesa);
  const sessoes = cartao(mesa, 'sessoes');
  const linhas = [...sessoes.querySelectorAll('li')];
  assert.equal(linhas.length, 2);
  assert.ok(texto(linhas[0]).startsWith('Edge · Windows') && texto(linhas[0]).includes('Esta sessão'), 'a sessão em uso vem primeiro');
  assert.equal(linhas[0].querySelector('button'), null, 'sem botão: sai-se dela por Sair');
  assert.equal(linhas[1].querySelector('b'), null, 'o aparelho do servidor não vira HTML');
  assert.ok(texto(linhas[1]).includes('<b>Firefox</b> · Linux') && texto(linhas[1]).includes('ontem, ') && texto(linhas[1]).includes('189.40.12.7'));
  assert.ok(texto(sessoes).includes('Encerrar vale na próxima ação daquele aparelho.')); assert.ok(botaoPorTexto(sessoes, 'Encerrar todas as outras'));
  botaoPorTexto(linhas[1], 'Encerrar').click(); await esperar(mesa);
  assert.equal(dialogo(mesa), null, 'encerrar é imediato, sem diálogo');
  assert.deepEqual(dados(mesa.chamadas.find(c => c.operacao === 'conta-sessao-encerrar').dados), {sessao: 'b'.repeat(16)});
  assert.equal(texto(estado(mesa)), '✓ Sessão encerrada: <b>Firefox</b> · Linux.');
  assert.equal(sessoes.querySelectorAll('li').length, 1);
  assert.equal(botaoPorTexto(sessoes, 'Encerrar todas as outras'), undefined, 'com uma sessão só, sem "encerrar todas"');
});

test('Encerrar todas as outras, e "Sessão não encontrada." recarrega a lista sem erro', async () => {
  let lista = [...SESSOES, sessaoItem('f'.repeat(16), 'Aplicativo Android', false)];
  let recusarEncerrar = false;
  const {mesa} = abrir({api: (op, d) => {
    if (op === 'conta-sessoes') return {sessoes: lista};
    if (op === 'conta-sessoes-encerrar-outras') { lista = lista.filter(s => s.atual); return {encerradas: 2, sessoes: lista}; }
    if (op === 'conta-sessao-encerrar' && recusarEncerrar) { lista = lista.filter(s => s.id !== d.sessao); return recusa('requisicao_invalida', 'Sessão não encontrada.'); }
    return undefined;
  }});
  await esperar(mesa);
  recusarEncerrar = true;
  botaoPorTexto(cartao(mesa, 'sessoes').querySelectorAll('li')[1], 'Encerrar').click(); await esperar(mesa);
  assert.equal(cartao(mesa, 'sessoes').querySelector('.campo-erro'), null, 'sem erro');
  assert.equal(cartao(mesa, 'sessoes').querySelectorAll('li').length, 2, 'a lista recarregou');
  recusarEncerrar = false;
  botaoPorTexto(cartao(mesa, 'sessoes'), 'Encerrar todas as outras').click(); await esperar(mesa);
  assert.equal(texto(estado(mesa)), '✓ 2 sessões encerradas.');
  assert.equal(cartao(mesa, 'sessoes').querySelectorAll('li').length, 1);
});

test('Seu uso neste mês: "R$ 18,40 de R$ 50", medidor com aria-label; esgotada vira aviso com "! Cota esgotada"; sem a rota o cartão some', async () => {
  const {mesa} = abrir(); await esperar(mesa);
  const uso = cartao(mesa, 'uso');
  assert.ok(!uso.hidden); assert.ok(texto(uso).includes('Gasto com IA') && texto(uso).includes('R$ 18,40 de R$ 50')); assert.ok(texto(uso).includes('O teto é definido pelo dono da redação.'));
  const medidor = uso.querySelector('.mesa-medidor');
  assert.equal(medidor.getAttribute('role'), 'img'); assert.equal(medidor.getAttribute('aria-label'), '37% da cota usada');
  assert.ok(!/token/i.test(texto(uso)), 'sempre em reais, nunca em tokens');
  const esgotada = abrir({api: op => (op === 'cota' ? {conta: {gasto_brl: '50.00', teto_brl: '50.00', saldo_brl: '0.00', esgotada: true}} : undefined)}); await esperar(esgotada.mesa);
  const aviso = cartao(esgotada.mesa, 'uso');
  assert.equal(aviso.dataset.esgotada, 'true'); assert.ok(texto(aviso).includes('! Cota esgotada') && texto(aviso).includes('R$ 50,00 de R$ 50'));
  assert.equal(aviso.querySelector('.mesa-medidor').getAttribute('aria-label'), 'Cota do mês esgotada: R$ 50,00 de R$ 50');
  const sem = abrir({api: op => (op === 'cota' ? recusa('operacao_inexistente', 'Operação inexistente.') : undefined)}); await esperar(sem.mesa);
  assert.ok(cartao(sem.mesa, 'uso').hidden, 'sem a rota, o cartão some');
});

test('Seus dados: só o caminho por pessoa, sem botões; para o dono, "fale com quem administra o serviço"', async () => {
  const reporter = abrir({papel: 'reporter'}); await esperar(reporter.mesa);
  assert.equal(texto(cartao(reporter.mesa, 'dados').querySelector('p')), 'Exportar seus dados e excluir sua conta ainda não estão na Mesa. Para pedir, fale com o dono da redação.');
  assert.equal(cartao(reporter.mesa, 'dados').querySelector('button'), null);
  const dono = abrir(); await esperar(dono.mesa);
  assert.ok(texto(cartao(dono.mesa, 'dados')).includes('fale com quem administra o serviço.'));
});

test('cada cartão carrega sozinho: se um falha, o erro do serviço fica no lugar dele e os outros seguem', async () => {
  const {mesa} = abrir({api: op => (op === 'conta-sessoes' ? recusa('erro', 'Falha ao ler as sessões.') : undefined)});
  await esperar(mesa);
  const sessoes = cartao(mesa, 'sessoes');
  assert.ok(sessoes.querySelector('[data-estado="erro"]'), 'o erro do serviço de estados'); assert.ok(texto(sessoes).includes('Falha ao ler as sessões.'));
  const tentar = botaoPorTexto(sessoes, 'Tentar de novo'); assert.ok(tentar);
  assert.ok(texto(cartao(mesa, 'perfil')).includes('Ana Lima'), 'o perfil carregou');
});

test('Idioma muda o idioma da Mesa e grava o da conta; Tema fica só neste navegador (a mesma chave do botão do cabeçalho)', async () => {
  const {mesa} = abrir(); await esperar(mesa);
  const idioma = mesa.$('conta-idioma');
  assert.equal(idioma.value, 'pt'); assert.deepEqual([...idioma.querySelectorAll('option')].map(o => o.textContent), ['Português', 'English']);
  assert.ok(texto(cartao(mesa, 'perfil')).includes('Também é o idioma dos e-mails do Vlado.'));
  mudar(idioma, 'en'); await esperar(mesa);
  assert.equal(mesa.janela.I18N.idioma(), 'en');
  assert.deepEqual(dados(mesa.chamadas.find(c => c.operacao === 'conta-atualizar').dados), {idioma: 'en'});
  const tema = mesa.$('conta-tema');
  assert.deepEqual([...tema.querySelectorAll('option')].map(o => o.value), ['sistema', 'light', 'dark']); assert.equal(tema.value, 'sistema');
  mudar(tema, 'light');
  assert.equal(mesa.guardado.get('apuracao:tema'), 'light'); assert.equal(mesa.doc.documentElement.dataset.theme, 'light', 'o cabeçalho acompanha');
  assert.equal(mesa.chamadas.filter(c => c.operacao === 'conta-atualizar').length, 1, 'o tema não vai ao servidor');
  mudar(tema, 'dark'); assert.equal(mesa.doc.documentElement.dataset.theme, 'dark');
  mudar(tema, 'sistema'); assert.equal(mesa.guardado.has('apuracao:tema'), false, 'Do sistema: nada guardado');
});

test('em inglês: abas, cartões, datas e a linha de estado saem em inglês', async () => {
  const {mesa} = abrir({idioma: 'en'}); await esperar(mesa);
  mesa.$('conta-aba-conta').click(); await esperar(mesa);
  const abas = [...mesa.doc.querySelectorAll('.conta-abas button')].map(b => b.textContent);
  assert.deepEqual(abas, ['My account', 'Team', 'Settings']);
  const tudo = texto(mesa.$('conta-painel-conta'));
  for (const frase of ['Profile', 'Sign-in and security', 'Where your account is open', 'Your usage this month', 'Your data', 'This session', 'Change password', 'set 12 days ago', 'Owner · ']) {
    assert.ok(tudo.includes(frase), frase);
  }
  assert.equal(mesa.$('area-titulo').textContent, 'My account');
});
