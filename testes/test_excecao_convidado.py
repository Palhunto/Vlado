"""SEG-06: o texto cru de uma exceção (caminho do servidor, nome de arquivo, corpo do provedor) não chega a um convidado, nem pelos
eventos nem pela situação da conversa (eventos() e listar()). O administrador continua vendo o detalhe; o servidor o registra com
uma referência curta ("ref. 1a2b3c4d") que o convidado pode informar.

Reaproveita a fixture de test_codex_integracao (importada por módulo, sem alterá-la): dois casos sintéticos e um provedor de mentira."""
import json
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import codex_apuracao as ca
import test_codex_integracao as integracao
from agente_fluxo_fixture import aguardar_fim, esperar
from inferencia_api import ErroIA

CAMINHO = '/app/casos/vila_serena/originais/relatorio_confidencial_041.pdf'
CONVIDADO = 'a1b2c3d4e5f60718'
REF = re.compile(r'\(ref\. ([0-9a-f]{8})\)')
PROIBIDOS = (CAMINHO, 'relatorio_confidencial', '/app/', 'vila_serena', 'Errno', 'Traceback', 'Detalhe:', 'request_id', 'req_')


class Base(unittest.TestCase):
    def setUp(self):
        integracao.CodexIntegrationTest.setUp(self)

    def falhar_ao_iniciar(self, erro, dono=CONVIDADO):
        """Faz `thread/start` levantar `erro` e devolve o id da conversa que terminou em erro."""
        rpc = self.manager._start()
        chamar = rpc.call

        def falha(method, params=None):
            if method == 'thread/start':
                raise erro
            return chamar(method, params)
        rpc.call = falha
        identifier = self.manager.perguntar({'caso': 'alpha', 'pergunta': 'Pergunta técnica sintética.'}, dono=dono)['conversa']
        aguardar_fim(self.manager, identifier)
        self.assertEqual(self.manager.contexts[identifier]['meta']['estado'], 'erro')
        return identifier

    def texto_de_tudo(self, resultado) -> str:
        return json.dumps(resultado, ensure_ascii=False)

    def assertSemVazamento(self, resultado, onde):
        texto = self.texto_de_tudo(resultado)
        for proibido in PROIBIDOS:
            self.assertNotIn(proibido, texto, f'{onde}: "{proibido}" chegou ao convidado')


