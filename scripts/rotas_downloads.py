"""Respostas com arquivo: exportações do caderno e das tabelas e originais conferidos.

Separado de ``interface_pesquisa`` sem mudar comportamento. Nenhum caminho vem do cliente:
cada original é resolvido pelo módulo dono do registro (caderno, diligências, apuração) ou
pela passagem/evidência já validada por ``executar``. Os arquivos são lidos dentro da trava
de cadastro, para não cruzar com exclusão ou nova versão do corpus.
"""
from __future__ import annotations

from comum import dentro
import apuracao
import caderno
import diligencias
import exportar_apuracao
import rotas_tabelas
from indice_sqlite import caminho_rodada

ORIGINAIS = ('apuracao-original', 'diligencias-original', 'caderno-original')
OPERACOES = ('apuracao-exportar', rotas_tabelas.EXPORTAR, *ORIGINAIS)
# Answered by ``executar`` with a validated passage or evidence; the file goes out here.
ORIGINAIS_PASSAGEM = ('original', 'achados-original')


class RotasDownloads:
    """Mixin of the request handler: uses its ``_send``, ``_chave_originais`` and ``server``."""

    def _baixar(self, operation, data, principal):
        """Always answers with the file (exceptions go to the caller's error responses)."""
        if operation == 'apuracao-exportar':
            with self.server.cadastro_lock:
                state = apuracao.listar(self.server.root, data.get('caso'))
            content, mime = exportar_apuracao.exportar(state, data.get('formato'))
            self._send(200, content, mime, {'Content-Disposition': f'attachment; filename="caderno.{data["formato"]}"'})
        elif operation == rotas_tabelas.EXPORTAR:
            with self.server.cadastro_lock:
                name, content = rotas_tabelas.exportar(self.server.root, data, casos=principal['casos'])
            self._send(200, content, 'text/csv; charset=utf-8',
                       {'Content-Disposition': f'attachment; filename="{name}"'})
        elif operation in ORIGINAIS:
            with self.server.cadastro_lock:
                if operation == 'apuracao-original':
                    path = apuracao.original(self.server.root, data)
                elif operation == 'diligencias-original':
                    path = diligencias.original_resposta(self.server.root, data)
                else:
                    path = (caderno.original_registro(self.server.root, data) if data.get('registro_id')
                            else caderno.original_documento(self.server.root, data))
                self._send(200, path.read_bytes(), 'application/octet-stream',
                           {'Content-Disposition': f'attachment; filename="original{path.suffix}"'})
        else:
            raise ValueError('Operação de arquivo desconhecida.')

    def _enviar_original(self, operation, data, result, principal):
        # Resolve only the original returned by a validated passage, never a client path.
        run = caminho_rodada(self.server.root, data['caso'], data['rodada'])
        path = dentro(run, result['evidencia' if operation == 'achados-original' else 'passagem']['original'])
        content = path.read_bytes()
        if operation == 'achados-original':  # recorded before sending: the next save may race the download
            self.server.registrar_original(self._chave_originais(principal, data), data['evidencia_id'])
        self._send(200, content, 'application/octet-stream',
                   {'Content-Disposition': 'attachment; filename="original.bin"'})
