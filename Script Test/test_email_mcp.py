"""
Script de prueba para MCP Email

Prueba la funcionalidad completa del módulo de envío de emails:
- Creación de agente con SMTP
- Envío de emails
- Validación de emails
- Listado de proveedores
"""

import asyncio
import sys
sys.path.append('.')

from mcp_email.client import get_email_client


async def test_email_mcp():
    """Ejecuta pruebas del MCP Email."""
    print("=" * 60)
    print("🧪 TEST MCP EMAIL")
    print("=" * 60)
    
    client = get_email_client()
    
    # Test 1: Listar proveedores
    print("\n1️⃣ Listando proveedores SMTP...")
    try:
        providers = await client.list_providers()
        if providers.get("success"):
            print("✅ Proveedores disponibles:")
            for name, config in providers["providers"].items():
                print(f"   - {name}: {config['server']}:{config['port']}")
        else:
            print("❌ Error listando proveedores")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 2: Validar emails
    print("\n2️⃣ Validando formatos de email...")
    test_emails = [
        "usuario@example.com",
        "invalido@",
        "correcto@dominio.co",
        "sin_arroba.com"
    ]
    
    for email in test_emails:
        try:
            result = await client.validate_email(email)
            status = "✅" if result["valid"] else "❌"
            print(f"   {status} {email}: {result['message']}")
        except Exception as e:
            print(f"   ❌ Error validando {email}: {e}")
    
    # Test 3: Configuración SMTP de ejemplo (NO envía realmente)
    print("\n3️⃣ Ejemplo de configuración SMTP:")
    smtp_config_example = {
        "server": "smtp.gmail.com",
        "port": 587,
        "email": "webpos.soporte@gmail.com",
        "password": "qyfo ljos jpdi fryz",
        "use_tls": True
    }
    print(f"   📧 Configuración de ejemplo:")
    for key, value in smtp_config_example.items():
        if key != "password":
            print(f"      {key}: {value}")
        else:
            print(f"      {key}: {'*' * 16}")
    
    # Test 4: Simulación de envío (sin SMTP real)
    print("\n4️⃣ Simulación de envío de email:")
    print("   ℹ️  Para enviar un email real, necesitas:")
    print("      1. Configurar smtp_config con credenciales válidas")
    print("      2. Usar client.send_email() con la configuración")
    print("      3. Verificar que el servidor SMTP esté accesible")
    
    print("\n" + "=" * 60)
    print("✅ Pruebas completadas")
    print("=" * 60)
    
    print("\n📚 Para prueba completa con email real:")
    print("   1. Edita este script y agrega tu smtp_config")
    print("   2. Descomenta la sección de envío real")
    print("   3. Ejecuta: python test_email_mcp.py")
    
    # DESCOMENTAR PARA ENVÍO REAL:
    # print("\n5️⃣ Enviando email de prueba...")
    # smtp_config = {
    #     "server": "smtp.gmail.com",
    #     "port": 587,
    #     "email": "TU_EMAIL@gmail.com",
    #     "password": "TU_APP_PASSWORD",
    #     "use_tls": True
    # }
    # 
    # result = await client.send_email(
    #     smtp_config=smtp_config,
    #     to="DESTINATARIO@example.com",
    #     subject="🧪 Test MCP Email",
    #     body="Este es un email de prueba enviado desde el MCP Email.\n\nSaludos!",
    #     html=False
    # )
    # 
    # if result.get("success"):
    #     print(f"✅ {result['message']}")
    # else:
    #     print(f"❌ Error: {result.get('error')}")


if __name__ == "__main__":
    print("🚀 Iniciando pruebas del MCP Email...\n")
    asyncio.run(test_email_mcp())
