"""
Módulo de cifrado para datos sensibles (credenciales SMTP, etc.).

Usa Fernet (AES-128-CBC con HMAC-SHA256) para cifrado simétrico.
La clave se configura via la variable de entorno ENCRYPTION_KEY.

Si ENCRYPTION_KEY no está configurada, se genera una clave efímera
al iniciar la app (se pierde al reiniciar) y se imprime un warning.
"""

import base64
import hashlib
import json
import os

from cryptography.fernet import Fernet

from .config import settings

_fernet_instance: Fernet | None = None


def _get_fernet() -> Fernet:
    """Obtiene o inicializa la instancia de Fernet."""
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance

    key_source = settings.ENCRYPTION_KEY
    if not key_source:
        # Generar clave efímera - los datos cifrados se perderán al reiniciar
        key_source = Fernet.generate_key().decode()
        print(
            "WARNING: ENCRYPTION_KEY no configurada. Usando clave efímera. "
            "Las credenciales SMTP cifradas se perderán al reiniciar. "
            "Configura ENCRYPTION_KEY con: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    else:
        # Derivar una clave Fernet válida (32 bytes base64) desde cualquier string
        raw = hashlib.sha256(key_source.encode()).digest()
        key_source = base64.urlsafe_b64encode(raw).decode()

    _fernet_instance = Fernet(key_source.encode())
    return _fernet_instance


def encrypt_dict(data: dict) -> str:
    """Cifra un diccionario y retorna un string base64 seguro para almacenar."""
    f = _get_fernet()
    plaintext = json.dumps(data).encode("utf-8")
    return f.encrypt(plaintext).decode("utf-8")


def decrypt_dict(token: str) -> dict:
    """Descifra un string previamente cifrado con encrypt_dict."""
    f = _get_fernet()
    plaintext = f.decrypt(token.encode("utf-8"))
    return json.loads(plaintext.decode("utf-8"))
