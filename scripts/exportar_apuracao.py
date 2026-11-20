"""Small Markdown notebook exporters. No HTML execution or remote resources."""
from io import BytesIO
from html import escape
from pathlib import Path
import re
from xml.sax.saxutils import escape as xml_escape

def referencias(note):
    for number, source in enumerate(note['fontes'], 1):
        identity = f"{source['caso']} / {source['rodada']}"
        if source['tipo'] == 'ia':
            identity += f" / {source['revisao']} / {source['achado_id']} v{source['achado_versao']}"
        else:
            identity += f" / índice {source['geracao']} / {source['referencia']}"
        yield f"Fonte {number} — {'Seleção de achado da IA' if source['tipo'] == 'ia' else 'Pesquisa documental'} — {identity}"
        if not source['documentos']:
            yield 'Achado sem evidência documental vinculada. Não equivale a fato conferido.'
        for doc in source['documentos']:
            page = f"página PDF {doc['pagina_pdf']} · " if doc.get('pagina_pdf') else ''
            yield f"{doc['nome_documento']} ({doc['documento_id']}) · {page}{doc['localizador']}"
            yield f"Original no projeto: execucoes/{source['caso']}/{source['rodada']}/{doc['original']}"
            yield f"SHA-256: {doc['original_sha256']}"
        yield 'Seleção preservada: ' + source['texto_selecionado']


def markdown(state):
    parts = ['# Caderno da apuração', f"Caso: {state['caso']} · revisão do caderno: {state['revisao']}",
             'Anotações humanas e seleções de fontes. A inclusão não representa conferência ou aprovação da IA.']
    for note in state['notas']:
        parts.extend(['## ' + note['titulo'].replace('\n', ' '), note['texto']])
        autor = (note.get('atualizado_por') or note.get('criado_por') or {}).get('nome')
        if autor:
            parts.append(f'Autoria (conta autenticada da Mesa): {autor}')
        if note['fontes']:
            parts.append('### Referências da nota ' + note['titulo'].replace('\n', ' '))
            parts.extend(ref.replace('\n', '\n\n') for ref in referencias(note))
    return '\n\n'.join(parts) + '\n'


def blocos(text):
    """The editor's basic subset: headings, lists, quotes, paragraphs, fences."""
    fenced = False
    for line in text.replace('\r\n', '\n').splitlines():
        if re.match(r'^\s*(```|~~~)', line):
            fenced = not fenced
            continue
        if fenced:
            yield 'codigo', line
            continue
        match = re.match(r'^(#{1,6})\s+(.*)', line)
        if match:
            yield 'h' + str(len(match[1])), match[2]
        elif re.match(r'^\s*[-+*]\s+', line):
            yield 'lista', re.sub(r'^\s*[-+*]\s+', '', line)
        elif re.match(r'^\s*\d+[.)]\s+', line):
            yield 'numerada', line.strip()
        elif re.match(r'^\s*>\s?', line):
            yield 'citacao', re.sub(r'^\s*>\s?', '', line)
        else:
            yield 'p', line


TOKEN = re.compile(r'(\*\*(.+?)\*\*|\*(.+?)\*|\[([^\]]+)\]\(([^\s)]+)\))')


def inline(text):
    start = 0
    for match in TOKEN.finditer(text):
        if match.start() > start:
            yield 'texto', text[start:match.start()], None
        if match[2] is not None:
            yield 'negrito', match[2], None
        elif match[3] is not None:
            yield 'italico', match[3], None
        elif re.match(r'^(https?://|mailto:)', match[5], re.I):
            yield 'link', match[4], match[5]
        else:
            yield 'texto', match[0], None
        start = match.end()
    if start < len(text):
        yield 'texto', text[start:], None


def docx(state):
    try:
        from docx import Document
        from docx.shared import Inches, Pt
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.opc.constants import RELATIONSHIP_TYPE
    except ImportError as exc:
        raise ValueError('Exportação DOCX exige python-docx de requirements.txt no Python do serviço.') from exc
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin = section.bottom_margin = Inches(.8)
    normal = document.styles['Normal']
    normal.font.name, normal.font.size = 'Calibri', Pt(11)
    for i, (kind, text) in enumerate(blocos(markdown(state))):
        if kind.startswith('h'):
            paragraph = document.add_paragraph(style='Title' if i == 0 else 'Heading ' + str(min(int(kind[1]), 9)))
        else:
            paragraph = document.add_paragraph(style='List Bullet' if kind == 'lista' else 'Quote' if kind == 'citacao' else 'Normal')
        for mode, value, url in inline(text) if kind != 'codigo' else [('texto', text, None)]:
            if mode == 'link':
                link = OxmlElement('w:hyperlink')
                link.set(qn('r:id'), paragraph.part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True))
                run = OxmlElement('w:r'); node = OxmlElement('w:t'); node.text = value
                run.append(node); link.append(run); paragraph._p.append(link)
            else:
                run = paragraph.add_run(value)
                run.bold = mode == 'negrito'; run.italic = mode == 'italico'
                if kind == 'codigo':
                    run.font.name = 'Consolas'
    output = BytesIO(); document.save(output)
    return output.getvalue()


def pdf(state):
    try:
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        import reportlab
    except ImportError as exc:
        raise ValueError('Exportação PDF exige reportlab de requirements.txt no Python do serviço.') from exc
    # Unicode font family bundled with reportlab, including real bold/italic faces.
    fonts = Path(reportlab.__file__).parent / 'fonts'
    if 'ApuracaoSans' not in pdfmetrics.getRegisteredFontNames():
        for name, file in (('ApuracaoSans', 'Vera.ttf'), ('ApuracaoBold', 'VeraBd.ttf'),
                           ('ApuracaoItalic', 'VeraIt.ttf'), ('ApuracaoBoldItalic', 'VeraBI.ttf')):
            pdfmetrics.registerFont(TTFont(name, str(fonts / file)))
        pdfmetrics.registerFontFamily('ApuracaoSans', normal='ApuracaoSans', bold='ApuracaoBold', italic='ApuracaoItalic', boldItalic='ApuracaoBoldItalic')
    styles = getSampleStyleSheet()
    for name in styles.byName:
        styles[name].fontName = 'ApuracaoSans'
        styles[name].splitLongWords = 1  # Wrap long paths without changing normal word spacing.
    styles.add(ParagraphStyle('NotebookQuote', parent=styles['BodyText'], leftIndent=18, textColor='#555555'))
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=48, bottomMargin=48)
    story = []
    for kind, text in blocos(markdown(state)):
        if not text:
            story.append(Spacer(1, 6)); continue
        value = ''
        for mode, content, url in inline(text) if kind != 'codigo' else [('texto', text, None)]:
            content = xml_escape(content)
            value += f'<b>{content}</b>' if mode == 'negrito' else f'<i>{content}</i>' if mode == 'italico' else f'<link href="{escape(url, quote=True)}">{content}</link>' if mode == 'link' else content
        style = styles['Heading' + str(min(int(kind[1]), 6))] if kind.startswith('h') else styles['NotebookQuote'] if kind == 'citacao' else styles['BodyText']
        story.append(Paragraph(('• ' if kind == 'lista' else '') + value, style))
    doc.build(story)
    return output.getvalue()


def exportar(state, formato):
    if formato == 'md':
        return markdown(state).encode('utf-8'), 'text/markdown; charset=utf-8'
    if formato == 'docx':
        return docx(state), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    if formato == 'pdf':
        return pdf(state), 'application/pdf'
    raise ValueError('Escolha Markdown, PDF ou DOCX.')
