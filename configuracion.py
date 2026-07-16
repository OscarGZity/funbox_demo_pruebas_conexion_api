"""
Datos de acceso a la instancia de Odoo 19.

Se mantienen en un archivo aparte para que los ejemplos no repitan credenciales
y para poder cambiar de servidor (pruebas / produccion) tocando un solo lugar.

Los valores se leen del archivo '.env' que debe estar junto a este archivo, y
que no se sube al repositorio porque contiene la API Key real. Para crearlo:

    cp .env.example .env

Los valores escritos abajo son solo respaldos, para que los ejemplos corran
contra un Odoo local sin configurar nada.
"""

import os

from dotenv import load_dotenv

# Python no lee el archivo '.env' por su cuenta: sin esta llamada, las variables
# de abajo se quedarian siempre con su valor de respaldo.
# load_dotenv() no pisa las variables que ya existan en el sistema, asi un
# servidor puede imponer sus propios valores sin tener que borrar el '.env'.
load_dotenv()

# URL del servidor, sin diagonal final. Puede ser http o https.
URL = os.environ.get("ODOO_URL", "http://localhost:8069")

# Nombre de la base de datos. En Odoo un mismo servidor puede tener varias.
BASE_DATOS = os.environ.get("ODOO_BASE_DATOS", "odoo19")

# API Key para el endpoint JSON-2 de Odoo 19 (/json/2/...). Ese endpoint NO
# acepta usuario y contraseña: solo autentica con el esquema Bearer usando una
# clave generada en Ajustes > Usuarios > (usuario) > Claves API.
# La clave hereda los permisos del usuario que la genero.
CLAVE_API = os.environ.get("ODOO_CLAVE_API", "coloca_aqui_tu_api_key")
