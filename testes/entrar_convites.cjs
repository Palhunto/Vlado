'use strict';
// Entrar: Aceitar convite (/aceitar/<token>), Esqueci a senha, Redefinir a senha (/redefinir/<token>) e Confirmar e-mail (/confirmar-email/<token>)
// (docs/design/componentes.md#aceitar-convite; contrato de contas 5.2, 5.3 e 8.1). Os formatos das respostas são os do servidor
// (test_convites.py, test_redefinicao_senha.py, test_recuperacao.py); test_entrar_convites.py confere as mesmas rotas no servidor de verdade.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {criarMesa, Evento} = require('./dom_minimo.cjs');

const HTML = fs.readFileSync(path.join(__dirname, '..', 'interface', 'entrar.html'), 'utf8');
const TOKEN = 'T'.repeat(43);
const CONVITE = {redacao: 'Redação Serena', email: 'ana@redacao.org', papel: 'reporter', convidado_por: 'Rui Castro', expira_em: '2026-11-29T15:00:00Z', idioma: 'pt', termos_versao: null};
// A recusa do servidor: `estado` diz o status, como em rotas_contas.py (erro, bloqueado, indisponivel).
const recusa = (codigo, erro, estado = 'erro') => Object.assign(new Error(erro), {result: {estado, codigo, erro}});
const STATUS = {erro: 400, bloqueado: 429, indisponivel: 503, credenciais: 401};

async function abrir({url = `http://127.0.0.1:8765/aceitar/${TOKEN}`, idioma = 'pt', api = () => undefined, entrada = {esqueci_senha: false}} = {}) {
  const pedidos = [], destinos = [];
  const mesa = criarMesa({html: HTML, url, armazenamento: {'vlado-idioma': idioma}, scripts: ['estados.js', 'entrar.js'],
    preparar: janela => {
      janela.location.replace = destino => destinos.push(['replace', destino]);
      janela.location.assign = destino => destinos.push(['assign', destino]);
      const original = janela.fetch;
      janela.fetch = async (endereco, opcoes) => {   // o status que o servidor daria a cada recusa
        const resposta = await original(endereco, opcoes);
        if (!resposta.ok) resposta.status = STATUS[(await resposta.json()).estado] || 400; else resposta.status = 200;
        return resposta;
      };
    },
    api: (operacao, dados) => {
      pedidos.push({operacao, dados: {...dados}});
      const propria = api(operacao, dados);
      if (propria !== undefined) { if (propria instanceof Error) throw propria; return propria; }
      if (operacao === 'entrada') { if (entrada instanceof Error) throw entrada; return entrada; }
      if (operacao === 'sessao') throw recusa('sem_sessao', 'sem sessão');
      return {};
    }});
  await mesa.esperar(10);
  return {mesa, pedidos, destinos, chamadas: operacao => pedidos.filter(p => p.operacao === operacao)};
}
const digitar = (entrada, texto) => { entrada.value = texto; entrada.dispatchEvent(new Evento('input', {bubbles: true})); };
const enviar = async (mesa, id) => { mesa.$(id).dispatchEvent(new Evento('submit', {bubbles: true, cancelable: true})); await mesa.esperar(10); };
const avisos = mesa => [...mesa.doc.querySelectorAll('.campo-erro')];
const visivel = (mesa, id) => !mesa.$(id).hidden;
const comConvite = (extra = {}) => ({api: operacao => (operacao === 'convite-consultar' ? {...CONVITE, ...extra} : undefined)});

