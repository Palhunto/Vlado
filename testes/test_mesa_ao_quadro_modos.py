"""O caminho inteiro da Mesa ao quadro (test_mesa_ao_quadro, da Sonda) nos dois modos de instrução da T3.

- Modo mesa: a raiz liga o prompts/MESA.md (manifesto 1.5.0 com a chave `mesa`), o modelo recebe o bloco
  `mesa:sistema` e os turnos `mesa:controle` + `mesa:formato:<etapa>`. A síntese usa o destino novo da P48:
  o achado sustentado vai para "Outros achados sustentados" (`fora_do_briefing`), e os quatro quadros e o
  original o tratam como sustentado, igual ao incluído, nunca como retirado.
- Modo legado: a mesma Mesa de test_mesa_ao_quadro.MesaInteiraTest (prompts sintéticos sem MESA.md, como uma
  instalação de antes da 1.5.0), agora com a prova de que o modelo recebeu o sistema antigo.

Servidor real, provedor simulado, sem rede. Na suíte lenta, como o teste de origem.
"""
import json
import threading
import unittest

import test_mesa_ao_quadro as mq  # módulo, para não recoletar os TestCases dele
from agente_fluxo_fixture import aguardar_fim, esperar
from codex_apuracao import ACTIVE, Conversas
from interface_pesquisa import Servidor
from modelo_pasta import copiar
from modo_mesa_fixture import ligar_mesa
import test_codex_integracao as integracao


def montar_mesa(root):
    mq.montar(root)
    ligar_mesa(root)


def instrucao_de_sistema(gerenciador):
    return next(p for m, p in gerenciador.rpc.calls if m == 'thread/start')['developerInstructions']


def turnos(gerenciador):
    return [p['input'][0]['text'] for m, p in gerenciador.rpc.calls if m == 'turn/start']


class MesaNoModoMesaTest(mq.Mesa, mq.QuadrosPelaMesa, unittest.TestCase):
    revisao, geracao = 'r3_sintese', 'g1'

    @classmethod
    def setUpClass(cls):
        # The same as mq.Mesa.setUpClass, on its own model folder (copiar caches by key).
        cls.temp, cls.root, _ = copiar('MesaAoQuadroModoMesaTest', montar_mesa)
        cls.gerenciador = Conversas(cls.root, integracao.FakeServer)
        cls.servidor = Servidor(('127.0.0.1', 0), cls.root)
        cls.servidor.conversas = cls.gerenciador
        cls.thread = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        cls.thread.start()
        cls.mesa = cls.percorrer_a_mesa(mq.CASO)
        cls.rodada = cls.mesa['eventos']['conversa']['rodadas'][-1]

    @classmethod
    def percorrer_a_mesa(cls, caso):
        """As cinco primeiras etapas pelo agente sintético da Sonda; a síntese, aqui, com a lista da P48."""
        enviada = cls.ok('codex-perguntar', {'caso': caso, 'pergunta': mq.PERGUNTA})
        identificador = enviada['conversa']
        etapas_vistas = []
        mq.agente(cls.gerenciador, identificador, etapas_vistas.append, ate='revisao')
        meta = lambda: cls.gerenciador.contexts[identificador]['meta']
        esperar(lambda: (meta().get('etapa') == 'sintese' and meta().get('turn_id')) or meta()['estado'] not in ACTIVE)
        tool = lambda args: cls.gerenciador.ferramenta(identificador, args)[0]
        referencia = tool({'acao': 'buscar', 'consulta': 'Valor global'})['resultados'][0]['referencia']
        briefing = ('## Resposta direta\n\nO contrato sintético responde à pergunta; o achado está na lista abaixo.\n\n'
                    '## Outros achados sustentados\n\n'
                    '- A001 v1: o contrato 041/2025 declara valor global de R$ 8.750.000,00, assinatura em 3 de '
                    f'março de 2025 e a Construtora Horizonte Azul como contratada. [fonte:{referencia}]\n')
        tool({'acao': 'guardar', 'etapa': 'sintese', 'texto': json.dumps({'texto': briefing, 'destinos': [
            {'achado_id': 'A001', 'destino': 'fora_do_briefing', 'motivo': 'Sustentado; fora do texto principal.'}]},
            ensure_ascii=False)})
        turno = meta()['turn_id']
        cls.gerenciador.rpc.emit('item/completed', {'item': {'id': 'msg-' + turno, 'type': 'agentMessage',
                                 'phase': 'final_answer', 'text': 'Etapa sintética entregue.'}})
        cls.gerenciador.rpc.emit('turn/completed', {'turn': {'id': turno, 'status': 'completed'}})
        etapas_vistas.append('sintese')
        final = aguardar_fim(cls.gerenciador, identificador)
        eventos = cls.ok('codex-eventos', {'conversa': identificador})
        return {'conversa': identificador, 'final': final, 'eventos': eventos, 'etapas': etapas_vistas}

    def test_o_modelo_recebeu_o_mesa_md(self):
        sistema = instrucao_de_sistema(self.gerenciador)
        self.assertTrue(sistema.startswith('# Mesa de apuração\n'))
        self.assertNotIn('ADAPTAÇÃO DE TRANSPORTE', sistema)
        vistos = turnos(self.gerenciador)
        self.assertEqual(len(vistos), len(mq.ETAPAS))
        self.assertTrue(all(t.startswith('CONTROLE AUTOMÁTICO. Pergunta atual: ' + mq.PERGUNTA) for t in vistos))
        escopo = next(e['dados'] for e in self.mesa['eventos']['eventos'] if e['tipo'] == 'escopo')
        self.assertEqual(escopo['instrucoes']['modo'], 'mesa')
        self.assertEqual(self.mesa['eventos']['conversa']['estado'], 'concluido')
        self.assertEqual(self.mesa['etapas'], list(mq.ETAPAS))

    def test_fora_do_briefing_aparece_como_sustentado_na_mesa(self):
        achado = self.detalhe('r3_sintese', 'g1')['achado']
        self.assertEqual((achado['suporte'], achado['destino']), ('sustentado', 'fora_do_briefing'))
        from comum import sha256
        digest = sha256(self.root / 'execucoes' / mq.CASO / self.rodada / achado['briefing'])
        texto = self.ok('achados-briefing', {'caso': mq.CASO, 'rodada': self.rodada, 'revisao': 'r3_sintese',
                                             'artefato_sha256': digest})['texto']
        self.assertIn('## Outros achados sustentados', texto)
        self.assertIn('- A001 v1:', texto)
        self.assertNotIn('[A001@v1]', texto)


class MesaNoModoLegadoTest(mq.MesaInteiraTest):
    """A Mesa de test_mesa_ao_quadro, inteira, com a prova do modo: rodada sem a chave `mesa`, sistema antigo."""

    def test_o_modelo_recebeu_o_sistema_antigo(self):
        sistema = instrucao_de_sistema(self.gerenciador)
        self.assertIn('ADAPTAÇÃO DE TRANSPORTE', sistema)
        self.assertNotIn('# Mesa de apuração\n', sistema)
        self.assertTrue(all('Etapa obrigatória atual:' in t for t in turnos(self.gerenciador)))
        escopo = next(e['dados'] for e in self.mesa['eventos']['eventos'] if e['tipo'] == 'escopo')
        self.assertEqual(escopo['instrucoes']['modo'], 'legado')


if __name__ == '__main__':
    unittest.main()
