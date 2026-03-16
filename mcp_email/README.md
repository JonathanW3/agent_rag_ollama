# MCP Email Module

Módulo de envío de emails mediante SMTP para el sistema de agentes.

## 🚀 Características

- ✅ Soporte para múltiples proveedores SMTP (Gmail, Outlook, Yahoo, Office365)
- ✅ Configuración por agente
- ✅ Envío asíncrono con asyncio
- ✅ Soporte para HTML
- ✅ CC, BCC y adjuntos
- ✅ Validación de emails
- ✅ Manejo robusto de errores
- ✅ Logging automático en SQLite

## 📁 Estructura

```
mcp_email/
├── __init__.py         # Exports del módulo
├── server.py           # Servidor MCP con tools
├── client.py           # Cliente para FastAPI
├── smtp_sender.py      # Lógica SMTP con smtplib
└── README.md          # Esta documentación
```

## 🔧 Uso Básico

### Desde Python

```python
from mcp_email.client import get_email_client

client = get_email_client()

# Configuración SMTP del agente
smtp_config = {
    "server": "smtp.gmail.com",
    "port": 587,
    "email": "bot@gmail.com",
    "password": "app_password",
    "use_tls": True
}

# Enviar email
result = await client.send_email(
    smtp_config=smtp_config,
    to="destinatario@example.com",
    subject="Test",
    body="Mensaje de prueba"
)

if result["success"]:
    print(f"✅ {result['message']}")
else:
    print(f"❌ {result['error']}")
```

### Desde API REST

```bash
# Enviar email
curl -X POST "http://localhost:8000/email/send" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "email-bot",
    "to": "usuario@example.com",
    "subject": "Asunto",
    "body": "Contenido del mensaje"
  }'
```

## ⚙️ Configuración por Proveedor

### Gmail
```python
{
    "server": "smtp.gmail.com",
    "port": 587,
    "email": "tu_email@gmail.com",
    "password": "app_password",  # Requiere App Password
    "use_tls": True
}
```

### Outlook
```python
{
    "server": "smtp-mail.outlook.com",
    "port": 587,
    "email": "tu_email@outlook.com",
    "password": "tu_password",
    "use_tls": True
}
```

### Yahoo
```python
{
    "server": "smtp.mail.yahoo.com",
    "port": 587,
    "email": "tu_email@yahoo.com",
    "password": "app_password",  # Requiere App Password
    "use_tls": True
}
```

## 🧪 Testing

```bash
# Ejecutar script de prueba
python test_email_mcp.py
```

## 📚 Documentación Completa

Ver [MCP_EMAIL_GUIDE.md](../MCP_EMAIL_GUIDE.md) para:
- Guía completa de configuración
- Casos de uso avanzados
- Integración con agentes
- Mejores prácticas de seguridad
- Troubleshooting

## 🔐 Seguridad

**IMPORTANTE:**
- Nunca uses tu password real de Gmail/Yahoo (usa App Passwords)
- No subas credenciales a repositorios
- Considera cifrar passwords si es crítico
- Implementa rate limiting para evitar spam

## ⚠️ Limitaciones

- Gmail: 500 emails/día (gratis), 2000/día (Workspace)
- Outlook: 300 emails/día
- Yahoo: 500 emails/día
- Adjuntos: Límite típico 25 MB

## 📝 Ejemplo Completo

```python
import asyncio
from mcp_email.client import get_email_client

async def main():
    client = get_email_client()
    
    # Configuración
    smtp_config = {
        "server": "smtp.gmail.com",
        "port": 587,
        "email": "bot@gmail.com",
        "password": "xxxx xxxx xxxx xxxx",
        "use_tls": True
    }
    
    # Enviar email simple
    result = await client.send_email(
        smtp_config=smtp_config,
        to="cliente@example.com",
        subject="Bienvenido",
        body="Gracias por registrarte!",
        html=False
    )
    
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

## 🤝 Integración con Agentes

Los agentes con `smtp_config` pueden enviar emails automáticamente:

```python
# Al crear agente
agent = create_agent(
    name="Email Bot",
    prompt="Eres un bot que envía emails...",
    smtp_config={...}
)

# El agente puede usar /email/send
# O detectar intención en /chat y enviar automáticamente
```

## 📊 Logs

Todos los emails enviados se registran en SQLite:
```sql
SELECT * FROM agent_logs WHERE action = 'email_sent';
```

## ✅ Checklist

- [ ] Proveedor SMTP elegido
- [ ] App Password generado (Gmail/Yahoo)
- [ ] smtp_config configurado en agente
- [ ] Email de prueba enviado
- [ ] Logs verificados

---

¿Preguntas? Consulta [MCP_EMAIL_GUIDE.md](../MCP_EMAIL_GUIDE.md)