// --- Aceitar convite ---------------------------------------------------------------------------------------------------------------------------
test('o convite aparece com redação, quem convidou, e-mail em destaque, papel e validade; o foco vai ao nome; o token sai do endereço', async () => {
  const {mesa, chamadas} = await abrir(comConvite());
  assert.deepEqual(mesa.erros, []);
  assert.deepEqual(chamadas('convite-consultar').map(p => p.dados), [{token: TOKEN}]);
  assert.equal(mesa.$('aceitar-rubrica').textContent, 'CONVITE');
  assert.equal(mesa.$('aceitar-titulo').textContent, 'Entre na Redação Serena');
  assert.equal(mesa.$('aceitar-texto').textContent, 'Rui Castro convidou ana@redacao.org como Repórter.');
  const destaque = mesa.$('aceitar-texto').querySelector('strong');
  assert.equal(destaque.textContent, 'ana@redacao.org'); assert.equal(destaque.getAttribute('translate'), 'no');
  assert.equal(mesa.$('aceitar-validade').textContent, 'Convite válido até 29 de nov.');
  assert.equal(mesa.$('aceitar-email').value, 'ana@redacao.org', 'o e-mail oculto para o gerenciador de senhas');
  assert.equal(mesa.$('aceitar-email').getAttribute('autocomplete'), 'username');
  assert.equal(mesa.$('aceitar-nome').getAttribute('autocomplete'), 'name'); assert.equal(mesa.$('aceitar-nome').getAttribute('maxlength'), '120');
  assert.equal(mesa.$('aceitar-senha').getAttribute('autocomplete'), 'new-password');
  assert.ok(mesa.doc.activeElement === mesa.$('aceitar-nome'), 'o foco inicial é o nome');
  assert.equal(new URL(mesa.janela.location.href).pathname, '/aceitar', 'o token não fica no endereço');
  assert.ok(mesa.$('aceitar-form').textContent.includes('Antes de começar'));
  assert.ok(mesa.$('aceitar-form').textContent.includes('O Vlado está em teste. Use só documentos públicos: trechos são enviados ao provedor de IA.'));
  assert.ok(mesa.$('aceitar-form').textContent.includes('De 12 a 256 caracteres. Pode colar ou usar o gerenciador de senhas.'));
  assert.equal(mesa.$('aceitar-enviar').textContent, 'Criar conta e entrar');
  assert.equal(visivel(mesa, 'aceitar-termos-rotulo'), false, 'sem termos, sem caixa');
});

test('o idioma da página é o do convite; "English" e "Português" trocam, e o texto montado acompanha', async () => {
  const {mesa} = await abrir(comConvite({idioma: 'en'}));
  assert.equal(mesa.$('aceitar-titulo').textContent, 'Join Redação Serena');
  assert.equal(mesa.$('aceitar-texto').textContent, 'Rui Castro invited ana@redacao.org as Reporter.');
  assert.equal(mesa.$('aceitar-validade').textContent, 'Invitation valid until Nov 29');
  assert.equal(mesa.$('aceitar-enviar').textContent, 'Create account and sign in');
  mesa.$('entrar-idioma').click(); await mesa.esperar(3);
  assert.equal(mesa.$('aceitar-titulo').textContent, 'Entre na Redação Serena');
  assert.equal(mesa.$('aceitar-texto').textContent, 'Rui Castro convidou ana@redacao.org como Repórter.');
});

test('redação e quem convidou são texto digitado por alguém: entram só como texto, nunca como HTML nem como link', async () => {
  const {mesa} = await abrir(comConvite({redacao: '<img src=x onerror=alert(1)>', convidado_por: 'https://golpe.example/entrar {papel}'}));
  assert.equal(mesa.$('aceitar-titulo').textContent, 'Entre na <img src=x onerror=alert(1)>');
  assert.equal(mesa.doc.querySelector('img'), null);
  assert.equal(mesa.$('aceitar-texto').querySelector('a'), null, 'nada vira link');
  assert.ok(mesa.$('aceitar-texto').textContent.startsWith('https://golpe.example/entrar {papel} convidou'), 'um {papel} digitado não é trocado');
});

