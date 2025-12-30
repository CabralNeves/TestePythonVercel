from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi import UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from typing import Tuple, Dict, Any
from io import BytesIO
import zipfile
import json

from PIL import Image, ImageOps
import exifread

from models.budget import BudgetRequest
from services.budget_pdf import generate_budget_pdf

app = FastAPI(title="Vercel Python App", version="0.1.0")


@app.get("/", response_class=HTMLResponse)
def read_root() -> HTMLResponse:
	# Página simples de exemplo
	html = """
	<!doctype html>
	<html lang="pt-br">
	<head>
		<meta charset="utf-8" />
		<meta name="viewport" content="width=device-width, initial-scale=1" />
		<title>Vercel Python App</title>
		<style>
			html, body { margin: 0; padding: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; background: #0b1020; color: #E6E8EC; }
			.container { max-width: 780px; margin: 0 auto; padding: 40px 20px; }
			.card { background: #12172b; border: 1px solid #1c2747; border-radius: 12px; padding: 24px; }
			h1 { margin: 0 0 12px; font-weight: 700; letter-spacing: .2px; }
			p { margin: 0 0 16px; color: #C6C9D3; }
			code { background: #0b1020; padding: 2px 6px; border-radius: 6px; border: 1px solid #1c2747; color: #9EE7FF; }
			a { color: #7bd2ff; text-decoration: none; }
			a:hover { text-decoration: underline; }
			.footer { margin-top: 16px; font-size: 12px; color: #97A0B5; }
		</style>
	</head>
	<body>
		<div class="container">
			<div class="card">
				<h1>🚀 Vercel + FastAPI</h1>
				<p>Aplicação mínima em Python pronta para deploy na Vercel.</p>
				<p>Tente a rota JSON: <a href="/api/hello/world"><code>/api/hello/world</code></a></p>
				<p>Interface de orçamento (PDF): <a href="/budget"><code>/budget</code></a></p>
				<p>Interface visual para imagens: <a href="/image"><code>/image</code></a></p>
				<p>Ou rode localmente: <code>uvicorn app:app --reload --port 8000</code> e abra <a href="http://localhost:8000" target="_blank"><code>http://localhost:8000</code></a>.</p>
				<div class="footer">v0.1.0</div>
			</div>
		</div>
	</body>
	</html>
	"""
	return HTMLResponse(content=html)


@app.get("/api/hello/{name}")
def say_hello(name: str) -> JSONResponse:
	message = f"Olá, {name}!"
	return JSONResponse(content={"message": message})


def _read_image_and_exif(file_bytes: bytes) -> Tuple[Image.Image, Dict[str, Any]]:
	# Extrai EXIF e cria imagem PIL em memória
	# Evita reler bytes várias vezes
	exif_data: Dict[str, Any] = {}
	with BytesIO(file_bytes) as bio:
		# EXIF (usando exifread para metadados detalhados)
		try:
			tags = exifread.process_file(bio, details=False)  # detalhes reduzidos para performance
			exif_data = {str(k): str(v) for k, v in tags.items()}
		except Exception:
			exif_data = {}
	# Reposiciona para abrir a imagem
	img = Image.open(BytesIO(file_bytes))
	return img, exif_data


def _apply_exif_orientation(img: Image.Image) -> Image.Image:
	# Ajusta orientação com base no EXIF, se existir
	try:
		return ImageOps.exif_transpose(img)
	except Exception:
		return img


def _fit_contain(img: Image.Image, max_side: int) -> Image.Image:
	# Redimensiona preservando aspecto, fazendo contain no lado informado
	img = img.copy()
	img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
	return img


def _choose_format_by_alpha(img: Image.Image, prefer_webp: bool = True) -> Tuple[str, Dict[str, Any]]:
	# Decide formato de saída pelo canal alpha
	has_alpha = (img.mode in ("RGBA", "LA")) or ("transparency" in img.info)
	params: Dict[str, Any] = {}
	if prefer_webp:
		# WEBP geralmente mais eficiente; mantém alpha se houver
		params = {"quality": 82, "method": 5}
		return ("WEBP", params) if not has_alpha else ("WEBP", params)
	# Fallback JPEG/PNG
	if has_alpha:
		return "PNG", {}
	return "JPEG", {"quality": 85, "optimize": True, "progressive": True}


