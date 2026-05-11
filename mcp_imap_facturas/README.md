# MCP IMAP Facturas

Servidor MCP (Model Context Protocol) de solo lectura sobre un buzón IMAP.
Permite a un agente auditar facturas enviadas, detectar clientes pendientes
de facturar y comparar períodos de facturación.

---

## Instalación de dependencias

```bash
# Desde la raíz del proyecto
pip install imap-tools>=1.5.0

# O instalar solo las dependencias de este módulo
pip install -r mcp_imap_facturas/requirements.txt
```

---

## Configuración del `.env`

Copia el archivo de ejemplo y completa tus credenciales:

```bash
cp mcp_imap_facturas/.env.example .env
```

Edita `.env` con los valores reales:

```env
IMAP_SERVER=mail.webpossa.com
IMAP_PORT=993
IMAP_USER=webpos_inbox@webpossa.com
IMAP_PASSWORD=tu_password_aqui
IMAP_USE_SSL=true
```

> El archivo `.env` ya está en `.gitignore`. **Nunca lo subas a git.**

---

## Validar la conexión antes de usar el MCP

Ejecuta el script de prueba para confirmar credenciales y descubrir el nombre
exacto de la carpeta Enviados en tu servidor:

```bash
python -m mcp_imap_facturas.test_connection
```

Salida esperada:

```
=== Test de conexión IMAP ===

[OK] Credenciales encontradas para webpos_inbox@webpossa.com en mail.webpossa.com:993
Conectando a mail.webpossa.com:993 ...
[OK] Conexión y autenticación exitosas.

Carpetas disponibles (8):
  · INBOX
  · Sent
  · Drafts
  · Trash
  ...

--- Últimos 5 emails en INBOX ---
  [412] 2026-04-30 ...
  ...

--- Últimos 5 emails en 'Sent' ---
  [98] 2026-04-29  Para: cliente@empresa.com  Asunto: Factura Abril 2026
  ...
```

Anota el nombre exacto de la carpeta Enviados (puede ser `Sent`, `Enviados`,
`INBOX.Sent`, `[Gmail]/Sent Mail`, etc.) para usarlo en las tools.

---

## Herramientas disponibles

| Tool | Descripción |
|---|---|
| `list_folders` | Lista todas las carpetas del buzón |
| `search_emails` | Busca emails con filtros (fecha, remitente, asunto, adjuntos) |
| `get_email_detail` | Cuerpo + metadata de adjuntos de un email por UID |
| `list_recipients_in_period` | Destinatarios únicos en un período, con conteo |
| `compare_periods` | Diferencia de destinatarios entre dos períodos |

---

## Agregar a Claude Desktop

Edita `~/AppData/Roaming/Claude/claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "imap-facturas": {
      "command": "python",
      "args": ["-m", "mcp_imap_facturas.server"],
      "cwd": "C:/Proyectos/rag_ollama_api",
      "env": {
        "IMAP_SERVER": "mail.webpossa.com",
        "IMAP_PORT": "993",
        "IMAP_USER": "webpos_inbox@webpossa.com",
        "IMAP_PASSWORD": "tu_password_aqui",
        "IMAP_USE_SSL": "true"
      }
    }
  }
}
```

> Alternativa: poner las variables en `.env` en la raíz del proyecto y omitir
> el bloque `"env"` (el servidor carga `.env` automáticamente con python-dotenv).

---

## Ejemplos de prompts para el agente

### Descubrir el nombre de la carpeta Enviados

```
Usa list_folders para mostrarme todas las carpetas de mi buzón.
```

### Listar a quién facturé este mes

```
Usa list_recipients_in_period con folder="Sent", since_date="2026-05-01",
before_date="2026-06-01" y subject_contains="factura". Muéstrame la lista
ordenada por cantidad de emails enviados.
```

### Detectar clientes pendientes del mes actual

```
Compara los destinatarios de mis facturas entre el mes pasado (abril 2026)
y este mes (mayo 2026) usando la carpeta Sent y filtrando por subject="factura".
Dime quiénes están en only_in_a (facturados en abril pero no en mayo todavía).
```

### Ver el detalle de una factura específica

```
Busca emails en Sent desde 2026-05-01 hasta hoy con subject_contains="factura"
y to_address="cliente@empresa.com". Luego muéstrame el detalle del primero
usando get_email_detail.
```

### Auditoría completa de clientes recurrentes

```
Necesito saber si tengo clientes recurrentes que facturé los últimos 3 meses
pero que aún no tienen factura de mayo. Usa compare_periods comparando
2026-02-01–2026-05-01 vs 2026-05-01–2026-06-01 en la carpeta Sent.
```

---

## Arquitectura

```
mcp_imap_facturas/
├── __init__.py         # Paquete Python
├── imap_client.py      # Conexión IMAP persistente + funciones de consulta
├── server.py           # Servidor MCP (tools + entrada stdio)
├── client.py           # Cliente Python para usar desde agentes FastAPI
├── test_connection.py  # Script de validación de credenciales
├── requirements.txt    # Dependencias del módulo
├── .env.example        # Plantilla de variables de entorno
└── README.md           # Esta documentación
```

### Diseño clave

- **Solo lectura**: el servidor nunca borra, mueve ni marca emails.
- **Conexión lazy + reconnect**: se conecta al primer uso; hace NOOP antes de
  cada operación y reconecta si la sesión cayó.
- **Thread-safe**: todas las operaciones IMAP corren en un executor con lock.
- **Logging a stderr**: stdout queda libre para el protocolo MCP.
- **Normalización de emails**: siempre minúsculas + trim para comparaciones.