test('antes de enviar: nome em branco e senha fora do tamanho recebem o erro junto ao campo, com foco; nada vai ao servidor', async () => {
  const {mesa, chamadas} = await abrir(comConvite());
  await enviar(mesa, 'aceitar-form');
  assert.equal(avisos(mesa)[0].textContent, 'Falta o nome. Escreva o seu nome.');
  assert.equal(mesa.$('aceitar-nome').getAttribute('aria-invalid'), 'true'); assert.ok(mesa.doc.activeElement === mesa.$('aceitar-nome'));
  digitar(mesa.$('aceitar-nome'), 'Ana Lima'); digitar(mesa.$('aceitar-senha'), 'curta');
  await enviar(mesa, 'aceitar-form');
  assert.equal(avisos(mesa).length, 1);
  assert.equal(avisos(mesa)[0].textContent, 'A senha deve ter de 12 a 256 caracteres.');
  assert.equal(mesa.$('aceitar-senha').getAttribute('aria-invalid'), 'true');
  assert.equal(chamadas('convite-aceitar').length, 0);
});

test('aceitar: o pedido leva token, nome, senha e cliente; a sessão já está aberta e a página vai a `destino`', async () => {
  const {mesa, chamadas, destinos} = await abrir({api: operacao => {
    if (operacao === 'convite-consultar') return CONVITE;
    if (operacao === 'convite-aceitar') return {conta: {id: 'a'.repeat(16), nome: 'Ana Lima', login: 'ana', email: 'ana@redacao.org', papel: 'reporter', casos: ['alfa']}, csrf: 'x', destino: '/?area=codex&caso=alfa'};
    return undefined;
  }});
  digitar(mesa.$('aceitar-nome'), '  Ana Lima '); digitar(mesa.$('aceitar-senha'), 'uma frase longa e boa');
  await enviar(mesa, 'aceitar-form');
  assert.deepEqual(chamadas('convite-aceitar').map(p => p.dados), [{token: TOKEN, nome: 'Ana Lima', senha: 'uma frase longa e boa', cliente: 'web'}]);
  assert.deepEqual(destinos, [['replace', '/?area=codex&caso=alfa']]);
  assert.equal(mesa.$('aceitar-enviar').getAttribute('aria-busy'), 'true', 'ocupado até a página mudar');
});

test('um destino que não é do mesmo site (//golpe, \\\\golpe) vira "/"', async () => {
  for (const destino of ['//golpe.example/', '/\\golpe', 'https://golpe.example/', '']) {
    const {mesa, destinos} = await abrir({api: operacao => {
      if (operacao === 'convite-consultar') return CONVITE;
      if (operacao === 'convite-aceitar') return {conta: {}, csrf: 'x', destino};
      return undefined;
    }});
    digitar(mesa.$('aceitar-nome'), 'Ana'); digitar(mesa.$('aceitar-senha'), 'uma frase longa e boa');
    await enviar(mesa, 'aceitar-form');
    assert.deepEqual(destinos, [['replace', '/']], JSON.stringify(destino));
  }
});

test('com termos_versao a caixa aparece, é obrigatória e a versão lida vai no aceite', async () => {
  const {mesa, chamadas} = await abrir({api: operacao => (operacao === 'convite-consultar' ? {...CONVITE, termos_versao: '2026-11'} : operacao === 'convite-aceitar' ? {conta: {}, csrf: 'x', destino: '/'} : undefined)});
  assert.equal(visivel(mesa, 'aceitar-termos-rotulo'), true);
  assert.equal(mesa.$('aceitar-termos-rotulo').textContent.trim(), 'Li e aceito os termos de uso e a política de privacidade do teste.');
  digitar(mesa.$('aceitar-nome'), 'Ana'); digitar(mesa.$('aceitar-senha'), 'uma frase longa e boa');
  await enviar(mesa, 'aceitar-form');
  assert.equal(avisos(mesa)[0].textContent, 'Falta aceitar os termos. Marque a caixa para continuar.');
  assert.equal(chamadas('convite-aceitar').length, 0);
  mesa.$('aceitar-termos').checked = true;
  await enviar(mesa, 'aceitar-form');
  assert.equal(chamadas('convite-aceitar')[0].dados.termos_versao, '2026-11');
});

