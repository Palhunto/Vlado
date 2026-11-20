"""Opt-in online test of automatic stages on an isolated synthetic corpus."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from comum import ROOT, PARTES, escrever_json, ler_json, sha256
from cadastrar_documentos import cadastrar
from codex_apuracao import Conversas, ACTIVE
from inferencia_api import seguro
from indice_achados import verificar


def pdfs_sinteticos(root):
    """Two Portuguese PDFs: native text with the fact on page 2, and an image-only scan (needs local OCR)."""
    import pymupdf
    ata = pymupdf.open()
    ata.new_page().insert_text((72, 100), 'MATERIAL SINTETICO - TESTE TECNICO. Ata do grupo ficticio Aurora.', fontsize=11)
    ata.new_page().insert_text((72, 100), 'Em 10 de janeiro de 2040, o grupo ficticio Aurora realizou uma reuniao.', fontsize=11)
    ata.save(root / 'ata.pdf')
    origem = pymupdf.open()
    pagina = origem.new_page()
    pagina.insert_text((72, 100), 'MATERIAL SINTETICO - TESTE TECNICO.', fontsize=14)
    pagina.insert_text((72, 130), 'Em 15 de janeiro de 2040, o grupo ficticio Aurora', fontsize=14)
    pagina.insert_text((72, 155), 'publicou um aviso sobre a reuniao.', fontsize=14)
    imagem = pagina.get_pixmap(dpi=200)
    aviso = pymupdf.open()
    aviso.new_page(width=pagina.rect.width, height=pagina.rect.height).insert_image(pagina.rect, pixmap=imagem)
    aviso.save(root / 'aviso_digitalizado.pdf')
    return [root / 'ata.pdf', root / 'aviso_digitalizado.pdf']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--saida-base', required=True)
    parser.add_argument('--complemento', action='store_true')
    parser.add_argument('--limite-tokens', type=int, default=None,
                        help='Teto de tokens (entrada+saída) desta consulta; a rodada para ao ultrapassar.')
    parser.add_argument('--pdf', action='store_true',
                        help='Corpus em PDF em português: um com texto nativo (fato na página 2) e um digitalizado (OCR local).')
    parser.add_argument('--ingles', action='store_true', help='Faz a pergunta em inglês sobre o corpus em português.')
    args = parser.parse_args()
    base = Path(args.saida_base).resolve()
    if not base.is_relative_to(ROOT.resolve()):
        raise ValueError('A fixture deve ficar dentro do projeto.')
    base.mkdir(parents=True, exist_ok=True)
    root = base / ('real_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_' + uuid.uuid4().hex[:8])
    root.mkdir()
    (root / 'prompts').mkdir()
    for name in (*PARTES, 'FLUXO_COMPLETO.md', 'manifesto_prompts.json'):
        shutil.copyfile(ROOT / 'prompts' / name, root / 'prompts' / name)
    for name in ('AGENTS.md', 'README.md'):
        shutil.copyfile(ROOT / name, root / name)
    origem = ler_json(ROOT / 'configuracao.json')
    escrever_json(root / 'configuracao.json', {'caso_ativo': None, 'manifesto_ativo': None,
        'maximo_documentos_inicial': 20, 'indice_sqlite': True, 'web_na_apuracao': False,
        **{k: origem.get(k) for k in ('provedor', 'modelo_preferido', 'max_tokens_saida', 'limites') if k in origem},
        **({'limites': {'tokens_por_consulta': args.limite_tokens, 'tokens_por_dia': args.limite_tokens * 2}}
           if args.limite_tokens else {})})
    # Use the provider chosen and the key pasted in the Mesa (the environment variable still wins).
    if (ROOT / 'ajustes/inferencia.json').is_file():
        (root / 'ajustes').mkdir()
        shutil.copyfile(ROOT / 'ajustes/inferencia.json', root / 'ajustes/inferencia.json')
    os.environ.setdefault('VLADO_SEGREDOS', str(ROOT / 'segredos' / 'chaves.json'))
    files = pdfs_sinteticos(root) if args.pdf else []
    for name, content in [] if args.pdf else [('ata.txt', 'MATERIAL SINTÉTICO — TESTE TÉCNICO.\nEm 10 de janeiro de 2040, o grupo fictício Aurora realizou uma reunião.\n'),
                          ('aviso.txt', 'MATERIAL SINTÉTICO — TESTE TÉCNICO.\nEm 15 de janeiro de 2040, o grupo fictício Aurora publicou um aviso sobre a reunião.\n')]:
        path = root / name
        path.write_text(content, encoding='utf-8')
        files.append(path)
    cadastrar(root, 'sintetico', files, novo=True, titulo='Integração automática — fixture sintética', natureza='sinteticos')
    manager = Conversas(root)
    report = {'natureza': 'teste online com corpus inteiramente sintético, sem aprovação humana',
              'fixture': str(root.relative_to(ROOT)), 'execucoes': []}
    print(json.dumps({'fixture': report['fixture']}, ensure_ascii=True), flush=True)
    cursor, identifier = 0, None
    try:
        if not manager.status()['autenticado']:
            raise ValueError('Login ChatGPT não disponível para o teste online.')
        questions = (['What events do the two synthetic documents describe? List up to two, in chronological order, '
                      'with the document, the PDF page and a supporting excerpt quoted in Portuguese. Answer in English.']
                     if args.ingles else
                     ['Quais são os acontecimentos nos dois documentos sintéticos? Liste até dois, em ordem cronológica, com documento, localização e trecho de apoio.'])
        if args.complemento:
            questions.append('Qual desses acontecimentos é o mais antigo? Reabra a fonte e cite o documento, a localização e o trecho.')
        for question in questions:
            result = manager.perguntar({'caso': 'sintetico', 'conversa': identifier, 'pergunta': question})
            identifier = result['conversa']
            deadline = time.monotonic() + 1200
            while time.monotonic() < deadline:
                update = manager.eventos(identifier, cursor, 10)
                cursor = update['cursor']
                for event in update['eventos']:
                    if event['tipo'] in ('etapa', 'estado', 'aviso', 'erro', 'publicacao'):
                        print(json.dumps({'tipo': event['tipo'], 'dados': event['dados']}, ensure_ascii=True), flush=True)
                if update['conversa']['estado'] not in ACTIVE and len(update['eventos']) < 100:
                    meta = update['conversa']
                    execution = ler_json(root / f'execucoes/sintetico/{meta["rodada"]}/saidas/codex_execucao.json')
                    item = {k: execution.get(k) for k in ('rodada', 'estado', 'modelo', 'thread_id', 'etapas_sem_registro', 'publicacao_achados')}
                    report['execucoes'].append(item)
                    if meta['estado'] != 'concluido':
                        raise ValueError('Fluxo não concluiu: ' + meta['estado'])
                    verified = verificar(root, 'sintetico', meta['rodada'], 'r3_sintese', 'g1')
                    item['achados_verificados'] = verified['achados']
                    break
            else:
                manager.cancelar(identifier)
                raise ValueError('Tempo total de teste excedido.')
        report['estado'] = 'ok'
        report['mesma_thread'] = len({r['thread_id'] for r in report['execucoes']}) == 1
    except Exception as exc:
        report.update(estado='erro', erro=seguro(exc))
        raise
    finally:
        manager.close()
        escrever_json(root / 'resultado.json', report)
        print(json.dumps({'resultado': str((root / 'resultado.json').relative_to(ROOT)), 'estado': report.get('estado')}, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
