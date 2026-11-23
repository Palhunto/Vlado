"""acessos_da_conta: what the audit log holds of the account itself, for its own data export (E4b-2b de Contas).

Only the lines the account caused (conta equal to it, without por, and not an event anyone can set off with its
login or e-mail), with its own IP; never alvo, another account or a name. Synthetic data only.
"""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import registro_acesso as r  # noqa: E402

CONTA, OUTRA, DONO = '0123456789abcdef', 'fedcba9876543210', 'aaaaaaaaaaaaaaaa'
DIA = datetime(2031, 3, 4, 12, 0, tzinfo=timezone.utc)


class AcessosDaContaTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.pasta = self.root / 'registro'
        env = mock.patch.dict(os.environ, {'VLADO_REGISTRO': str(self.pasta)})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(r.encerrar_requisicao)

    def gravar(self, evento, resultado='ok', conta=CONTA, minutos=0, **extras):
        r.registrar(evento, resultado, conta, DIA + timedelta(minutes=minutos), **extras)

    def test_so_o_que_a_propria_conta_fez_com_o_ip_dela(self):
        self.gravar('login_ok', ip='203.0.113.7', cliente='web')
        self.gravar('download', minutos=1, tipo='exportacao', ip='203.0.113.7', alvo=OUTRA)
        self.gravar('papel_alterado', minutos=2, por=DONO, ip='198.51.100.9')  # the dono acted on it: dono's IP
        self.gravar('login_ok', conta=OUTRA, minutos=3, ip='198.51.100.10')
        self.gravar('login_falha', 'falha', minutos=4, motivo='credenciais', ip='192.0.2.66')  # anyone with its login
        self.gravar('redefinicao_pedida', minutos=5, ip='192.0.2.67')  # anyone with its e-mail
        self.gravar('conta_desativada_por_inatividade', minutos=6, por='manutencao')
        self.gravar('logout', minutos=60 * 24 + 1, ip='203.0.113.8')  # the next day, its own file
        self.assertEqual(len(list(self.pasta.glob('auditoria-*.jsonl'))), 2)
        self.assertEqual(r.acessos_da_conta(self.root, CONTA), [
            {'em': '2031-03-04T12:00:00Z', 'evento': 'login_ok', 'resultado': 'ok', 'cliente': 'web', 'ip': '203.0.113.7'},
            {'em': '2031-03-04T12:01:00Z', 'evento': 'download', 'resultado': 'ok', 'ip': '203.0.113.7'},
            {'em': '2031-03-05T12:01:00Z', 'evento': 'logout', 'resultado': 'ok', 'ip': '203.0.113.8'}])

    def test_nunca_outra_conta_alvo_ou_texto(self):
        self.gravar('acesso_negado', 'negado', motivo='outra_redacao', codigo='caso_indisponivel', alvo=OUTRA,
                    organizacao='org' + 'b' * 16, ip='203.0.113.7')
        [item] = r.acessos_da_conta(self.root, CONTA)
        self.assertEqual(set(item), {'em', 'evento', 'resultado', 'ip'})
        self.assertNotIn(OUTRA, str(item))

    def test_no_maximo_as_mais_novas_por_ultimo(self):
        with mock.patch.object(r, 'MAX_ACESSOS_DA_CONTA', 3):
            for minuto in range(5):
                self.gravar('login_ok', minutos=minuto)
            self.assertEqual([i['em'][-6:-4] for i in r.acessos_da_conta(self.root, CONTA)], ['02', '03', '04'])

    def test_sem_registro_lista_vazia(self):
        self.assertEqual(r.acessos_da_conta(self.root, CONTA), [])

    def test_ultima_linha_cortada_e_pulada_e_linha_ilegivel_no_meio_levanta(self):
        self.gravar('login_ok')
        arquivo = next(self.pasta.glob('auditoria-*.jsonl'))
        with open(arquivo, 'ab') as f:
            f.write(b'{"em":"2031-03-04T12:09:00Z","evento":"lo')  # a write in progress, or a crash
        self.assertEqual(len(r.acessos_da_conta(self.root, CONTA)), 1)
        with open(arquivo, 'ab') as f:
            f.write(b'\n')  # now a whole line that cannot be read
        with self.assertRaises(ValueError):
            r.acessos_da_conta(self.root, CONTA)

    def test_pasta_ilegivel_levanta_oserror(self):
        self.gravar('login_ok')
        with mock.patch.object(Path, 'iterdir', side_effect=PermissionError(13, 'negado')):
            with self.assertRaises(OSError):
                r.acessos_da_conta(self.root, CONTA)

    def test_conta_invalida(self):
        for conta in (None, '', 'manutencao', CONTA.upper()):
            with self.subTest(conta=conta), self.assertRaises(ValueError):
                r.acessos_da_conta(self.root, conta)

    def test_sem_variavel_le_o_registro_da_raiz(self):
        with mock.patch.dict(os.environ, {'VLADO_REGISTRO': ''}):
            r.registrar('login_ok', 'ok', CONTA, DIA, destino=self.root / 'registro')
            self.assertEqual([i['evento'] for i in r.acessos_da_conta(self.root, CONTA)], ['login_ok'])


if __name__ == '__main__':
    unittest.main()
