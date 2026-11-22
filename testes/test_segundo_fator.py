"""Segundo fator, as contas de aritmética e de cifra (``scripts/segundo_fator.py``; contrato de contas, seções 7 e 8.2).

TOTP contra os vetores da RFC 6238, a regra de que um código não vale duas vezes, os códigos de reserva e a
semente cifrada com a chave de ``segredos/contas.chave``. Tudo numa pasta temporária; sem rede.
"""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import segundo_fator as fator

SEMENTE_DA_RFC = b'12345678901234567890'
# RFC 6238, appendix B, SHA-1: time in seconds and the last six digits of the eight-digit code.
VETORES = ((59, '287082'), (1111111109, '081804'), (1111111111, '050471'), (1234567890, '005924'), (2000000000, '279037'),
           (20000000000, '353130'))
CONTA, OUTRA = 'a' * 16, 'b' * 16


def instante(segundos):
    return datetime.fromtimestamp(segundos, timezone.utc)


class TotpTest(unittest.TestCase):
    def test_codigos_da_rfc_6238(self):
        for segundos, codigo in VETORES:
            self.assertEqual(fator.codigo_do_passo(SEMENTE_DA_RFC, segundos // 30), codigo, segundos)
            self.assertEqual(fator.conferir(SEMENTE_DA_RFC, codigo, instante(segundos)), segundos // 30)

    def test_um_passo_de_tolerancia_para_cada_lado_e_nenhum_a_mais(self):
        agora = instante(1234567890)
        passo = fator.passo_de(agora)
        for desvio, aceito in ((-2, False), (-1, True), (0, True), (1, True), (2, False)):
            codigo = fator.codigo_do_passo(SEMENTE_DA_RFC, passo + desvio)
            self.assertEqual(fator.conferir(SEMENTE_DA_RFC, codigo, agora) is not None, aceito, desvio)

    def test_o_mesmo_codigo_nao_vale_duas_vezes(self):
        agora = instante(1234567890)
        codigo = fator.codigo_do_passo(SEMENTE_DA_RFC, fator.passo_de(agora))
        passo = fator.conferir(SEMENTE_DA_RFC, codigo, agora)
        self.assertIsNone(fator.conferir(SEMENTE_DA_RFC, codigo, agora, ultimo_passo=passo))
        self.assertIsNone(fator.conferir(SEMENTE_DA_RFC, codigo, agora + timedelta(seconds=30), ultimo_passo=passo))
        anterior = fator.codigo_do_passo(SEMENTE_DA_RFC, passo - 1)  # nor a code older than the last one used
        self.assertIsNone(fator.conferir(SEMENTE_DA_RFC, anterior, agora, ultimo_passo=passo))
        seguinte = fator.codigo_do_passo(SEMENTE_DA_RFC, passo + 1)
        self.assertEqual(fator.conferir(SEMENTE_DA_RFC, seguinte, agora + timedelta(seconds=30), ultimo_passo=passo), passo + 1)

    def test_so_seis_digitos_sao_um_codigo(self):
        agora = instante(59)
        self.assertEqual(fator.conferir(SEMENTE_DA_RFC, ' 287 082 ', agora), 1)  # as apps show it
        for errado in ('287083', '28708', '2870820', 'abcdef', '', None, 287082, ['287082'], '２８７０８２', '-87082'):
            self.assertIsNone(fator.conferir(SEMENTE_DA_RFC, errado, agora), errado)
        self.assertIsNone(fator.conferir(fator.nova_semente(), '287082', agora))  # another seed

    def test_semente_e_endereco_para_o_aplicativo(self):
        semente = fator.nova_semente()
        self.assertEqual(len(semente), 20)
        self.assertNotEqual(semente, fator.nova_semente())
        self.assertRegex(fator.em_base32(semente), r'^[A-Z2-7]{32}$')
        endereco = fator.endereco(SEMENTE_DA_RFC, 'ana maria@exemplo.test')
        self.assertEqual(endereco, 'otpauth://totp/Vlado%3Aana%20maria%40exemplo.test?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'
                                   '&issuer=Vlado&algorithm=SHA1&digits=6&period=30')
        hostil = fator.endereco(SEMENTE_DA_RFC, 'x?secret=AAAA&issuer=Outro#')
        self.assertEqual(hostil.count('secret='), 1)  # a label never adds or replaces a parameter
        self.assertEqual(hostil.count('issuer='), 1)


class DependenciaTest(unittest.TestCase):
    def test_cryptography_e_dependencia_direta_com_a_versao_da_trava(self):
        # Decision 13: it used to come only through the OCR's dependencies, which could drop it without notice.
        raiz = Path(__file__).resolve().parents[1]
        diretas = dict(re.findall(r'^([A-Za-z0-9._-]+)==(\S+)$', (raiz / 'requirements.txt').read_text(encoding='utf-8'), re.M))
        self.assertIn('cryptography', diretas)
        trava = dict(re.findall(r'^([A-Za-z0-9._-]+)==(\S+?)(?:\s|\\)', (raiz / 'deploy' / 'requirements.lock').read_text(encoding='utf-8'), re.M))
        self.assertEqual(trava.get('cryptography'), diretas['cryptography'])
        import cryptography
        self.assertEqual(cryptography.__version__, diretas['cryptography'])  # what this environment runs is what is pinned


class ReservaTest(unittest.TestCase):
    def test_dez_codigos_diferentes_num_formato_que_se_dita(self):
        codigos = fator.novos_codigos_de_reserva()
        self.assertEqual((len(codigos), len(set(codigos))), (10, 10))
        for codigo in codigos:
            self.assertRegex(codigo, r'^[A-HJ-NP-Z2-9]{5}-[A-HJ-NP-Z2-9]{5}$')
        self.assertFalse(set(codigos) & set(fator.novos_codigos_de_reserva()))

    def test_o_que_a_pessoa_digita_vira_a_mesma_forma_e_o_armazenamento_guarda_so_o_resumo(self):
        codigo = fator.novos_codigos_de_reserva()[0]
        resumo = fator.resumo_da_reserva(codigo)
        self.assertRegex(resumo, r'^[0-9a-f]{64}$')
        self.assertNotIn(codigo.replace('-', ''), resumo.upper())
        for digitado in (codigo.lower(), codigo.replace('-', ''), f'  {codigo[:5]} {codigo[6:]} ', codigo.replace('-', ' - ')):
            self.assertEqual(fator.resumo_da_reserva(digitado), resumo, digitado)
        outro = codigo[:-1] + ('A' if codigo[-1] != 'A' else 'B')
        self.assertNotEqual(fator.resumo_da_reserva(outro), resumo)
        for invalido in ('', None, 'ABCDE-FGHJ', 'ABCDE-FGHJKL', 'ABCDE-FGHJ0', 'ABCDE-FGHJI', '287082', 5, 'A' * 41, ['x']):
            self.assertIsNone(fator.resumo_da_reserva(invalido), invalido)


class SementeCifradaTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        env = patch.dict(os.environ, {'VLADO_SEGREDOS': ''})
        env.start()
        self.addCleanup(env.stop)
        fator._CHAVES.clear()
        self.addCleanup(fator._CHAVES.clear)

    def test_semente_cifrada_so_abre_com_a_chave_e_na_conta_dela(self):
        semente = fator.nova_semente()
        guardada = fator.cifrar(self.root, semente, CONTA)
        self.assertEqual(fator.decifrar(self.root, guardada, CONTA), semente)
        self.assertNotEqual(guardada, fator.cifrar(self.root, semente, CONTA))  # a new nonce each time
        self.assertNotIn(fator.em_base32(semente), guardada)
        self.assertNotIn(semente.hex(), guardada)
        with self.assertRaises(fator.SementeIlegivel):
            fator.decifrar(self.root, guardada, OUTRA)  # the row of one account does not open as another's
        for estragada in (guardada[:-4] + 'AAAA', 'nao-e-base64!', '', None, guardada[:10]):
            with self.assertRaises(fator.SementeIlegivel):
                fator.decifrar(self.root, estragada, CONTA)

    def test_a_chave_fica_em_segredos_fora_da_pasta_das_contas_e_nao_e_trocada_em_silencio(self):
        guardada = fator.cifrar(self.root, b'x' * 20, CONTA)
        arquivo = self.root / 'segredos' / 'contas.chave'
        self.assertEqual(fator.arquivo_da_chave(self.root), arquivo)
        self.assertTrue(re.fullmatch(r'[0-9a-f]{64}\n', arquivo.read_text(encoding='ascii')))
        self.assertFalse((self.root / 'acesso').exists())
        fator._CHAVES.clear()  # another process: the same key is read again
        self.assertEqual(fator.decifrar(self.root, guardada, CONTA), b'x' * 20)
        arquivo.write_text('estragada\n', encoding='ascii')
        fator._CHAVES.clear()
        for acao in (lambda: fator.cifrar(self.root, b'y' * 20, CONTA), lambda: fator.decifrar(self.root, guardada, CONTA)):
            with self.assertRaises(fator.ChaveIlegivel):
                acao()
        self.assertEqual(arquivo.read_text(encoding='ascii'), 'estragada\n')  # left as it was, for who restores it

    def test_quem_copia_so_o_banco_nao_gera_codigos(self):
        guardada = fator.cifrar(self.root, SEMENTE_DA_RFC, CONTA)
        outra_instalacao = tempfile.TemporaryDirectory()
        self.addCleanup(outra_instalacao.cleanup)
        with self.assertRaises(fator.SementeIlegivel):
            fator.decifrar(Path(outra_instalacao.name), guardada, CONTA)  # another key: the seed does not open


if __name__ == '__main__':
    unittest.main()
