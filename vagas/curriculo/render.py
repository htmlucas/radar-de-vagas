"""Transforma o documento montado em .docx (python-docx) e .pdf (fpdf2).

Os dois seguem o mesmo layout. O PDF é gerado direto em Python para não
depender de Word ou LibreOffice instalados.
"""

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from fpdf import FPDF
from fpdf.enums import XPos, YPos

AZUL = (31, 56, 100)
CINZA = (90, 90, 90)
PRETO = (25, 25, 25)

SECOES = [
    ("Resumo profissional", "resumo"),
    ("Experiência profissional", "experiencias"),
    ("Projetos", "projetos"),
    ("Competências técnicas", "competencias"),
    ("Formação acadêmica", "formacao"),
    ("Certificações", "certificacoes"),
]


def linha_contato(contato: dict) -> str:
    campos = ["cidade", "disponibilidade", "email", "telefone", "linkedin", "github"]
    return "  ·  ".join(contato[c] for c in campos if contato.get(c))


def texto_formacao(f: dict) -> str:
    status = f" ({f['status']})" if f.get("status") else ""
    return f"{f['curso']} — {f['instituicao']}{status}"


# =========================================================================== DOCX
def _borda_inferior(paragrafo) -> None:
    p_pr = paragrafo._p.get_or_add_pPr()
    borda = OxmlElement("w:pBdr")
    inferior = OxmlElement("w:bottom")
    for k, v in {"w:val": "single", "w:sz": "6", "w:space": "1", "w:color": "1F3864"}.items():
        inferior.set(qn(k), v)
    borda.append(inferior)
    p_pr.append(borda)


def _run(paragrafo, texto, tamanho=10.5, negrito=False, italico=False, cor=PRETO):
    r = paragrafo.add_run(texto)
    r.font.size, r.font.bold, r.font.italic = Pt(tamanho), negrito, italico
    r.font.color.rgb = RGBColor(*cor)
    return r


def salvar_docx(doc_dados: dict, caminho: Path) -> Path:
    doc = Document()
    for secao in doc.sections:
        secao.top_margin = secao.bottom_margin = Cm(1.6)
        secao.left_margin = secao.right_margin = Cm(1.9)
    estilo = doc.styles["Normal"]
    estilo.font.name = "Calibri"
    estilo.font.size = Pt(10.5)
    estilo.paragraph_format.space_after = Pt(2)

    c = doc_dados["contato"]
    _run(doc.add_paragraph(), c["nome"], 20, negrito=True, cor=AZUL)
    _run(doc.add_paragraph(), c["titulo"], 12, cor=CINZA)
    _run(doc.add_paragraph(), linha_contato(c), 9.5, cor=CINZA)

    for titulo, chave in SECOES:
        valor = doc_dados.get(chave)
        if not valor:
            continue
        cab = doc.add_paragraph()
        cab.paragraph_format.space_before = Pt(10)
        cab.paragraph_format.space_after = Pt(4)
        _run(cab, titulo.upper(), 11, negrito=True, cor=AZUL)
        _borda_inferior(cab)

        if chave == "resumo":
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            _run(p, valor)
        elif chave == "experiencias":
            for exp in valor:
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(5)
                _run(p, f"{exp['cargo']} — {exp['empresa']}", negrito=True)
                _run(p, f"   {exp['periodo']}", 9.5, italico=True, cor=CINZA)
                for a in exp["atividades"]:
                    b = doc.add_paragraph(style="List Bullet")
                    _run(b, a)
        elif chave == "projetos":
            for proj in valor:
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(4)
                _run(p, proj["nome"], negrito=True)
                if proj.get("link"):
                    _run(p, f"   {proj['link']}", 9.5, cor=CINZA)
                _run(doc.add_paragraph(), proj["descricao"])
        elif chave == "competencias":
            for area, itens in valor.items():
                p = doc.add_paragraph()
                _run(p, f"{area}: ", negrito=True)
                _run(p, ", ".join(itens))
        elif chave == "formacao":
            for f in valor:
                _run(doc.add_paragraph(style="List Bullet"), texto_formacao(f))
        elif chave == "certificacoes":
            for cert in valor:
                _run(doc.add_paragraph(style="List Bullet"), cert)

    caminho.parent.mkdir(parents=True, exist_ok=True)
    doc.save(caminho)
    return caminho


