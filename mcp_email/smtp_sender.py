"""
SMTP Email Sender

Wrapper simplificado para envío de emails mediante SMTP.
Soporta Gmail, Outlook, Yahoo y servidores SMTP personalizados.
"""

import smtplib
import asyncio
import socket
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class SMTPSender:
    """Cliente SMTP para envío de emails."""
    
    @staticmethod
    async def send_email(
        smtp_config: Dict[str, Any],
        to: str,
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        html: bool = False,
        attachments: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Envía un email mediante SMTP.
        
        Args:
            smtp_config: Configuración SMTP del agente
                {
                    "server": "smtp.gmail.com",
                    "port": 587,
                    "email": "tu_email@gmail.com",
                    "password": "tu_app_password",
                    "use_tls": True
                }
            to: Email del destinatario
            subject: Asunto del email
            body: Cuerpo del email
            cc: Lista de emails en copia (opcional)
            bcc: Lista de emails en copia oculta (opcional)
            html: Si True, el body se interpreta como HTML
            attachments: Lista de rutas de archivos a adjuntar (opcional)
            
        Returns:
            Dict con resultado: {"success": bool, "message": str, "error": str}
        """
        try:
            # Validar configuración SMTP
            required_keys = ["server", "port", "email", "password"]
            for key in required_keys:
                if key not in smtp_config:
                    return {
                        "success": False,
                        "error": f"Falta configuración SMTP: {key}"
                    }
            
            # Validar email destinatario
            if not to or '@' not in to:
                return {
                    "success": False,
                    "error": f"Email destinatario inválido: {to}"
                }
            
            # Crear mensaje
            msg = MIMEMultipart('mixed')
            msg['From'] = smtp_config['email']
            msg['To'] = to
            msg['Subject'] = subject
            
            if cc:
                msg['Cc'] = ', '.join(cc)
            
            # Agregar cuerpo del mensaje
            body_part = MIMEMultipart('alternative')
            if html:
                body_part.attach(MIMEText(body, 'html', 'utf-8'))
            else:
                body_part.attach(MIMEText(body, 'plain', 'utf-8'))
            
            msg.attach(body_part)
            
            # Agregar archivos adjuntos si existen
            if attachments:
                for filepath in attachments:
                    try:
                        path = Path(filepath)
                        if not path.exists():
                            logger.warning(f"Archivo no encontrado: {filepath}")
                            continue
                        
                        with open(path, 'rb') as f:
                            part = MIMEBase('application', 'octet-stream')
                            part.set_payload(f.read())
                        
                        encoders.encode_base64(part)
                        part.add_header(
                            'Content-Disposition',
                            f'attachment; filename= {path.name}'
                        )
                        msg.attach(part)
                    except Exception as e:
                        logger.error(f"Error adjuntando archivo {filepath}: {e}")
            
            # Preparar lista de destinatarios
            recipients = [to]
            if cc:
                recipients.extend(cc)
            if bcc:
                recipients.extend(bcc)
            
            # Ejecutar envío en thread separado para no bloquear asyncio
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                SMTPSender._send_sync,
                smtp_config,
                msg,
                recipients
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error enviando email: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    @staticmethod
    def _send_sync(
        smtp_config: Dict[str, Any],
        msg: MIMEMultipart,
        recipients: List[str]
    ) -> Dict[str, Any]:
        """
        Envío síncrono del email (ejecutado en thread separado).
        
        Args:
            smtp_config: Configuración SMTP
            msg: Mensaje MIME preparado
            recipients: Lista de destinatarios
            
        Returns:
            Dict con resultado
        """
        try:
            server = smtp_config['server']
            port = smtp_config['port']
            email = smtp_config['email']
            password = smtp_config['password']
            use_tls = smtp_config.get('use_tls', True)
            use_ssl = smtp_config.get('use_ssl', False)
            
            # Conectar al servidor SMTP
            if use_ssl:
                # Puerto 465 - SSL directo
                smtp = smtplib.SMTP_SSL(server, port, timeout=30)
            else:
                # Puerto 587 - TLS
                smtp = smtplib.SMTP(server, port, timeout=30)
                smtp.ehlo()
                if use_tls:
                    smtp.starttls()
                    smtp.ehlo()
            
            # Autenticar
            smtp.login(email, password)
            
            # Enviar mensaje
            smtp.send_message(msg)
            smtp.quit()
            
            logger.info(f"Email enviado exitosamente a {recipients}")
            
            return {
                "success": True,
                "message": f"Email enviado exitosamente a {', '.join(recipients)}",
                "recipients": recipients
            }
            
        except smtplib.SMTPAuthenticationError as e:
            error_msg = "Error de autenticación SMTP. Verifica email y password."
            logger.error(f"{error_msg}: {e}")
            return {
                "success": False,
                "error": error_msg,
                "details": str(e)
            }
        
        except smtplib.SMTPRecipientsRefused as e:
            error_msg = f"Destinatario(s) rechazado(s): {recipients}"
            logger.error(f"{error_msg}: {e}")
            return {
                "success": False,
                "error": error_msg,
                "details": str(e)
            }
        
        except smtplib.SMTPException as e:
            error_msg = f"Error SMTP: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
        
        except socket.timeout:
            error_msg = (
                f"Timeout de conexión con {server}:{port}. "
                f"Posibles causas:\n"
                f"1. Firewall bloqueando la conexión\n"
                f"2. Servidor SMTP incorrecto o inaccesible\n"
                f"3. Puerto bloqueado (prueba 587 para TLS o 465 para SSL)\n"
                f"4. Problemas de red o internet\n"
                f"Sugerencia: Verifica tu configuración y firewall."
            )
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "error_type": "timeout"
            }
        
        except OSError as e:
            # Manejo específico para errores de Windows (WinError 10060, etc.)
            if "10060" in str(e) or "10061" in str(e):
                error_msg = (
                    f"No se puede conectar al servidor SMTP {server}:{port}.\n"
                    f"Error de conexión: {str(e)}\n\n"
                    f"Soluciones:\n"
                    f"1. Verifica que el servidor y puerto sean correctos\n"
                    f"2. Desactiva temporalmente el firewall/antivirus\n"
                    f"3. Verifica tu conexión a internet\n"
                    f"4. Prueba con otro proveedor SMTP\n"
                    f"5. Si usas proxy/VPN, desactívalo temporalmente"
                )
            else:
                error_msg = f"Error de sistema operativo: {str(e)}"
            
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "error_type": "connection"
            }
        
        except Exception as e:
            error_msg = f"Error inesperado: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "error_type": "unknown"
            }


# Configuraciones SMTP predefinidas para proveedores comunes
SMTP_PROVIDERS = {
    "gmail": {
        "server": "smtp.gmail.com",
        "port": 587,
        "use_tls": True,
        "instructions": "Gmail requiere App Password. Ve a Google Account → Security → 2FA → App Passwords"
    },
    "outlook": {
        "server": "smtp-mail.outlook.com",
        "port": 587,
        "use_tls": True,
        "instructions": "Usa tu password normal de Outlook/Hotmail"
    },
    "yahoo": {
        "server": "smtp.mail.yahoo.com",
        "port": 587,
        "use_tls": True,
        "instructions": "Yahoo requiere App Password. Ve a Account Security → Generate App Password"
    },
    "office365": {
        "server": "smtp.office365.com",
        "port": 587,
        "use_tls": True,
        "instructions": "Usa tu password de Office 365"
    }
}


def get_provider_config(provider: str) -> Dict[str, Any]:
    """
    Obtiene la configuración predefinida de un proveedor SMTP.
    
    Args:
        provider: Nombre del proveedor (gmail, outlook, yahoo, office365)
        
    Returns:
        Configuración SMTP del proveedor
    """
    return SMTP_PROVIDERS.get(provider.lower(), {})
