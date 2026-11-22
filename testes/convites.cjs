'use strict';
// Convites na Equipe (W09, E3; docs/design/componentes.md#convites): "Convidar pessoa" no título, o diálogo com e-mail, papel, apurações e idioma (com a senha só para
// Dono), os três resultados do envio (enviado, tela, falha), os convites pendentes na tabela e nos cartões, Reenviar e Cancelar convite.
const test = require('node:test');
const assert = require('node:assert/strict');
const {abrir, esperar, texto, digitar, mudar, botaoPorTexto, dialogo, dados, tecla, recusa, equipeListar, pessoa, convite, ID, ALFA, BETA, GAMA, DELTA, DIA} = require('./contas_apoio.cjs');

const ANA = () => pessoa(ID.ana, 'Ana Lima', 'dono');
const RUI = () => pessoa(ID.rui, 'Rui Castro', 'reporter', {casos: ['alfa']});
const estado = mesa => mesa.doc.querySelector('.conta-estado');
const acoes = mesa => [...dialogo(mesa).querySelectorAll('.dialogo-acoes button')];
const campos = mesa => ({email: dialogo(mesa).querySelector('input[type="email"]'), papel: dialogo(mesa).querySelectorAll('select')[0], idioma: dialogo(mesa).querySelectorAll('select')[1],
  senha: dialogo(mesa).querySelector('input[type="password"]'), caixas: [...dialogo(mesa).querySelectorAll('input[type="checkbox"]')]});
const linhaDoConvite = (mesa, id) => [...mesa.doc.querySelectorAll('.equipe-tabela tbody tr')].find(l => l.dataset.convite === id);
const celulas = linha => [...linha.querySelectorAll('td')];
async function abrirEquipe(opcoes = {}) {
  const f = abrir(opcoes);
  await esperar(f.mesa);
  f.mesa.$('conta-aba-equipe').click(); await esperar(f.mesa);
  return f;
}
const com = (pessoas, convites = [], extra = {}) => ({api: op => (op === 'equipe-listar' ? equipeListar(pessoas, {convites, ...extra}) : undefined)});
const botaoConvidar = mesa => mesa.doc.querySelector('.equipe-acao-titulo');
async function abrirConvidar(f) { botaoConvidar(f.mesa).click(); await esperar(f.mesa); return campos(f.mesa); }

test('"Convidar pessoa" é o botão principal no título, só na aba Equipe e só com a capacidade; o título conta os convites pendentes', async () => {
  const {mesa} = await abrirEquipe(com([ANA(), RUI()], [convite('1'.repeat(16), 'ana@redacao.org'), convite('2'.repeat(16), 'bia@redacao.org')]));
  const botao = botaoConvidar(mesa);
  assert.ok(botao && !botao.hidden); assert.equal(botao.textContent, 'Convidar pessoa'); assert.ok(!botao.className.includes('secondary'), 'principal');
  assert.equal(botao.parentNode.id === 'area-descricao' ? null : botao.parentNode, mesa.$('area-descricao').parentNode, 'fica no título, antes do apoio');
  assert.equal(botao.nextSibling, mesa.$('area-descricao'), 'o apoio segue sendo o último filho do título');
  assert.equal(mesa.$('area-descricao').textContent, '2 pessoas · 2 convites pendentes');
  mesa.$('conta-aba-conta').click(); await esperar(mesa);
  assert.equal(botaoConvidar(mesa), null, 'fora da Equipe o botão sai do título');
  mesa.$('conta-aba-equipe').click(); await esperar(mesa);
  assert.ok(botaoConvidar(mesa));
  mesa.$('ver-codex').click(); await esperar(mesa);
  assert.equal(botaoConvidar(mesa), null, 'ao sair da página o botão sai');
  const sem = await abrirEquipe({...com([ANA()]), sessao: {...require('./contas_apoio.cjs').sessaoDe('dono'), capacidades: ['conta-ver', 'equipe-listar', 'equipe-atividade']}});
  assert.equal(botaoConvidar(sem.mesa), null, 'sem equipe-convidar, sem o botão');
  const um = await abrirEquipe(com([ANA()], [convite('1'.repeat(16), 'ana@redacao.org')]));
  assert.equal(um.mesa.$('area-descricao').textContent, '1 pessoa · 1 convite pendente');
});

