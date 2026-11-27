"""Editar entidade contra a rota de verdade (mapa-entidade-detalhe, mapa-entidade-atualizar; interface/formularios.js).

O teste do navegador usa um servidor simulado; aqui o detalhe vem de ``rotas_evidencia.executar`` e o corpo do
"Salvar" tem a forma que o formulário monta a partir dele: tipo, nome, variantes, identificadores com o valor sem
máscara e a fonte pelo índice, e as evidências em ``referencia``/``papel``/``suporte``/``natureza``/``justificativa``.
Dados sintéticos (identificadores fictícios); sem modelo nem rede.
"""
from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_achados import Ambiente
import mapa_relacoes
import rotas_evidencia
from test_tabelas_apuracao import Fontes

CPF = '52998224725'  # dígitos de um CPF de teste, sintético


class EditarEntidadeTest(Fontes, unittest.TestCase):
    def setUp(self):
        env, (_, _, _, second) = Ambiente.copia_completa(); self.addCleanup(env.cleanup)
        self.preparar(env, second)

    def pedido(self, **campos):
        return {'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, 'autor': 'Editora B', **campos}

    def test_detalhe_sem_mascara_e_atualizacao_com_o_corpo_do_formulario(self):
        criada = mapa_relacoes.salvar_entidade(self.root, self.pedido(
            tipo='pessoa', nome='Marta Reis', variantes=['M. Reis'], identificadores=[{'tipo': 'cpf', 'valor': CPF, 'fonte': 0}],
            evidencias=[self.link(self.ia())]), 'criar')
        mapa = rotas_evidencia.executar(self.root, 'mapa-ver', {'caso': 'alpha'})
        mascarado = next(e for e in mapa['entidades'] if e['id'] == criada['id'])['identificadores'][0]
        self.assertNotIn(CPF, str(mascarado), 'o mapa continua mascarando')
        detalhe = rotas_evidencia.executar(self.root, 'mapa-entidade-detalhe', {'caso': 'alpha', 'id': criada['id']})
        estado = detalhe['estado']
        self.assertEqual(estado['identificadores'][0]['valor'], CPF, 'o detalhe traz o valor salvo, para o formulário reenviar')
        self.assertEqual(detalhe['evidencias'][0]['estado'], 'conferida')

        # o que o formulário envia: o identificador como está, a fonte pelo índice, a variante nova, as evidências sem a forma salva
        corpo = self.pedido(id=criada['id'], anterior_sha256=detalhe['sha256'], tipo=estado['tipo'], nome='Marta Reis Prado',
                            variantes=[*estado['variantes'], 'Marta Prado'],
                            identificadores=[{'tipo': i['tipo'], 'valor': i['valor'], 'fonte': i['fonte']} for i in estado['identificadores']],
                            evidencias=[{k: e[k] for k in ('referencia', 'papel', 'suporte', 'natureza', 'justificativa')} for e in detalhe['evidencias']])
        rotas_evidencia.executar(self.root, 'mapa-entidade-atualizar', corpo)
        depois = rotas_evidencia.executar(self.root, 'mapa-entidade-detalhe', {'caso': 'alpha', 'id': criada['id']})
        self.assertEqual(depois['estado']['nome'], 'Marta Reis Prado')
        self.assertEqual(depois['estado']['variantes'], ['M. Reis', 'Marta Prado'])
        self.assertEqual(depois['estado']['identificadores'][0]['valor'], CPF)

        # o valor mascarado do mapa, reenviado por engano, seria recusado: a tela nunca usa o mapa-ver para editar
        with self.assertRaises(ValueError):
            rotas_evidencia.executar(self.root, 'mapa-entidade-atualizar', {**corpo, 'requisicao_id': uuid.uuid4().hex, 'anterior_sha256': depois['sha256'],
                'identificadores': [{'tipo': 'cpf', 'valor': str(mascarado.get('valor_exibicao')), 'fonte': 0}]})


if __name__ == '__main__':
    unittest.main()
