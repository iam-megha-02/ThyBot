FROM python:3.11-slim

WORKDIR /app

# System deps: psycopg2-binary ships prebuilt wheels for linux, but
# libpq itself still needs to be present at runtime for it to load.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Installed before the general requirements so sentence-transformers'
# unpinned `torch>=1.11.0` constraint is already satisfied by this CPU
# build — otherwise pip resolves the default CUDA build on Linux,
# pulling several GB of unused NVIDIA toolkit packages (cuBLAS, cuDNN,
# triton, ...) into a container with no GPU that will ever use them.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bake the clinical knowledge base into the image at build time rather
# than requiring a manual post-deploy step — data/clinical_index/ is
# gitignored (it's a reproducible build artifact, not source), so
# without this the container would start with an empty knowledge base
# until someone remembered to run the ingestion script by hand.
RUN python -m scripts.build_knowledge_base

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
