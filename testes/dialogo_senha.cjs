'use strict';
// Diálogo com senha (docs/design/componentes.md#dialogo-senha; contrato de contas, 5.15): o campo "Sua senha", o reenvio do mesmo pedido com `senha`
// quando o servidor responde 403 senha_necessaria, a senha incorreta no campo, o bloqueio e a senha que nunca fica guardada.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento} = require('./dom_minimo.cjs');

const falha = (codigo, erro = 'texto do servidor', estado = 'proibido') => Object.assign(new Error(erro), {result: {estado, codigo, erro}});
const dialogo = mesa => mesa.doc.querySelector('dialog.dialogo');
const entradas = mesa => [...dialogo(mesa).querySelectorAll('input')];
const botoes = mesa => [...dialogo(mesa).querySelectorAll('.dialogo-acoes button')];
const botaoAcao = mesa => botoes(mesa)[1];
const mensagensDoCampo = mesa => [...dialogo(mesa).querySelectorAll('.dialogo-erro-campo')].filter(p => !p.hidden);
const erroDoDialogo = mesa => dialogo(mesa).querySelector('.dialogo-erro:not(.dialogo-erro-campo)');
function digitar(entrada, texto) { entrada.value = texto; entrada.dispatchEvent(new Evento('input', {bubbles: true})); }
const tecla = (alvo, key) => { const evento = new Evento('keydown', {key, bubbles: true, cancelable: true}); alvo.dispatchEvent(evento); return evento; };

// A Mesa termina de iniciar (inclusive o foco do título) antes do diálogo abrir; senão o foco inicial do teste competiria com o dela.
async function abrir({idioma = 'pt'} = {}) {
  const mesa = criarMesa({idioma, armazenamento: idioma === 'en' ? {'vlado-idioma': 'en'} : {}});
  await mesa.esperar(12);
  return {mesa, pedidos: [], D: mesa.janela.Dialogo};
}
// Objetos criados dentro da Mesa (outro contexto) comparam por conteúdo, não por protótipo.
const dados = valor => JSON.parse(JSON.stringify(valor));

test('o campo "Sua senha": type=password, current-password, Mostrar, apoio; a ação só habilita com a senha; o foco inicial é o campo', async () => {
  const {mesa, D} = await abrir();
  const resposta = D.comSenha({operacao: 'equipe-remover', dados: {conta: 'c1'}, enviar: async () => ({ok: true}),
    dialogo: {titulo: 'Remover {item} da redação?', item: 'Ana Lima', texto: 'Texto.', acao: 'Remover da redação', destrutiva: true}});
  await mesa.esperar(3);
  const [campo] = entradas(mesa);
  assert.equal(campo.type, 'password'); assert.equal(campo.autocomplete, 'current-password');
  assert.equal(dialogo(mesa).querySelector('label').textContent, 'Sua senha');
  assert.ok(dialogo(mesa).textContent.includes('A senha com que você entra na Mesa.'), 'apoio sob o campo');
  assert.ok(mesa.doc.activeElement === campo, 'foco inicial no campo');
  assert.equal(dialogo(mesa).dataset.variante, 'destrutivo');
  assert.ok(botaoAcao(mesa).disabled, 'ação desabilitada com o campo vazio');
  const mostrar = dialogo(mesa).querySelector('.dialogo-mostrar');
  mostrar.click();
  assert.equal(campo.type, 'text'); assert.equal(mostrar.getAttribute('aria-pressed'), 'true'); assert.equal(mostrar.textContent, 'Ocultar');
  mostrar.click();
  assert.equal(campo.type, 'password');
  digitar(campo, 'abc');
  assert.ok(!botaoAcao(mesa).disabled, 'habilita com a senha digitada');
  assert.equal(dialogo(mesa).querySelector('.dialogo-titulo').textContent, 'Remover Ana Lima da redação?', 'o nome entra sem aspas');
  botoes(mesa)[0].click();
  assert.equal(await resposta, null, 'Cancelar devolve null');
});