class ExcecaoInternaTest(Base):
    def test_excecao_com_caminho_vira_texto_fixo_com_referencia_para_o_convidado(self):
        identifier = self.falhar_ao_iniciar(OSError(2, 'No such file or directory', CAMINHO))
        resposta = self.manager.eventos(identifier, dono=CONVIDADO)
        self.assertSemVazamento(resposta, 'eventos()')
        erros = [e for e in resposta['eventos'] if e['tipo'] == 'erro']
        self.assertEqual(len(erros), 1)
        mensagem = erros[0]['dados']['mensagem']
        self.assertTrue(mensagem.startswith(ca.FALHA_INTERNA), mensagem)
        self.assertRegex(mensagem, REF)
        self.assertEqual(set(erros[0]['dados']) - {'mensagem'}, set(), 'só a mensagem pública sai; nada de detalhe, ref ou publica')

    def test_a_situacao_da_conversa_tambem_chega_limpa_por_eventos_e_por_listar(self):
        identifier = self.falhar_ao_iniciar(ValueError('configuracao.json ilegível em ' + CAMINHO))
        resposta = self.manager.eventos(identifier, dono=CONVIDADO)
        situacao = resposta['conversa']['situacao']
        self.assertEqual((situacao['codigo'], situacao['causa']), ('erro', 'erro'))
        self.assertTrue(situacao['mensagem'].startswith('A execução falhou. O que já foi concluído foi preservado.'))
        self.assertNotIn('Detalhe', situacao['mensagem'])
        self.assertRegex(situacao['mensagem'], REF)
        lista = self.manager.listar('alpha', dono=CONVIDADO)
        self.assertSemVazamento(lista, 'listar()')
        self.assertRegex(lista['conversas'][0]['situacao']['mensagem'], REF)
        # O evento de estado (do _finish) também não leva o detalhe.
        estado = [e for e in resposta['eventos'] if e['tipo'] == 'estado'][-1]
        self.assertNotIn('Detalhe', estado['dados']['mensagem'])
        self.assertSemVazamento(estado, 'evento de estado')

    def test_a_referencia_e_a_mesma_no_evento_na_situacao_e_no_log_do_servidor(self):
        with self.assertLogs('vlado.conversas', level='WARNING') as capturado:
            identifier = self.falhar_ao_iniciar(OSError(2, 'No such file or directory', CAMINHO))
        resposta = self.manager.eventos(identifier, dono=CONVIDADO)
        no_evento = REF.search([e for e in resposta['eventos'] if e['tipo'] == 'erro'][0]['dados']['mensagem']).group(1)
        na_situacao = REF.search(resposta['conversa']['situacao']['mensagem']).group(1)
        self.assertEqual(no_evento, na_situacao)
        log = '\n'.join(capturado.output)
        self.assertIn(f'ref {no_evento}', log)
        self.assertIn(CAMINHO, log, 'o detalhe fica no log do servidor, para o administrador')

    def test_o_administrador_continua_vendo_o_detalhe_completo(self):
        identifier = self.falhar_ao_iniciar(OSError(2, 'No such file or directory', CAMINHO))
        admin = self.manager.eventos(identifier)  # dono=None: administrador
        erro = [e for e in admin['eventos'] if e['tipo'] == 'erro'][0]['dados']
        self.assertIn(CAMINHO, erro['mensagem'])
        self.assertRegex(erro['ref'], r'^[0-9a-f]{8}$')
        self.assertIn(f'(ref. {erro["ref"]})', erro['publica'])
        self.assertIn('Detalhe:', admin['conversa']['situacao']['mensagem'])
        self.assertIn(CAMINHO, admin['conversa']['situacao']['mensagem'])
        self.assertIn(CAMINHO, self.manager.listar('alpha')['conversas'][0]['situacao']['mensagem'])

    def test_ler_como_convidado_nao_altera_o_que_o_administrador_ve(self):
        identifier = self.falhar_ao_iniciar(OSError(2, 'No such file or directory', CAMINHO))
        self.manager.eventos(identifier, dono=CONVIDADO)
        self.manager.listar('alpha', dono=CONVIDADO)
        admin = self.manager.eventos(identifier)
        self.assertIn(CAMINHO, self.texto_de_tudo(admin), 'a leitura do convidado não mexeu nos dados guardados')

    def test_outro_convidado_nao_alcanca_a_conversa(self):
        identifier = self.falhar_ao_iniciar(OSError(2, 'x', CAMINHO))
        with self.assertRaisesRegex(ValueError, 'indisponível'):
            self.manager.eventos(identifier, dono='b2b2b2b2b2b2b2b2')
        self.assertEqual(self.manager.listar('alpha', dono='b2b2b2b2b2b2b2b2'), {'conversas': []})


