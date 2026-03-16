# MCP Email - Guía Completa

## 📧 Integración de Email con SMTP

Sistema de envío de emails mediante SMTP integrado con el protocolo MCP (Model Context Protocol). Permite que cualquier agente envíe emails usando proveedores SMTP como Gmail, Outlook, Yahoo o servidores personalizados.

---

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────┐
│            FastAPI Application                  │
│                                                 │
│  ┌──────────┐     ┌──────────┐    ┌─────────┐ │
│  │ /chat    │     │ /email/  │    │ /agents │ │
│  │ endpoint │     │ send     │    │         │ │
│  └────┬─────┘     └────┬─────┘    └────┬────┘ │
│       │                │               │       │
│       └────────┬───────┴───────────────┘       │
│                │                               │
│         ┌──────▼───────┐                       │
│         │  Email MCP   │                       │
│         │  Client      │                       │
│         └──────┬───────┘                       │
│                │                               │
└────────────────┼───────────────────────────────┘
                 │
         ┌───────▼────────┐
         │  Email MCP     │
         │  Server        │
         └───────┬────────┘
                 │
         ┌───────▼────────┐
         │  SMTP Sender   │
         │  (smtplib)     │
         └───────┬────────┘
                 │
     ┌───────────┴───────────┐
     │                       │
┌────▼─────┐         ┌──────▼──────┐
│  Gmail   │         │  Outlook    │
│  SMTP    │   ...   │  Yahoo      │
└──────────┘         └─────────────┘
```

---

## 🚀 Inicio Rápido

### 1. Crear agente con capacidad de email

```bash
curl -X POST "http://localhost:8000/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Asistente de Email",
    "agent_id": "email-bot",
    "prompt": "Eres un asistente que ayuda a redactar y enviar emails profesionales.",
    "description": "Bot especializado en comunicaciones por email",
    "smtp_config": {
      "server": "smtp.gmail.com",
      "port": 587,
      "email": "tu_bot@gmail.com",
      "password": "tu_app_password_aqui",
      "use_tls": true
    }
  }'
```

### 2. Enviar un email

```bash
curl -X POST "http://localhost:8000/email/send" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "email-bot",
    "to": "destinatario@example.com",
    "subject": "Prueba de Email",
    "body": "Hola! Este es un email de prueba enviado desde el agente.",
    "cc": [],
    "html": false
  }'
```

---

## ⚙️ Configuración por Proveedor

### Gmail

**Requisitos:**
1. Activar autenticación de dos factores (2FA)
2. Generar App Password: https://myaccount.google.com/apppasswords

```json
{
  "smtp_config": {
    "server": "smtp.gmail.com",
    "port": 587,
    "email": "tu_email@gmail.com",
    "password": "xxxx xxxx xxxx xxxx",  // App Password de 16 dígitos
    "use_tls": true
  }
}
```

### Outlook / Hotmail

```json
{
  "smtp_config": {
    "server": "smtp-mail.outlook.com",
    "port": 587,
    "email": "tu_email@outlook.com",
    "password": "tu_password_normal",
    "use_tls": true
  }
}
```

### Yahoo

**Requisitos:**
1. Generar App Password: https://login.yahoo.com/account/security

```json
{
  "smtp_config": {
    "server": "smtp.mail.yahoo.com",
    "port": 587,
    "email": "tu_email@yahoo.com",
    "password": "app_password_aqui",
    "use_tls": true
  }
}
```

### Office 365

```json
{
  "smtp_config": {
    "server": "smtp.office365.com",
    "port": 587,
    "email": "tu_email@empresa.com",
    "password": "tu_password",
    "use_tls": true
  }
}
```

### Servidor SMTP Personalizado

```json
{
  "smtp_config": {
    "server": "mail.tuempresa.com",
    "port": 465,  // Puerto SSL
    "email": "bot@tuempresa.com",
    "password": "password_seguro",
    "use_ssl": true,  // Para puerto 465
    "use_tls": false
  }
}
```

---

## 📝 Endpoints Disponibles

### POST `/email/send`
Envía un email usando la configuración SMTP de un agente.

**Request:**
```json
{
  "agent_id": "email-bot",
  "to": "destinatario@example.com",
  "subject": "Asunto del email",
  "body": "Contenido del mensaje",
  "cc": ["copia@example.com"],  // Opcional
  "bcc": ["oculta@example.com"],  // Opcional
  "html": false,  // true para HTML
  "attachments": []  // Rutas de archivos opcional
}
```

**Response:**
```json
{
  "status": "ok",
  "message": "Email enviado exitosamente a destinatario@example.com",
  "agent_id": "email-bot",
  "recipients": ["destinatario@example.com"]
}
```

### GET `/email/providers`
Lista proveedores SMTP predefinidos con sus configuraciones.

**Response:**
```json
{
  "success": true,
  "providers": {
    "gmail": {
      "server": "smtp.gmail.com",
      "port": 587,
      "use_tls": true,
      "instructions": "Gmail requiere App Password..."
    },
    "outlook": { ... },
    "yahoo": { ... },
    "office365": { ... }
  }
}
```

### POST `/email/validate`
Valida el formato de un email.

**Query Parameter:** `email=usuario@example.com`

**Response:**
```json
{
  "success": true,
  "email": "usuario@example.com",
  "valid": true,
  "message": "Email válido"
}
```

---

## 🤖 Uso con Agentes

### Crear agente especializado en emails

```python
# Ejemplo con Python requests
import requests

