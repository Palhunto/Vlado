"""Uma apuração MÉDIA, toda sintética, na Redação Beta de uma prévia que já existe (preparada por testes/previa_dono.py). NÃO é um teste (fora da suíte).

  .venv/Scripts/python.exe testes/previa_apuracao_media.py --pasta <pasta da prévia>        (a que tem piloto/ dentro)

Grava SÓ em <pasta>/piloto e não toca o servidor: não o reinicia nem fala com ele. Nenhuma chamada de modelo ou de rede. Tudo pelos mesmos caminhos do código da Mesa
(cadastro de documentos, rodada e achados publicados pela fixture, hipóteses, linha do tempo, mapa, perguntas, diligências e notas do caderno), como scripts/demo_evidencias.py.

A apuração: "Merenda escolar de Vale do Sol" (município fictício), na redação Beta: dono Dono Beta, participa Rep Beta. 10 documentos (8 txt, 1 xlsx, 1 docx), uma rodada com
8 achados, 4 hipóteses (sustenta, contraria e falta), 15 acontecimentos em 3 anos com os 10 tipos de data, 12 entidades e 14 ligações no mapa, 6 perguntas (e as 6
diligências que nascem delas), 4 pedidos e prazos à parte em estados diferentes, 3 notas, e dois documentos feitos para a comparação (contrato e termo aditivo).
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import sys
import tempfile
import uuid

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'scripts'))
sys.path.insert(0, str(RAIZ / 'testes'))

CASO = 'merenda_vale_do_sol_sintetico'
TITULO = 'Merenda escolar de Vale do Sol (sintética)'
LOGIN_DONO, LOGIN_REPORTER = 'dono.beta', 'rep.beta'
MUNICIPIO = 'Vale do Sol'

# --- os documentos --------------------------------------------------------------------------------------------------------------------------------------------------
AVISO = 'DOCUMENTO SINTÉTICO PARA TESTE DA MESA. Nomes, empresas, valores e datas são fictícios.'
EDITAL = [AVISO, 'PREFEITURA MUNICIPAL DE VALE DO SOL', 'EDITAL DO PREGÃO ELETRÔNICO Nº 017/2023', 'Publicado em 14 de março de 2023.',
          'Objeto: fornecimento de merenda escolar para a rede municipal de ensino, por doze meses.',
          'Valor máximo estimado: R$ 1.920.000,00 (um milhão, novecentos e vinte mil reais).',
          'A abertura das propostas está marcada para 5 de abril de 2023.',
          'Exigência de habilitação: no mínimo três propostas válidas para a sessão de disputa.',
          'Fiscal do contrato a ser designado pela Secretaria Municipal de Educação.']
ATA = [AVISO, 'ATA DA SESSÃO DO PREGÃO ELETRÔNICO Nº 017/2023', 'Sessão realizada em 5 de abril de 2023, às 10h.',
       'Foram recebidas duas propostas válidas: Nutri Vale Alimentos Ltda. e Comercial Horizonte Merenda ME.',
       'A Nutri Vale Alimentos Ltda. ofertou R$ 1.840.000,00 e foi declarada vencedora.',
       'A Comercial Horizonte Merenda ME ofertou R$ 1.905.000,00.',
       'O pregoeiro prosseguiu a sessão com duas propostas, sem registrar justificativa para a exigência do edital.',
       'Ata assinada em 6 de abril de 2023 pelo pregoeiro Eduardo Salles.']
CONTRATO = [AVISO, 'CONTRATO Nº 062/2023', 'Contratante: Município de Vale do Sol, por meio da Secretaria Municipal de Educação.',
            'Contratada: Nutri Vale Alimentos Ltda., CNPJ fictício 00.000.000/0001-00.',
            'Cláusula 1. Objeto: fornecimento de merenda escolar por doze meses.',
            'Cláusula 2. Valor global: R$ 1.840.000,00 (um milhão, oitocentos e quarenta mil reais).',
            'Cláusula 3. Vigência: de 15 de maio de 2023 a 14 de maio de 2024.',
            'Cláusula 4. Pagamento em doze parcelas mensais, contra atesto da entrega pelo fiscal.',
            'Cláusula 5. Fiscal do contrato: Helena Brandão.',
            'Cláusula 6. Contrato assinado em 2 de maio de 2023 pela secretária Marta Cavalcante Dias e por Otávio Mendes Lacerda.']
ADITIVO = [linha.replace('CONTRATO Nº 062/2023', 'TERMO ADITIVO Nº 01 AO CONTRATO Nº 062/2023')
               .replace('R$ 1.840.000,00 (um milhão, oitocentos e quarenta mil reais)', 'R$ 2.300.000,00 (dois milhões e trezentos mil reais)')
               .replace('de 15 de maio de 2023 a 14 de maio de 2024', 'de 15 de maio de 2023 a 14 de novembro de 2024')
               .replace('assinado em 2 de maio de 2023', 'assinado em 2 de maio de 2023; este termo, em 18 de setembro de 2024')
           for linha in CONTRATO]
ADITIVO.append('Cláusula 7. O acréscimo de R$ 460.000,00 corresponde a 25% do valor original, conforme parecer jurídico nº 033/2024.')
PARECER = [AVISO, 'PARECER JURÍDICO Nº 033/2024', 'Consulta: aditivo de valor ao contrato nº 062/2023, em 21 de agosto de 2024.',
           'O acréscimo não pode exceder 25% do valor inicial atualizado do contrato.',
           'O valor pretendido, R$ 460.000,00, equivale exatamente a 25% de R$ 1.840.000,00.',
           'Recomenda-se a motivação formal do aditivo e a comprovação de que as entregas do período foram atestadas.',
           'Não consta dos autos o atesto de entregas dos meses de novembro de 2023 a janeiro de 2024.',
           'Parecer emitido pelo procurador municipal Eduardo Salles.']
EMPENHO = [AVISO, 'NOTA DE EMPENHO Nº 0412/2024', 'Data de emissão: 12 de março de 2024.',
           'Credor: Nutri Vale Alimentos Ltda.', 'Valor empenhado: R$ 153.333,33, referente à parcela de fevereiro de 2024.',
           'Pagamento realizado em 20 de março de 2024.', 'Dotação: Educação, alimentação escolar.']
FISCALIZACAO = [AVISO, 'RELATÓRIO DE FISCALIZAÇÃO DO CONTRATO Nº 062/2023', 'Período: maio de 2023 a fevereiro de 2024. Emitido em março de 2024.',
                'Fiscal responsável: Helena Brandão.',
                'Entregas incompletas em 7 dos 10 meses fiscalizados, com faltas de hortifrúti e proteínas.',
                'Em três meses, novembro de 2023, dezembro de 2023 e janeiro de 2024, não há registro de entrega.',
                'Mesmo assim, as parcelas desses meses foram pagas integralmente.',
                'A Nutri Vale Alimentos Ltda. subcontratou a Comercial Horizonte Merenda ME para parte do hortifrúti.',
                'Observação: Otávio Mendes Lacerda consta como sócio das duas empresas no cadastro municipal de fornecedores.']
OFICIO = [AVISO, 'OFÍCIO Nº 118/2025 – SECRETARIA MUNICIPAL DE EDUCAÇÃO', 'Resposta ao pedido da Controladoria, recebido em 10 de fevereiro de 2025.',
          'A Secretaria afirma que todas as entregas foram realizadas e que o atesto é prática verbal.',
          'A Secretaria informa que o aditivo foi motivado pela ampliação do número de alunos atendidos.',
          'Não foram anexados novos atestos de entrega.', 'Assinado pela secretária Marta Cavalcante Dias em 3 de março de 2025.']
TEXTOS = {'edital_pregao_017_2023.txt': EDITAL, 'ata_sessao_pregao_017_2023.txt': ATA, 'contrato_062_2023.txt': CONTRATO,
          'termo_aditivo_01_contrato_062_2023.txt': ADITIVO, 'parecer_juridico_033_2024.txt': PARECER, 'nota_empenho_0412_2024.txt': EMPENHO,
          'relatorio_fiscalizacao_merenda_2024.txt': FISCALIZACAO, 'oficio_118_2025_secretaria_educacao.txt': OFICIO}


def escrever_xlsx(arquivo: Path, folha: str, linhas: list[list]) -> None:
    """Uma planilha .xlsx mínima e válida (texto em linha, números), sem biblioteca de planilhas."""
    import zipfile
    from xml.sax.saxutils import escape

    def coluna(i):
        return 'ABCDEFGHIJ'[i]
    corpo = []
    for n, linha in enumerate(linhas, start=1):
        celulas = []
        for i, valor in enumerate(linha):
            ref = f'{coluna(i)}{n}'
            if isinstance(valor, (int, float)):
                celulas.append(f'<c r="{ref}"><v>{valor}</v></c>')
            else:
                celulas.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(valor))}</t></is></c>')
        corpo.append(f'<row r="{n}">{"".join(celulas)}</row>')
    partes = {
        '[Content_Types].xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                               '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                               '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                               '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        '_rels/.rels': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                           f'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{escape(folha)}" sheetId="1" r:id="rId1"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                      '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        'xl/worksheets/sheet1.xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                                    f'<sheetData>{"".join(corpo)}</sheetData></worksheet>',
    }
    with zipfile.ZipFile(arquivo, 'w', zipfile.ZIP_DEFLATED) as pacote:
        for nome, conteudo in partes.items():
            pacote.writestr(nome, conteudo)


def escrever_documentos(pasta: Path) -> list[Path]:
    """8 txt, 1 xlsx (planilha dos pagamentos) e 1 docx (relatório da Controladoria)."""
    import docx
    arquivos = []
    for nome, linhas in TEXTOS.items():
        arquivo = pasta / nome
        arquivo.write_text('\n'.join(linhas) + '\n', encoding='utf-8')
        arquivos.append(arquivo)
    arquivo = pasta / 'planilha_pagamentos_contrato_062_2023.xlsx'
    parcelas = [('01', '2023-06', 153333.33, '2023-07-05', 'sim'), ('02', '2023-07', 153333.33, '2023-08-04', 'sim'), ('03', '2023-08', 153333.33, '2023-09-05', 'sim'),
                ('04', '2023-09', 153333.33, '2023-10-04', 'sim'), ('05', '2023-10', 153333.33, '2023-11-06', 'sim'), ('06', '2023-11', 153333.33, '2023-12-05', 'não'),
                ('07', '2023-12', 153333.33, '2024-01-04', 'não'), ('08', '2024-01', 153333.33, '2024-02-05', 'não'), ('09', '2024-02', 153333.33, '2024-03-20', 'sim'),
                ('10', '2024-03', 153333.33, '2024-04-04', 'sim'), ('11', '2024-04', 153333.34, '2024-05-06', 'sim'), ('12', 'aditivo', 460000.00, '2024-11-08', 'não')]
    linhas = [['Parcela', 'Mês de referência', 'Valor pago (R$)', 'Data do pagamento', 'Atesto de entrega'], *[list(p) for p in parcelas],
              ['Total', '', round(sum(p[2] for p in parcelas), 2), '', '']]
    escrever_xlsx(arquivo, 'Pagamentos', linhas)
    arquivos.append(arquivo)
    documento = docx.Document()
    documento.add_heading('Relatório de auditoria da Controladoria-Geral do Município', level=1)
    documento.add_paragraph(AVISO)
    for paragrafo in ('Auditoria sobre o contrato nº 062/2023 (merenda escolar), concluída em junho de 2025 pela controladora Joana Prates.',
                      'Constatação 1: o pregão prosseguiu com duas propostas, contra a exigência do edital de ao menos três.',
                      'Constatação 2: três parcelas foram pagas sem atesto de entrega, e a parcela do aditivo foi paga em 8 de novembro de 2024 sem atesto.',
                      'Constatação 3: sócio comum entre a contratada e a empresa subcontratada, sem declaração de conflito de interesses.',
                      'Recomendação: encaminhar o relatório ao Tribunal de Contas do Estado e ao Ministério Público.'):
        documento.add_paragraph(paragrafo)
    arquivo = pasta / 'relatorio_controladoria_2025.docx'
    documento.save(arquivo)
    arquivos.append(arquivo)
    return arquivos


# --- achados: a rodada R001, publicada pelo caminho da fixture ----------------------------------------------------------------------------------------------------------
# (documento, trecho da linha, atribuição, contexto, limitação) por evidência; os números vêm da posição da linha no arquivo
EVIDENCIAS = [
    ('E001', 'contrato_062_2023.txt', 'Cláusula 2. Valor global', 'Contrato nº 062/2023', 'Valor global declarado no contrato.', 'O contrato não prova que o valor foi pago.'),
    ('E002', 'termo_aditivo_01_contrato_062_2023.txt', 'Cláusula 2. Valor global', 'Termo aditivo nº 01', 'Novo valor global declarado no aditivo.', 'Declaração do próprio termo.'),
    ('E003', 'termo_aditivo_01_contrato_062_2023.txt', 'Cláusula 7.', 'Termo aditivo nº 01', 'Acréscimo de R$ 460.000,00, 25% do valor original.', 'Cita o parecer, mas não o reproduz.'),
    ('E004', 'parecer_juridico_033_2024.txt', 'não pode exceder 25%', 'Parecer jurídico nº 033/2024', 'Limite legal do acréscimo segundo o parecer.', 'Opinião jurídica, não decisão.'),
    ('E005', 'parecer_juridico_033_2024.txt', 'Não consta dos autos o atesto', 'Parecer jurídico nº 033/2024', 'Lacuna de atesto apontada pelo procurador.', 'Não diz se as entregas ocorreram.'),
    ('E006', 'relatorio_fiscalizacao_merenda_2024.txt', 'Entregas incompletas em 7', 'Relatório de fiscalização', 'Entregas incompletas em 7 de 10 meses.', 'Período de maio de 2023 a fevereiro de 2024.'),
    ('E007', 'relatorio_fiscalizacao_merenda_2024.txt', 'não há registro de entrega', 'Relatório de fiscalização', 'Três meses sem registro de entrega.', 'Ausência de registro não é prova de ausência de entrega.'),
    ('E008', 'relatorio_fiscalizacao_merenda_2024.txt', 'foram pagas integralmente', 'Relatório de fiscalização', 'Parcelas dos meses sem entrega pagas.', 'Fiscal não anexa os comprovantes de pagamento.'),
    ('E009', 'relatorio_fiscalizacao_merenda_2024.txt', 'consta como sócio das duas empresas', 'Relatório de fiscalização', 'Sócio comum no cadastro de fornecedores.', 'Cadastro municipal, não registro da Junta Comercial.'),
    ('E010', 'ata_sessao_pregao_017_2023.txt', 'duas propostas válidas', 'Ata do pregão', 'Só duas propostas válidas.', 'Ata não diz por que prosseguiu.'),
    ('E011', 'edital_pregao_017_2023.txt', 'no mínimo três propostas', 'Edital do pregão', 'Exigência do edital de ao menos três propostas.', 'Texto do edital.'),
    ('E012', 'oficio_118_2025_secretaria_educacao.txt', 'todas as entregas foram realizadas', 'Ofício da Secretaria', 'Versão da Secretaria: entregas realizadas.', 'Declaração da parte interessada, sem anexos.'),
    ('E013', 'nota_empenho_0412_2024.txt', 'Valor empenhado', 'Nota de empenho', 'Parcela de fevereiro de 2024 empenhada.', 'Um empenho isolado.'),
    ('E014', 'ata_sessao_pregao_017_2023.txt', 'ofertou R$ 1.840.000,00', 'Ata do pregão', 'Proposta vencedora.', 'Valor da proposta, não do pagamento.'),
]
# (id, pergunta, natureza, limitações, [(evidência, papel)])
ACHADOS = [
    ('A001', 'Qual o valor do contrato nº 062/2023?', 'declaracao_documental', 'Valor contratual, não o efetivamente pago.', [('E001', 'suporte'), ('E014', 'contexto')]),
    ('A002', 'O aditivo elevou o valor do contrato?', 'declaracao_documental', 'Conforme o próprio termo aditivo.', [('E002', 'suporte'), ('E003', 'suporte')]),
    ('A003', 'O aditivo respeitou o limite de 25%?', 'inferencia', 'Depende do valor inicial atualizado, que o parecer não detalha.', [('E003', 'suporte'), ('E004', 'suporte')]),
    ('A004', 'As entregas foram completas?', 'declaracao_documental', 'Relatório cobre dez dos doze meses.', [('E006', 'suporte'), ('E012', 'contradicao')]),
    ('A005', 'Houve pagamento sem entrega registrada?', 'alegacao_atribuida', 'Atribuída ao relatório de fiscalização.', [('E007', 'suporte'), ('E008', 'suporte'), ('E005', 'contexto')]),
    ('A006', 'A contratada e a subcontratada têm sócio em comum?', 'alegacao_atribuida', 'Cadastro municipal, sem conferência na Junta Comercial.', [('E009', 'suporte')]),
    ('A007', 'O pregão cumpriu a exigência de propostas?', 'declaracao_documental', 'A ata não registra justificativa.', [('E010', 'suporte'), ('E011', 'contradicao')]),
    ('A008', 'Há comprovante das entregas dos três meses sem registro?', 'pendencia', 'Nenhum documento do acervo comprova.', []),
]


def numero_da_linha(pasta_dos_arquivos: Path, nome: str, trecho: str) -> tuple[int, str]:
    for numero, linha in enumerate((pasta_dos_arquivos / nome).read_text(encoding='utf-8').splitlines(), start=1):
        if trecho in linha:
            return numero, linha
    raise SystemExit(f'Trecho {trecho!r} não está em {nome}.')


def publicar_achados(root: Path, caso: str, arquivos: Path):
    """Rodada R001 e achados publicados (r1) e revisados com briefing (r2), no formato e pelas funções da fixture de achados, sem modelo. Devolve (ia, publicados)."""
    from fixture_achados import Ambiente
    from comum import sha256
    from indice_achados import construir
    from nova_rodada import criar_rodada
    from registros_achados import publicar
    from selecionar_caso import selecionar
    selecionar(root, caso)
    try:
        criar_rodada(root, 'R001', 'Os contratos de merenda escolar de Vale do Sol foram cumpridos e aditados dentro da lei? (pergunta sintética)', indice=False)
    finally:
        selecionar(root, None)
    run = root / 'execucoes' / caso / 'R001'
    quadro = json.loads((run / f'entradas/casos/{caso}/manifesto.json').read_text(encoding='utf-8'))
    por_arquivo = {doc['arquivo'].split('/')[-1]: (indice, doc) for indice, doc in enumerate(quadro['documentos'])}
    evidencias = []
    for eid, nome, trecho, atribuicao, contexto, limitacoes in EVIDENCIAS:
        indice, doc = next((i, d) for chave, (i, d) in por_arquivo.items() if chave.endswith(nome) or nome in chave)
        linha, texto = numero_da_linha(arquivos, nome, trecho)
        original = 'entradas/' + doc['arquivo']
        evidencias.append({'id': eid, 'documento_id': doc.get('documento_id') or doc.get('id') or f'D{indice + 1:03}', 'modo': 'direta', 'original': original,
                           'original_sha256': doc['sha256'], 'fonte_textual': original, 'fonte_sha256': doc['sha256'], 'indice': None,
                           'localizador': {'tipo': 'linhas', 'pagina_pdf': None, 'linha_inicio': linha, 'linha_fim': linha, 'descricao': ''},
                           'trecho': texto, 'atribuicao': atribuicao, 'contexto': contexto, 'limitacoes': limitacoes})
    achados = [{'id': aid, 'subquestao': pergunta, 'versoes': [{'versao': 1, 'redacao': pergunta.rstrip('?') + ': ver as fontes ligadas.', 'natureza': natureza, 'limitacoes': limitacoes}]}
               for aid, pergunta, natureza, limitacoes, _ in ACHADOS]
    vinculos = [{'achado_id': aid, 'versao': 1, 'evidencia_id': eid, 'papel': papel, 'justificativa': 'Relação atribuída na simulação sintética.'}
                for aid, _, _, _, ligacoes in ACHADOS for eid, papel in ligacoes]
    ambiente = Ambiente.__new__(Ambiente)  # só os métodos de apoio: nada do __init__, que reescreveria prompts/ e configuracao.json da pasta
    ambiente.temp, ambiente.root = None, root
    dados = {'esquema': 1, 'caso_id': caso, 'rodada': 'R001', 'snapshot_sha256': sha256(run / 'snapshot.json'), 'revisao': 'r1', 'anterior': None,
             'achados': achados, 'evidencias': evidencias, 'vinculos': vinculos, 'revisoes_assistidas': [], 'destinos': [], 'conferencias_humanas': [],
             'verificacao_externa': {'estado': 'nao_realizada', 'relato': None, 'limitacao': 'Corpus fechado; sem verificação externa.'},
             'procedencia': [{'etapa': 'busca', 'artefatos': [], 'ferramentas': ['simulação sintética'], 'modelo_informado_ou_observado': None}], 'artefatos': []}
    ambiente.relatorio(dados, 'saidas/04_evidencias_brutas.md', 'evidencias', ' '.join(e['id'] for e in evidencias) + ' · fontes sintéticas.', 0)
    ambiente.relatorio(dados, 'saidas/05_cruzamentos_brutos.md', 'cruzamentos', ' '.join(a['id'] + '@v1' for a in achados) + ' · redações sintéticas.', 0)
    primeiro = publicar(root, caso, 'R001', dados)
    revisado = ambiente.sucessora(dados, primeiro, 'r2')
    revisado['achados'][0]['versoes'].append({'versao': 2, 'redacao': 'O contrato nº 062/2023 declara valor global de R$ 1.840.000,00.', 'natureza': 'declaracao_documental',
                                              'limitacoes': 'Declaração documental, sem verificação de pagamento.'})
    revisado['vinculos'].extend({**v, 'versao': 2} for v in revisado['vinculos'] if v['achado_id'] == 'A001' and v['versao'] == 1)
    revisado['revisoes_assistidas'] = [{'achado_id': 'A001', 'versao': 1, 'suporte': 'parcial', 'motivo': 'Delimitar a atribuição ao contrato.', 'fontes_reabertas': ['E001', 'E014'],
                                         'limitacoes': 'Revisão sintética.', 'acao': 'corrigir'},
                                        {'achado_id': 'A001', 'versao': 2, 'suporte': 'sustentado', 'motivo': 'Atribuição delimitada.', 'fontes_reabertas': ['E001', 'E014'],
                                         'limitacoes': 'Revisão sintética.', 'acao': 'manter'}]
    revisado['procedencia'].append({'etapa': 'revisao', 'artefatos': [], 'ferramentas': ['simulação sintética'], 'modelo_informado_ou_observado': None})
    ambiente.relatorio(revisado, 'saidas/06_revisao_assistida.md', 'revisao', 'A001@v1 parcial; A001@v2 sustentado; demais não revisados.', -1)
    ambiente.relatorio(revisado, 'saidas/07_achados_revisados.md', 'achados_revisados', 'A001@v2 e os demais em v1 · síntese sintética.', -1)
    ambiente.briefing(revisado)
    segundo = publicar(root, caso, 'R001', revisado)
    construir(root, caso, 'R001', 'r1', 'g1')
    construir(root, caso, 'R001', 'r2', 'g2')

    def ia(eid):
        return {'tipo': 'ia', 'caso_id': caso, 'rodada': 'R001', 'revisao': 'r2', 'registros_sha256': segundo['manifesto']['registros_sha256'], 'evidencia_id': eid}
    return ia, [e['id'] for e in evidencias]


# --- os Quadros, as perguntas, os pedidos e as notas ---------------------------------------------------------------------------------------------------------------------

def _base(caso, autor, **campos):
    return {'caso': caso, 'requisicao_id': uuid.uuid4().hex, 'autor': autor, **campos}


def _vinculo(ref, papel='suporte', suporte='nao_revisado', natureza=None, justificativa='Vínculo atribuído na simulação sintética.'):
    natureza = natureza or ('declaracao_documental' if suporte == 'sustentado' else 'pendencia')
    return {'referencia': ref, 'papel': papel, 'suporte': suporte, 'natureza': natureza, 'justificativa': justificativa}


ARQUIVOS_DO_CASO: list[Path] = []


def notas_humanas(root, caso, conta):
    """Três trechos do caderno (registros humanos), que servem de evidência 'humana' nos quadros."""
    import caderno
    docs = caderno.documentos(root, caso)
    escolhas = (('oficio_118_2025_secretaria_educacao.txt', 'todas as entregas foram realizadas', 'Versão da Secretaria', 'A Secretaria não anexou atestos.'),
                ('relatorio_fiscalizacao_merenda_2024.txt', 'consta como sócio das duas empresas', 'Sócio comum', 'Conferir na Junta Comercial.'),
                ('parecer_juridico_033_2024.txt', 'equivale exatamente a 25%', 'Aditivo no limite', 'Está exatamente no teto: perguntar o valor inicial atualizado.'))
    humanas = []
    for nome, trecho, titulo, anotacao in escolhas:
        doc = next(d for d in docs['documentos'] if nome in json.dumps(d, ensure_ascii=False))
        numero, linha = numero_da_linha(ARQUIVOS_DO_CASO[0], nome, trecho)
        nota = caderno.salvar(root, {'caso': caso, 'origem_id': docs['origem_id'], 'documento_id': doc['documento_id'], 'documento_sha256': doc['sha256'], 'pagina_pdf': None,
                                     'localizador': f'Linha {numero}', 'trecho': linha, 'titulo': titulo, 'anotacao': anotacao, 'autor': conta['nome'], 'tipo': 'trecho',
                                     'transcricao_manual': False, 'requisicao_id': uuid.uuid4().hex}, conta)
        humanas.append({'tipo': 'humana', 'caso_id': caso, 'registro_id': nota['registro']['id'], 'sha256': nota['sha256'], 'fonte': 0})
    return humanas


def quadros(root, caso, conta, ia, humanas):
    import hipoteses
    import linha_tempo
    import mapa_relacoes as mapa
    autor = conta['nome']
    # Hipóteses: sustenta, contraria e falta (as lacunas de cada uma viram as seis perguntas)
    for enunciado, vinculos, lacunas in (
            ('O contrato nº 062/2023 foi cumprido integralmente.',
             [_vinculo(ia('E012'), 'suporte', 'parcial', 'alegacao_atribuida'), _vinculo(ia('E006'), 'contradicao', 'sustentado'), _vinculo(ia('E007'), 'contradicao', 'sustentado'),
              _vinculo(ia('E005'), 'contexto')],
             ['Comprovantes de entrega de novembro de 2023 a janeiro de 2024.', 'Atestos de entrega assinados pelo fiscal.']),
            ('O aditivo respeitou o limite legal de 25%.',
             [_vinculo(ia('E003'), 'suporte', 'sustentado', 'declaracao_documental'), _vinculo(ia('E004'), 'suporte', 'parcial', 'inferencia'), _vinculo(humanas[2], 'contexto')],
             ['Valor inicial atualizado do contrato, com reajustes, para conferir a base dos 25%.']),
            ('Houve pagamento sem entrega comprovada.',
             [_vinculo(ia('E008'), 'suporte', 'sustentado', 'alegacao_atribuida'), _vinculo(ia('E007'), 'suporte', 'sustentado'), _vinculo(ia('E012'), 'contradicao', 'parcial', 'alegacao_atribuida'),
              _vinculo(humanas[0], 'contradicao', 'sustentado', 'alegacao_atribuida')],
             ['Comprovantes bancários dos pagamentos.', 'Atesto da parcela do aditivo paga em novembro de 2024.']),
            ('A contratada e a empresa subcontratada têm o mesmo sócio.',
             [_vinculo(ia('E009'), 'suporte', 'parcial', 'alegacao_atribuida'), _vinculo(humanas[1], 'suporte', 'sustentado', 'alegacao_atribuida')],
             ['Contrato social das duas empresas na Junta Comercial.'])):
        hipoteses.salvar(root, _base(caso, autor, enunciado=enunciado, evidencias=vinculos, lacunas=[{'descricao': d} for d in lacunas]), 'criar', conta)
    # Linha do tempo: 15 acontecimentos em três anos, com os dez tipos de data, exatas e parciais
    marcos = (
        ('Publicação do edital do pregão 017/2023', [('publicacao', '2023-03-14')], ['E011']),
        ('Sessão do pregão, com duas propostas', [('fato', '2023-04-05')], ['E010', 'E014']),
        ('Ata do pregão assinada pelo pregoeiro', [('emissao_documento', '2023-04-06')], ['E010']),
        ('Assinatura do contrato nº 062/2023', [('assinatura', '2023-05-02')], ['E001']),
        ('Início da vigência do contrato', [('vigencia_inicio', '2023-05-15')], ['E001']),
        ('Primeiras entregas incompletas registradas', [('fato', '2023-11')], ['E006']),
        ('Fim da vigência original', [('vigencia_fim', '2024-05-14')], ['E001']),
        ('Relatório de fiscalização do contrato', [('emissao_documento', '2024-03')], ['E006', 'E007']),
        ('Parcela de fevereiro empenhada e paga', [('registro', '2024-03-12'), ('pagamento', '2024-03-20')], ['E013']),
        ('Parecer jurídico sobre o aditivo', [('emissao_documento', '2024-08-21')], ['E004', 'E005']),
        ('Assinatura do termo aditivo nº 01', [('assinatura', '2024-09-18')], ['E002', 'E003']),
        ('Pagamento da parcela do aditivo', [('pagamento', '2024-11-08')], ['E008']),
        ('Recebimento do pedido da Controladoria', [('recebimento', '2025-02-10')], ['E012']),
        ('Resposta da Secretaria: entregas realizadas', [('declarada_por_fonte', '2025')], ['E012']),
        ('Relatório da Controladoria sobre o contrato', [('registro', '2025-06'), ('declarada_por_fonte', '2025-06-30')], ['E009']))
    for descricao, datas, eids in marcos:
        linha_tempo.salvar(root, _base(caso, autor, descricao=descricao, evidencias=[_vinculo(ia(e), 'suporte', 'sustentado') for e in eids],
                                       datas=[{'tipo': tipo, 'valor': valor, 'fonte': 0} for tipo, valor in datas]), 'criar', conta)
    # Mapa de relações: 12 entidades (pessoas e organizações são os dois tipos que o mapa tem) e 14 ligações de vários tipos
    entidades = {}
    for chave, tipo, nome, eid in (
            ('marta', 'pessoa', 'Marta Cavalcante Dias', 'E001'), ('ricardo', 'pessoa', 'Ricardo Paes Nogueira', None), ('helena', 'pessoa', 'Helena Brandão', 'E006'),
            ('otavio', 'pessoa', 'Otávio Mendes Lacerda', 'E009'), ('joana', 'pessoa', 'Joana Prates', None), ('eduardo', 'pessoa', 'Eduardo Salles', 'E004'),
            ('prefeitura', 'organizacao', 'Prefeitura Municipal de Vale do Sol', 'E011'), ('secretaria', 'organizacao', 'Secretaria Municipal de Educação', 'E012'),
            ('nutri', 'organizacao', 'Nutri Vale Alimentos Ltda.', 'E001'), ('horizonte', 'organizacao', 'Comercial Horizonte Merenda ME', 'E010'),
            ('controladoria', 'organizacao', 'Controladoria-Geral do Município', None), ('tce', 'organizacao', 'Tribunal de Contas do Estado', None)):
        entidades[chave] = mapa.salvar_entidade(root, _base(caso, autor, tipo=tipo, nome=nome, evidencias=[_vinculo(ia(eid))] if eid else []), 'criar', conta)['id']
    for origem, destino, tipo, eid in (
            ('marta', 'secretaria', 'secretária de', 'E012'), ('secretaria', 'prefeitura', 'integra', 'E011'), ('ricardo', 'prefeitura', 'prefeito de', 'E011'),
            ('nutri', 'secretaria', 'contratada pela', 'E001'), ('otavio', 'nutri', 'sócio de', 'E009'), ('otavio', 'horizonte', 'sócio de', 'E009'),
            ('helena', 'nutri', 'fiscal do contrato com', 'E006'), ('marta', 'nutri', 'assinou contrato com', 'E001'), ('horizonte', 'nutri', 'subcontratada por', 'E009'),
            ('prefeitura', 'nutri', 'pagou', 'E008'), ('eduardo', 'secretaria', 'emitiu parecer para', 'E004'), ('joana', 'controladoria', 'dirige', 'E012'),
            ('controladoria', 'nutri', 'auditou o contrato de', 'E012'), ('controladoria', 'tce', 'recomendou encaminhar ao', 'E012')):
        mapa.salvar_relacao(root, _base(caso, autor, origem=entidades[origem], destino=entidades[destino], tipo=tipo, evidencias=[_vinculo(ia(eid))] if eid else []), 'criar', conta)


def perguntas_e_pedidos(root, caso, conta):
    """As 6 perguntas (uma por lacuna das hipóteses, com a diligência de contato que nasce de cada uma) e 4 pedidos e prazos à parte, em estados diferentes."""
    import diligencias
    import entrevistas
    autor, hoje = conta['nome'], datetime.date.today()

    def em(dias):
        return (hoje + datetime.timedelta(days=dias)).isoformat()
    tipos = ('pedido_informacao', 'entrevista', 'pedido_lai', 'pedido_informacao', 'entrevista', 'pedido_lai')
    destinos = ('Secretaria Municipal de Educação', 'Helena Brandão, fiscal do contrato', 'Controladoria-Geral do Município', 'Procuradoria Municipal',
                'Otávio Mendes Lacerda, sócio da contratada', 'Junta Comercial do Estado')
    prazos = (em(-12), em(9), em(21), em(-3), em(5), em(30))
    lacunas = entrevistas.lacunas(root, caso)['lacunas']
    criadas = []
    for linha, tipo, destino, prazo in zip(lacunas, tipos, destinos, prazos):
        criadas.append(entrevistas.preparar(root, _base(caso, autor, origem=linha['origem'], tipo=tipo, destinatario=destino, responsavel='Rep Beta', prazo=prazo), conta))
    pedidos = (('Pedir à Secretaria a cópia dos atestos de entrega de 2023 e 2024', 'Dono Beta', em(-20), 'concluida'),
               ('Solicitar à Controladoria o relatório completo e os papéis de trabalho', 'Dono Beta', em(14), 'aguardando_resposta'),
               ('Entrevistar a fiscal do contrato sobre as entregas dos três meses sem registro', 'Rep Beta', em(6), 'em_andamento'),
               ('Pedir ao Tribunal de Contas o andamento de eventual representação', 'Rep Beta', em(45), 'a_solicitar'))
    for acao, responsavel, prazo, estado in pedidos:
        criada = diligencias.salvar(root, _base(caso, autor, observacao='', origem=None, acao=acao, responsavel=responsavel, prazo=prazo), 'criar', conta)
        if estado != 'a_solicitar':
            diligencias.salvar(root, _base(caso, autor, diligencia_id=criada['id'], anterior_sha256=criada['sha256'], observacao='Atualização sintética.', acao=acao,
                                           responsavel=responsavel, prazo=prazo, estado=estado), 'atualizar', conta)
    return len(criadas), len(pedidos)


def notas_da_apuracao(root, caso, conta):
    import apuracao
    textos = (('Pauta: merenda de Vale do Sol', '## Pauta\n\nContratos de merenda escolar do município fictício de Vale do Sol, de 2023 a 2025.\n\n### O que conferir\n\n'
                                                '- [ ] Atestos de entrega de novembro de 2023 a janeiro de 2024\n- [ ] Base de cálculo dos 25% do aditivo\n- [ ] Contrato social das duas empresas\n'),
              ('Linha de raciocínio', '## Raciocínio\n\n1. O pregão teve duas propostas, e o edital pedia três.\n2. Três parcelas foram pagas sem registro de entrega.\n'
                                      '3. O aditivo ficou no teto de 25%.\n\nNada disto é conclusão: são pontos para documentar.'),
              ('Quem ouvir', '## Fontes a procurar\n\n- Helena Brandão (fiscal)\n- Joana Prates (Controladoria)\n- Otávio Mendes Lacerda (sócio das duas empresas, resposta por escrito)\n'))
    for titulo, texto in textos:
        apuracao.executar(root, 'apuracao-nota-salvar', {'caso': caso, 'requisicao_id': uuid.uuid4().hex, 'titulo': titulo, 'texto': texto}, conta)
    return len(textos)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pasta', type=Path, required=True, help='a pasta da prévia (a que tem piloto/ dentro)')
    args = parser.parse_args()
    for saida in (sys.stdout, sys.stderr):
        if hasattr(saida, 'reconfigure'):
            saida.reconfigure(encoding='utf-8')
    pasta = args.pasta.resolve()
    root = pasta / 'piloto'
    if not (root / 'acesso').is_dir() or not (root / 'casos' / 'catalogo.json').is_file():
        raise SystemExit(f'{pasta} não parece uma prévia (falta piloto/acesso ou piloto/casos).')
    import os
    os.environ.update({'VLADO_ACESSO': '', 'VLADO_SEGREDOS': ''})
    import acesso
    contas = {c['login']: c for c in acesso.listar(root)}
    if LOGIN_DONO not in contas or LOGIN_REPORTER not in contas:
        raise SystemExit('A prévia não tem o Dono Beta e o Rep Beta.')
    dono, reporter = contas[LOGIN_DONO], contas[LOGIN_REPORTER]
    redacao = acesso.ver_conta(root, dono['id'])['organizacao']['id']
    import comum
    if any(c['id'] == CASO for c in comum.ler_json(root / 'casos' / 'catalogo.json')['casos']):
        raise SystemExit(f'A apuração {CASO} já existe nesta prévia: nada foi feito.')

    from cadastrar_documentos import cadastrar
    with tempfile.TemporaryDirectory(prefix='vlado_media_') as temporaria:
        arquivos = escrever_documentos(Path(temporaria))
        cadastrar(root, CASO, arquivos, titulo=TITULO, natureza='sinteticos', novo=True)
        ARQUIVOS_DO_CASO.append(Path(temporaria))
        ia, ids = publicar_achados(root, CASO, Path(temporaria))
        # a apuração é da redação Beta: o dono é o responsável e o repórter participa
        acesso.atribuir_caso(root, CASO, redacao)
        acesso.definir_responsavel(root, CASO, dono['id'], 'operador', redacao)
        acesso.incluir_participante(root, CASO, reporter['id'], 'operador', redacao)
        conta = {'id': dono['id'], 'nome': dono['nome']}
        humanas = notas_humanas(root, CASO, conta)
        quadros(root, CASO, conta, ia, humanas)
        perguntas, pedidos = perguntas_e_pedidos(root, CASO, conta)
        notas = notas_da_apuracao(root, CASO, conta)
    print(f'Apuração {CASO!r} ({TITULO}) na redação Beta: {len(arquivos)} documentos, {len(ids)} evidências, 8 achados, 4 hipóteses, 15 acontecimentos, 12 entidades e 14 ligações, '
          f'{perguntas} perguntas, {pedidos} pedidos e prazos à parte, {notas} notas e {len(humanas)} trechos do caderno.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
