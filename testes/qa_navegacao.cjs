'use strict';
// Caminhos dos roteiros Playwright pela barra lateral VISÍVEL da Mesa (a estrutura do canvas, Onda 3, fase 3).
// Cadastro, "Apurações e lixeira" e "Nova apuração" saíram da barra (ficam ocultos no DOM): clicar nos ids ocultos
// (#ver-cadastro, #ver-gerenciar, #mesa-nova) não funciona mais. Quando a barra mudar de novo, só este arquivo muda.
//   Cadastro e recibo       = Documentos > aba "Cadastro e recibo"
//   Apurações e lixeira     = Visão geral > "Trocar de apuração" (some quando ainda não há apuração)
//   Nova apuração           = Visão geral > "Nova apuração"
// Pré-condição: viewport de desktop (no celular a barra é uma gaveta; abra-a antes).

async function irParaCadastro(pagina) {
  await pagina.click('#ver-documentos');
  await pagina.click('#mesa-aba-recibo');
}

async function irParaGerenciar(pagina) {
  await pagina.click('#ver-inicio');
  await pagina.click('#inicio-trocar');
}

async function irParaNovaApuracao(pagina) {
  await pagina.click('#ver-inicio');
  await pagina.click('#inicio-nova');
}

module.exports = {irParaCadastro, irParaGerenciar, irParaNovaApuracao};
