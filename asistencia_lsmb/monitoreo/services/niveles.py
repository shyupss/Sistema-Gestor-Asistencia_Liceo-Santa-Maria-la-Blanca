# Reenvío: el código de los niveles de alerta vive en alertas/services/niveles.py
# (alertas no puede importar de monitoreo). Este módulo solo lo reexporta para
# que monitoreo y su test sigan importando desde aquí sin cambios.
from alertas.services.niveles import nivel_alerta, umbral_critico

__all__ = ["nivel_alerta", "umbral_critico"]
