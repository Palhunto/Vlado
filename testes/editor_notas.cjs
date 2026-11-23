// Drive the real Vditor UI; persisted Markdown remains observable in the backing field.
// Vditor's own toolbar (with the mode switch) sits under the Caderno's "Mais" button.
async function more(page){
  await page.locator('#apuracao-formatar:not([hidden])').waitFor();
  if(await page.locator('#apuracao-mais').getAttribute('aria-expanded')!=='true')await page.click('#apuracao-mais');
  await page.locator('#apuracao-vditor .vditor-toolbar').waitFor();
}
async function mode(page,name){
  await more(page);
  // O menu dos modos do Vditor abre ao passar o mouse e ao clicar: espera a barra assentar, passa o mouse e só clica se ainda não abriu
  // (um clique a mais fecharia o menu aberto; intermitência medida em qa_visual).
  const alvo=page.locator(`#apuracao-vditor button[data-mode="${name}"]`);
  const modo=page.locator('#apuracao-vditor button[data-type="edit-mode"]');
  await page.locator('#apuracao-vditor .vditor-toolbar').waitFor({state:'visible'});
  await page.waitForTimeout(300);
  await modo.hover();
  const aberto=()=>alvo.waitFor({state:'visible',timeout:2500}).then(()=>true,()=>false);
  if(!await aberto()){
    await modo.click();
    if(!await aberto()){await modo.click();await alvo.waitFor({state:'visible',timeout:4000});}
  }
  await alvo.click();
}
async function write(page,text){
  if(!await page.locator('#apuracao-vditor .vditor-sv').isVisible())await mode(page,'sv');
  await page.locator('#apuracao-vditor .vditor-sv').fill(text);
  await page.waitForFunction(text=>document.querySelector('#apuracao-texto').value.trim()===text.trim(),text);
}
const read=page=>page.locator('#apuracao-texto').inputValue();
module.exports={more,mode,write,read};
