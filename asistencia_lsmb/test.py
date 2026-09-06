import os
from pathlib import Path
from dotenv import load_dotenv

# BASE_DIR es la carpeta "asistencia_lsmb"
BASE_DIR = Path(__file__).resolve().parent

# Le decimos a Python: "El .env está un nivel más atrás de mi carpeta"
env_path = BASE_DIR.parent / '.env'

# Intentamos cargar el archivo
load_dotenv(env_path)

# A partir de aquí, las variables ya están listas para usarse, ya sea que
# las haya cargado load_dotenv (en local) o Docker (en el contenedor)
DB_NAME = os.getenv('POSTGRES_USER')

print("TEST: " + DB_NAME if not(DB_NAME is None) else "sin cargar")