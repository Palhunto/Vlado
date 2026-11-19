"""Códigos estáveis de erro para a interface traduzir; as mensagens em português não mudam."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import erros
from inferencia_api import ErroIA


class CodigosTest(unittest.TestCase):
    def test_mensagens_conhecidas_viram_codigos_e_parametros(self):
        casos = {
            'Sessão expirada ou convite revogado. Abra novamente o link do convite.': ('sessao_expirada', {}),
            'Limite diário de 3 pergunta(s) atingido. Tente novamente amanhã.': ('cota_diaria_esgotada', {'cota': 3}),
            'Já há uma pergunta em andamento para este convite. Aguarde a resposta ou cancele.': ('pergunta_em_andamento', {}),
            'Conversa indisponível para este acesso.': ('conversa_indisponivel', {}),
            'Apuração não liberada para este convite.': ('caso_nao_liberado', {}),
            'Operação não permitida para convidados.': ('operacao_proibida', {}),
            'Requisição vazia ou muito grande.': ('requisicao_invalida', {}),
            'Informe uma pergunta de até 16000 caracteres.': ('pergunta_invalida', {}),
            'Limite diário de uso da instalação atingido. Tente novamente amanhã (UTC).': ('limite_tokens_dia', {}),
            'Esta pergunta já foi concluída e publicada; não há o que retomar.': ('conversa_concluida', {}),
            'A marcação foi alterada em outra janela. Abra Conferir novamente.': ('marcacao_alterada', {}),
            'A etapa revisao publicou a revisão r2_revisao sem chegar a ser registrada como aceita.':
                ('conversa_nao_retomavel', {}),
            'Cursor posterior ao histórico.': ('cursor_posterior', {}),
            'O conteúdo do item mudou desde a conferência. Revise o alcance e confirme novamente.': ('alcance_alterado', {}),
            'Não foi possível apagar tudo (arquivo em uso ou sem permissão).': ('apagamento_incompleto', {}),
            'Apuração não liberada para esta conta.': ('caso_nao_liberado', {}),
            'Selecione uma apuração para os quadros de evidência.': ('quadro_sem_caso', {}),
            'Campos inválidos no pedido do quadro.': ('quadro_campos_invalidos', {}),
            'Registro não encontrado nesta apuração.': ('registro_inexistente', {}),
            'O registro mudou. Atualize antes de salvar; seu formulário foi preservado.': ('registro_mudou', {}),
            'Evidência de outra apuração; vincule somente fontes desta apuração.': ('evidencia_outro_caso', {}),
            'O quadro de hipóteses está sendo salvo em outra janela ou um salvamento foi interrompido.': ('quadro_em_uso', {}),
            'Histórico do registro divergente (estado malformado); nenhuma atualização foi aplicada.':
                ('historico_divergente', {}),
            'Referência a fonte do caderno inválida.': ('referencia_evidencia_invalida', {}),
            'Escolha dois documentos diferentes.': ('documentos_comparacao_invalidos', {}),
            'Contexto deve ter de 0 a 10 linhas.': ('contexto_comparacao_invalido', {}),
            'O conjunto de achados referenciado mudou de identidade.': ('achados_mudaram', {}),
            'Evidência não pertence a esta revisão/caso/rodada.': ('evidencia_fora_da_revisao', {}),
            'Documento sem original congelado nesta rodada.': ('documento_sem_original', {}),
            'D002 não tem texto utilizável nesta rodada; compare no original.':
                ('documento_sem_texto', {'documento': 'D002'}),
            'O arquivo X está em execução em outro processo.': ('erro', {}),  # anchored patterns only
        }
        for mensagem, esperado in casos.items():
            with self.subTest(mensagem=mensagem):
                self.assertEqual(erros.codigo_de(mensagem), esperado)

    def test_desconhecida_vira_erro_e_erro_ia_usa_o_proprio_codigo(self):
        self.assertEqual(erros.codigo_de('Algo inesperado.'), ('erro', {}))
        import json
        try:
            json.loads('{quebrado')
        except json.JSONDecodeError as exc:
            self.assertEqual(erros.codigo_de(str(exc), exc), ('json_invalido', {}))
        self.assertEqual(erros.codigo_de('Falha remota.', ErroIA('Falha remota.', codigo='conexao')), ('ia_conexao', {}))
        self.assertEqual(erros.codigo_de('Chave de API ausente: cole a chave.', ErroIA('x', codigo='autenticacao')),
                         ('chave_ausente', {}))

    def test_codigos_sao_unicos_e_estaveis(self):
        nomes = [codigo for codigo, _ in erros.PADROES]
        self.assertEqual(len(nomes), len(set(nomes)))
        self.assertTrue(all(n.replace('_', '').isalnum() and n == n.lower() for n in nomes))


if __name__ == '__main__':
    unittest.main()