test('a Mesa pede antes: envia uma vez, com `senha`, e Enter envia quando a ação está habilitada', async () => {
  const {mesa, pedidos, D} = await abrir();
  const resposta = D.comSenha({operacao: 'equipe-remover', dados: {conta: 'c1'}, enviar: async (operacao, dados) => { pedidos.push({operacao, dados}); return {conta: {id: 'c1'}}; },
    dialogo: {titulo: 'Titulo', acao: 'Fazer'}});
  await mesa.esperar(3);
  const [campo] = entradas(mesa);
  tecla(campo, 'Enter');
  assert.equal(pedidos.length, 0, 'Enter com o campo vazio não envia');
  digitar(campo, 'minha-senha');
  tecla(campo, 'Enter');
  assert.deepEqual(dados(await resposta), {conta: {id: 'c1'}});
  assert.deepEqual(dados(pedidos), [{operacao: 'equipe-remover', dados: {conta: 'c1', senha: 'minha-senha'}}]);
  assert.equal(mesa.doc.querySelector('dialog.dialogo'), null, 'o diálogo fecha');
});

test('fallback: sem pedir antes, o pedido segue sem senha; 403 senha_necessaria abre o diálogo e reenvia o MESMO pedido com `senha`', async () => {
  const {mesa, pedidos, D} = await abrir();
  const enviar = async (operacao, dados) => {
    pedidos.push({operacao, dados: {...dados}});
    if (!dados.senha) throw falha('senha_necessaria', 'Digite a sua senha para confirmar.');
    return {estado: 'ok'};
  };
  const resposta = D.comSenha({operacao: 'contas-recuperar', dados: {id: 'c9'}, pedirAntes: false, enviar, dialogo: {titulo: 'Gerar novo link de ativação?', acao: 'Gerar novo link'}});
  await mesa.esperar(4);
  assert.equal(pedidos.length, 1); assert.deepEqual(dados(pedidos[0].dados), {id: 'c9'}, 'o primeiro pedido vai sem senha');
  assert.ok(dialogo(mesa), 'o diálogo abre');
  digitar(entradas(mesa)[0], 'senha-certa');
  botaoAcao(mesa).click();
  assert.deepEqual(dados(await resposta), {estado: 'ok'});
  assert.deepEqual(dados(pedidos[1]), {operacao: 'contas-recuperar', dados: {id: 'c9', senha: 'senha-certa'}}, 'o mesmo pedido, com a senha');
});

test('fallback: sem pedir antes e sem exigência de senha, o diálogo nem abre; outra falha sobe como veio', async () => {
  const {mesa, D} = await abrir();
  const ok = await D.comSenha({operacao: 'x', pedirAntes: false, enviar: async () => ({estado: 'ok'}), dialogo: {titulo: 'T'}});
  assert.deepEqual(dados(ok), {estado: 'ok'}); assert.equal(dialogo(mesa), null);
  await assert.rejects(D.comSenha({operacao: 'x', pedirAntes: false, enviar: async () => { throw falha('conta_inexistente', 'Conta não encontrada.', 'erro'); }, dialogo: {titulo: 'T'}}),
    /Conta não encontrada\./);
  assert.equal(dialogo(mesa), null, 'nenhum diálogo para outra recusa');
});

test('senha incorreta: erro junto ao campo, campo limpo e com o foco; a nova tentativa manda o que foi digitado, nunca a senha anterior', async () => {
  const {mesa, pedidos, D} = await abrir();
  const enviar = async (operacao, dados) => {
    pedidos.push({...dados});
    if (dados.senha !== 'certa') throw falha('senha_atual_incorreta', 'Senha incorreta.');
    return {estado: 'ok'};
  };
  const resposta = D.comSenha({operacao: 'ia-config-salvar', dados: {chave: 'k'}, enviar, dialogo: {titulo: 'Salvar a chave de IA?', acao: 'Salvar chave'}});
  await mesa.esperar(3);
  const [campo] = entradas(mesa);
  digitar(campo, 'errada'); botaoAcao(mesa).click(); await mesa.esperar(4);
  assert.equal(mensagensDoCampo(mesa).length, 1); assert.equal(mensagensDoCampo(mesa)[0].textContent, 'Senha incorreta. Confira e tente de novo.');
  assert.equal(campo.getAttribute('aria-invalid'), 'true'); assert.equal(campo.value, '', 'o campo é limpo');
  assert.ok(mesa.doc.activeElement === campo, 'o foco volta ao campo');
  assert.ok(botaoAcao(mesa).disabled, 'sem senha digitada a ação fica indisponível');
  digitar(campo, 'certa'); botaoAcao(mesa).click();
  assert.deepEqual(dados(await resposta), {estado: 'ok'});
  assert.deepEqual(pedidos.map(p => p.senha), ['errada', 'certa']);
});