def _save_image_to_bytes(img: Image.Image, fmt: str, params: Dict[str, Any]) -> bytes:
	with BytesIO() as out:
		if fmt.upper() == "JPEG" and img.mode in ("RGBA", "LA", "P"):
			img = img.convert("RGB")
		img.save(out, format=fmt, **params)
		return out.getvalue()


@app.post("/api/image/process")
async def process_image(file: UploadFile = File(...)) -> StreamingResponse:
	# Limites e validação básica
	allowed_content_types = {"image/jpeg", "image/png", "image/webp"}
	if file.content_type not in allowed_content_types:
		raise HTTPException(status_code=400, detail="Formato não suportado. Envie JPEG, PNG ou WEBP.")

	file_bytes = await file.read()
	max_bytes = 4_500_000  # limite sugerido para Vercel serverless (~4.5MB)
	if len(file_bytes) > max_bytes:
		raise HTTPException(status_code=413, detail="Arquivo muito grande. Envie até ~4.5MB.")

	try:
		img, exif_data = _read_image_and_exif(file_bytes)
		img = _apply_exif_orientation(img)
		width, height = img.size
	except Exception:
		raise HTTPException(status_code=400, detail="Não foi possível ler a imagem enviada.")

	# Geração de variações
	results: Dict[str, bytes] = {}

	# Thumbnail 256
	thumb = _fit_contain(img, 256)
	thumb_fmt, thumb_params = _choose_format_by_alpha(thumb, prefer_webp=True)
	results[f"thumb_256.{thumb_fmt.lower()}"] = _save_image_to_bytes(thumb, thumb_fmt, thumb_params)

	# Medium 1024
	medium = _fit_contain(img, 1024)
	medium_fmt, medium_params = _choose_format_by_alpha(medium, prefer_webp=True)
	results[f"medium_1024.{medium_fmt.lower()}"] = _save_image_to_bytes(medium, medium_fmt, medium_params)

	# Otimizada (mantém dimensions originais, troca para WEBP/JPEG/PNG com compressão)
	opt_fmt, opt_params = _choose_format_by_alpha(img, prefer_webp=True)
	results[f"optimized.{opt_fmt.lower()}"] = _save_image_to_bytes(img, opt_fmt, opt_params)

	# Metadados
	meta = {
		"original": {"width": width, "height": height, "content_type": file.content_type, "filename": file.filename},
		"exif": exif_data,
	}
	meta_bytes = json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8")
	results["metadata.json"] = meta_bytes

	# Empacota em ZIP em memória
	zip_buffer = BytesIO()
	with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
		for name, data in results.items():
			zf.writestr(name, data)
	zip_buffer.seek(0)

	filename_base = (file.filename or "image").rsplit(".", 1)[0]
	headers = {
		"Content-Disposition": f'attachment; filename="{filename_base}_processed.zip"'
	}
	return StreamingResponse(zip_buffer, media_type="application/zip", headers=headers)

@app.post("/api/budget/pdf")
async def budget_pdf(payload: BudgetRequest) -> StreamingResponse:
	if not payload.items:
		raise HTTPException(status_code=400, detail="Inclua pelo menos um item no orçamento.")

	pdf_bytes = generate_budget_pdf(payload.model_dump())
	headers = {"Content-Disposition": 'attachment; filename="orcamento.pdf"'}
	return StreamingResponse(BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)

