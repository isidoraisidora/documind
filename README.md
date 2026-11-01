# DocuMind

A Retrieval-Augmented Generation (RAG) application. Upload PDF or TXT documents, ask questions about them, and get answers grounded in the documents, with the source passages (file and page) shown next to each answer.

The project is also an exercise in shipping a small multi-service application end to end: it is containerized with Docker, runs locally with Docker Compose, is tested and published by GitHub Actions, and deploys to Kubernetes.

## How it works

```mermaid
flowchart LR
    U[Browser] --> N[nginx frontend]
    N -->|/api/*| A[FastAPI backend]
    A --> D[(PostgreSQL + pgvector)]
    A --> G[Groq LLM API]
```

**Ingestion** (`POST /documents`)
1. The file is read and text is extracted per page (PDF via `pypdf`, or plain text).
2. Each page is split into overlapping chunks of about 500 characters.
3. Each chunk is converted into a 384-dimensional embedding with a local model (`BAAI/bge-small-en-v1.5` via `fastembed`).
4. Chunks and embeddings are stored in PostgreSQL using the `pgvector` extension. Re-uploading a file with the same name replaces its old chunks.

**Question answering** (`POST /query`)
1. The question is embedded with the same model.
2. The 4 most similar chunks are retrieved with a cosine-distance search (`ORDER BY embedding <=> query`).
3. The chunks and the question are sent to an LLM on Groq, which is instructed to answer only from the provided context and to cite sources like `[1]`.
4. The API returns the answer together with the source chunks.

## Tech stack

| Area | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn |
| Vector store | PostgreSQL 16 with pgvector |
| Embeddings | fastembed (`BAAI/bge-small-en-v1.5`, runs locally) |
| LLM | Groq API (default model `openai/gpt-oss-20b`) |
| Frontend | Static HTML with Bootstrap 5, served by nginx |
| Containers | Docker, Docker Compose |
| CI/CD | GitHub Actions, GitHub Container Registry (GHCR) |
| Orchestration | Kubernetes (Deployments, StatefulSet, Services, Ingress, ConfigMap, Secret, PersistentVolumeClaim) |
| Tests | pytest |

## Project structure

```
documind/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app and endpoints
│   │   ├── config.py        # settings from environment variables
│   │   ├── db.py            # database connection and schema setup
│   │   └── rag.py           # text extraction, chunking, embeddings, LLM call
│   ├── tests/
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── Dockerfile
├── frontend/
│   ├── index.html
│   ├── nginx.conf           # serves the page and proxies /api/ to the backend
│   └── Dockerfile
├── k8s/                     # Kubernetes manifests
├── .github/workflows/       # CI/CD pipeline
├── docker-compose.yml
├── kind-config.yaml         # local Kubernetes cluster (kind)
└── .env.example
```

## Configuration

Secrets and settings are read from environment variables. Copy the example file and fill it in:

```bash
cp .env.example .env
```

| Variable | Purpose | Default |
|---|---|---|
| `GROQ_API_KEY` | Groq API key (required for answering questions) | none |
| `POSTGRES_PASSWORD` | Database password (used by Docker Compose) | none |
| `LLM_MODEL` | Groq model used for answers | `openai/gpt-oss-20b` |
| `TOP_K` | Number of chunks retrieved per question | `4` |
| `DATABASE_URL` | PostgreSQL connection string | local dev database |

`.env` is git-ignored and must never be committed. Groq changes its model list from time to time. If you get a `model_not_found` error, list the models your key can use and set `LLM_MODEL` to one of them.

## Run with Docker Compose

Prerequisites: Docker Desktop and a Groq API key.

```bash
docker compose up --build
```

Open **http://localhost:8080**. The first build takes a few minutes because the embedding model is downloaded into the backend image.

```bash
docker compose logs api      # backend logs
docker compose down          # stop; the database volume is kept
docker compose down -v       # stop and delete the database volume
```

The Compose setup starts three containers: `db` (pgvector/PostgreSQL with a named volume and a healthcheck), `api` (waits until the database is healthy), and `frontend` (nginx). The API is not published to the host. nginx reaches it over the internal network and forwards `/api/` to it.

## Run locally without Docker

Useful for development. You need Python 3.12 and a PostgreSQL instance with pgvector.

```bash
# database (published on 5433 to avoid clashing with a local PostgreSQL on 5432)
docker run -d --name pgvector-dev -p 5433:5432 -e POSTGRES_PASSWORD=postgres pgvector/pgvector:pg16

cd backend
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1   macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --port 8000
```