test('bloqueio (429): o texto de 15 minutos no erro do diálogo, a ação indisponível e só "Cancelar" sobra', async () => {
  const {mesa, D} = await abrir();
  const resposta = D.comSenha({operacao: 'equipe-papel', enviar: async () => { throw falha('bloqueado', 'Muitas tentativas.', 'bloqueado'); }, dialogo: {titulo: 'T', acao: 'Fazer'}});
  await mesa.esperar(3);
  digitar(entradas(mesa)[0], 'x'); botaoAcao(mesa).click(); await mesa.esperar(4);
  assert.ok(erroDoDialogo(mesa) && !erroDoDialogo(mesa).hidden); assert.equal(erroDoDialogo(mesa).getAttribute('role'), 'alert');
  assert.ok(erroDoDialogo(mesa).textContent.startsWith('Muitas senhas erradas seguidas. Por 15 minutos'));
  assert.ok(botaoAcao(mesa).disabled, 'a ação não volta');
  digitar(entradas(mesa)[0], 'outra');
  assert.ok(botaoAcao(mesa).disabled, 'nem digitando de novo');
  botoes(mesa)[0].click();
  assert.equal(await resposta, null);
});

test('as demais recusas (ultimo_dono, senha_necessaria com o diálogo já aberto) ficam no erro do diálogo, e aoRecusar avisa quem chamou', async () => {
  const {mesa, D} = await abrir();
  let recusas = 0;
  const resposta = D.comSenha({operacao: 'equipe-papel', enviar: async () => { throw falha('ultimo_dono', 'A redação precisa de ao menos um dono ativo.', 'erro'); },
    dialogo: {titulo: 'T', acao: 'Fazer', aoRecusar: () => { recusas += 1; }}});
  await mesa.esperar(3);
  digitar(entradas(mesa)[0], 'x'); botaoAcao(mesa).click(); await mesa.esperar(4);
  assert.equal(erroDoDialogo(mesa).textContent, 'A redação precisa de ao menos um dono ativo.');
  assert.equal(recusas, 1); assert.equal(mensagensDoCampo(mesa).length, 0, 'não é erro de campo');
  assert.equal(entradas(mesa)[0].value, '', 'a senha não fica no campo depois de uma recusa que não é dela');
  assert.ok(botaoAcao(mesa).disabled, 'sem senha digitada a ação espera; digitando, a pessoa pode tentar de novo');
  digitar(entradas(mesa)[0], 'de-novo');
  assert.ok(!botaoAcao(mesa).disabled, 'a pessoa pode tentar de novo');
  botoes(mesa)[0].click();
  assert.equal(await resposta, null);
});

test('a senha não fica guardada: some do campo ao fechar e a próxima abertura começa vazia', async () => {
  const {mesa, D} = await abrir();
  const primeira = D.comSenha({operacao: 'x', enviar: async () => ({}), dialogo: {titulo: 'T', acao: 'Fazer'}});
  await mesa.esperar(3);
  const antigo = entradas(mesa)[0];
  digitar(antigo, 'segredo'); botoes(mesa)[0].click(); await primeira;
  assert.equal(antigo.value, '', 'o campo é limpo ao fechar');
  const segunda = D.comSenha({operacao: 'x', enviar: async () => ({}), dialogo: {titulo: 'T', acao: 'Fazer'}});
  await mesa.esperar(3);
  assert.equal(entradas(mesa)[0].value, ''); botoes(mesa)[0].click(); await segunda;
});

