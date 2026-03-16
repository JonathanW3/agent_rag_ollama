FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias del sistema necesarias para compilar paquetes nativos
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias primero (cache de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY app/ app/
COPY mcp_sqlite/ mcp_sqlite/
COPY mcp_email/ mcp_email/
COPY mcp_mysql/ mcp_mysql/
COPY data/ data/

# Crear directorios necesarios
RUN mkdir -p data/uploads data/chroma

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