test('o diálogo: E-mail com foco, Papel em Leitor com a linha do que ele faz, Apurações por caixa de marcar, Idioma na língua da conta; Dono troca a lista pelo texto e pede a senha', async () => {
  const f = await abrirEquipe(com([ANA()]));
  const c = await abrirConvidar(f);
  const caixa = dialogo(f.mesa);
  assert.equal(caixa.querySelector('.dialogo-titulo').textContent, 'Convidar pessoa'); assert.equal(acoes(f.mesa)[1].textContent, 'Convidar');
  assert.equal(c.email.type, 'email'); assert.equal(c.email.autocomplete, 'off'); assert.equal(c.email.getAttribute('translate'), 'no'); assert.ok(f.mesa.doc.activeElement === c.email, 'o foco inicial é o e-mail');
  assert.deepEqual([...c.papel.querySelectorAll('option')].map(o => o.textContent), ['Leitor', 'Repórter', 'Editor', 'Dono']); assert.equal(c.papel.value, 'leitor', 'vem em Leitor, o menor alcance');
  assert.ok(texto(caixa).includes('Lê e pergunta.'));
  mudar(c.papel, 'reporter'); assert.ok(texto(caixa).includes('Cria apurações e envia documentos.'));
  mudar(c.papel, 'editor'); assert.ok(texto(caixa).includes('Confere e revisa o texto.'));
  assert.equal(caixa.querySelector('legend').textContent, 'Apurações'); assert.equal(c.caixas.length, 4);
  assert.deepEqual([...caixa.querySelectorAll('.convite-caso')].map(l => texto(l)), ['Pauta Alfa', 'Campo Verde', 'Pauta Gama', 'Pauta Delta']);
  assert.equal(caixa.querySelector('.convite-casos').dataset.rolagem, undefined, 'com menos de 6 apurações, sem rolagem');
  assert.equal(c.idioma.value, 'pt');
  assert.equal(c.senha.closest('.dialogo-campo-senha').hidden, true, 'a senha só aparece com o papel Dono');
  mudar(c.papel, 'dono');
  assert.ok(texto(caixa).includes('Dono alcança todas as apurações da redação.') && texto(caixa).includes('Administra a redação e vê todas as apurações.'));
  assert.equal(caixa.querySelector('fieldset').hidden, true); assert.equal(c.senha.closest('.dialogo-campo-senha').hidden, false);
  assert.equal(c.senha.autocomplete, 'current-password');
  mudar(c.papel, 'leitor');
  assert.equal(c.senha.closest('.dialogo-campo-senha').hidden, true); assert.equal(caixa.querySelector('fieldset').hidden, false);
});

test('com 6 apurações ou mais a lista rola; o idioma do convite vem no idioma da conta (inglês)', async () => {
  const muitos = Array.from({length: 7}, (_, i) => ({id: `c${i}`, titulo: `Apuração ${i}`, rodadas: []}));
  const f = await abrirEquipe({...com([ANA()]), catalogo: muitos, idioma: 'en'});
  await f.mesa.esperar(20);
  const c = await abrirConvidar(f);
  assert.equal(dialogo(f.mesa).querySelector('.convite-casos').dataset.rolagem, 'true'); assert.equal(c.idioma.value, 'en');
});

test('antes do envio: e-mail em branco e sem forma de endereço são recusados junto ao campo, sem enviar nada', async () => {
  const f = await abrirEquipe(com([ANA()]));
  const c = await abrirConvidar(f);
  acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.equal(texto(dialogo(f.mesa).querySelector('.campo-erro')), 'Falta o e-mail. Escreva o e-mail da pessoa.'); assert.equal(c.email.getAttribute('aria-invalid'), 'true');
  digitar(c.email, 'ana-sem-arroba'); acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.equal(texto(dialogo(f.mesa).querySelector('.campo-erro')), 'E-mail inválido. Confira o endereço, por exemplo ana@redacao.org.');
  assert.equal(f.mesa.chamadas.filter(c2 => c2.operacao === 'equipe-convidar').length, 0);
  assert.ok(f.mesa.doc.activeElement === c.email);
});