@app.get("/image", response_class=HTMLResponse)
def image_ui() -> HTMLResponse:
	# UI aprimorada para upload/processamento com drag-and-drop, progresso e preview
	html = """
	<!doctype html>
	<html lang="pt-br">
	<head>
		<meta charset="utf-8" />
		<meta name="viewport" content="width=device-width, initial-scale=1" />
		<title>Processamento de Imagem</title>
		<style>
			:root { --bg:#0b1020; --card:#12172b; --border:#1c2747; --text:#E6E8EC; --muted:#C6C9D3; --accent:#7bd2ff; --accent-2:#9EE7FF; --danger:#ff6b6b; --ok:#8ce99a; }
			html, body { margin:0; padding:0; background:radial-gradient(1200px 800px at 20% -10%, #13214a 0%, #0b1020 60%), var(--bg); color:var(--text); font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
			.container { max-width: 880px; margin: 0 auto; padding: 40px 20px; }
			.card { background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.0)); border: 1px solid var(--border); border-radius: 14px; padding: 24px; box-shadow: 0 10px 30px rgba(0,0,0,0.25); }
			h1 { margin: 0 0 12px; font-weight: 700; letter-spacing: .2px; }
			p { margin: 0 0 16px; color: var(--muted); }
			a { color: var(--accent); text-decoration: none; }
			a:hover { text-decoration: underline; }
			.row { display: grid; grid-template-columns: 1fr; gap: 16px; }
			@media (min-width: 860px) { .row { grid-template-columns: 1fr 1fr; } }
			.panel { background: rgba(255,255,255,0.02); border: 1px dashed var(--border); border-radius: 12px; padding: 16px; }
			.label { font-size: 14px; color: var(--muted); margin-bottom: 8px; display:block; }
			.input { display:none; }
			.dropzone { border: 2px dashed var(--border); border-radius: 12px; padding: 18px; background: #0b1020; display:flex; align-items:center; gap:14px; cursor:pointer; transition: border-color .2s, background .2s; }
			.dropzone:hover { border-color: var(--accent); background:#0d1430; }
			.dropzone .icon { width: 32px; height: 32px; color: var(--accent-2); }
			.help { font-size: 13px; color: var(--muted); }
			.btn { appearance: none; border: 1px solid var(--border); border-radius: 10px; background: #0f1630; color: var(--text); padding: 10px 14px; cursor: pointer; transition: background .2s, transform .02s; }
			.btn:hover { background: #101a3a; }
			.btn:active { transform: translateY(1px); }
			.preview { display:flex; align-items:center; justify-content:center; min-height: 320px; border-radius: 10px; overflow:hidden; background:#0b1020; border:1px solid var(--border); }
			.preview img { max-width: 100%; max-height: 320px; object-fit: contain; display:block; }
			.fileinfo { margin-top: 10px; font-size: 13px; color: var(--muted); }
			.progress { height: 10px; background: #0b1020; border:1px solid var(--border); border-radius: 999px; overflow:hidden; }
			.progress > span { display:block; height:100%; width:0%; background: linear-gradient(90deg, #47b5ff, #7bd2ff); transition: width .15s ease-out; }
			.status { font-size: 14px; color: var(--muted); margin-top: 8px; min-height: 22px; }
			.badge { display:inline-block; padding: 2px 8px; border-radius: 999px; border:1px solid var(--border); background:#0f1630; color:#cfd8ff; font-size:12px; }
			code { background:#0b1020; border:1px solid var(--border); border-radius:6px; padding:2px 6px; color:#9EE7FF; }
		</style>
	</head>
	<body>
		<div class="container">
			<div class="card">
				<h1>🖼️ Processamento de Imagem</h1>
				<p>Envie uma imagem (JPEG/PNG/WEBP) para gerar miniatura, versão média, otimizada e metadados EXIF em um arquivo ZIP.</p>
				<div class="row">
					<div class="panel">
						<span class="label">Selecionar arquivo</span>
						<div id="dropzone" class="dropzone" title="Clique para selecionar ou arraste sua imagem">
							<svg class="icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
								<path d="M12 16V4m0 0l-4 4m4-4l4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
								<path d="M20 16v3a1 1 0 01-1 1H5a1 1 0 01-1-1v-3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
							</svg>
							<div>
								<div>Solte sua imagem aqui <span class="badge">JPEG/PNG/WEBP</span></div>
								<div class="help">ou clique para procurar (até ~4.5MB)</div>
							</div>
						</div>
						<input id="file" type="file" accept="image/jpeg,image/png,image/webp" class="input" />
						<div style="margin-top: 12px; display:flex; gap:8px; align-items:center;">
							<button id="btnProcess" class="btn">Processar</button>
							<a id="downloadLink" class="btn" style="display:none;" download>Baixar ZIP</a>
						</div>
						<div style="margin-top:12px" class="progress"><span id="bar"></span></div>
						<div class="fileinfo" id="fileinfo"></div>
						<div class="status" id="status"></div>
					</div>
					<div class="panel">
						<div class="label">Preview</div>
						<div class="preview"><img id="previewImg" alt="Preview" /></div>
					</div>
				</div>
				<p style="margin-top:16px">Endpoint usado: <code>POST /api/image/process</code></p>
			</div>
		</div>
		<script>
			const input = document.getElementById('file');
			const dropzone = document.getElementById('dropzone');
			const btn = document.getElementById('btnProcess');
			const statusEl = document.getElementById('status');
			const link = document.getElementById('downloadLink');
			const previewImg = document.getElementById('previewImg');
			const bar = document.getElementById('bar');
			const fileinfo = document.getElementById('fileinfo');

			input.addEventListener('change', () => {
				const f = input.files && input.files[0];
				if (f) {
					previewImg.src = URL.createObjectURL(f);
					renderFileInfo(f);
				} else {
					previewImg.removeAttribute('src');
					fileinfo.textContent = '';
				}
				link.style.display = 'none';
				statusEl.textContent = '';
				bar.style.width = '0%';
			});

			dropzone.addEventListener('click', () => input.click());
			dropzone.addEventListener('dragover', (e) => {
				e.preventDefault();
				dropzone.style.borderColor = 'var(--accent)';
			});
			dropzone.addEventListener('dragleave', () => {
				dropzone.style.borderColor = 'var(--border)';
			});
			dropzone.addEventListener('drop', (e) => {
				e.preventDefault();
				dropzone.style.borderColor = 'var(--border)';
				if (!e.dataTransfer.files || !e.dataTransfer.files[0]) return;
				const f = e.dataTransfer.files[0];
				if (!/^image\\/(jpeg|png|webp)$/.test(f.type)) {
					statusEl.textContent = 'Formato inválido. Envie JPEG, PNG ou WEBP.';
					return;
				}
				input.files = e.dataTransfer.files;
				previewImg.src = URL.createObjectURL(f);
				renderFileInfo(f);
				link.style.display = 'none';
				statusEl.textContent = '';
				bar.style.width = '0%';
			});

			btn.addEventListener('click', async () => {
				const f = input.files && input.files[0];
				if (!f) {
					statusEl.textContent = 'Selecione um arquivo primeiro.';
					return;
				}
				statusEl.textContent = 'Processando...';
				link.style.display = 'none';
				bar.style.width = '0%';

				try {
					const fd = new FormData();
					fd.append('file', f, f.name);

					// Usamos XHR para acompanhar progresso
					const xhr = new XMLHttpRequest();
					xhr.open('POST', '/api/image/process');
					xhr.responseType = 'blob';

					xhr.upload.onprogress = (e) => {
						if (!e.lengthComputable) return;
						const pct = Math.min(100, Math.round((e.loaded / e.total) * 100));
						bar.style.width = pct + '%';
					};

					xhr.onload = () => {
						if (xhr.status >= 200 && xhr.status < 300) {
							const blob = xhr.response;
							const url = URL.createObjectURL(blob);
							link.href = url;
							link.download = (f.name.split('.').slice(0, -1).join('.') || 'image') + '_processed.zip';
							link.style.display = 'inline-block';
							statusEl.textContent = 'Pronto! Clique em "Baixar ZIP".';
							bar.style.width = '100%';
						} else {
							const reader = new FileReader();
							reader.onload = () => {
								statusEl.textContent = 'Erro: ' + (reader.result || 'Falha no processamento');
							};
							reader.readAsText(xhr.response);
						}
					};

					xhr.onerror = () => {
						statusEl.textContent = 'Erro de rede durante o upload.';
					};

					xhr.send(fd);
				} catch (e) {
					statusEl.textContent = 'Erro: ' + (e?.message || 'Falha inesperada');
				}
			});

			function renderFileInfo(f) {
				const sizeKB = (f.size / 1024).toFixed(1);
				const imgEl = new Image();
				imgEl.onload = () => {
					fileinfo.textContent = `${f.name} — ${imgEl.naturalWidth}x${imgEl.naturalHeight}px — ${sizeKB} KB — ${f.type}`;
				};
				imgEl.src = URL.createObjectURL(f);
			}
		</script>
	</body>
	</html>
	"""
	return HTMLResponse(content=html)

