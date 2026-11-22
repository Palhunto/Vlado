"""Respostas com arquivo: exportações do caderno e das tabelas e originais conferidos.

Separado de ``interface_pesquisa``. Nenhum caminho vem do cliente: cada original é resolvido
pelo módulo dono do registro (caderno, diligências, apuração) ou pela passagem/evidência já
validada por ``executar``. Trava de cadastro (``cadastro_lock`` da Mesa): os bytes saem do
disco dentro dela e o envio ao navegador corre sempre fora dela, para que um cliente lento não
pare cadastro, gestão, lixeira e tudo que passa por ``executar``.

- ``apuracao-original``, ``diligencias-original`` e ``caderno-original``: resolvem, validam e
  leem o original dentro da trava; enviam fora.
- ``original`` e ``achados-original``: ``executar`` valida a passagem ou a evidência dentro da
  trava e ``_ler_original`` lê o arquivo ainda dentro dela; ``_enviar_original`` envia fora.
- Exportações: o caderno só lê o estado dentro da trava e converte fora; a tabela monta o CSV
  dentro dela. O envio corre fora.

Ler dentro da trava garante que a exclusão definitiva (que corre na mesma trava) não apaga nem
troca o arquivo entre a validação e a leitura.
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
                content = path.read_bytes()
            self._send(200, content, 'application/octet-stream',
                       {'Content-Disposition': f'attachment; filename="original{path.suffix}"'})
        else:
            raise ValueError('Operação de arquivo desconhecida.')

    def _ler_original(self, operation, data, result):
        """Bytes of the original of a validated passage; the caller still holds the cadastro lock."""
        # Resolve only the original returned by a validated passage, never a client path.
        run = caminho_rodada(self.server.root, data['caso'], data['rodada'])
        return dentro(run, result['evidencia' if operation == 'achados-original' else 'passagem']['original']).read_bytes()

    def _enviar_original(self, operation, data, content, principal):
        """Send bytes read by ``_ler_original``, outside the cadastro lock."""
        if operation == 'achados-original':  # recorded before sending: the next save may race the download
            self.server.registrar_original(self._chave_originais(principal, data), data['evidencia_id'])
        self._send(200, content, 'application/octet-stream',
                   {'Content-Disposition': 'attachment; filename="original.bin"'})
