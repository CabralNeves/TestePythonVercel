# Vercel Python App (FastAPI)

Aplicação mínima em Python com FastAPI, pronta para deploy na Vercel.

## Requisitos

- Python 3.10+ (recomendado 3.11)
- Node.js (para CLI da Vercel)
- Git

## Setup local

1. Crie e ative um virtualenv:

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows PowerShell
# No Linux/Mac: source .venv/bin/activate
```

2. Instale as dependências:

```bash
pip install -r requirements.txt
```

3. Rode o servidor local:

```bash
uvicorn app:app --reload --port 8000
```

Abra `http://localhost:8000` no navegador.

## Estrutura

```
app.py          # App FastAPI (exporta a variável `app`)
requirements.txt
vercel.json     # Config para deploy
```

## Deploy na Vercel

1. Instale a CLI:

```bash
npm i -g vercel
```

2. Login:

```bash
vercel login
```

3. Deploy:

```bash
vercel
```

Aceite os padrões quando perguntado. Ao finalizar, a CLI mostra a URL do projeto.

## GitHub

Criar repositório e publicar:

```bash
git init
git add .
git commit -m "feat: criar app FastAPI mínimo para Vercel"
git branch -M main
git remote add origin https://github.com/<seu_usuario>/<seu_repositorio>.git
git push -u origin main
```

## Segurança

- Nunca commitar `.env` ou segredos.
- Use variáveis de ambiente (Defina na Vercel: Project Settings → Environment Variables).

## Rotas

- `GET /` — página HTML simples
- `GET /api/hello/{name}` — retorna JSON com saudação
- `POST /api/image/process` — upload de imagem (JPEG/PNG/WEBP) e retorno de ZIP com:
  - `thumb_256.webp` (ou png/jpeg): miniatura 256px
  - `medium_1024.webp` (ou png/jpeg): versão 1024px
  - `optimized.webp` (ou png/jpeg): versão otimizada mantendo dimensões originais
  - `metadata.json`: dimensões originais e EXIF extraído

### Exemplo de uso (cURL)

```bash
curl -X POST http://localhost:8000/api/image/process \
  -H "Content-Type: multipart/form-data" \
  -F "file=@caminho/para/sua_imagem.jpg" \
  --output processed.zip
```

Na Vercel, recomenda-se enviar arquivos até ~4.5MB por requisição (limite típico de Serverless Functions).