test('vários campos com validação: cada erro vai junto ao seu campo, o foco ao primeiro, e nada é enviado (Trocar senha)', async () => {
  const {mesa, pedidos, D} = await abrir();
  const resposta = D.confirmar({variante: 'simples', titulo: 'Trocar senha', acao: 'Trocar senha',
    campos: [{id: 'atual', rotulo: 'Senha atual'}, {id: 'nova', rotulo: 'Nova senha', autocomplete: 'new-password'}, {id: 'repita', rotulo: 'Repita a nova senha', autocomplete: 'new-password'}],
    validar: v => ({...(v.atual ? {} : {atual: 'Falta a senha atual. Digite a senha com que você entra hoje.'}),
      ...(v.nova.length < 12 ? {nova: 'A senha deve ter de 12 a 256 caracteres.'} : v.nova !== v.repita ? {repita: 'As duas senhas não coincidem. Digite a mesma senha nos dois campos.'} : {})}),
    executar: async ctx => { pedidos.push(ctx.valores()); }});
  await mesa.esperar(3);
  const campos = entradas(mesa);
  assert.equal(campos.length, 3); assert.deepEqual(campos.map(c => c.autocomplete), ['current-password', 'new-password', 'new-password']);
  assert.ok(!botaoAcao(mesa).disabled, 'sem `exigido`, a ação fica habilitada: a Mesa confere ao enviar');
  botaoAcao(mesa).click(); await mesa.esperar(3);
  assert.deepEqual(mensagensDoCampo(mesa).map(p => p.textContent), ['Falta a senha atual. Digite a senha com que você entra hoje.', 'A senha deve ter de 12 a 256 caracteres.']);
  assert.ok(mesa.doc.activeElement === campos[0], 'o foco vai ao primeiro campo com erro');
  assert.equal(pedidos.length, 0);
  digitar(campos[0], 'atual-1234'); digitar(campos[1], 'uma-senha-nova-123'); digitar(campos[2], 'outra-diferente-12');
  botaoAcao(mesa).click(); await mesa.esperar(3);
  assert.deepEqual(mensagensDoCampo(mesa).map(p => p.textContent), ['As duas senhas não coincidem. Digite a mesma senha nos dois campos.']);
  assert.ok(mesa.doc.activeElement === campos[2]);
  digitar(campos[2], 'uma-senha-nova-123'); botaoAcao(mesa).click(); await mesa.esperar(4);
  assert.deepEqual(dados(pedidos), [{atual: 'atual-1234', nova: 'uma-senha-nova-123', repita: 'uma-senha-nova-123'}]);
  assert.equal(await resposta, true);
});

test('em inglês, o rótulo, o apoio, o Mostrar e a recusa saem em inglês', async () => {
  const {mesa, D} = await abrir({idioma: 'en'});
  await mesa.esperar(6);
  const resposta = D.comSenha({operacao: 'x', enviar: async () => { throw falha('senha_atual_incorreta', 'Senha incorreta.'); }, dialogo: {titulo: 'Salvar a chave de IA?', acao: 'Salvar chave'}});
  await mesa.esperar(4);
  const texto = dialogo(mesa).textContent;
  assert.ok(texto.includes('Your password'), 'rótulo'); assert.ok(texto.includes('The password you use to sign in to the desk.'), 'apoio');
  assert.equal(dialogo(mesa).querySelector('.dialogo-mostrar').textContent, 'Show');
  digitar(entradas(mesa)[0], 'x'); botaoAcao(mesa).click(); await mesa.esperar(4);
  assert.equal(mensagensDoCampo(mesa)[0].textContent, 'Wrong password. Check it and try again.');
  botoes(mesa)[0].click(); await resposta;
});

test('R1: com o bloqueio (429), o Enter no campo também não envia mais um pedido', async () => {
  const {mesa, pedidos, D} = await abrir();
  const resposta = D.comSenha({operacao: 'equipe-papel', enviar: async (operacao, corpo) => { pedidos.push(corpo); throw falha('bloqueado', 'Muitas tentativas.', 'bloqueado'); }, dialogo: {titulo: 'T', acao: 'Fazer'}});
  await mesa.esperar(3);
  digitar(entradas(mesa)[0], 'x'); botaoAcao(mesa).click(); await mesa.esperar(4);
  assert.equal(pedidos.length, 1);
  digitar(entradas(mesa)[0], 'outra-senha');
  const evento = tecla(entradas(mesa)[0], 'Enter'); await mesa.esperar(4);
  assert.ok(evento.defaultPrevented, 'o Enter é tratado, não deixa o formulário agir');
  assert.equal(pedidos.length, 1, 'nenhum pedido novo depois do bloqueio');
  botoes(mesa)[0].click(); assert.equal(await resposta, null);
});