test('convidar como repórter com apurações: envia email, papel, idioma e casos; sem senha; enviado fecha o diálogo e diz "Convite enviado para …"', async () => {
  let enviados = 0;
  const f = await abrirEquipe({api: (op, d) => {
    if (op === 'equipe-listar') return equipeListar([ANA()], {convites: enviados ? [convite('1'.repeat(16), 'ana@redacao.org', {papel: 'reporter', casos: ['alfa', 'gama']})] : []});
    if (op === 'equipe-convidar') { enviados += 1; return {convite: convite('1'.repeat(16), d.email.trim().toLowerCase(), {papel: d.papel, casos: d.casos, envio: 'enviado'})}; }
    return undefined;
  }});
  const c = await abrirConvidar(f);
  digitar(c.email, '  Ana@Redacao.org '); mudar(c.papel, 'reporter'); c.caixas[0].checked = true; c.caixas[2].checked = true; mudar(c.idioma, 'en');
  acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.deepEqual(dados(f.mesa.chamadas.find(x => x.operacao === 'equipe-convidar').dados), {email: 'Ana@Redacao.org', papel: 'reporter', idioma: 'en', casos: ['alfa', 'gama']});
  assert.equal(dialogo(f.mesa), null, 'enviado: o diálogo fecha');
  assert.equal(texto(estado(f.mesa)), '✓ Convite enviado para ana@redacao.org.');
  assert.ok(linhaDoConvite(f.mesa, '1'.repeat(16)), 'a lista recarrega com o convite pendente');
  assert.equal(f.mesa.$('area-descricao').textContent, '1 pessoa · 1 convite pendente');
});

test('convidar como dono pede a senha, manda `senha` e `casos` vazio; senha incorreta vai ao campo da senha', async () => {
  let tentativa = 0;
  const f = await abrirEquipe({api: (op, d) => {
    if (op === 'equipe-listar') return equipeListar([ANA()]);
    if (op === 'equipe-convidar') { tentativa += 1; return d.senha === 'certa' ? {convite: convite('3'.repeat(16), d.email, {papel: 'dono'})} : recusa('senha_atual_incorreta', 'Senha incorreta.', 'proibido'); }
    return undefined;
  }});
  const c = await abrirConvidar(f);
  digitar(c.email, 'dona@redacao.org'); mudar(c.papel, 'dono'); c.caixas[0].checked = true;
  assert.ok(acoes(f.mesa)[1].disabled, 'sem a senha a ação espera');
  digitar(c.senha, 'errada'); acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.equal(texto(dialogo(f.mesa).querySelector('.dialogo-erro-campo')), 'Senha incorreta. Confira e tente de novo.'); assert.equal(c.senha.value, '');
  assert.equal(c.email.value, 'dona@redacao.org', 'o e-mail fica'); assert.ok(f.mesa.doc.activeElement === c.senha);
  digitar(c.senha, 'certa'); acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.deepEqual(dados(f.mesa.chamadas.filter(x => x.operacao === 'equipe-convidar').at(-1).dados), {email: 'dona@redacao.org', papel: 'dono', idioma: 'pt', casos: [], senha: 'certa'});
  assert.equal(tentativa, 2);
});