# =========================================================================== PDF
FONTES_WINDOWS = Path("C:/Windows/Fonts")


class _PDF(FPDF):
    def __init__(self):
        super().__init__(format="A4")
        self.set_margins(19, 16, 19)
        self.set_auto_page_break(True, margin=16)
        regular, negrito, italico = (FONTES_WINDOWS / f for f in ("calibri.ttf", "calibrib.ttf", "calibrii.ttf"))
        if regular.exists() and negrito.exists() and italico.exists():
            self.add_font("Corpo", "", str(regular))
            self.add_font("Corpo", "B", str(negrito))
            self.add_font("Corpo", "I", str(italico))
            self.fonte, self.unicode = "Corpo", True
        else:  # sem Calibri: fonte embutida (só latin-1)
            self.fonte, self.unicode = "Helvetica", False

    def texto(self, s: str) -> str:
        if self.unicode:
            return s
        s = s.replace("—", "-").replace("–", "-").replace("·", "|").replace("•", "-")
        return s.encode("latin-1", "replace").decode("latin-1")

    def escrever(self, s, tamanho=10.5, estilo="", cor=PRETO, altura=5, alinhar="L"):
        self.set_font(self.fonte, estilo, tamanho)
        self.set_text_color(*cor)
        self.multi_cell(0, altura, self.texto(s), align=alinhar, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def secao(self, titulo):
        self.ln(3)
        self.escrever(titulo.upper(), 11, "B", AZUL, 6)
        self.set_draw_color(*AZUL)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)

    def marcador(self, s):
        self.set_font(self.fonte, "", 10.5)
        self.set_text_color(*PRETO)
        self.cell(5, 5, self.texto("•"))
        self.multi_cell(0, 5, self.texto(s), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def salvar_pdf(doc_dados: dict, caminho: Path) -> Path:
    pdf = _PDF()
    pdf.add_page()
    c = doc_dados["contato"]
    pdf.escrever(c["nome"], 20, "B", AZUL, 9)
    pdf.escrever(c["titulo"], 12, "", CINZA, 6)
    pdf.escrever(linha_contato(c), 9.5, "", CINZA, 5)

    for titulo, chave in SECOES:
        valor = doc_dados.get(chave)
        if not valor:
            continue
        pdf.secao(titulo)
        if chave == "resumo":
            pdf.escrever(valor, alinhar="J")
        elif chave == "experiencias":
            for exp in valor:
                pdf.ln(1.5)
                pdf.set_font(pdf.fonte, "B", 10.5)
                pdf.set_text_color(*PRETO)
                cabecalho = pdf.texto(f"{exp['cargo']} — {exp['empresa']}")
                pdf.cell(pdf.get_string_width(cabecalho) + 3, 5.5, cabecalho)
                pdf.set_font(pdf.fonte, "I", 9.5)
                pdf.set_text_color(*CINZA)
                pdf.cell(0, 5.5, pdf.texto(exp["periodo"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                for a in exp["atividades"]:
                    pdf.marcador(a)
        elif chave == "projetos":
            for proj in valor:
                pdf.ln(1)
                nome = proj["nome"] + (f"   {proj['link']}" if proj.get("link") else "")
                pdf.escrever(nome, 10.5, "B")
                pdf.escrever(proj["descricao"], alinhar="J")
        elif chave == "competencias":
            for area, itens in valor.items():
                pdf.set_font(pdf.fonte, "B", 10.5)
                pdf.set_text_color(*PRETO)
                rotulo = pdf.texto(f"{area}: ")
                pdf.cell(pdf.get_string_width(rotulo), 5, rotulo)
                pdf.set_font(pdf.fonte, "", 10.5)
                pdf.multi_cell(0, 5, pdf.texto(", ".join(itens)), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        elif chave == "formacao":
            for f in valor:
                pdf.marcador(texto_formacao(f))
        elif chave == "certificacoes":
            for cert in valor:
                pdf.marcador(cert)

    caminho.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(caminho))
    return caminho