test('R2: o reenvio leva o MESMO pedido, copiado na entrada; mexer no objeto depois, ou o `enviar` mexer no que recebe, não muda o reenvio', async () => {
  const {mesa, pedidos, D} = await abrir();
  const corpo = {conta: 'c1', papel: 'dono'};
  const enviar = async (operacao, recebido) => {
    pedidos.push(JSON.parse(JSON.stringify(recebido)));
    recebido.papel = 'alterado-por-quem-recebeu'; delete recebido.conta;  // quem recebe pode mexer na sua cópia
    if (!recebido.senha) throw falha('senha_necessaria', 'Digite a sua senha para confirmar.');
    return {estado: 'ok'};
  };
  const resposta = D.comSenha({operacao: 'equipe-papel', dados: corpo, pedirAntes: false, enviar, dialogo: {titulo: 'T', acao: 'Fazer'}});
  await mesa.esperar(4);
  corpo.conta = 'outra-conta'; corpo.extra = 'entrou-depois';  // quem chamou mexe no objeto com o diálogo aberto
  digitar(entradas(mesa)[0], 'senha'); botaoAcao(mesa).click();
  assert.deepEqual(dados(await resposta), {estado: 'ok'});
  assert.deepEqual(pedidos, [{conta: 'c1', papel: 'dono'}, {conta: 'c1', papel: 'dono', senha: 'senha'}], 'o reenvio é o pedido de antes, mais a senha');
});

test('R3: qualquer recusa que não é da senha limpa os campos de senha (a senha não fica entre tentativas); a recusa do campo limpa só o dele', async () => {
  const {mesa, D} = await abrir();
  let resposta = falha('ultimo_dono', 'A redação precisa de ao menos um dono ativo.', 'erro');
  const confirmacao = D.confirmar({variante: 'simples', titulo: 'T', acao: 'Fazer', campos: [{id: 'a', rotulo: 'Um'}, {id: 'b', rotulo: 'Dois'}],
    executar: async () => { throw resposta; }});
  await mesa.esperar(3);
  digitar(entradas(mesa)[0], 'um'); digitar(entradas(mesa)[1], 'dois');
  botaoAcao(mesa).click(); await mesa.esperar(4);
  assert.deepEqual(entradas(mesa).map(c => c.value), ['', ''], 'recusa que não é de um campo: todos os campos de senha são limpos');
  assert.ok(erroDoDialogo(mesa) && !erroDoDialogo(mesa).hidden);
  resposta = Object.assign(new Error('Senha incorreta.'), {campo: 'a'});
  digitar(entradas(mesa)[0], 'um'); digitar(entradas(mesa)[1], 'dois');
  botaoAcao(mesa).click(); await mesa.esperar(4);
  assert.deepEqual(entradas(mesa).map(c => c.value), ['', 'dois'], 'recusa de um campo: só o dele é limpo');
  botoes(mesa)[0].click(); await confirmacao;
});

test('campo oculto: não é exigido nem vai em valores() até campoVisivel(id, true); esconder de novo limpa o que foi digitado', async () => {
  const {mesa, D} = await abrir();
  let visto = null;
  const confirmacao = D.confirmar({variante: 'simples', titulo: 'T', acao: 'Fazer', campos: [{id: 's', rotulo: 'Sua senha', exigido: true, oculto: true}],
    preparar: ctx => { visto = ctx; }, executar: async ctx => { visto.enviado = ctx.valores(); }});
  await mesa.esperar(4);
  const [campo] = entradas(mesa);
  assert.equal(campo.closest('.dialogo-campo-senha').hidden, true); assert.ok(!botaoAcao(mesa).disabled, 'oculto não é exigido: a ação segue habilitada');
  visto.campoVisivel('s', true);
  assert.equal(campo.closest('.dialogo-campo-senha').hidden, false); assert.ok(botaoAcao(mesa).disabled, 'visível e exigido: a ação espera a senha');
  digitar(campo, 'segredo'); assert.ok(!botaoAcao(mesa).disabled);
  visto.campoVisivel('s', false);
  assert.equal(campo.value, '', 'esconder limpa'); assert.deepEqual(dados(visto.valores()), {s: ''}, 'um campo oculto nunca leva valor');
  botaoAcao(mesa).click(); await mesa.esperar(4);
  assert.deepEqual(dados(visto.enviado), {s: ''}); assert.equal(await confirmacao, true);
});