agent_data = {
    "name": "Asistente de Marketing",
    "agent_id": "marketing-bot",
    "prompt": """Eres un asistente de marketing experto en redacción de emails.
    Cuando el usuario pida enviar un email:
    1. Pregunta destinatario si no lo especificó
    2. Redacta un email profesional y persuasivo
    3. Muestra el borrador antes de enviar
    
    Mantén un tono profesional pero cercano.""",
    "description": "Bot para campañas de email marketing",
    "smtp_config": {
        "server": "smtp.gmail.com",
        "port": 587,
        "email": "marketing@empresa.com",
        "password": "app_password_aqui",
        "use_tls": True
    }
}

response = requests.post(
    "http://localhost:8000/agents",
    json=agent_data
)
print(response.json())
```

### Actualizar configuración SMTP de un agente

```bash
curl -X PUT "http://localhost:8000/agents/email-bot" \
  -H "Content-Type: application/json" \
  -d '{
    "smtp_config": {
      "server": "smtp.gmail.com",
      "port": 587,
      "email": "nuevo_email@gmail.com",
      "password": "nuevo_app_password",
      "use_tls": true
    }
  }'
```

---

## 🔐 Seguridad

### Mejores Prácticas

1. **Nunca uses tu password real de Gmail**: Usa App Passwords
2. **No subas credenciales a Git**: Usa variables de entorno
3. **Cifra passwords en Redis**: Implementa cifrado si es crítico
4. **Limita rate limits**: Implementa contadores diarios
5. **Valida destinatarios**: Verifica formatos antes de enviar

### Cifrado de Passwords (Opcional)

```python
# Ejemplo de cifrado con cryptography
from cryptography.fernet import Fernet
import os

# Generar clave (hacer solo una vez, guardar en .env)
key = Fernet.generate_key()
cipher = Fernet(key)

# Al guardar agente
encrypted_password = cipher.encrypt(password.encode()).decode()

# Al usar
password = cipher.decrypt(encrypted_password.encode()).decode()
```

---

## 📊 Logs y Monitoreo

Cada email enviado se registra automáticamente en SQLite (si MCP está habilitado):

```sql
SELECT * FROM agent_logs 
WHERE action = 'email_sent' 
ORDER BY timestamp DESC;
```

**Datos registrados:**
- Timestamp del envío
- Destinatario(s)
- Asunto
- CC/BCC
- Éxito/Error

---

## 🎯 Casos de Uso

### 1. Notificaciones Automáticas

```python
# Agente que envía notificaciones cuando ocurre un evento
{
  "agent_id": "notifier",
  "to": "admin@empresa.com",
  "subject": "🚨 Alerta: Sistema detectó anomalía",
  "body": "Se detectó un pico de tráfico inusual a las 14:30."
}
```

### 2. Respuestas Automáticas

```python
# Bot de soporte que envía confirmaciones
{
  "agent_id": "support-bot",
  "to": "cliente@example.com",
  "subject": "Ticket #12345 recibido",
  "body": "Hemos recibido tu solicitud. Te responderemos en 24h.",
  "html": true  # Para email con formato
}
```

### 3. Campañas de Marketing

```python
# Bot que envía newsletters
for cliente in clientes:
    enviar_email(
        agent_id="marketing-bot",
        to=cliente.email,
        subject=f"Hola {cliente.nombre}, tenemos una oferta especial",
        body=generar_contenido_personalizado(cliente),
        html=True
    )