test('convite que não vale (consulta ou aceite): uma resposta só, "Este convite não vale mais", o texto e "Ir para a entrada"', async () => {
  const sem = recusa('convite_invalido', 'Convite inválido, cancelado ou vencido. Peça um novo a quem convidou.');
  const consulta = await abrir({api: operacao => (operacao === 'convite-consultar' ? sem : undefined)});
  assert.equal(consulta.mesa.$('aceitar-titulo').textContent, 'Este convite não vale mais');
  assert.equal(consulta.mesa.$('aceitar-texto').textContent, 'Convite inválido, cancelado ou vencido. Peça um novo a quem convidou.');
  assert.equal(visivel(consulta.mesa, 'aceitar-form'), false); assert.equal(visivel(consulta.mesa, 'aceitar-rubrica'), false);
  const ir = consulta.mesa.$('aceitar-sair').querySelector('a');
  assert.equal(ir.textContent, 'Ir para a entrada'); assert.equal(ir.getAttribute('href'), '/entrar');
  const aceite = await abrir({api: operacao => (operacao === 'convite-consultar' ? CONVITE : operacao === 'convite-aceitar' ? sem : undefined)});
  digitar(aceite.mesa.$('aceitar-nome'), 'Ana'); digitar(aceite.mesa.$('aceitar-senha'), 'uma frase longa e boa');
  await enviar(aceite.mesa, 'aceitar-form');
  assert.equal(aceite.mesa.$('aceitar-titulo').textContent, 'Este convite não vale mais');
  const recarga = await abrir({url: 'http://127.0.0.1:8765/aceitar'});
  assert.equal(recarga.mesa.$('aceitar-titulo').textContent, 'Este convite não vale mais', 'recarregada depois de o token sair do endereço');
  assert.equal(recarga.chamadas('convite-consultar').length, 0);
});

test('as demais respostas do aceite: senha_invalida abaixo da senha, 400 do nome abaixo do nome, 429 e 503 na caixa de aviso', async () => {
  const caso = async resposta => {
    const aberto = await abrir({api: operacao => (operacao === 'convite-consultar' ? CONVITE : operacao === 'convite-aceitar' ? resposta : undefined)});
    digitar(aberto.mesa.$('aceitar-nome'), 'Ana'); digitar(aberto.mesa.$('aceitar-senha'), 'uma frase longa e boa');
    await enviar(aberto.mesa, 'aceitar-form');
    return aberto.mesa;
  };
  const senha = await caso(recusa('senha_invalida', 'A senha deve ter de 12 a 256 caracteres.'));
  assert.equal(avisos(senha)[0].textContent, 'A senha deve ter de 12 a 256 caracteres.'); assert.equal(senha.$('aceitar-senha').getAttribute('aria-invalid'), 'true');
  const nome = await caso(recusa('requisicao_invalida', 'O nome deve ter de 1 a 120 caracteres.'));
  assert.equal(avisos(nome)[0].textContent, 'Falta o nome. Escreva o seu nome.'); assert.equal(nome.$('aceitar-nome').getAttribute('aria-invalid'), 'true');
  const outra = await caso(recusa('requisicao_invalida', 'Campos inválidos no aceite do convite.'));
  assert.equal(avisos(outra).length, 0); assert.equal(outra.$('entrar-mensagem').hidden, false);
  const bloqueio = await caso(recusa('bloqueado', 'Muitas tentativas.', 'bloqueado'));
  assert.equal(bloqueio.$('entrar-mensagem').textContent, 'Muitas tentativas. Aguarde alguns minutos e tente de novo.');
  const fora = await caso(recusa('x', 'x', 'indisponivel'));
  assert.equal(fora.$('entrar-mensagem').textContent, 'Registro de acesso indisponível. Avise a administração.');
  assert.equal(fora.$('aceitar-enviar').disabled, false, 'o botão volta depois de uma recusa');
});