class ErroDoProvedorTest(Base):
    def test_erro_com_codigo_conhecido_mostra_so_o_texto_em_portugues_sem_o_detalhe(self):
        identifier = self.falhar_ao_iniciar(ErroIA('Falha de conexão ou prazo esgotado na API. Detalhe: HTTPSConnectionPool '
                                                   '(host=api.interno.example, request_id=req_abc123)', codigo='conexao'))
        resposta = self.manager.eventos(identifier, dono=CONVIDADO)
        self.assertSemVazamento(resposta, 'ErroIA conexao')
        self.assertNotIn('interno.example', self.texto_de_tudo(resposta))
        erro = [e for e in resposta['eventos'] if e['tipo'] == 'erro'][0]['dados']['mensagem']
        self.assertTrue(erro.startswith(ca.CAUSAS_ERRO['conexao'][2]), erro)
        self.assertEqual(resposta['conversa']['situacao']['mensagem'][:len(ca.CAUSAS_ERRO['conexao'][2])], ca.CAUSAS_ERRO['conexao'][2])

    def test_erro_sem_codigo_do_provedor_vira_texto_fixo(self):
        identifier = self.falhar_ao_iniciar(ErroIA('Falha na API: {"error": {"type": "api_error", "request_id": "req_abc123", '
                                                   '"message": "token de ' + CAMINHO + ' inválido"}}'))
        resposta = self.manager.eventos(identifier, dono=CONVIDADO)
        self.assertSemVazamento(resposta, 'ErroIA sem codigo')
        erro = [e for e in resposta['eventos'] if e['tipo'] == 'erro'][0]['dados']['mensagem']
        self.assertTrue(erro.startswith(ca.FALHA_INTERNA), erro)

    def test_erro_de_configuracao_que_cita_arquivo_nao_chega_ao_convidado(self):
        identifier = self.falhar_ao_iniciar(ErroIA('ajustes/inferencia.json ilegível; salve o provedor novamente na Mesa.'))
        resposta = self.manager.eventos(identifier, dono=CONVIDADO)
        self.assertNotIn('inferencia.json', self.texto_de_tudo(resposta))
        self.assertNotIn('ajustes/', self.texto_de_tudo(resposta))

    def test_turno_que_falha_no_provedor_com_mensagem_crua(self):
        identifier = self.manager.perguntar({'caso': 'alpha', 'pergunta': 'Pergunta técnica sintética.'}, dono=CONVIDADO)['conversa']
        meta = lambda: self.manager.contexts[identifier]['meta']
        esperar(lambda: meta().get('turn_id') or meta()['estado'] not in ca.ACTIVE)
        turno = meta()['turn_id']
        self.manager.rpc.emit('turn/completed', {'turn': {'id': turno, 'status': 'failed',
                                                          'error': {'message': f'upstream falhou lendo {CAMINHO} (req_abc123)'}}})
        aguardar_fim(self.manager, identifier)
        resposta = self.manager.eventos(identifier, dono=CONVIDADO)
        self.assertSemVazamento(resposta, 'turn/completed')
        erro = [e for e in resposta['eventos'] if e['tipo'] == 'erro'][0]['dados']
        self.assertTrue(erro['mensagem'].startswith(ca.FALHA_INTERNA), erro)
        self.assertIn(CAMINHO, self.texto_de_tudo(self.manager.eventos(identifier)), 'o administrador vê o detalhe')

    def test_turno_com_codigo_conhecido_mostra_o_texto_curado(self):
        identifier = self.manager.perguntar({'caso': 'alpha', 'pergunta': 'Pergunta técnica sintética.'}, dono=CONVIDADO)['conversa']
        meta = lambda: self.manager.contexts[identifier]['meta']
        esperar(lambda: meta().get('turn_id') or meta()['estado'] not in ca.ACTIVE)
        self.manager.rpc.emit('turn/completed', {'turn': {'id': meta()['turn_id'], 'status': 'failed', 'error': {
            'message': 'chave sk-ant-NaoDeveAparecer inválida para ' + CAMINHO, 'codexErrorInfo': 'autenticacao'}}})
        aguardar_fim(self.manager, identifier)
        resposta = self.manager.eventos(identifier, dono=CONVIDADO)
        self.assertSemVazamento(resposta, 'turn autenticacao')
        self.assertNotIn('NaoDeveAparecer', self.texto_de_tudo(resposta))
        erro = [e for e in resposta['eventos'] if e['tipo'] == 'erro'][0]['dados']['mensagem']
        self.assertTrue(erro.startswith(ca.CAUSAS_ERRO['autenticacao'][2]), erro)