```

---

## ⚠️ Limitaciones y Consideraciones

### Rate Limits por Proveedor

| Proveedor | Límite Diario | Límite por Hora |
|-----------|---------------|-----------------|
| Gmail (gratis) | 500 emails | ~20-50 |
| Gmail Workspace | 2000 emails | ~100 |
| Outlook | 300 emails | ~30 |
| Yahoo | 500 emails | ~50 |

### Tamaño de Adjuntos

- **Límite típico**: 25 MB por email
- **Recomendado**: < 10 MB para mejor deliverability

### Errores Comunes

**Error de autenticación:**
```
Error de autenticación SMTP. Verifica email y password.
```
- Solución: Revisa que uses App Password (no password normal)

**Destinatario rechazado:**
```
Destinatario(s) rechazado(s): [email]
```
- Solución: Verifica formato del email y que existe

**Timeout de conexión:**
```
Error SMTP: Connection timed out
```
- Solución: Verifica firewall y puerto correcto (587 vs 465)

---

## 🧪 Testing

### Test Script Completo

```python
import requests
import time

API_URL = "http://localhost:8000"

# 1. Crear agente de prueba
print("1. Creando agente...")
agent = requests.post(f"{API_URL}/agents", json={
    "name": "Test Email Bot",
    "agent_id": "test-email-bot",
    "prompt": "Eres un bot de prueba.",
    "smtp_config": {
        "server": "smtp.gmail.com",
        "port": 587,
        "email": "tu_email@gmail.com",
        "password": "tu_app_password",
        "use_tls": True
    }
}).json()
print(f"✅ Agente creado: {agent['id']}")

# 2. Validar email
print("\n2. Validando email...")
validation = requests.post(
    f"{API_URL}/email/validate?email=test@example.com"
).json()
print(f"✅ Email válido: {validation['valid']}")

# 3. Enviar email de prueba
print("\n3. Enviando email...")
email_result = requests.post(f"{API_URL}/email/send", json={
    "agent_id": "test-email-bot",
    "to": "tu_email_personal@gmail.com",
    "subject": "🧪 Email de Prueba",
    "body": "Este es un email de prueba del sistema MCP Email.",
    "html": False
}).json()
print(f"✅ Email enviado: {email_result['message']}")

# 4. Ver logs
time.sleep(2)
print("\n4. Verificando logs...")
stats = requests.get(
    f"{API_URL}/mcp/agents/test-email-bot/stats"
).json()
print(f"✅ Emails enviados: {stats['statistics']['logs_by_action']}")

print("\n✅ Todas las pruebas completadas!")
```

---

## 📚 Ejemplos Avanzados

### Email con HTML

```python
html_body = """
<html>
  <body>
    <h1 style="color: #4CAF50;">¡Bienvenido!</h1>
    <p>Gracias por registrarte en nuestro servicio.</p>
    <a href="https://example.com" style="background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none;">
      Comenzar
    </a>
  </body>
</html>
"""

requests.post(f"{API_URL}/email/send", json={
    "agent_id": "marketing-bot",
    "to": "cliente@example.com",
    "subject": "Bienvenido a nuestro servicio",
    "body": html_body,
    "html": True
})
```

### Email con CC y BCC

```python
requests.post(f"{API_URL}/email/send", json={
    "agent_id": "support-bot",
    "to": "cliente@example.com",
    "subject": "Respuesta a tu consulta",
    "body": "Aquí está la información solicitada...",
    "cc": ["supervisor@empresa.com"],
    "bcc": ["logs@empresa.com"]  # Para auditoría
})
```

---

## 🔄 Integración con Chat

Los agentes pueden detectar automáticamente cuándo enviar emails basándose en el contexto de la conversación.

Ejemplo de prompt para agente:

```
Eres un asistente con capacidad de enviar emails.

Cuando el usuario diga frases como:
- "Envía un email a..."
- "Manda un correo a..."
- "Notifica a X por email..."

Debes:
1. Confirmar el destinatario
2. Redactar el email
3. Mostrar un preview al usuario
4. Pedir confirmación antes de enviar

Formato de respuesta para enviar:
SEND_EMAIL:
TO: email@example.com
SUBJECT: asunto aquí
BODY: contenido del mensaje
```

---

## 📞 Soporte

Para problemas o preguntas:
- Revisa los logs en SQLite
- Verifica configuración SMTP
- Consulta documentación del proveedor
- Prueba con un cliente de email externo primero

---

## ✅ Checklist de Configuración

- [ ] Proveedor SMTP elegido (Gmail, Outlook, etc.)
- [ ] App Password generado (si aplica)
- [ ] Agente creado con smtp_config
- [ ] Email de prueba enviado exitosamente
- [ ] Logs verificados en SQLite
- [ ] Rate limits considerados
- [ ] Seguridad evaluada (cifrado opcional)

---

**¡Listo!** Ahora tus agentes pueden enviar emails de forma automática 📧🤖
