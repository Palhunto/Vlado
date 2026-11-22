'use strict';
// Entrar, num navegador de verdade (Chromium) contra o servidor de verdade: convite, Esqueci a senha, Redefinir e Confirmar e-mail.
// Quem chama é testes/test_entrar_navegador.py, que sobe o servidor, cria os links e depois confere o que o servidor guardou.
// Uso: node qa_entrar_convites.cjs '<json>'   com {porta, origem, esqueci, convites[4], redefinires[4], emails[4], capturas?}: um de cada por tela e tema.
// Sem argumento não faz nada (o `node --test testes/*.cjs` não precisa de servidor). Com `capturas`, grava um PNG por estado, em 375 e 1440 px, nos dois temas.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

if (!process.argv[2]) process.exit(0);
const args = JSON.parse(process.argv[2]);
const {chromium} = require(path.join(__dirname, '..', '.ferramentas', 'node', 'node_modules', 'playwright'));

const TELAS = [['375', {width: 375, height: 812}], ['1440', {width: 1440, height: 900}]];
const TEMAS = ['light', 'dark'];

async function contexto(browser, tela, tema) {
  const ctx = await browser.newContext({viewport: tela, colorScheme: tema, locale: 'pt-BR'});
  // O servidor fala HTTP e se apresenta como a origem https: o navegador vê a origem, e o servidor recebe o pedido com o Host e o Origin certos.
  await ctx.route(`${args.origem}/**`, async rota => {
    const pedido = rota.request(), endereco = new URL(pedido.url());
    const resposta = await rota.fetch({url: `http://127.0.0.1:${args.porta}${endereco.pathname}${endereco.search}`,
      headers: {...pedido.headers(), host: new URL(args.origem).host}, maxRedirects: 0});
    await rota.fulfill({response: resposta});
  });
  return ctx;
}
async function capturar(page, nome, tela, tema) {
  if (!args.capturas) return;
  fs.mkdirSync(args.capturas, {recursive: true});
  await page.screenshot({path: path.join(args.capturas, `${nome}-${tela}-${tema}.png`), fullPage: true});
}
// Espera um elemento; se não vier, o erro diz em que página parou e o que a caixa de aviso dizia (ajuda a ver a recusa do servidor).
async function aguardar(pagina, seletor) {
  try { await pagina.waitForSelector(seletor, {timeout: 15000}); }
  catch (erro) {
    const aviso = await pagina.textContent('#entrar-mensagem').catch(() => '?');
    throw new Error(`faltou ${seletor} em ${pagina.url()}; caixa de aviso: ${JSON.stringify(aviso)}; ${erro.message.split('\n')[0]}`);
  }
}
const texto = async (page, seletor) => (await page.textContent(seletor)).replace(/\s+/g, ' ').trim();