@app.get("/budget", response_class=HTMLResponse)
def budget_ui() -> HTMLResponse:
	# UI para entrada de itens e geração do PDF de orçamento
	html = """
	<!doctype html>
	<html lang="pt-br">
	<head>
		<meta charset="utf-8" />
		<meta name="viewport" content="width=device-width, initial-scale=1" />
		<title>Orçamento (PDF)</title>
		<style>
			:root { --bg:#0b1020; --card:#12172b; --border:#1c2747; --text:#E6E8EC; --muted:#C6C9D3; --accent:#7bd2ff; }
			html, body { margin:0; padding:0; background:radial-gradient(1200px 800px at 20% -10%, #13214a 0%, #0b1020 60%), var(--bg); color:var(--text); font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
			.container { max-width: 980px; margin: 0 auto; padding: 40px 20px; }
			.card { background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.0)); border: 1px solid var(--border); border-radius: 14px; padding: 24px; box-shadow: 0 10px 30px rgba(0,0,0,0.25); }
			h1 { margin: 0 0 12px; font-weight: 700; letter-spacing: .2px; }
			p { margin: 0 0 16px; color: var(--muted); }
			.grid { display:grid; grid-template-columns: 1fr; gap:16px; }
			@media (min-width: 880px) { .grid { grid-template-columns: 1fr 1fr; } }
			.group { border: 1px dashed var(--border); border-radius: 12px; padding: 16px; }
			.label { font-size: 13px; color: var(--muted); margin-bottom: 6px; display:block; }
			.input, .select, .textarea { width:100%; padding:10px 12px; border-radius:10px; border:1px solid var(--border); background:#0b1020; color:var(--text); }
			table { width: 100%; border-collapse: collapse; }
			th, td { border-bottom:1px solid var(--border); padding:8px; text-align:left; }
			tfoot td { border-top:1px solid var(--border); }
			actions { display:flex; gap:8px; }
			.btn { appearance:none; border:1px solid var(--border); border-radius:10px; background:#0f1630; color:var(--text); padding:10px 14px; cursor:pointer; }
			.btn:hover { background:#101a3a; }
			footer { display:flex; align-items:center; gap:10px; margin-top:12px; color:var(--muted); }
			code { background:#0b1020; border:1px solid var(--border); border-radius:6px; padding:2px 6px; color:#9EE7FF; }
		</style>
	</head>
	<body>
		<div class="container">
			<div class="card">
				<h1>🧾 Orçamento (PDF)</h1>
				<p>Preencha os dados, inclua itens e gere um PDF de orçamento.</p>

				<div class="grid">
					<div class="group">
						<div class="label">Empresa</div>
						<input id="company_name" class="input" placeholder="Nome da empresa" />
						<input id="company_email" class="input" placeholder="Email da empresa" style="margin-top:8px" />
					</div>
					<div class="group">
						<div class="label">Cliente</div>
						<input id="client_name" class="input" placeholder="Nome do cliente" />
						<input id="client_email" class="input" placeholder="Email do cliente" style="margin-top:8px" />
					</div>
				</div>

				<div class="group" style="margin-top:16px">
					<div class="label">Itens</div>
					<table id="itemsTable">
						<thead>
							<tr>
								<th style="width:55%">Descrição</th>
								<th style="width:15%">Qtd</th>
								<th style="width:15%">Unitário</th>
								<th style="width:15%">Ações</th>
							</tr>
						</thead>
						<tbody></tbody>
						<tfoot>
							<tr>
								<td colspan="4"><button id="addItem" type="button" class="btn" onclick="addRow()">Adicionar item</button></td>
							</tr>
						</tfoot>
					</table>
				</div>

				<div class="grid" style="margin-top:16px">
					<div class="group">
						<div class="label">Moeda e ajustes</div>
						<select id="currency" class="select">
							<option value="R$" selected>R$ (BRL)</option>
							<option value="$">$ (USD)</option>
							<option value="€">€ (EUR)</option>
						</select>
						<div style="display:flex; gap:8px; margin-top:8px">
							<input id="discount_percent" class="input" type="number" placeholder="Desconto % (ex.: 5)" min="0" step="0.1" />
							<input id="tax_percent" class="input" type="number" placeholder="Imposto % (ex.: 8)" min="0" step="0.1" />
						</div>
					</div>
					<div class="group">
						<div class="label">Observações</div>
						<textarea id="notes" class="textarea" rows="5" placeholder="Termos, prazos e observações"></textarea>
					</div>
				</div>

				<div style="margin-top:16px; display:flex; gap:8px">
					<button id="btnGenerate" class="btn">Gerar PDF</button>
					<a id="downloadPdf" class="btn" style="display:none;" download>Baixar PDF</a>
				</div>
				<footer>Endpoint: <code>POST /api/budget/pdf</code></footer>
			</div>
		</div>

		<script>
			const tbody = document.querySelector('#itemsTable tbody');
			const addItemBtn = document.getElementById('addItem');
			const btnGenerate = document.getElementById('btnGenerate');
			const downloadPdf = document.getElementById('downloadPdf');

			function addRow(desc='', qty=1, price=0) {
				const tr = document.createElement('tr');
				tr.innerHTML = \`
					<td><input class="input" placeholder="Descrição" value="\${desc}"></td>
					<td><input class="input" type="number" min="1" step="1" value="\${qty}"></td>
					<td><input class="input" type="number" min="0" step="0.01" value="\${price}"></td>
					<td><button class="btn btn-del">Remover</button></td>
				\`;
				tr.querySelector('.btn-del').addEventListener('click', () => tr.remove());
				tbody.appendChild(tr);
			}

			// Permitir uso via onclick no botão (fallback em ambientes que bloqueiem addEventListener cedo)
			window.addRow = addRow;

			// Linha inicial garantida (sempre adiciona uma)
			addRow('Serviço', 1, 100);

			btnGenerate.addEventListener('click', async () => {
				const items = Array.from(tbody.querySelectorAll('tr')).map(tr => {
					const [descEl, qtyEl, priceEl] = tr.querySelectorAll('input');
					return {
						description: descEl.value.trim(),
						quantity: parseInt((qtyEl.value || '0').replace(',', '.')),
						unit_price: parseFloat((priceEl.value || '0').replace(',', '.'))
					};
				}).filter(it => it.description && it.quantity > 0);

				if (!items.length) { alert('Adicione pelo menos um item.'); return; }

				const payload = {
					company_name: document.getElementById('company_name').value,
					company_email: document.getElementById('company_email').value,
					client_name: document.getElementById('client_name').value,
					client_email: document.getElementById('client_email').value,
					currency: document.getElementById('currency').value,
					discount_percent: parseFloat((document.getElementById('discount_percent').value || '0').replace(',', '.')),
					tax_percent: parseFloat((document.getElementById('tax_percent').value || '0').replace(',', '.')),
					notes: document.getElementById('notes').value,
					items
				};

				const resp = await fetch('/api/budget/pdf', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify(payload)
				});
				if (!resp.ok) {
					let msg = 'Falha ao gerar PDF';
					try {
						const data = await resp.json();
						if (data && data.detail) msg += `: ${Array.isArray(data.detail) ? data.detail[0].msg || '' : data.detail}`;
					} catch (_) {
						try { msg += `: ${await resp.text()}`; } catch (__){}
					}
					alert(msg);
					return;
				}
				const blob = await resp.blob();
				const url = URL.createObjectURL(blob);
				downloadPdf.href = url;
				downloadPdf.download = 'orcamento.pdf';
				downloadPdf.style.display = 'inline-block';
				downloadPdf.click();
			});
		</script>
	</body>
	</html>
	"""
	return HTMLResponse(content=html)