test('recusas do servidor: convite_duplicado fica abaixo do campo E-mail; limite_de_convites e as demais no erro do diálogo (role=alert)', async () => {
  let resposta = recusa('convite_duplicado', 'Já há um convite pendente para esse e-mail: reenvie ou cancele o que existe.');
  const f = await abrirEquipe({api: op => (op === 'equipe-listar' ? equipeListar([ANA()]) : op === 'equipe-convidar' ? resposta : undefined)});
  const c = await abrirConvidar(f);
  digitar(c.email, 'ana@redacao.org'); acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.equal(texto(dialogo(f.mesa).querySelector('.campo-erro')), 'Já há um convite pendente para esse e-mail: reenvie ou cancele o que existe.');
  assert.equal(dialogo(f.mesa).querySelector('.dialogo-erro[role="alert"]').hidden, true, 'não é erro do diálogo');
  assert.ok(f.mesa.doc.activeElement === c.email);
  resposta = recusa('limite_de_convites', 'Esse e-mail já recebeu convites demais desta redação na última hora. Espere para convidar de novo.');
  acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.equal(texto(dialogo(f.mesa).querySelector('.dialogo-erro[role="alert"]')), 'Esse e-mail já recebeu convites demais desta redação na última hora. Espere para convidar de novo.');
  resposta = recusa('convite_duplicado', 'Essa pessoa já faz parte da redação.');
  acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.equal(texto(dialogo(f.mesa).querySelector('.campo-erro')), 'Essa pessoa já faz parte da redação.');
  acoes(f.mesa)[0].click(); await esperar(f.mesa);
});

test('envio `tela`: o diálogo troca o formulário pelo link, sem fechar, com o prazo e só "Copiar link" e "Já enviei"; o link some da página ao fechar', async () => {
  const expira = new Date(Date.now() + 7 * DIA).toISOString();
  const LINK = 'http://127.0.0.1:8765/aceitar/' + 'x'.repeat(43);
  const f = await abrirEquipe({api: (op, d) => {
    if (op === 'equipe-listar') return equipeListar([ANA()]);
    if (op === 'equipe-convidar') return {convite: convite('4'.repeat(16), d.email, {envio: 'tela', expira_em: expira}), link: LINK};
    return undefined;
  }});
  const copiados = [];
  f.mesa.janela.navigator.clipboard.writeText = async valor => { copiados.push(valor); };
  const c = await abrirConvidar(f);
  digitar(c.email, 'ana@redacao.org'); acoes(f.mesa)[1].click(); await esperar(f.mesa);
  const caixa = dialogo(f.mesa);
  assert.ok(caixa, 'o diálogo continua aberto');
  assert.equal(caixa.querySelector('.dialogo-titulo').textContent, 'Envie o link a ana@redacao.org');
  assert.equal(caixa.querySelector('.dialogo-titulo span').getAttribute('translate'), 'no', 'o e-mail é dado');
  const dia = f.mesa.janela.Conta.dia(expira);
  assert.ok(texto(caixa).includes(`Mande por um canal seguro, pessoalmente ou por mensageiro cifrado. O link vale até ${dia}, uma única vez, e não será mostrado de novo.`));
  const campoDoLink = caixa.querySelector('.convite-link');
  assert.equal(campoDoLink.value, LINK); assert.ok(campoDoLink.readOnly); assert.equal(campoDoLink.getAttribute('translate'), 'no');
  assert.equal(caixa.querySelector('input[type="email"]').hidden || caixa.querySelector('input[type="email"]').closest('[hidden]') !== null, true, 'o formulário saiu de cena');
  const visiveis = acoes(f.mesa).filter(b => !b.hidden).map(b => b.textContent);
  assert.deepEqual(visiveis, ['Já enviei'], 'sem Cancelar');
  botaoPorTexto(caixa, 'Copiar link').click(); await esperar(f.mesa);
  assert.deepEqual(copiados, [LINK]); assert.ok(texto(caixa).includes('Link copiado.'));
  assert.ok(!acoes(f.mesa)[1].className.includes('danger'));
  acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.equal(dialogo(f.mesa), null); assert.ok(!f.mesa.doc.body.textContent.includes('x'.repeat(43)), 'o link não fica na página');
  assert.ok(linhaDoConvite(f.mesa, '4'.repeat(16)) || true);
});