class ErroDeConsultaDaFerramentaTest(Base):
    def test_aviso_de_erro_de_consulta_nao_leva_o_texto_do_erro_ao_convidado(self):
        identifier = self.manager.perguntar({'caso': 'alpha', 'pergunta': 'Pergunta técnica sintética.'}, dono=CONVIDADO)['conversa']
        meta = lambda: self.manager.contexts[identifier]['meta']
        esperar(lambda: meta().get('turn_id') or meta()['estado'] not in ca.ACTIVE)
        resultado = self.manager.ferramenta(identifier, {'acao': 'buscar', 'consulta': '"aspas abertas'})[0]
        self.assertEqual(resultado['estado'], 'erro_consulta')
        avisos = [e for e in self.manager.eventos(identifier, dono=CONVIDADO)['eventos']
                  if e['tipo'] == 'aviso' and 'consultar' in e['dados']['mensagem']]
        self.assertEqual(len(avisos), 1)
        self.assertTrue(avisos[0]['dados']['mensagem'].startswith(ca.ERRO_DE_CONSULTA), avisos[0])
        self.assertNotIn('Aspas', avisos[0]['dados']['mensagem'])
        admin = [e for e in self.manager.eventos(identifier)['eventos'] if e['tipo'] == 'aviso' and 'Erro de consulta' in e['dados']['mensagem']]
        self.assertIn('Aspas', admin[0]['dados']['mensagem'], 'o administrador vê o erro')
        self.manager.cancelar(identifier)