Interactive API docs are at http://127.0.0.1:8000/docs. The frontend expects to be served by nginx (it calls `/api/...`), so use Docker Compose to try the full UI.

## Run on Kubernetes (kind)

The manifests in `k8s/` run the whole stack in a local [kind](https://kind.sigs.k8s.io/) cluster.

Prerequisites: Docker, `kind` and `kubectl`.

```bash
# 1. create the cluster (maps the cluster's port 80 to localhost:8081)
kind create cluster --name documind --config kind-config.yaml

# 2. install the ingress controller
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl wait --namespace ingress-nginx --for=condition=ready pod --selector=app.kubernetes.io/component=controller --timeout=180s

# 3. build the images and load them into the cluster
docker build -t documind-api:local backend
docker build -t documind-frontend:local frontend
kind load docker-image documind-api:local documind-frontend:local --name documind

# 4. create the namespace and the secret (never commit real values)
kubectl apply -f k8s/namespace.yaml
kubectl create secret generic documind-secrets -n documind \
  --from-literal=POSTGRES_PASSWORD=postgres \
  --from-literal=DATABASE_URL=postgresql://postgres:postgres@postgres:5432/postgres \
  --from-literal=GROQ_API_KEY=your-groq-key

# 5. deploy everything
kubectl apply -f k8s/
kubectl get pods -n documind -w
```

When the `api`, `frontend` and `postgres-0` pods show `1/1 Running`, open **http://documind.localhost:8081**. If that name does not resolve in your browser, use a port-forward instead:

```bash
kubectl port-forward svc/frontend 8082:80 -n documind
# then open http://localhost:8082
```

What the manifests contain:

| File | Resource |
|---|---|
| `namespace.yaml` | `documind` namespace |
| `config.yaml` | ConfigMap with non-secret settings (`TOP_K`, `LLM_MODEL`) |
| `postgres.yaml` | Headless Service and StatefulSet with a 1Gi PersistentVolumeClaim |
| `api.yaml` | Deployment (resource limits, liveness and readiness probes on `/health`) and Service |
| `frontend.yaml` | Deployment and Service |
| `ingress.yaml` | Ingress routing `documind.localhost` to the frontend |

Notes:
- kind keeps its own image store. After rebuilding an image, run `kind load docker-image ...` again and then `kubectl rollout restart deployment/<name> -n documind`.
- If a pod shows `ImagePullBackOff`, the image was not loaded into the cluster or its name does not match the manifest.
- If cluster creation fails on a very new Kubernetes node image, try an older one: `kind create cluster --name documind --config kind-config.yaml --image kindest/node:<older-version>`.
- To remove everything: `kubectl delete namespace documind`, or `kind delete cluster --name documind`.

## CI/CD

The GitHub Actions workflow in `.github/workflows/` runs on every push and pull request to `main`:

1. **test:** installs the backend dependencies and runs the pytest suite. The embedding model and the LLM call are mocked, so the tests need no network access or API key.
2. **docker:** builds the backend and frontend images with Docker Buildx (with layer caching). On pushes to `main`, it publishes them to GitHub Container Registry as `ghcr.io/<owner>/<repo>-api` and `ghcr.io/<owner>/<repo>-frontend`, tagged `latest` and with the commit SHA. On pull requests it only builds, to verify the Dockerfiles.

No extra secrets are needed. Registry login uses the automatically provided `GITHUB_TOKEN`.

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest
```

The tests cover chunking, the `/health` endpoint, and the `/query` flow with the database, embeddings and LLM mocked.

## API

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check (used by Kubernetes probes) |
| POST | `/documents` | Upload a PDF or TXT file (multipart form field `file`) |
| GET | `/documents` | List indexed documents and their chunk counts |
| POST | `/query` | Ask a question: body `{"question": "..."}` returns `answer` and `sources` |

Through nginx (Compose or Kubernetes), the same endpoints are available under the `/api/` prefix.

## Limitations

This is a learning project, so some things are deliberately simple:

- Chunking is by character count, so chunks can end mid-word. There is no semantic or sentence-aware splitting.
- Retrieval is plain vector similarity, with no re-ranking, hybrid search or relevance threshold, so a question can still be answered from loosely related chunks.
- There is no authentication, and all uploaded documents are shared by everyone who can reach the app.
- Documents cannot be deleted through the API. Uploading a file with the same name replaces it.
- PDFs must contain extractable text. Scanned PDFs without OCR are not supported.
- The database runs as a single instance with no backups.
- Answer quality depends on the chosen Groq model, and the free tier is rate limited.