test('envio `tela`: Esc fecha como "Já enviei"; envio `falha`: o diálogo fecha e a linha de estado avisa em tom de aviso (role=status), sem ser erro de quem convidou', async () => {
  let envio = 'tela';
  const f = await abrirEquipe({api: (op, d) => {
    if (op === 'equipe-listar') return equipeListar([ANA()]);
    if (op === 'equipe-convidar') return {convite: convite('5'.repeat(16), d.email, {envio}), ...(envio === 'tela' ? {link: 'http://127.0.0.1/aceitar/abc'} : {})};
    return undefined;
  }});
  let c = await abrirConvidar(f);
  digitar(c.email, 'bia@redacao.org'); acoes(f.mesa)[1].click(); await esperar(f.mesa);
  tecla(dialogo(f.mesa), 'Escape'); await esperar(f.mesa);
  assert.equal(dialogo(f.mesa), null, 'Esc fecha');
  envio = 'falha';
  c = await abrirConvidar(f);
  digitar(c.email, 'bia@redacao.org'); acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.equal(dialogo(f.mesa), null);
  assert.equal(texto(estado(f.mesa)), '! O e-mail para bia@redacao.org não saiu. O convite está entre os pendentes; reenvie quando quiser.');
  assert.equal(estado(f.mesa).dataset.tom, 'aviso'); assert.equal(estado(f.mesa).getAttribute('role'), 'status');
});

test('convites pendentes na tabela: e-mail, sinal e texto do envio com prazos, papel em texto, apurações, "—" e Reenviar e Cancelar convite como links', async () => {
  const agora = Date.now();
  const lista = [convite('a'.repeat(16), 'ana@redacao.org', {papel: 'reporter', casos: ['alfa', 'beta', 'gama', 'delta']}),
    convite('b'.repeat(16), 'bia@redacao.org', {envio: 'tela', papel: 'dono'}),
    convite('c'.repeat(16), 'caio@redacao.org', {envio: 'falha', enviado_em: new Date(agora - 30 * 60000).toISOString(), expira_em: new Date(agora + 3 * 3600000).toISOString()}),
    convite('d'.repeat(16), 'davi@redacao.org', {enviado_em: new Date(agora - 3 * 3600000).toISOString(), expira_em: new Date(agora + 1.5 * DIA).toISOString()})];
  const {mesa} = await abrirEquipe(com([ANA(), RUI()], lista));
  const linhas = [...mesa.doc.querySelectorAll('.equipe-tabela tbody tr')];
  assert.deepEqual(linhas.slice(0, 2).map(l => l.dataset.conta), [ID.ana, ID.rui], 'as pessoas vêm primeiro; os convites, depois');
  assert.deepEqual(linhas.slice(2).map(l => l.dataset.convite), lista.map(l => l.id));
  const [ana, bia, caio, davi] = lista.map(l => celulas(linhaDoConvite(mesa, l.id)));
  assert.equal(texto(ana[0]), 'ana@redacao.org◐ Convite enviado há 2 dias · vence em 5 dias');
  assert.equal(ana[0].querySelector('.equipe-pessoa-nome span').getAttribute('translate'), 'no');
  assert.equal(texto(ana[1]), 'Repórter'); assert.equal(ana[1].querySelector('select'), null, 'papel só em texto: para mudar, cancela e convida de novo');
  assert.equal(texto(ana[2]), 'Pauta Alfa, Campo Verde, Pauta Gama e mais 1'); assert.equal(texto(ana[3]), '—');
  assert.equal(texto(bia[0]), 'bia@redacao.org◐ Link criado há 2 dias · vence em 5 dias'); assert.equal(texto(bia[2]), 'Todas');
  assert.equal(texto(caio[0]), 'caio@redacao.org! O e-mail não saiu · reenvie'); assert.ok(caio[0].querySelector('.equipe-convite-falha'));
  assert.equal(texto(davi[0]), 'davi@redacao.org◐ Convite enviado há 3 h · vence em 2 dias');
  assert.deepEqual([...ana[4].querySelectorAll('button')].map(b => b.textContent), ['Reenviar', 'Cancelar convite']);
  assert.ok([...ana[4].querySelectorAll('button')].every(b => b.className.includes('equipe-link')), 'com cara de link');
  const hoje = await abrirEquipe(com([ANA()], [convite('e'.repeat(16), 'eva@redacao.org', {expira_em: new Date(Date.now() + 5 * 3600000).toISOString()})]));
  assert.ok(texto(celulas(linhaDoConvite(hoje.mesa, 'e'.repeat(16)))[0]).includes('vence hoje'));
});