class AvisosComTextoDeExcecaoTest(Base):
    """B1 da revisão: três avisos (falha na publicação, registro de uso que não grava, falha da ferramenta) e outros pontos gravavam o
    texto da exceção sem `publica`; o convidado lia caminho, caso e documento. Agora todos passam por registrar_falha, e o que ficar
    sem `publica` é tratado como falha interna na leitura."""

    def conversa_em_curso(self):
        identifier = self.manager.perguntar({'caso': 'alpha', 'pergunta': 'Pergunta técnica sintética.'}, dono=CONVIDADO)['conversa']
        meta = lambda: self.manager.contexts[identifier]['meta']
        esperar(lambda: meta().get('turn_id') or meta()['estado'] not in ca.ACTIVE)
        return identifier

    def avisos(self, identifier, dono):
        return [e for e in self.manager.eventos(identifier, dono=dono)['eventos'] if e['tipo'] == 'aviso']

    def assertAvisoSeguro(self, identifier, comeco):
        convidado = [e for e in self.avisos(identifier, CONVIDADO) if e['dados']['mensagem'].startswith(comeco)]
        self.assertEqual(len(convidado), 1, [e['dados'] for e in self.avisos(identifier, CONVIDADO)])
        self.assertSemVazamento(convidado, comeco)
        self.assertRegex(convidado[0]['dados']['mensagem'], REF)
        admin = [e for e in self.avisos(identifier, None) if CAMINHO in e['dados']['mensagem'] or 'vila_serena' in e['dados']['mensagem']]
        self.assertTrue(admin, 'o administrador vê o detalhe completo')
        return convidado[0]['dados']['mensagem']

    def test_falha_ao_executar_a_ferramenta(self):
        identifier = self.conversa_em_curso()
        original = self.manager.ferramenta

        def quebra(ident, args):
            raise OSError(2, 'No such file or directory', CAMINHO)
        self.manager.ferramenta = quebra
        self.addCleanup(setattr, self.manager, 'ferramenta', original)
        self.manager.rpc.emit('item/tool/call', {'tool': 'consultar_acervo', 'arguments': {'acao': 'cobertura'},
                                                 'callId': 'c1', 'turnId': 'turn-1'}, request=321)
        self.manager.rpc.answer(321)
        mensagem = self.assertAvisoSeguro(identifier, 'Falha ao executar a ferramenta de consulta.')
        self.assertIn('(ref. ', mensagem)
        self.manager.cancelar(identifier)

    def test_registro_de_uso_que_nao_grava(self):
        identifier = self.conversa_em_curso()
        gravar = ca.escrever_json

        def sem_disco(caminho, *args, **kwargs):
            if 'api_uso_' in str(caminho):
                raise OSError(28, 'No space left on device', CAMINHO)
            return gravar(caminho, *args, **kwargs)
        ca.escrever_json = sem_disco
        self.addCleanup(setattr, ca, 'escrever_json', gravar)
        self.manager.rpc.emit('item/usage', {'turnId': 'turn-1', 'modelo': 'm', 'uso': {'entrada': 7}})
        esperar(lambda: any(e['tipo'] == 'aviso' and 'Registro de uso' in e['dados']['mensagem']
                            for e in self.manager.eventos(identifier)['eventos']))
        mensagem = self.assertAvisoSeguro(identifier, 'Registro de uso da API 0001 não gravado.')
        self.assertNotIn('No space left', mensagem)
        self.manager.cancelar(identifier)

    def test_falha_na_verificacao_ou_publicacao(self):
        import fluxo_codex
        original = fluxo_codex.Fluxo.finalize

        def falha(self_):
            raise OSError(5, 'Input/output error', CAMINHO)
        fluxo_codex.Fluxo.finalize = falha
        self.addCleanup(setattr, fluxo_codex.Fluxo, 'finalize', original)
        identifier = self.manager.perguntar({'caso': 'alpha', 'pergunta': 'Pergunta técnica sintética.'}, dono=CONVIDADO)['conversa']
        from agente_fluxo_fixture import completar
        completar(self.manager, identifier)
        aguardar_fim(self.manager, identifier)
        avisos = [e for e in self.avisos(identifier, CONVIDADO) if e['dados']['mensagem'].startswith('Falha na verificação ou na publicação')]
        self.assertEqual(len(avisos), 2, 'duas tentativas')
        self.assertSemVazamento(self.manager.eventos(identifier, dono=CONVIDADO), 'publicação')
        self.assertTrue(any(CAMINHO in e['dados']['mensagem'] for e in self.avisos(identifier, None)), 'o administrador vê o detalhe')

    def test_custo_nao_calculado_e_limites_nao_conferidos_e_aviso_do_provedor(self):
        import custo
        import limites
        identifier = self.conversa_em_curso()
        calcular, ler = custo.custo_da_chamada, limites.ler
        custo.custo_da_chamada = lambda *a, **k: (_ for _ in ()).throw(ValueError('tabela ilegível em ' + CAMINHO))
        limites.ler = lambda *a, **k: (_ for _ in ()).throw(OSError(13, 'Permission denied', CAMINHO))
        self.addCleanup(setattr, custo, 'custo_da_chamada', calcular)
        self.addCleanup(setattr, limites, 'ler', ler)
        self.manager.rpc.emit('item/usage', {'turnId': 'turn-1', 'modelo': 'm', 'uso': {'entrada': 7}})
        self.manager.rpc.emit('warning', {'message': 'proxy interno ' + CAMINHO + ' recusou'})
        esperar(lambda: len([e for e in self.avisos(identifier, None) if CAMINHO in e['dados']['mensagem']]) >= 3)
        textos = [e['dados']['mensagem'] for e in self.avisos(identifier, CONVIDADO)]
        for comeco in ('Custo da chamada não calculado.', 'Limites de tokens não conferidos.', 'Aviso do provedor recebido'):
            self.assertTrue(any(t.startswith(comeco) for t in textos), (comeco, textos))
        self.assertSemVazamento(self.avisos(identifier, CONVIDADO), 'custo, limites e provedor')
        # O começo que o teste de custo espera continua no que o administrador lê.
        self.assertTrue(any(e['dados']['mensagem'].startswith('Limites de tokens não conferidos') for e in self.avisos(identifier, None)))
        self.manager.cancelar(identifier)


