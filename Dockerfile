FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias del sistema + Microsoft ODBC Driver 17 for SQL Server
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential curl gnupg2 apt-transport-https && \
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg && \
    curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 unixodbc-dev && \
    rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias primero (cache de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY app/ app/
COPY mcp_sqlite/ mcp_sqlite/
COPY mcp_email/ mcp_email/
COPY mcp_mysql/ mcp_mysql/
COPY mcp_mysql_ibm/ mcp_mysql_ibm/
COPY mcp_mysql_autopart/ mcp_mysql_autopart/
COPY mcp_google_calendar/ mcp_google_calendar/
COPY mcp_FE/ mcp_FE/
COPY mcp_sqlserver/ mcp_sqlserver/
COPY mcp_imap_facturas/ mcp_imap_facturas/
COPY data/ data/

# Crear directorios necesarios
RUN mkdir -p data/uploads data/chroma

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