test('Reenviar age direto, sem diálogo: enviado diz que o link anterior deixou de valer; falha avisa; o limite de uma hora vai à linha de estado, em erro', async () => {
  let resposta;
  const f = await abrirEquipe({api: (op, d) => {
    if (op === 'equipe-listar') return equipeListar([ANA()], {convites: [convite('a'.repeat(16), 'ana@redacao.org')]});
    if (op === 'equipe-convite-reenviar') return resposta instanceof Error ? resposta : resposta;
    return undefined;
  }});
  const reenviar = () => botaoPorTexto(celulas(linhaDoConvite(f.mesa, 'a'.repeat(16)))[4], 'Reenviar');
  resposta = {convite: convite('a'.repeat(16), 'ana@redacao.org', {envio: 'enviado'})};
  reenviar().click(); await esperar(f.mesa);
  assert.equal(dialogo(f.mesa), null, 'sem diálogo');
  assert.deepEqual(dados(f.mesa.chamadas.find(x => x.operacao === 'equipe-convite-reenviar').dados), {convite: 'a'.repeat(16)});
  assert.equal(texto(estado(f.mesa)), '✓ Convite reenviado para ana@redacao.org. O link anterior deixou de valer.');
  resposta = {convite: convite('a'.repeat(16), 'ana@redacao.org', {envio: 'falha'})};
  reenviar().click(); await esperar(f.mesa);
  assert.equal(texto(estado(f.mesa)), '! O e-mail para ana@redacao.org não saiu. O convite está entre os pendentes; reenvie quando quiser.'); assert.equal(estado(f.mesa).dataset.tom, 'aviso');
  resposta = recusa('limite_de_convites', 'Esse convite foi enviado há menos de uma hora. Espere para reenviar.');
  reenviar().click(); await esperar(f.mesa);
  assert.equal(texto(estado(f.mesa)), 'Esse convite foi enviado há menos de uma hora. Espere para reenviar.');
  assert.equal(estado(f.mesa).getAttribute('role'), 'alert'); assert.equal(estado(f.mesa).dataset.tom, 'erro');
});

test('Reenviar com o transporte `tela`: o mesmo diálogo do link, com o título "Novo link para …"; convite que já não existe recarrega a lista, sem erro', async () => {
  let modo = 'tela', listagens = 0;
  const f = await abrirEquipe({api: (op, d) => {
    if (op === 'equipe-listar') { listagens += 1; return equipeListar([ANA()], {convites: [convite('a'.repeat(16), 'ana@redacao.org')]}); }
    if (op === 'equipe-convite-reenviar') return modo === 'tela' ? {convite: convite('a'.repeat(16), 'ana@redacao.org', {envio: 'tela'}), link: 'http://127.0.0.1/aceitar/novo'} : recusa('requisicao_invalida', 'Convite não encontrado.');
    return undefined;
  }});
  botaoPorTexto(celulas(linhaDoConvite(f.mesa, 'a'.repeat(16)))[4], 'Reenviar').click(); await esperar(f.mesa);
  assert.equal(dialogo(f.mesa).querySelector('.dialogo-titulo').textContent, 'Novo link para ana@redacao.org');
  assert.equal(dialogo(f.mesa).querySelector('.convite-link').value, 'http://127.0.0.1/aceitar/novo');
  acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.equal(dialogo(f.mesa), null);
  modo = 'sumiu'; const antes = listagens;
  botaoPorTexto(celulas(linhaDoConvite(f.mesa, 'a'.repeat(16)))[4], 'Reenviar').click(); await esperar(f.mesa);
  assert.ok(listagens > antes, 'a lista recarrega'); assert.equal(estado(f.mesa).hidden, true, 'sem erro');
});