// --- Esqueci a senha --------------------------------------------------------------------------------------------------------------------------
test('com e-mail de verdade o link "Esqueci a senha" aparece na linha do rótulo; sem ele (tela, ou a leitura falha) fica o texto', async () => {
  const ligado = await abrir({url: 'http://127.0.0.1:8765/entrar', entrada: {esqueci_senha: true}});
  assert.equal(visivel(ligado.mesa, 'entrar-esqueci'), true); assert.equal(visivel(ligado.mesa, 'entrar-esqueci-texto'), false);
  assert.equal(ligado.mesa.$('entrar-esqueci').textContent, 'Esqueci a senha');
  assert.ok(!ligado.mesa.$('entrar-senha').closest('label').contains(ligado.mesa.$('entrar-esqueci')), 'o link não entra no nome do campo');
  for (const entrada of [{esqueci_senha: false}, new Error('fora do ar'), {}]) {
    const desligado = await abrir({url: 'http://127.0.0.1:8765/entrar', entrada});
    assert.equal(visivel(desligado.mesa, 'entrar-esqueci'), false);
    assert.equal(desligado.mesa.$('entrar-esqueci-texto').textContent, 'Esqueceu a senha? Fale com quem administra o serviço.');
    assert.equal(visivel(desligado.mesa, 'entrar-esqueci-texto'), true);
  }
});

test('Esqueci a senha: e-mail em branco, o pedido, a resposta única e o caminho de volta', async () => {
  const {mesa, chamadas} = await abrir({url: 'http://127.0.0.1:8765/entrar', entrada: {esqueci_senha: true},
    api: operacao => (operacao === 'senha-esqueci' ? {estado: 'enviado', mensagem: 'Se houver uma conta com esse e-mail, a mensagem para redefinir a senha foi enviada.'} : undefined)});
  mesa.$('entrar-esqueci').click(); await mesa.esperar(3);
  assert.equal(visivel(mesa, 'esqueci-secao'), true); assert.equal(visivel(mesa, 'entrar-secao'), false);
  assert.equal(mesa.$('esqueci-titulo').textContent, 'Criar uma senha nova');
  assert.equal(mesa.$('esqueci-email').getAttribute('autocomplete'), 'email'); assert.ok(mesa.doc.activeElement === mesa.$('esqueci-email'));
  await enviar(mesa, 'esqueci-form');
  assert.equal(avisos(mesa)[0].textContent, 'Falta o e-mail. Escreva o e-mail da sua conta.');
  assert.equal(chamadas('senha-esqueci').length, 0);
  digitar(mesa.$('esqueci-email'), '  ana@redacao.org ');
  await enviar(mesa, 'esqueci-form');
  assert.deepEqual(chamadas('senha-esqueci').map(p => p.dados), [{email: 'ana@redacao.org'}]);
  assert.equal(visivel(mesa, 'esqueci-form'), false);
  assert.equal(mesa.$('esqueci-resposta').textContent, 'Se houver uma conta com esse e-mail, enviamos um link para criar uma senha nova. Ele vale por 1 hora e uma única vez. Confira também a caixa de spam.');
  assert.ok(mesa.$('esqueci-enviado').textContent.includes('Entra com um login antigo, sem e-mail? Fale com quem administra o serviço.'));
  mesa.$('esqueci-voltar').click(); await mesa.esperar(3);
  assert.equal(visivel(mesa, 'entrar-secao'), true); assert.equal(visivel(mesa, 'esqueci-secao'), false);
});

test('Esqueci a senha chamado com o transporte `tela` mostra o mesmo texto de quando o link não aparece', async () => {
  const {mesa} = await abrir({url: 'http://127.0.0.1:8765/entrar', entrada: {esqueci_senha: true},
    api: operacao => (operacao === 'senha-esqueci' ? recusa('transporte_indisponivel', 'Nesta instalação a senha é recuperada por quem administra a redação.') : undefined)});
  mesa.$('entrar-esqueci').click(); digitar(mesa.$('esqueci-email'), 'ana@redacao.org');
  await enviar(mesa, 'esqueci-form');
  assert.equal(mesa.$('entrar-mensagem').textContent, 'Esqueceu a senha? Fale com quem administra o serviço.');
});

