"""Prepara dependências no notebook, sem autenticação nem chamadas de modelo."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import venv

from ambiente import diagnostico

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verificar', action='store_true', help='Só diagnosticar; não instalar nem criar ambiente.')
    parser.add_argument('--somente-texto', action='store_true', help='Não instalar a biblioteca visual opcional.')
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        raise ValueError('É necessário Python 3.12 ou superior. Consulte a seção Instalação do README.md.')
    if args.verificar:
        result = diagnostico()
        result['leitura_visual_pdf'] = importlib.util.find_spec('fitz') is not None
        if not any(result['inferencia_api']['chaves'].values()):
            result['orientacao_api'] = ('Defina ANTHROPIC_API_KEY ou OPENAI_API_KEY no ambiente do servidor '
                                        'antes de abrir a Mesa; a chave nunca vai para o projeto.')
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0 if result['pronto'] else 1
    target = ROOT / '.venv'
    if target.resolve().parent != ROOT.resolve():
        raise ValueError('O destino do ambiente está fora desta pasta. Nada foi instalado.')
    if target.exists() and not (target / 'pyvenv.cfg').is_file():
        raise ValueError('Já existe uma pasta .venv que não é um ambiente reconhecido. Preserve-a e revise o destino.')
    if not target.exists():
        print('Criando ambiente Python nesta pasta...', flush=True)
        venv.EnvBuilder(with_pip=True).create(target)
    python = target / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    if not python.is_file():
        raise ValueError('Ambiente .venv incompleto. Consulte a seção Instalação do README.md antes de tentar novamente.')
    listas = ['requirements.txt'] if args.somente_texto else ['requirements.txt', 'requirements-opcional.txt']
    comando = [str(python), '-m', 'pip', 'install', '--disable-pip-version-check']
    for lista in listas:
        comando += ['-r', str(ROOT / lista)]
    subprocess.run(comando, cwd=ROOT, check=True)
    subprocess.run([str(python), str(ROOT / 'scripts/ambiente.py')], cwd=ROOT, check=True)
    subprocess.run([str(python), str(ROOT / 'scripts/montar_fluxo.py'), '--check'], cwd=ROOT, check=True)
    subprocess.run([str(python), str(ROOT / 'scripts/verificar_projeto.py')], cwd=ROOT, check=True)
    print('Dependências preparadas. Defina a chave da API no ambiente e abra Abrir mesa.vbs.')
    print('Provedor e modelo ficam em configuracao.json; a chave fica só na variável de ambiente.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f'Preparação não concluída: {exc}', file=sys.stderr)
        raise SystemExit(1)
