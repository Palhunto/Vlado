'use strict';
// Caminhos dos roteiros Playwright pela barra lateral VISÍVEL da Mesa (a estrutura do canvas, Onda 3, fase 3).
// Cadastro, "Apurações e lixeira" e "Nova apuração" saíram da barra (ficam ocultos no DOM): clicar nos ids ocultos
// (#ver-gerenciar, #mesa-nova) não funciona mais. Quando a barra mudar de novo, só este arquivo muda.
//   Documentos              = barra lateral > Documentos (#area-documentos): lista, área de envio (#documentos-zona) e recibo
//   Nova apuração           = Visão geral > "Nova apuração" (#area-nova, passo 1: nome, natureza, fontes) > "Continuar para
//                             documentos" (passo 2: a mesma tela Documentos; o primeiro lote enviado cria a apuração)
//   Apurações e lixeira     = Visão geral > "Trocar de apuração" (some quando ainda não há apuração)
// A área "Cadastrar arquivos" (#area-cadastro, #cadastro-*) saiu (R4, P16.5): o envio de uma apuração que já existe é a área de
// envio de Documentos, e uma apuração nova nasce pela Nova apuração.
// Pré-condição: viewport de desktop (no celular a barra é uma gaveta; abra-a antes).

async function irParaDocumentos(pagina) {
  await pagina.click('#ver-documentos');
  await pagina.locator('#area-documentos:not([hidden])').waitFor();
}

async function irParaGerenciar(pagina) {
  await pagina.click('#ver-inicio');
  await pagina.click('#inicio-trocar');
}

async function irParaNovaApuracao(pagina) {
  await pagina.click('#ver-inicio');
  await pagina.click('#inicio-nova');
  await pagina.locator('#area-nova:not([hidden])').waitFor();
}

// Passo 1 da Nova apuração preenchido até "Continuar para documentos"; termina na tela Documentos (passo 2), ainda sem apuração criada.
async function criarApuracao(pagina, {nome, natureza = 'publicos', fontes = 'somente_documental', site = ''} = {}) {
  await irParaNovaApuracao(pagina);
  await pagina.fill('#nova-nome', nome);
  await pagina.selectOption('#nova-natureza', natureza);
  if (fontes === 'documentos_web') {
    await pagina.check('input[name="nova-fontes"][value="documentos_web"]');
    await pagina.fill('#nova-site', site);
  }
  await pagina.click('#nova-continuar');
  await pagina.locator('#area-documentos:not([hidden])').waitFor();
}

// Envia arquivos pela área de envio de Documentos e espera o recibo do lote (novo, se já havia um de um lote anterior).
async function enviarArquivos(pagina, arquivos, {timeout = 60000} = {}) {
  const recibo = pagina.locator('#documentos-recibo');
  const antes = await recibo.evaluate(el => el.hidden ? '' : el.textContent).catch(() => '');
  await pagina.setInputFiles('#documentos-zona input[type=file]', arquivos);
  await pagina.waitForFunction(textoAntes => {
    const el = document.getElementById('documentos-recibo');
    return el && !el.hidden && el.textContent.includes('Recibo do lote') && el.textContent !== textoAntes;
  }, antes, {timeout});
}

// Diálogo de confirmação próprio da Mesa (Dialogo.confirmar, UX-16): substitui o confirm() do navegador, então page.once('dialog') não o alcança.
// A ação principal é o botão que não é "secondary" (".danger" nas destrutivas); Cancelar é o "secondary". Esc também cancela.
const DIALOGO = 'dialog.dialogo[open]';
async function dialogoConfirmar(pagina) {
  const caixa = pagina.locator(DIALOGO).last();
  await caixa.waitFor();
  await caixa.locator('.dialogo-acoes button:not(.secondary)').click();
  await caixa.waitFor({state: 'hidden'});
}
async function dialogoCancelar(pagina) {
  const caixa = pagina.locator(DIALOGO).last();
  await caixa.waitFor();
  await caixa.locator('.dialogo-acoes button.secondary').click();
  await caixa.waitFor({state: 'hidden'});
}

module.exports = {irParaDocumentos, irParaGerenciar, irParaNovaApuracao, criarApuracao, enviarArquivos, dialogoConfirmar, dialogoCancelar};