// --- Redefinir a senha ------------------------------------------------------------------------------------------------------------------------
const URL_REDEFINIR = `http://127.0.0.1:8765/redefinir/${TOKEN}`;
test('Redefinir: senha nova com foco, tamanho conferido, o pedido leva token e senha, e o cartão manda de volta ao Entrar (sem sessão)', async () => {
  const {mesa, chamadas, destinos} = await abrir({url: URL_REDEFINIR, api: operacao => (operacao === 'senha-redefinir' ? {estado: 'senha_redefinida'} : undefined)});
  assert.equal(mesa.$('redefinir-titulo').textContent, 'Crie uma senha nova');
  assert.ok(mesa.doc.activeElement === mesa.$('redefinir-senha')); assert.equal(mesa.$('redefinir-senha').getAttribute('autocomplete'), 'new-password');
  assert.equal(new URL(mesa.janela.location.href).pathname, '/redefinir');
  digitar(mesa.$('redefinir-senha'), 'curta');
  await enviar(mesa, 'redefinir-form');
  assert.equal(avisos(mesa)[0].textContent, 'A senha deve ter de 12 a 256 caracteres.'); assert.equal(chamadas('senha-redefinir').length, 0);
  digitar(mesa.$('redefinir-senha'), 'uma senha nova e longa');
  await enviar(mesa, 'redefinir-form');
  assert.deepEqual(chamadas('senha-redefinir').map(p => p.dados), [{token: TOKEN, senha: 'uma senha nova e longa'}]);
  assert.equal(visivel(mesa, 'redefinir-form'), false); assert.equal(visivel(mesa, 'redefinir-pronto'), true);
  assert.ok(mesa.$('redefinir-pronto').textContent.includes('Senha nova salva. As sessões abertas desta conta foram encerradas. Entre com a senha nova.'));
  assert.equal(mesa.$('redefinir-senha').value, '', 'a senha não fica no campo');
  assert.equal(destinos.length, 0, 'não abre sessão nem navega sozinha');
  mesa.$('redefinir-entrar').click();
  assert.deepEqual(destinos, [['assign', '/entrar']]);
});

test('Redefinir: link que não vale (uma resposta só) mostra o estado e "Pedir outro link", que abre Esqueci a senha', async () => {
  const sem = recusa('link_invalido', 'Link inválido, usado ou vencido. Peça outro em Esqueci a senha.');
  const {mesa} = await abrir({url: URL_REDEFINIR, api: operacao => (operacao === 'senha-redefinir' ? sem : undefined)});
  digitar(mesa.$('redefinir-senha'), 'uma senha nova e longa');
  await enviar(mesa, 'redefinir-form');
  assert.equal(mesa.$('redefinir-titulo').textContent, 'Este link não vale mais');
  assert.equal(visivel(mesa, 'redefinir-form'), false);
  assert.ok(mesa.$('redefinir-sem-efeito').textContent.includes('Link inválido, usado ou vencido. Peça outro em Esqueci a senha.'));
  mesa.$('redefinir-outro').click(); await mesa.esperar(3);
  assert.equal(visivel(mesa, 'esqueci-secao'), true);
  const recarga = await abrir({url: 'http://127.0.0.1:8765/redefinir'});
  assert.equal(recarga.mesa.$('redefinir-titulo').textContent, 'Este link não vale mais');
});

