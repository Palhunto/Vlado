import sys
sys.stdout.reconfigure(encoding='utf-8')


def lum(h):
    h = h.lstrip('#')
    r, g, b = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def cr(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


# (id, frente, fundo, minimo, uso)
C = [
    # claro: texto
    ('C01', '#202c29', '#f6f5f0', 4.5, 'texto / fundo da página'),
    ('C02', '#202c29', '#fffefa', 4.5, 'texto / superfície (cartões, cabeçalho)'),
    ('C03', '#202c29', '#efefe8', 4.5, 'texto / barra lateral e painel do original'),
    ('C04', '#202c29', '#f1f2e9', 4.5, 'texto / caixa "Sua pergunta" (leitura)'),
    ('C05', '#202c29', '#f7ecdf', 4.5, 'texto / fundo de aviso (lacuna, cartão LAI)'),
    ('C06', '#202c29', '#e8eee6', 4.5, 'texto / verde suave (aviso de teste no Entrar)'),
    ('C07', '#202c29', '#ffe9a8', 4.5, 'texto / realce do trecho citado no original'),
    ('C08', '#5f6a63', '#f6f5f0', 4.5, 'secundário / fundo'),
    ('C09', '#5f6a63', '#fffefa', 4.5, 'secundário / superfície'),
    ('C10', '#5f6a63', '#efefe8', 4.5, 'secundário / barra lateral; botão indisponível'),
    ('C11', '#5f6a63', '#f1f2e9', 4.5, 'secundário / leitura ("Sua pergunta")'),
    ('C12', '#5f6a63', '#e4e9dc', 4.5, 'secundário / item ativo (tema atual)'),
    ('C13', '#5f6a63', '#e8eee6', 4.5, 'secundário / verde suave'),
    ('C14', '#1e4d3e', '#fffefa', 4.5, 'verde / superfície (links, "Conferido no original")'),
    ('C15', '#1e4d3e', '#f6f5f0', 4.5, 'verde / fundo (links)'),
    ('C16', '#1e4d3e', '#e8eee6', 4.5, 'verde / verde suave (selo "Conferido", aba ativa, selo de fonte)'),
    ('C17', '#ffffff', '#1e4d3e', 4.5, 'branco / verde (botão principal, item ativo da barra)'),
    ('C18', '#ffffff', '#2e604c', 4.5, 'branco / verde ao passar o mouse'),
    ('C19', '#1e4d3e', '#ffffff', 4.5, 'verde / branco (contador no item ativo)'),
    ('C20', '#8e4b28', '#f7ecdf', 4.5, 'aviso / fundo de aviso (lacuna, "Lida por OCR")'),
    ('C21', '#8e4b28', '#efefe8', 4.5, 'aviso / barra lateral ("1 vence")'),
    ('C22', '#8e4b28', '#fffefa', 4.5, 'aviso / superfície (nota de OCR, "1 sem evidência")'),
    ('C23', '#8e4b28', '#f6f5f0', 4.5, 'aviso / fundo ("dia não informado")'),
    ('C24', '#ffffff', '#8e4b28', 4.5, 'branco / aviso (sinal "?" da lacuna)'),
    ('C25', '#87342c', '#fffefa', 4.5, 'erro / superfície (botão destrutivo, erro de campo)'),
    ('C26', '#87342c', '#f8e9e5', 4.5, 'erro / fundo de erro (selo "Sem suporte")'),
    # claro: gráficos e controles (3:1)
    ('C30', '#8a5a12', '#f6f5f0', 3, 'foco novo / fundo'),
    ('C31', '#8a5a12', '#fffefa', 3, 'foco novo / superfície'),
    ('C32', '#8a5a12', '#efefe8', 3, 'foco novo / barra lateral'),
    ('C33', '#8a5a12', '#f1f2e9', 3, 'foco novo / leitura'),
    ('C34', '#8a5a12', '#e8eee6', 3, 'foco novo / verde suave'),
    ('C35', '#8a5a12', '#f7ecdf', 3, 'foco novo / fundo de aviso'),
    ('C36', '#8a5a12', '#1e4d3e', 3, 'foco novo / verde (anel junto ao botão principal)'),
    ('C37', '#53886c', '#f6f5f0', 3, 'foco atual / fundo (comparação)'),
    ('C38', '#53886c', '#fffefa', 3, 'foco atual / superfície (comparação)'),
    ('C39', '#53886c', '#efefe8', 3, 'foco atual / barra lateral (comparação)'),
    ('C40', '#53886c', '#e4e9dc', 3, 'foco atual / item ativo (comparação)'),
    ('C41', '#74837a', '#fffefa', 3, 'borda de campo / superfície'),
    ('C42', '#74837a', '#f6f5f0', 3, 'borda de campo / fundo'),
    ('C43', '#74837a', '#efefe8', 3, 'borda de botão secundário / painel do original'),
    ('C44', '#87342c', '#fffefa', 3, 'borda de campo com erro (2 px) / superfície'),
    ('C45', '#b06a5c', '#fffefa', 3, 'borda do botão destrutivo / superfície'),
    ('C46', '#1d8058', '#fffefa', 3, 'pessoa / superfície'),
    ('C47', '#5b5fb8', '#fffefa', 3, 'empresa / superfície'),
    ('C48', '#3d4a45', '#fffefa', 3, 'órgão público / superfície'),
    ('C49', '#ffffff', '#1d8058', 3, 'ícone branco / pessoa'),
    ('C50', '#ffffff', '#5b5fb8', 3, 'ícone branco / empresa'),
    ('C51', '#ffffff', '#3d4a45', 3, 'ícone branco / órgão público'),
    ('C52', '#5f6a63', '#f6f5f0', 3, 'ligação do mapa / fundo'),
    ('C53', '#1e4d3e', '#f6f5f0', 3, 'ligação selecionada (4 px), marco cheio / fundo'),
    ('C54', '#8e4b28', '#f6f5f0', 3, 'ligação a confirmar e intervalo sem documento, tracejados / fundo'),
    ('C55', '#7f9685', '#f6f5f0', 3, 'trilho da linha do tempo; barra do gráfico / fundo'),
    ('C56', '#1e4d3e', '#dddfd6', 3, 'barra de progresso / trilha'),
    ('C57', '#dddfd6', '#fffefa', 3, 'trilha da barra de progresso / superfície'),
    ('C58', '#c47800', '#ffe9a8', 3, 'contorno do realce / realce'),
    ('C59', '#c47800', '#ffffff', 3, 'contorno do realce / página branca'),
    ('C60', '#dddfd6', '#f6f5f0', 3, 'borda de cartão / fundo'),
    ('C61', '#c58b55', '#f7ecdf', 3, 'borda de aviso / fundo de aviso'),
    ('C62', '#7f9685', '#e8eee6', 3, 'borda do selo "Conferido" / verde suave'),
    ('C63', '#b0508a', '#fffefa', 3, 'proposta "ameixa" para órgão público / superfície'),
    ('C64', '#ffffff', '#b0508a', 3, 'ícone branco / proposta "ameixa"'),
    # escuro: texto
    ('E01', '#eae9df', '#171d1a', 4.5, 'texto / fundo'),
    ('E02', '#eae9df', '#202823', 4.5, 'texto / superfície (rodapé do celular)'),
    ('E03', '#eae9df', '#121714', 4.5, 'texto / barra lateral e cabeçalho do celular'),
    ('E04', '#eae9df', '#28322c', 4.5, 'texto / leitura'),
    ('E05', '#eae9df', '#2c3c2e', 4.5, 'texto / verde suave (balão da pergunta)'),
    ('E06', '#eae9df', '#372e21', 4.5, 'texto / fundo de aviso (lacuna)'),
    ('E07', '#a8b3a9', '#171d1a', 4.5, 'secundário / fundo'),
    ('E08', '#a8b3a9', '#202823', 4.5, 'secundário / superfície (rodapé)'),
    ('E09', '#a8b3a9', '#121714', 4.5, 'secundário / cabeçalho'),
    ('E10', '#a8b3a9', '#2c3c2e', 4.5, 'secundário / verde suave'),
    ('E11', '#a8c79d', '#171d1a', 4.5, 'verde / fundo (links)'),
    ('E12', '#a8c79d', '#2c3c2e', 4.5, 'verde / verde suave (selo de fonte)'),
    ('E13', '#a8c79d', '#202823', 4.5, 'verde / superfície'),
    ('E14', '#172315', '#a8c79d', 4.5, 'texto sobre verde (botão principal)'),
    ('E15', '#172315', '#bad8af', 4.5, 'texto sobre verde ao passar o mouse'),
    ('E16', '#e6bc7a', '#372e21', 4.5, 'aviso / fundo de aviso ("Lacuna.")'),
    ('E17', '#e6bc7a', '#171d1a', 4.5, 'aviso / fundo'),
    ('E18', '#172315', '#e6bc7a', 4.5, 'sinal "?" sobre ocre'),
    ('E19', '#e7a097', '#202823', 4.5, 'erro / superfície'),
    ('E20', '#e7a097', '#382725', 4.5, 'erro / fundo de erro'),
    # escuro: gráficos e controles
    ('E30', '#e6bc7a', '#171d1a', 3, 'foco / fundo'),
    ('E31', '#e6bc7a', '#202823', 3, 'foco / superfície'),
    ('E32', '#e6bc7a', '#121714', 3, 'foco / cabeçalho e barra lateral'),
    ('E33', '#e6bc7a', '#2c3c2e', 3, 'foco / verde suave'),
    ('E34', '#64786a', '#202823', 3, 'borda de campo atual / superfície'),
    ('E35', '#64786a', '#171d1a', 3, 'borda de campo atual / fundo'),
    ('E36', '#64786a', '#28322c', 3, 'borda de campo atual / leitura'),
    ('E37', '#8a9c8f', '#202823', 3, 'borda de campo nova / superfície (lado de fora, rodapé)'),
    ('E38', '#8a9c8f', '#171d1a', 3, 'borda de campo nova / fundo (lado de dentro do campo)'),
    ('E39', '#8a9c8f', '#121714', 3, 'borda de campo nova / barra lateral'),
    ('E40', '#8a9c8f', '#28322c', 3, 'borda de campo nova / leitura'),
    ('E52', '#64786a', '#2c3c2e', 3, 'borda de campo atual / verde suave (item ativo)'),
    ('E53', '#8a9c8f', '#2c3c2e', 3, 'borda de campo nova / verde suave (item ativo)'),
    ('E54', '#172315', '#a8b3a9', 3, 'ícone escuro / órgão público no escuro, opção (a)'),
    ('E41', '#aa8754', '#372e21', 3, 'borda de aviso / fundo de aviso'),
    ('E42', '#3fa877', '#202823', 3, 'pessoa / superfície'),
    ('E43', '#8487e6', '#202823', 3, 'empresa / superfície'),
    ('E44', '#ffffff', '#3fa877', 3, 'ícone branco / pessoa'),
    ('E45', '#ffffff', '#8487e6', 3, 'ícone branco / empresa'),
    ('E46', '#172315', '#3fa877', 3, 'ícone escuro / pessoa'),
    ('E47', '#172315', '#8487e6', 3, 'ícone escuro / empresa'),
    ('E48', '#a8b3a9', '#28322c', 3, 'ligação do mapa / fundo do mapa'),
    ('E49', '#d46a9c', '#202823', 3, 'proposta "ameixa" escura / superfície'),
    ('E50', '#172315', '#d46a9c', 3, 'ícone escuro / proposta "ameixa" escura'),
    ('E51', '#3c4940', '#171d1a', 3, 'divisória / fundo'),
]
for i, a, b, m, u in C:
    r = cr(a, b)
    ok = 'passa' if r >= m else '**não passa**'
    print(f'| {i} | {u} | `{a}` / `{b}` | {r:.2f}:1 | {m:g}:1 | {ok} |')