(async () => {
  const browser = await chromium.launch();
  const resultado = {};
  try {
    let indice = -1;
    // Cada tela e tema usa o seu próprio convite, link de redefinição e link de e-mail (cada um vale uma vez).
    for (const [rotuloTela, tela] of TELAS) for (const tema of TEMAS) {
      indice += 1;
      const convite = args.convites[indice], redefinir = args.redefinires[indice], confirmar = args.emails[indice];
      const marca = `${rotuloTela}-${tema}`;
      const ctx = await contexto(browser, tela, tema);
      const erros = [];
      const nova = async () => { const pagina = await ctx.newPage(); pagina.on('pageerror', erro => erros.push(erro.message)); return pagina; };

      // 1. Entrar com "Esqueci a senha" ligado (transporte simulado) e o pedido do link
      const entrar = await nova();
      await entrar.goto(`${args.origem}/entrar`);
      await aguardar(entrar, '#entrar-esqueci:not([hidden])');
      assert.equal(await entrar.isVisible('#entrar-esqueci-texto'), false);
      assert.equal(await texto(entrar, '#entrar-esqueci'), 'Esqueci a senha');
      await capturar(entrar, 'entrar-esqueci-link', rotuloTela, tema);
      await entrar.click('#entrar-esqueci');
      await aguardar(entrar, '#esqueci-secao:not([hidden])');
      await capturar(entrar, 'esqueci-formulario', rotuloTela, tema);
      await entrar.fill('#esqueci-email', args.esqueci);
      await entrar.click('#esqueci-enviar');
      await aguardar(entrar, '#esqueci-enviado:not([hidden])');
      assert.equal(await texto(entrar, '#esqueci-resposta'),
        'Se houver uma conta com esse e-mail, enviamos um link para criar uma senha nova. Ele vale por 1 hora e uma única vez. Confira também a caixa de spam.');
      await capturar(entrar, 'esqueci-enviado', rotuloTela, tema);
      await entrar.close();
      resultado[`esqueci-${marca}`] = 'ok';

      // 2. Convite: o que a pessoa vê, o erro de campo, o aceite (a sessão já aberta) e o mesmo link de novo
      const aceitar = await nova();
      await aceitar.goto(`${args.origem}/aceitar/${convite.token}`);
      await aguardar(aceitar, '#aceitar-cartao:not([hidden])');
      assert.equal(await texto(aceitar, '#aceitar-titulo'), `Entre na ${convite.redacao}`);
      assert.equal(await texto(aceitar, '#aceitar-texto'), `${convite.por} convidou ${convite.email} como Repórter.`);
      assert.equal(new URL(aceitar.url()).pathname, '/aceitar', 'o token saiu do endereço');
      assert.equal(await aceitar.inputValue('#aceitar-email'), convite.email);
      await capturar(aceitar, 'aceitar-convite', rotuloTela, tema);
      await aceitar.click('#aceitar-enviar');   // sem nome: erro junto ao campo, nada enviado
      assert.equal(await texto(aceitar, '.campo-erro'), 'Falta o nome. Escreva o seu nome.');
      await capturar(aceitar, 'aceitar-erro-de-campo', rotuloTela, tema);
      await aceitar.fill('#aceitar-nome', convite.nome);
      await aceitar.fill('#aceitar-senha', convite.senha);
      await Promise.all([aceitar.waitForURL(url => !url.pathname.startsWith('/aceitar')), aceitar.click('#aceitar-enviar')]);
      assert.equal(new URL(aceitar.url()).pathname, '/', `foi à Mesa: ${aceitar.url()}`);
      const sessao = await aceitar.evaluate(async () => (await fetch('/api/sessao')).json());
      assert.equal(sessao.conta.email, convite.email, 'a sessão já está aberta');
      assert.equal(sessao.conta.papel, 'reporter');
      await aceitar.evaluate(() => localStorage.setItem('vlado-idioma', 'pt'));   // a Mesa pode ter guardado o idioma padrão do servidor
      await aceitar.goto(`${args.origem}/aceitar/${convite.token}`);   // o mesmo link: uma resposta só, sem dizer a causa
      await aguardar(aceitar, '#aceitar-cartao:not([hidden])');
      assert.equal(await texto(aceitar, '#aceitar-titulo'), 'Este convite não vale mais');
      assert.equal(await texto(aceitar, '#aceitar-texto'), 'Convite inválido, cancelado ou vencido. Peça um novo a quem convidou.');
      await capturar(aceitar, 'aceitar-sem-efeito', rotuloTela, tema);
      await aceitar.close();
      resultado[`aceitar-${marca}`] = 'ok';

      // 3. Redefinir a senha: o formulário, o cartão de sucesso, "Entrar", e o mesmo link de novo (com "Pedir outro link")
      const senha = await nova();
      await senha.goto(`${args.origem}/redefinir/${redefinir.token}`);
      await aguardar(senha, '#redefinir-form:not([hidden])');
      assert.equal(await texto(senha, '#redefinir-titulo'), 'Crie uma senha nova');
      await capturar(senha, 'redefinir-formulario', rotuloTela, tema);
      await senha.fill('#redefinir-senha', redefinir.senha);
      await senha.click('#redefinir-enviar');
      await aguardar(senha, '#redefinir-pronto:not([hidden])');
      assert.ok((await texto(senha, '#redefinir-pronto')).startsWith('Senha nova salva. As sessões abertas desta conta foram encerradas. Entre com a senha nova.'));
      await capturar(senha, 'redefinir-pronto', rotuloTela, tema);
      await Promise.all([senha.waitForURL(url => url.pathname === '/entrar'), senha.click('#redefinir-entrar')]);
      await senha.goto(`${args.origem}/redefinir/${redefinir.token}`);
      await senha.fill('#redefinir-senha', redefinir.senha);
      await senha.click('#redefinir-enviar');
      await aguardar(senha, '#redefinir-sem-efeito:not([hidden])');
      assert.equal(await texto(senha, '#redefinir-titulo'), 'Este link não vale mais');
      await capturar(senha, 'redefinir-sem-efeito', rotuloTela, tema);
      await senha.click('#redefinir-outro');
      await aguardar(senha, '#esqueci-secao:not([hidden])');
      await senha.close();
      resultado[`redefinir-${marca}`] = 'ok';

      // 4. Confirmar o e-mail: o sucesso e o mesmo link de novo
      const email = await nova();
      await email.goto(`${args.origem}/confirmar-email/${confirmar.token}`);
      await aguardar(email, '#confirmar-cartao:not([hidden])');
      assert.equal(await texto(email, '#confirmar-titulo'), 'E-mail confirmado');
      await capturar(email, 'confirmar-email', rotuloTela, tema);
      await email.goto(`${args.origem}/confirmar-email/${confirmar.token}`);
      await aguardar(email, '#confirmar-cartao:not([hidden])');
      assert.equal(await texto(email, '#confirmar-titulo'), 'Este link não vale mais');
      await capturar(email, 'confirmar-email-sem-efeito', rotuloTela, tema);
      await email.close();
      resultado[`email-${marca}`] = 'ok';

      assert.deepEqual(erros, [], 'nenhum erro de JavaScript nas páginas');
      await ctx.close();
    }
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify(resultado));
})().catch(erro => { console.error(erro.stack || erro); process.exit(1); });