test('Redefinir: senha_invalida abaixo do campo; requisicao_invalida, 429 e 503 na caixa de aviso', async () => {
  const caso = async resposta => {
    const aberto = await abrir({url: URL_REDEFINIR, api: operacao => (operacao === 'senha-redefinir' ? resposta : undefined)});
    digitar(aberto.mesa.$('redefinir-senha'), 'uma senha nova e longa');
    await enviar(aberto.mesa, 'redefinir-form');
    return aberto.mesa;
  };
  assert.equal(avisos(await caso(recusa('senha_invalida', 'x')))[0].textContent, 'A senha deve ter de 12 a 256 caracteres.');
  assert.equal((await caso(recusa('requisicao_invalida', 'Campos inválidos na redefinição de senha.'))).$('entrar-mensagem').hidden, false);
  assert.equal((await caso(recusa('bloqueado', 'x', 'bloqueado'))).$('entrar-mensagem').textContent, 'Muitas tentativas. Aguarde alguns minutos e tente de novo.');
  assert.equal((await caso(recusa('x', 'x', 'indisponivel'))).$('entrar-mensagem').textContent, 'Registro de acesso indisponível. Avise a administração.');
});

// --- Confirmar o e-mail -----------------------------------------------------------------------------------------------------------------------
const URL_EMAIL = `http://127.0.0.1:8765/confirmar-email/${TOKEN}`;
test('Confirmar e-mail: o link é o próprio pedido; sucesso leva à Mesa, link que não vale leva à entrada; o token sai do endereço', async () => {
  const ok = await abrir({url: URL_EMAIL, api: operacao => (operacao === 'email-confirmar' ? {estado: 'email_confirmado'} : undefined)});
  assert.deepEqual(ok.chamadas('email-confirmar').map(p => p.dados), [{token: TOKEN}]);
  assert.equal(ok.mesa.$('confirmar-titulo').textContent, 'E-mail confirmado');
  assert.equal(ok.mesa.$('confirmar-texto').textContent, 'O e-mail da sua conta foi trocado. Use o novo e-mail para entrar.');
  assert.equal(ok.mesa.$('confirmar-destino').textContent, 'Ir para a Mesa'); assert.equal(ok.mesa.$('confirmar-destino').getAttribute('href'), '/');
  assert.equal(new URL(ok.mesa.janela.location.href).pathname, '/confirmar-email');
  const sem = await abrir({url: URL_EMAIL, api: operacao => (operacao === 'email-confirmar' ? recusa('link_invalido', 'Link inválido, usado ou vencido. Peça outro em Minha conta.') : undefined)});
  assert.equal(sem.mesa.$('confirmar-titulo').textContent, 'Este link não vale mais');
  assert.equal(sem.mesa.$('confirmar-texto').textContent, 'Link inválido, usado ou vencido. Peça outro em Minha conta.');
  assert.equal(sem.mesa.$('confirmar-destino').getAttribute('href'), '/entrar');
  const recarga = await abrir({url: 'http://127.0.0.1:8765/confirmar-email'});
  assert.equal(recarga.mesa.$('confirmar-titulo').textContent, 'Este link não vale mais');
  assert.equal(recarga.chamadas('email-confirmar').length, 0);
  const fora = await abrir({url: URL_EMAIL, api: operacao => (operacao === 'email-confirmar' ? recusa('x', 'x', 'indisponivel') : undefined)});
  assert.equal(fora.mesa.$('confirmar-titulo').textContent, 'Confirmar o e-mail');
  assert.equal(fora.mesa.$('entrar-mensagem').textContent, 'Registro de acesso indisponível. Avise a administração.');
});

test('as seções novas em inglês', async () => {
  const sem = await abrir({url: URL_EMAIL, idioma: 'en', api: operacao => (operacao === 'email-confirmar' ? {estado: 'email_confirmado'} : undefined)});
  assert.equal(sem.mesa.$('confirmar-titulo').textContent, 'E-mail confirmed');
  assert.equal(sem.mesa.$('confirmar-destino').textContent, 'Go to the desk');
  const esqueci = await abrir({url: 'http://127.0.0.1:8765/entrar', idioma: 'en', entrada: {esqueci_senha: true}});
  assert.equal(esqueci.mesa.$('entrar-esqueci').textContent, 'Forgot password');
  const redefinir = await abrir({url: URL_REDEFINIR, idioma: 'en'});
  assert.equal(redefinir.mesa.$('redefinir-titulo').textContent, 'Create a new password');
  assert.equal(redefinir.mesa.$('redefinir-enviar').textContent, 'Save the new password');
});