class EventoDeErroSemPublicaTest(Base):
    def conversa_com_eventos(self):
        identifier = self.manager.perguntar({'caso': 'alpha', 'pergunta': 'Pergunta técnica sintética.'}, dono=CONVIDADO)['conversa']
        meta = lambda: self.manager.contexts[identifier]['meta']
        esperar(lambda: meta().get('turn_id') or meta()['estado'] not in ca.ACTIVE)
        return identifier

    def test_evento_de_erro_antigo_sem_publica_vira_falha_interna(self):
        identifier = self.conversa_com_eventos()
        self.manager._event(identifier, 'erro', {'mensagem': f'[Errno 2] No such file or directory: {CAMINHO}'})  # como se fosse antigo
        self.manager._event(identifier, 'erro', {'mensagem': 'texto cru', 'codigo': 'qualquer', 'detalhe': CAMINHO, 'ref': '0123abcd'})
        resposta = self.manager.eventos(identifier, dono=CONVIDADO)
        self.assertSemVazamento(resposta, 'erro antigo')
        erros = [e['dados'] for e in resposta['eventos'] if e['tipo'] == 'erro']
        self.assertEqual(erros[0], {'mensagem': ca.FALHA_INTERNA + ' (sem referência)'})
        self.assertEqual(erros[1], {'mensagem': ca.FALHA_INTERNA + ' (ref. 0123abcd)'}, 'com ref, a mesma referência')
        self.assertIn(CAMINHO, self.texto_de_tudo(self.manager.eventos(identifier)), 'o administrador vê o que foi gravado')
        self.manager.cancelar(identifier)

    def test_erro_com_texto_fixo_declarado_continua_legivel_para_o_convidado(self):
        identifier = self.conversa_com_eventos()
        self.manager._event(identifier, 'erro', ca.evento_curado('Conexão com a API perdida. Saídas parciais preservadas.'))
        erros = [e['dados'] for e in self.manager.eventos(identifier, dono=CONVIDADO)['eventos'] if e['tipo'] == 'erro']
        self.assertEqual(erros, [{'mensagem': 'Conexão com a API perdida. Saídas parciais preservadas.'}])
        self.manager.cancelar(identifier)

    def test_aviso_antigo_com_caminho_ou_arquivo_e_omitido_e_aviso_comum_passa(self):
        identifier = self.conversa_com_eventos()
        for texto in (f'Falhou em {CAMINHO}', r'Erro em C:\dados\caso\x', '[Errno 13] Permission denied', 'Abriu relatorio_final.pdf sem texto'):
            self.manager._event(identifier, 'aviso', {'mensagem': texto})
        self.manager._event(identifier, 'aviso', {'mensagem': 'Aguardando o fim de um cadastro em andamento.'})
        avisos = [e['dados']['mensagem'] for e in self.manager.eventos(identifier, dono=CONVIDADO)['eventos'] if e['tipo'] == 'aviso']
        self.assertEqual(avisos[-5:], [ca.AVISO_OMITIDO] * 4 + ['Aguardando o fim de um cadastro em andamento.'])
        self.manager.cancelar(identifier)

    def test_todos_os_eventos_de_erro_do_codigo_declaram_a_publica(self):
        """Ninguém grava um evento de erro com dicionário literal só com `mensagem`: use registrar_falha ou evento_curado."""
        fonte = (Path(ca.__file__)).read_text(encoding='utf-8')
        sem_publica = re.findall(r"_event\(identifier, '(?:erro|aviso)', \{'mensagem': (?:seguro|str)\(", fonte)
        sem_publica += re.findall(r"_event\(identifier, 'aviso', \{'mensagem': pipeline\.last_error", fonte)
        self.assertEqual(sem_publica, [], 'evento com texto de exceção sem passar por registrar_falha')
        literais = re.findall(r"_event\(identifier, 'erro', \{'mensagem'", fonte)
        self.assertEqual(literais, [], "evento de erro com dicionário literal: use evento_curado(...)")


