from typing import Dict, Any, List, Tuple
from datetime import datetime
from fpdf import FPDF


def _safe_text(text: str) -> str:
	# Garantir compatibilidade latin-1 (core fonts) sem quebrar o PDF
	if text is None:
		return ""
	return text.encode("latin-1", "replace").decode("latin-1")


def _format_currency(value: float, currency: str) -> str:
	# Formatação aproximada estilo pt-BR com símbolo configurável
	formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
	return f"{currency} {formatted}"


def _calc_totals(items: List[Dict[str, Any]], discount_percent: float = 0.0, tax_percent: float = 0.0) -> Dict[str, float]:
	subtotal = 0.0
	for it in items:
		qty = float(it.get("quantity", 0))
		unit = float(it.get("unit_price", 0.0))
		subtotal += qty * unit
	discount = (discount_percent or 0.0) / 100.0 * subtotal
	total_after_discount = max(subtotal - discount, 0.0)
	tax = (tax_percent or 0.0) / 100.0 * total_after_discount
	grand_total = total_after_discount + tax
	return {
		"subtotal": round(subtotal, 2),
		"discount": round(discount, 2),
		"tax": round(tax, 2),
		"total": round(grand_total, 2),
	}


def generate_budget_pdf(payload: Dict[str, Any]) -> bytes:
	company_name = payload.get("company_name") or "Minha Empresa"
	company_email = payload.get("company_email") or ""
	client_name = payload.get("client_name") or ""
	client_email = payload.get("client_email") or ""
	currency = payload.get("currency") or "R$"
	discount_percent = float(payload.get("discount_percent") or 0.0)
	tax_percent = float(payload.get("tax_percent") or 0.0)
	notes = payload.get("notes") or ""
	items: List[Dict[str, Any]] = payload.get("items") or []

	totals = _calc_totals(items, discount_percent, tax_percent)

	pdf = FPDF(orientation="P", unit="mm", format="A4")
	pdf.set_auto_page_break(auto=True, margin=15)
	pdf.add_page()

	# Cabeçalho
	pdf.set_font("Helvetica", "B", 16)
	pdf.cell(0, 10, _safe_text(f"Orçamento"), ln=1)
	pdf.set_font("Helvetica", "", 10)
	now = datetime.now().strftime("%d/%m/%Y %H:%M")
	pdf.cell(0, 6, _safe_text(f"Gerado em {now}"), ln=1)
	pdf.ln(2)

	# Empresa / Cliente
	pdf.set_font("Helvetica", "B", 12)
	pdf.cell(0, 7, _safe_text("Dados da Empresa"), ln=1)
	pdf.set_font("Helvetica", "", 11)
	pdf.cell(0, 6, _safe_text(company_name), ln=1)
	if company_email:
		pdf.cell(0, 6, _safe_text(company_email), ln=1)
	pdf.ln(2)

	pdf.set_font("Helvetica", "B", 12)
	pdf.cell(0, 7, _safe_text("Cliente"), ln=1)
	pdf.set_font("Helvetica", "", 11)
	if client_name:
		pdf.cell(0, 6, _safe_text(client_name), ln=1)
	if client_email:
		pdf.cell(0, 6, _safe_text(client_email), ln=1)
	pdf.ln(4)

	# Tabela de itens
	col_item, col_qty, col_unit, col_total = 110, 20, 30, 30
	pdf.set_font("Helvetica", "B", 11)
	pdf.cell(col_item, 8, _safe_text("Item"), border=1)
	pdf.cell(col_qty, 8, _safe_text("Qtd"), border=1, align="C")
	pdf.cell(col_unit, 8, _safe_text("Unitário"), border=1, align="R")
	pdf.cell(col_total, 8, _safe_text("Total"), border=1, align="R", ln=1)

	pdf.set_font("Helvetica", "", 11)
	if not items:
		pdf.cell(0, 8, _safe_text("Nenhum item informado."), border=1, ln=1)
	else:
		for it in items:
			desc = _safe_text(str(it.get("description", ""))[:120])
			qty = float(it.get("quantity", 0))
			unit = float(it.get("unit_price", 0.0))
			line_total = qty * unit
			pdf.cell(col_item, 8, desc, border=1)
			pdf.cell(col_qty, 8, _safe_text(f"{qty:g}"), border=1, align="C")
			pdf.cell(col_unit, 8, _safe_text(_format_currency(unit, currency)), border=1, align="R")
			pdf.cell(col_total, 8, _safe_text(_format_currency(line_total, currency)), border=1, align="R", ln=1)

	# Totais
	pdf.ln(2)
	def row_total(label: str, value: float, bold: bool = False):
		pdf.set_font("Helvetica", "B" if bold else "", 11)
		pdf.cell(col_item + col_qty + col_unit, 8, _safe_text(label), align="R")
		pdf.cell(col_total, 8, _safe_text(_format_currency(value, currency)), align="R", ln=1)
	row_total("Subtotal:", totals["subtotal"])
	if discount_percent:
		row_total(f"Desconto ({discount_percent:.1f}%):", -totals["discount"])
	if tax_percent:
		row_total(f"Impostos ({tax_percent:.1f}%):", totals["tax"])
	row_total("Total:", totals["total"], bold=True)

	# Notas
	if notes:
		pdf.ln(4)
		pdf.set_font("Helvetica", "B", 11)
		pdf.cell(0, 6, _safe_text("Observações"), ln=1)
		pdf.set_font("Helvetica", "", 10)
		for line in _safe_text(notes).splitlines()[:12]:
			pdf.multi_cell(0, 5, line)

	# Retorno como bytes
	return pdf.output(dest="S").encode("latin-1")