// --- O Entrar do canvas (R5 da pré-entrega do Design; componentes.md#entrar) -----------------------------------------------------------------
test('o Entrar tem marca e frase acima do cartão, "Entrar", "E-mail" e "Senha", o aviso de teste e o rodapé do canvas', async () => {
  const {mesa} = await abrir({url: 'http://127.0.0.1:8765/entrar'});
  assert.equal(mesa.doc.querySelector('.entrar-topo .brand').textContent, 'Vlado.');
  assert.equal(mesa.doc.querySelector('.entrar-frase').textContent, 'Apuração documental com a fonte de cada afirmação à vista.');
  assert.equal(mesa.$('entrar-titulo').textContent, 'Entrar');
  assert.equal(mesa.$('entrar-login').closest('label').querySelector('span').textContent, 'E-mail', 'a entrada aceita o e-mail (e o login antigo)');
  assert.equal(mesa.$('entrar-login').getAttribute('autocomplete'), 'username');
  assert.equal(mesa.$('entrar-enviar').textContent, 'Entrar');
  assert.equal(visivel(mesa, 'entrar-teste'), true);
  assert.equal(mesa.$('entrar-teste').querySelector('.entrar-aviso-titulo').textContent, 'O Vlado está em teste com redações convidadas');
  assert.ok(mesa.$('entrar-teste').textContent.includes('O acesso chega por convite, no e-mail da sua redação. Recebeu um? Abra o link do convite para criar a conta.'));
  const rodape = mesa.doc.querySelector('.entrar-rodape');
  assert.ok(rodape.textContent.includes('Use só documentos públicos. Trechos são enviados ao provedor de IA para análise.'));
  assert.ok(rodape.contains(mesa.$('entrar-idioma')) && rodape.contains(mesa.$('entrar-tema')), 'idioma e tema ficam no rodapé');
  assert.equal(mesa.doc.querySelector('.entrar-topo').contains(mesa.$('entrar-idioma')), false);
  mesa.$('entrar-idioma').click(); await mesa.esperar(3);
  assert.equal(mesa.$('entrar-titulo').textContent, 'Sign in');
  assert.equal(mesa.doc.querySelector('.entrar-frase').textContent, 'Documentary reporting with the source of every claim in sight.');
  assert.equal(mesa.$('entrar-idioma').textContent, 'Português');
});

test('o aviso de teste é só da entrada: some no convite, na redefinição e em Esqueci a senha', async () => {
  assert.equal(visivel((await abrir()).mesa, 'entrar-teste'), false, 'convite');
  assert.equal(visivel((await abrir({url: URL_REDEFINIR})).mesa, 'entrar-teste'), false, 'redefinir');
  const esqueci = await abrir({url: 'http://127.0.0.1:8765/entrar', entrada: {esqueci_senha: true}});
  esqueci.mesa.$('entrar-esqueci').click(); await esqueci.mesa.esperar(3);
  assert.equal(visivel(esqueci.mesa, 'entrar-teste'), false, 'Esqueci a senha');
  esqueci.mesa.$('esqueci-voltar').click(); await esqueci.mesa.esperar(3);
  assert.equal(visivel(esqueci.mesa, 'entrar-teste'), true, 'de volta à entrada');
});

test('o Entrar não oferece o que o dono tirou: chave de acesso, e não inventa os links de Termos e Privacidade sem destino', async () => {
  const {mesa} = await abrir({url: 'http://127.0.0.1:8765/entrar'});
  const texto = mesa.doc.body.textContent;
  assert.ok(!/chave de acesso/i.test(texto));
  assert.equal([...mesa.doc.querySelectorAll('a')].filter(a => /termos|privacidade/i.test(a.textContent)).length, 0);
});