test('validar(...) devolvendo false não envia nem limpa nada; falha silenciosa não mostra mensagem do diálogo nem limpa a senha', async () => {
  const {mesa, D} = await abrir();
  let falhar = false, chamadas = 0;
  const confirmacao = D.confirmar({variante: 'simples', titulo: 'T', acao: 'Fazer', campos: [{id: 's', rotulo: 'Sua senha'}],
    validar: () => (falhar ? false : {}), executar: async () => { chamadas += 1; throw Object.assign(new Error('já mostrei junto ao meu campo'), {silencioso: true}); }});
  await mesa.esperar(3);
  digitar(entradas(mesa)[0], 'guardada');
  falhar = true; botaoAcao(mesa).click(); await mesa.esperar(3);
  assert.equal(chamadas, 0); assert.equal(entradas(mesa)[0].value, 'guardada', 'validar=false não limpa a senha');
  falhar = false; botaoAcao(mesa).click(); await mesa.esperar(4);
  assert.equal(chamadas, 1); assert.ok(erroDoDialogo(mesa).hidden, 'silencioso: sem mensagem do diálogo');
  assert.equal(entradas(mesa)[0].value, 'guardada', 'silencioso: quem lançou cuida da senha');
  assert.ok(!botaoAcao(mesa).disabled, 'o diálogo volta a ficar disponível');
  botoes(mesa)[0].click(); await confirmacao;
});

test('trocarPor: executar troca o formulário por outra vista sem fechar; a ação e o Esc fecham (true); semCancelar tira o botão; o que a vista mostrou sai da página', async () => {
  const {mesa, D} = await abrir();
  const confirmacao = D.confirmar({variante: 'simples', titulo: 'Titulo antigo', acao: 'Fazer', campos: [{id: 's', rotulo: 'Sua senha'}],
    executar: async ctx => { ctx.trocarPor({titulo: 'Envie o link a {item}', item: 'ana@redacao.org', itemAspas: false, texto: 'Texto novo.', acao: 'Já enviei', semCancelar: true,
      montar: vista => { const valor = mesa.doc.createElement('input'); valor.value = 'SEGREDO-DO-LINK'; valor.className = 'o-link'; vista.append(valor); }}); }});
  await mesa.esperar(3);
  digitar(entradas(mesa)[0], 'x'); botaoAcao(mesa).click(); await mesa.esperar(4);
  const caixa = dialogo(mesa);
  assert.ok(caixa, 'o diálogo não fechou');
  assert.equal(caixa.querySelector('.dialogo-titulo').textContent, 'Envie o link a ana@redacao.org');
  assert.ok(caixa.textContent.includes('Texto novo.')); assert.ok(caixa.querySelector('.o-link'));
  assert.equal(caixa.querySelector('.dialogo-campo-senha').hidden, true, 'o formulário saiu de cena');
  assert.deepEqual(botoes(mesa).filter(b => !b.hidden).map(b => b.textContent), ['Já enviei']);
  assert.ok(!botaoAcao(mesa).disabled);
  tecla(caixa, 'Escape'); await mesa.esperar(3);
  assert.equal(await confirmacao, true, 'Esc fecha como a ação');
  assert.equal(mesa.doc.querySelector('dialog.dialogo'), null); assert.ok(!mesa.doc.body.textContent.includes('SEGREDO-DO-LINK'), 'o link não fica na página');
});

test('em cada campo de senha o erro vem antes do apoio (o erro a 4 px do campo, o apoio depois) e o aria-describedby segue a mesma ordem', async () => {
  const {mesa, D} = await abrir();
  const confirmacao = D.confirmar({variante: 'simples', titulo: 'T', acao: 'Fazer', campos: [{id: 's', rotulo: 'Sua senha', apoio: 'A senha com que você entra na Mesa.'}]});
  await mesa.esperar(3);
  const grupo = dialogo(mesa).querySelector('.dialogo-campo-senha');
  const filhos = [...grupo.children].map(c => (c.className.includes('dialogo-erro-campo') ? 'erro' : c.className.includes('dialogo-nota') ? 'apoio' : c.localName));
  assert.deepEqual(filhos, ['label', 'div', 'erro', 'apoio']);
  const ids = entradas(mesa)[0].getAttribute('aria-describedby').split(' ');
  assert.equal(ids[0], grupo.querySelector('.dialogo-erro-campo').id); assert.equal(ids[1], grupo.querySelector('.dialogo-nota').id);
  botoes(mesa)[0].click(); await confirmacao;
});