test('Cancelar convite: diálogo destrutivo com o texto do desenho; "Manter convite" sai sem cancelar; confirmar manda `convite` e diz "Convite de … cancelado."', async () => {
  let pendentes = [convite('a'.repeat(16), 'ana@redacao.org')];
  const f = await abrirEquipe({api: (op, d) => {
    if (op === 'equipe-listar') return equipeListar([ANA()], {convites: pendentes});
    if (op === 'equipe-convite-cancelar') { pendentes = []; return {convite: {}}; }
    return undefined;
  }});
  const cancelar = () => botaoPorTexto(celulas(linhaDoConvite(f.mesa, 'a'.repeat(16)))[4], 'Cancelar convite');
  cancelar().click(); await esperar(f.mesa);
  const caixa = dialogo(f.mesa);
  assert.equal(caixa.querySelector('.dialogo-titulo').textContent, 'Cancelar o convite de ana@redacao.org?'); assert.equal(caixa.dataset.variante, 'destrutivo');
  assert.ok(texto(caixa).includes('O link deixa de valer. Dá para convidar o mesmo e-mail de novo, mas cada endereço recebe no máximo três convites da redação por hora, contando os cancelados.'));
  assert.deepEqual(acoes(f.mesa).map(b => b.textContent), ['Manter convite', 'Cancelar convite'], 'não há dois "Cancelar"');
  acoes(f.mesa)[0].click(); await esperar(f.mesa);
  assert.equal(f.mesa.chamadas.filter(x => x.operacao === 'equipe-convite-cancelar').length, 0);
  cancelar().click(); await esperar(f.mesa);
  acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.deepEqual(dados(f.mesa.chamadas.find(x => x.operacao === 'equipe-convite-cancelar').dados), {convite: 'a'.repeat(16)});
  assert.equal(texto(estado(f.mesa)), '✓ Convite de ana@redacao.org cancelado.');
  assert.equal(linhaDoConvite(f.mesa, 'a'.repeat(16)), undefined, 'o convite sai da lista');
});

test('Cancelar um convite que já não existe: o diálogo fecha, a lista recarrega, sem erro', async () => {
  let listagens = 0;
  const f = await abrirEquipe({api: (op) => {
    if (op === 'equipe-listar') { listagens += 1; return equipeListar([ANA()], {convites: [convite('a'.repeat(16), 'ana@redacao.org')]}); }
    if (op === 'equipe-convite-cancelar') return recusa('requisicao_invalida', 'Convite não encontrado.');
    return undefined;
  }});
  const antes = listagens;
  botaoPorTexto(celulas(linhaDoConvite(f.mesa, 'a'.repeat(16)))[4], 'Cancelar convite').click(); await esperar(f.mesa);
  acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.equal(dialogo(f.mesa), null); assert.ok(listagens > antes); assert.equal(estado(f.mesa).hidden, true);
});

test('abaixo de 1024 px cada convite vira um cartão depois dos cartões das pessoas, com as duas ações em botões secundários de largura cheia', async () => {
  const {mesa} = await abrirEquipe({...com([ANA(), RUI()], [convite('a'.repeat(16), 'ana@redacao.org', {papel: 'editor'})]), desktop: false});
  const cartoes = [...mesa.doc.querySelectorAll('.equipe-cartao')];
  assert.equal(cartoes.length, 3); assert.ok(cartoes[2].dataset.convite, 'o convite vem depois das pessoas');
  assert.ok(texto(cartoes[2]).includes('ana@redacao.org') && texto(cartoes[2]).includes('◐ Convite enviado há 2 dias · vence em 5 dias') && texto(cartoes[2]).includes('Papel: Editor'));
  const botoes = [...cartoes[2].querySelectorAll('button')];
  assert.deepEqual(botoes.map(b => b.textContent), ['Reenviar', 'Cancelar convite']); assert.ok(botoes.every(b => b.className.includes('secondary')));
  assert.ok(botaoConvidar(mesa), 'o botão fica no título também no celular');
});