class EtapaSemEntregaTest(Base):
    """Ressalva do SEG-06: o aviso de etapa sem entrega leva o texto de qualquer exceção ao guardar a etapa (`last_error`)."""

    def test_o_convidado_le_so_o_texto_fixo_e_o_administrador_le_o_detalhe(self):
        import fluxo_codex
        caminho = '/dados/vlado/execucoes/alpha/R001/saidas/inventario.json'
        original = fluxo_codex.Fluxo.artifact

        def quebra(self_, etapa, conteudo):
            raise OSError(28, 'No space left on device', caminho)
        fluxo_codex.Fluxo.artifact = quebra
        self.addCleanup(setattr, fluxo_codex.Fluxo, 'artifact', original)
        identifier = self.manager.perguntar({'caso': 'alpha', 'pergunta': 'Pergunta técnica sintética.'}, dono=CONVIDADO)['conversa']
        meta = lambda: self.manager.contexts[identifier]['meta']
        esperar(lambda: meta().get('etapa') == 'inventario' and meta().get('turn_id'))
        self.manager.ferramenta(identifier, {'acao': 'cobertura'})  # sem ela o inventário é recusado antes de gravar
        try:
            self.manager.ferramenta(identifier, {'acao': 'guardar', 'etapa': 'inventario', 'texto': 'x'})
        except (ValueError, OSError):
            pass
        self.manager.rpc.emit('turn/completed', {'turn': {'id': meta()['turn_id'], 'status': 'completed'}})
        sem_entrega = lambda e: e['tipo'] == 'aviso' and 'terminou sem uma entrega' in (e['dados'].get('publica') or e['dados']['mensagem'])
        esperar(lambda: any(sem_entrega(e) for e in self.manager.eventos(identifier)['eventos']))
        convidado = [e for e in self.manager.eventos(identifier, dono=CONVIDADO)['eventos'] if sem_entrega(e)]
        self.assertEqual(len(convidado), 1)
        mensagem = convidado[0]['dados']['mensagem']
        self.assertTrue(mensagem.startswith('A etapa inventario terminou sem uma entrega validada. Nova tentativa automática. (ref. '), mensagem)
        for proibido in (caminho, '/dados/', 'vlado', 'No space left', 'Errno', 'inventario.json', 'alpha'):
            self.assertNotIn(proibido, self.texto_de_tudo(convidado), proibido)
        admin = [e['dados'] for e in self.manager.eventos(identifier)['eventos'] if sem_entrega(e)]
        self.assertIn(caminho, admin[0]['mensagem'], 'o administrador vê o detalhe completo')
        self.assertEqual(admin[0]['ref'], REF.search(mensagem).group(1))
        self.manager.cancelar(identifier)


class FiltroDeAparenciaTest(unittest.TestCase):
    """A rede de segurança para aviso sem `publica`: omite o que parece caminho, nome de arquivo ou erro de sistema."""

    OMITE = (
        'Falhou em /app/casos/x/y.pdf', '/dados/vlado/execucoes/alpha/R001/saidas', 'erro lendo /srv/mesa/x', 'usou /usr/bin/python',
        'em /tmp', 'sob /raiz/qualquer/coisa/aqui', 'falhou em ~/x', 'C:\\dados\\vlado\\x', 'C:/dados/vlado/x', '\\\\servidor\\pasta\\x',
        'dados\\vlado\\x', 'em execucoes/alpha/R001', 'em saidas/consultas_sqlite', '[Errno 2] No such file', '[WinError 5] Acesso negado',
        'Traceback (most recent call last)', 'abriu notas.md', 'gravou eventos.jsonl', 'leu resumo.txt', 'relatorio.PDF', 'planilha.xlsx',
        'registro.log', 'banco.sqlite', 'copia.age', 'foto.jpeg',
    )
    PASSA = (
        'Etapa plano terminou sem uma entrega validada.', 'Aguardando o fim de um cadastro em andamento.', 'Limites de tokens não conferidos.',
        'e/ou ainda', 'TCP/IP', '1/2 das etapas', '3/5 referências', 'input/output', 'Nova tentativa automática.', 'Veja (a/b).',
        'R$ 1,50/hora', 'Texto. Depois outro.', 'cache 12h/30m', 'Fluxo editorial incompleto; etapas não registradas: plano, busca',
        '2 referência(s) da resposta sem leitura registrada nesta rodada. Conferência pendente.',
    )

    def test_omite_caminho_absoluto_de_qualquer_raiz_relativo_da_mesa_e_extensoes_que_a_mesa_grava(self):
        for texto in self.OMITE:
            self.assertIsNotNone(ca.SUSPEITO.search(texto), texto)

    def test_deixa_passar_o_aviso_comum(self):
        for texto in self.PASSA:
            self.assertIsNone(ca.SUSPEITO.search(texto), texto)

    def test_na_leitura_do_convidado_o_aviso_antigo_com_caminho_fora_da_lista_antiga_e_omitido(self):
        antigo = {'seq': 1, 'em_utc': 'x', 'tipo': 'aviso', 'dados': {'mensagem': 'Falhou em /dados/vlado/execucoes/alpha/R001/saidas'}}
        self.assertEqual(ca.evento_para_convidado(antigo)['dados']['mensagem'], ca.AVISO_OMITIDO)
        comum = {'seq': 2, 'em_utc': 'x', 'tipo': 'aviso', 'dados': {'mensagem': 'Nova tentativa automática.'}}
        self.assertEqual(ca.evento_para_convidado(comum), comum)


