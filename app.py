from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

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