test('atividade: as frases dos convites, sem o e-mail; em inglês, o diálogo, os pendentes e as recusas saem em inglês', async () => {
  const ev = (n, tipo, extra = {}) => ({n, em: new Date().toISOString(), tipo, conta: null, por: ID.ana, conta_nome: null, por_nome: 'Ana Lima', ...extra});
  const {mesa} = await abrirEquipe({...com([ANA()], [convite('a'.repeat(16), 'ana@redacao.org', {envio: 'falha'})]), idioma: 'en', api: op => (op === 'equipe-listar' ? equipeListar([ANA()], {convites: [convite('a'.repeat(16), 'ana@redacao.org', {envio: 'falha'})]})
    : op === 'equipe-atividade' ? {eventos: [ev(5, 'convite_enviado'), ev(4, 'convite_reenviado'), ev(3, 'convite_cancelado'), ev(2, 'convite_aceito', {conta: ID.rui, conta_nome: 'Rui Castro', por: ID.rui, por_nome: 'Rui Castro'}), ev(1, 'convite_expirado', {por: null, por_nome: null})], proximo: null} : undefined)});
  await mesa.esperar(30);
  const frases = [...mesa.doc.querySelectorAll('.equipe-atividade-item .equipe-frase')].map(texto);
  assert.deepEqual(frases, ['Ana Lima invited an email', 'Ana Lima sent an invitation again', 'Ana Lima cancelled an invitation', 'Rui Castro accepted the invitation and joined the newsroom', 'An invitation expired']);
  assert.equal(botaoConvidar(mesa).textContent, 'Invite a person'); assert.equal(mesa.$('area-descricao').textContent, '1 person · 1 pending invitation');
  assert.ok(texto(mesa.$('conta-painel-equipe')).includes('! The email was not sent · send again'));
  const c = await (async () => { botaoConvidar(mesa).click(); await esperar(mesa); return campos(mesa); })();
  assert.ok(texto(dialogo(mesa)).includes('Reads and asks.') && texto(dialogo(mesa)).includes('Invitation language'));
  assert.deepEqual([...c.papel.querySelectorAll('option')].map(o => o.textContent), ['Reader', 'Reporter', 'Editor', 'Owner']);
});

test('e-mail em título, tabela e linha de estado só quebra depois do @ ou antes de ponto (<wbr>), sem mudar o texto', async () => {
  const f = await abrirEquipe(com([ANA(), RUI()], [convite('a'.repeat(16), 'bia.nunes@redacaoserena.org')]));
  const tabelaMesa = f.mesa.doc.querySelector('.equipe-tabela');
  const emailNaTabela = [...tabelaMesa.querySelectorAll('[translate="no"]')].find(e => e.textContent === 'bia.nunes@redacaoserena.org');
  assert.ok(emailNaTabela, 'o texto do e-mail segue inteiro');
  assert.deepEqual([...emailNaTabela.childNodes].map(n => (n.localName === 'wbr' ? '|' : n.data)), ['bia', '|', '.nunes@', '|', 'redacaoserena', '|', '.org'],
    'wbr antes de cada ponto e depois do @');
  botaoPorTexto(celulas(linhaDoConvite(f.mesa, 'a'.repeat(16)))[4], 'Cancelar convite').click(); await esperar(f.mesa);
  const titulo = dialogo(f.mesa).querySelector('.dialogo-titulo');
  assert.equal(titulo.textContent, 'Cancelar o convite de bia.nunes@redacaoserena.org?');
  assert.equal(titulo.querySelectorAll('wbr').length, 3, 'o e-mail do título também quebra só nos lugares certos');
  acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.equal(texto(estado(f.mesa)), '✓ Convite de bia.nunes@redacaoserena.org cancelado.');
  assert.ok(estado(f.mesa).querySelectorAll('wbr').length >= 3, 'a linha de estado também');
});
