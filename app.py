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

@app.get("/image", response_class=HTMLResponse)
def image_ui() -> HTMLResponse:
	# UI simples para upload e processamento de imagem, com preview e botão para baixar ZIP
	html = """
	<!doctype html>
	<html lang="pt-br">
	<head>
		<meta charset="utf-8" />
		<meta name="viewport" content="width=device-width, initial-scale=1" />
		<title>Processamento de Imagem</title>
		<style>
			:root { --bg:#0b1020; --card:#12172b; --border:#1c2747; --text:#E6E8EC; --muted:#C6C9D3; --accent:#7bd2ff; }
			html, body { margin:0; padding:0; background:var(--bg); color:var(--text); font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
			.container { max-width: 880px; margin: 0 auto; padding: 40px 20px; }
			.card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 24px; }
			h1 { margin: 0 0 12px; font-weight: 700; letter-spacing: .2px; }
			p { margin: 0 0 16px; color: var(--muted); }
			a { color: var(--accent); text-decoration: none; }
			a:hover { text-decoration: underline; }
			.row { display: grid; grid-template-columns: 1fr; gap: 16px; }
			@media (min-width: 860px) { .row { grid-template-columns: 1fr 1fr; } }
			.panel { background: rgba(255,255,255,0.02); border: 1px dashed var(--border); border-radius: 10px; padding: 16px; }
			.label { font-size: 14px; color: var(--muted); margin-bottom: 8px; display:block; }
			.input { display:block; width:100%; padding: 10px 12px; border-radius: 10px; border:1px solid var(--border); background:#0b1020; color:var(--text); }
			.btn { appearance: none; border: 1px solid var(--border); border-radius: 10px; background: #0f1630; color: var(--text); padding: 10px 14px; cursor: pointer; }
			.btn:hover { background: #101a3a; }
			.preview { display:flex; align-items:center; justify-content:center; min-height: 260px; border-radius: 8px; overflow:hidden; background:#0b1020; border:1px solid var(--border); }
			.preview img { max-width: 100%; max-height: 260px; object-fit: contain; display:block; }
			.status { font-size: 14px; color: var(--muted); margin-top: 8px; min-height: 20px; }
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
						<label class="label" for="file">Selecionar arquivo</label>
						<input id="file" type="file" accept="image/jpeg,image/png,image/webp" class="input" />
						<div style="margin-top: 12px; display:flex; gap:8px;">
							<button id="btnProcess" class="btn">Processar</button>
							<a id="downloadLink" class="btn" style="display:none;" download>Baixar ZIP</a>
						</div>
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
			const btn = document.getElementById('btnProcess');
			const statusEl = document.getElementById('status');
			const link = document.getElementById('downloadLink');
			const previewImg = document.getElementById('previewImg');

			input.addEventListener('change', () => {
				const f = input.files && input.files[0];
				if (f) {
					previewImg.src = URL.createObjectURL(f);
				} else {
					previewImg.removeAttribute('src');
				}
				link.style.display = 'none';
				statusEl.textContent = '';
			});

			btn.addEventListener('click', async () => {
				const f = input.files && input.files[0];
				if (!f) {
					statusEl.textContent = 'Selecione um arquivo primeiro.';
					return;
				}
				statusEl.textContent = 'Processando...';
				link.style.display = 'none';

				try {
					const fd = new FormData();
					fd.append('file', f, f.name);
					const resp = await fetch('/api/image/process', {
						method: 'POST',
						body: fd
					});
					if (!resp.ok) {
						const text = await resp.text();
						throw new Error(text || 'Falha no processamento');
					}
					const blob = await resp.blob();
					const url = URL.createObjectURL(blob);
					link.href = url;
					link.download = (f.name.split('.').slice(0, -1).join('.') || 'image') + '_processed.zip';
					link.style.display = 'inline-block';
					statusEl.textContent = 'Pronto! Clique em "Baixar ZIP".';
				} catch (e) {
					statusEl.textContent = 'Erro: ' + (e?.message || 'Falha inesperada');
				}
			});
		</script>
	</body>
	</html>
	"""
	return HTMLResponse(content=html)

