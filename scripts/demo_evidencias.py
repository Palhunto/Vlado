"""Demonstração do núcleo de evidências sobre dados sintéticos.

Monta numa pasta temporária um caso sintético com rodada e achados publicados, cria duas
hipóteses, três eventos, uma comparação entre dois documentos e um mapa com duas entidades
homônimas, e imprime cada quadro com o localizador de cada evidência. Ao final, apaga a pasta.

Não recebe argumentos, não usa rede, não chama modelo e não toca casos reais do projeto.

  python scripts/demo_evidencias.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import uuid

RAIZ = Path(__file__).resolve().parents[1]
for pasta in (RAIZ / 'scripts', RAIZ / 'testes'):
    if str(pasta) not in sys.path:
        sys.path.insert(0, str(pasta))

import caderno  # noqa: E402
import comparador  # noqa: E402
from criar_caso import criar_caso  # noqa: E402
import dados_sinteticos  # noqa: E402
from fixture_achados import Ambiente  # noqa: E402
import hipoteses  # noqa: E402
import linha_tempo  # noqa: E402
import mapa_relacoes as mapa  # noqa: E402
from nova_rodada import criar_rodada  # noqa: E402
from selecionar_caso import selecionar  # noqa: E402

CASO = 'alpha'
CASO_COMPARACAO = 'gamma'


def _base(**campos):
    return {'caso': CASO, 'requisicao_id': uuid.uuid4().hex, 'autor': 'Demonstração sintética', **campos}


def _vinculo(ref, papel='suporte', suporte='nao_revisado', natureza=None):
    natureza = natureza or ('declaracao_documental' if suporte == 'sustentado' else 'pendencia')
    return {'referencia': ref, 'papel': papel, 'suporte': suporte, 'natureza': natureza,
            'justificativa': 'Vínculo sintético da demonstração.'}


def _evidencia(link):
    """Uma linha legível: estado, papel, suporte, localizador e trecho."""
    if link['estado'] != 'conferida':
        return f"[{link['papel']}] indisponível: {link.get('erro')}"
    e = link['evidencia']
    trecho = e['trecho'] or '(leitura visual no original)'
    return (f"[{link['papel']} · {link['suporte']} · {link['natureza']}] {e['localizador']['legivel']}"
            f" — \"{trecho}\"")


def _titulo(texto):
    print(f"\n{'=' * 72}\n{texto}\n{'=' * 72}")


def preparar(env):
    """Rodada R001 com achados publicados (r1, r2) e uma nota humana no caderno."""
    _, _, _, second = env.completo()
    ia = lambda eid: {'tipo': 'ia', 'caso_id': CASO, 'rodada': 'R001', 'revisao': 'r2',
                      'registros_sha256': second['manifesto']['registros_sha256'], 'evidencia_id': eid}
    docs = caderno.documentos(env.root, CASO)
    doc = docs['documentos'][0]
    nota = caderno.salvar(env.root, {
        'caso': CASO, 'origem_id': docs['origem_id'], 'documento_id': doc['documento_id'],
        'documento_sha256': doc['sha256'], 'pagina_pdf': None, 'localizador': 'Linha 2',
        'trecho': 'Outra versão declara valor 14.', 'titulo': 'Trecho humano', 'anotacao': '',
        'autor': 'Repórter sintético', 'tipo': 'trecho', 'transcricao_manual': False,
        'requisicao_id': uuid.uuid4().hex})
    humana = {'tipo': 'humana', 'caso_id': CASO, 'registro_id': nota['registro']['id'],
              'sha256': nota['sha256'], 'fonte': 0}
    return ia, humana


def demo_hipoteses(root, ia, humana):
    hipoteses.salvar(root, _base(
        enunciado='O valor declarado na fonte é 12.',
        evidencias=[_vinculo(ia('E001'), suporte='sustentado', natureza='alegacao_atribuida'),
                    _vinculo(humana, 'contradicao', 'sustentado'),
                    _vinculo(ia('E003'), 'contexto')],
        lacunas=[{'descricao': 'Comprovante de pagamento do valor declarado.'}]))
    hipoteses.salvar(root, _base(enunciado='O valor foi efetivamente pago.'))
    quadro = hipoteses.quadro(root, CASO)
    _titulo(f"QUADRO DE HIPÓTESES ({quadro['total']})")
    for h in quadro['hipoteses']:
        print(f"\n• {h['enunciado']}\n  situação: {h['situacao']} · condição: {h['condicao']} · natureza: {h['natureza']}")
        for rotulo, chave in (('sustentam', 'sustentam'), ('contrariam', 'contrariam'), ('contexto', 'contexto')):
            for link in h[chave]:
                print(f"  {rotulo}: {_evidencia(link)}")
        for falta in h['faltam']:
            print(f"  falta ({falta['origem']}): {falta['descricao']}")
    print(f"\n  aviso: {quadro['aviso']}")
    return quadro


def demo_linha(root, ia, humana):
    links = [_vinculo(ia('E001'), suporte='sustentado'), _vinculo(humana, 'contexto')]
    linha_tempo.salvar(root, _base(descricao='Emissão do documento sintético', evidencias=links,
                                   datas=[{'tipo': 'emissao_documento', 'valor': '2021-03', 'fonte': 0}]))
    linha_tempo.salvar(root, _base(descricao='Declaração do valor 12', evidencias=links,
                                   datas=[{'tipo': 'fato', 'valor': '2021-03-12', 'fonte': 0},
                                          {'tipo': 'declarada_por_fonte', 'valor': '2021', 'fonte': 1}]))
    linha_tempo.salvar(root, _base(descricao='Registro da versão com valor 14', evidencias=links[:1],
                                   datas=[{'tipo': 'registro', 'valor': '2021-04-02', 'fonte': 0}]))
    resultado = linha_tempo.linha(root, CASO)
    _titulo(f"LINHA DO TEMPO ({resultado['total']} entradas)")
    for e in resultado['entradas']:
        d = e['data']
        aprox = ' (aproximada)' if d.get('aproximada') else ''
        print(f"\n• {d['valor']} [{d['precisao']}]{aprox} — {d['rotulo']}\n  {e['descricao']}")
        print(f"  fonte da data: {_evidencia(e['fonte_da_data'])}")
    for div in resultado['divergencias']:
        print(f"\n  divergência ({div['tipo']}): {', '.join(div['valores'])} — {div['classe']}")
    print(f"\n  aviso: {resultado['aviso']}")
    return resultado


def demo_comparacao(root, tmp):
    tmp.mkdir(parents=True, exist_ok=True)
    v1, v2 = tmp /'contrato_v1_sintetico.txt', tmp / 'contrato_v2_sintetico.txt'
    original = [dados_sinteticos.AVISO, *dados_sinteticos.CONTRATO]
    alterado = [linha.replace('R$ 8.750.000,00', 'R$ 10.937.500,00').replace('3 de marco de 2025', '18 de setembro de 2025')
                for linha in original]
    v1.write_text('\n'.join(original) + '\n', encoding='utf-8')
    v2.write_text('\n'.join(alterado) + '\n', encoding='utf-8')
    criar_caso(root, CASO_COMPARACAO, 'Comparação sintética', [v1, v2], 'sinteticos')
    selecionar(root, CASO_COMPARACAO)
    try:
        criar_rodada(root, 'R001', 'Demonstração técnica sintética, sem pergunta editorial.', indice=False)
    finally:
        selecionar(root, None)
    resultado = comparador.comparar_documentos(root, CASO_COMPARACAO, 'R001', 'D001', 'D002', contexto=1)
    _titulo(f"COMPARAÇÃO D001 × D002 ({resultado['total_alteracoes']} alterações, semelhança {resultado['semelhanca']})")
    for c in resultado['alteracoes']:
        la, lb = c['localizador_a'], c['localizador_b']
        loc = lambda doc, l: (f'{doc} (ausente)' if not l else f"{doc} linha {l['linha_inicio']}"
                              if l['linha_inicio'] == l['linha_fim'] else f"{doc} linhas {l['linha_inicio']}–{l['linha_fim']}")
        print(f"\n• {c['operacao']} · {c['classe']} · {loc('D001', la)} → {loc('D002', lb)}")
        print(f"  A: {c['a']}\n  B: {c['b']}")
        calc = c['calculo']
        if calc:
            if calc.get('diferenca') is not None:
                print(f"  diferença B − A: {calc['diferenca']}")
            else:
                print(f"  diferença não calculada: {calc.get('motivo')}")
    print(f"\n  aviso: {resultado['aviso']}")
    return resultado


def demo_mapa(root, ia, humana):
    a = mapa.salvar_entidade(root, _base(tipo='pessoa', nome='Lúcia Prates', evidencias=[_vinculo(ia('E001'))],
                                         identificadores=[{'tipo': 'matricula', 'valor': '7781', 'fonte': 0}]))
    b = mapa.salvar_entidade(root, _base(tipo='pessoa', nome='Lucia  PRATES', evidencias=[_vinculo(humana)],
                                         identificadores=[{'tipo': 'matricula', 'valor': '9902', 'fonte': 0}]))
    org = mapa.salvar_entidade(root, _base(tipo='organizacao', nome='Construtora Horizonte Azul Ltda.'))
    mapa.salvar_relacao(root, _base(origem=a['id'], destino=org['id'], tipo='fiscal de contrato com',
                                    evidencias=[_vinculo(ia('E001'), suporte='sustentado')]))
    resultado = mapa.mapa(root, CASO)
    nomes = {e['id']: e['nome'] for e in resultado['entidades']}
    _titulo(f"MAPA DE RELAÇÕES ({len(resultado['entidades'])} entidades, {len(resultado['relacoes'])} relações)")
    for e in resultado['entidades']:
        ids = ', '.join(f"{i['tipo']} {i['valor_exibicao']}" for i in e['identificadores']) or 'sem identificador'
        print(f"\n• {e['nome']} ({e['tipo']}) · {ids} · {e['situacao']}")
        for link in e['evidencias']:
            print(f"  evidência: {_evidencia(link)}")
    for r in resultado['relacoes']:
        print(f"\n• {nomes[r['origem']]} —[{r['tipo']}]→ {nomes[r['destino']]} · {r['situacao']}")
        for link in r['evidencias']:
            print(f"  evidência: {_evidencia(link)}")
    for h in resultado['homonimos']:
        print(f"\n• possível homônimo: {' / '.join(h['nomes'])} · motivo {h['motivo']} · situação {h['situacao']}")
        if h['identificadores_divergentes']:
            print(f"  identificadores divergentes: {', '.join(h['identificadores_divergentes'])}")
        print(f"  {h['aviso']}")
    print(f"\n  aviso: {resultado['aviso']}")
    return resultado


def main() -> int:
    if len(sys.argv) > 1:
        print(__doc__)
        return 2
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    env = Ambiente()
    try:
        print(f"Demonstração do núcleo de evidências — dados sintéticos, sem rede e sem modelo.\nAviso: {dados_sinteticos.AVISO}")
        ia, humana = preparar(env)
        demo_hipoteses(env.root, ia, humana)
        demo_linha(env.root, ia, humana)
        demo_comparacao(env.root, env.root / 'origem_comparacao')
        demo_mapa(env.root, ia, humana)
        print('\nDemonstração concluída; a pasta temporária será apagada.')
    finally:
        env.cleanup()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