class AjudantesTest(unittest.TestCase):
    def test_sanear_texto_corta_o_detalhe_e_deixa_so_a_referencia(self):
        cru = 'A execução falhou. O que já foi concluído foi preservado. Detalhe: [Errno 2] /app/x/y.pdf [ref 0123abcd]'
        self.assertEqual(ca.sanear_texto(cru), 'A execução falhou. O que já foi concluído foi preservado. (ref. 0123abcd)')
        self.assertEqual(ca.sanear_texto('Texto curado, sem detalhe.'), 'Texto curado, sem detalhe.')
        self.assertEqual(ca.sanear_texto('Sem ref. Detalhe: caminho /x'), 'Sem ref.')
        self.assertIsNone(ca.sanear_texto(None))
        self.assertEqual(ca.sanear_texto(cru), ca.sanear_texto(ca.sanear_texto(cru)), 'idempotente')

    def test_mensagem_publica_por_tipo_de_erro(self):
        self.assertEqual(ca.mensagem_publica(OSError('/app/x')), ca.FALHA_INTERNA)
        self.assertEqual(ca.mensagem_publica(ErroIA('qualquer texto')), ca.FALHA_INTERNA)
        self.assertEqual(ca.mensagem_publica(ErroIA('x Detalhe: y', codigo='servidor')), ca.CAUSAS_ERRO['servidor'][2])
        self.assertEqual(ca.mensagem_publica('texto', 'limite'), ca.CAUSAS_ERRO['limite'][2])
        # códigos sem texto próprio: a mensagem curada do módulo de custo, sem o detalhe
        self.assertEqual(ca.mensagem_publica(ErroIA('Limite diário atingido. Detalhe: interno', codigo='limite_dia')),
                         'Limite diário atingido.')
        self.assertEqual(ca.mensagem_publica(ErroIA('', codigo='limite_dia')), ca.FALHA_INTERNA)

    def test_evento_para_convidado_preserva_o_que_nao_e_falha_e_nao_muta_o_original(self):
        normal = {'seq': 1, 'em_utc': 'x', 'tipo': 'escopo', 'dados': {'caso': 'alpha', 'rodada': 'R001'}}
        self.assertEqual(ca.evento_para_convidado(normal), normal)
        falha = {'seq': 2, 'em_utc': 'x', 'tipo': 'erro', 'dados': {'mensagem': 'cru /app/x', 'publica': 'fixo (ref. 0123abcd)', 'ref': '0123abcd'}}
        copia = json.loads(json.dumps(falha))
        limpo = ca.evento_para_convidado(falha)
        self.assertEqual(limpo['dados'], {'mensagem': 'fixo (ref. 0123abcd)'})
        self.assertEqual(falha, copia, 'o evento guardado não é alterado')
        antigo = {'seq': 3, 'em_utc': 'x', 'tipo': 'estado', 'dados': {'mensagem': 'Falhou. Detalhe: /app/z'}}
        self.assertEqual(ca.evento_para_convidado(antigo)['dados']['mensagem'], 'Falhou.')


if __name__ == '__main__':
    unittest.main()
