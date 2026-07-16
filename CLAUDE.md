# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Proposito del proyecto

Coleccion de ejemplos didacticos del API externa de Odoo 19, dirigidos a
desarrolladores junior. El objetivo no es una libreria reutilizable: cada script
es una leccion que se ejecuta sola y demuestra un concepto del API.

Esto invierte dos criterios normales de codigo:

- **Los comentarios son mas densos de lo habitual.** Explican el "por que" del
  API de Odoo (comportamientos que sorprenden a un junior), no el "que" del
  codigo. Es intencional; no reducirlos por limpieza.
- **La duplicacion entre ejemplos se tolera** para que cada archivo se lea
  completo sin saltar a otro. `llamar_odoo()` esta repetida en cada ejemplo.

## Ejecucion

No hay build, ni linter, ni suite de pruebas. Cada ejemplo se corre directo:

```bash
python3 01_buscar_contacto_por_vat.py                  # usa un vat de ejemplo
python3 02_leer_tickets_por_vat.py GOMO950919B75       # vat como argumento
```

Los ejemplos golpean una instancia real de Odoo. Todos son de solo lectura
(`search_read`, `search_count`), asi que ejecutarlos es la forma de verificarlos.

Dependencias: `python-dotenv` para `configuracion.py`. Todo lo demas es libreria
estandar (`urllib`, `json`) y asi debe mantenerse.

## Configuracion

`configuracion.py` centraliza el acceso y llama `load_dotenv()`; los ejemplos
nunca leen variables de entorno por su cuenta. Los datos reales viven en `.env`
(no versionado); `.env.example` es la plantilla.

Trampa conocida: una variable definida pero vacia en `.env` gana sobre el valor
de respaldo de `os.environ.get()`, y produce un 401 que no explica la causa.

## Contrato del API JSON-2 (Odoo 19)

Los ejemplos usan el endpoint nuevo de Odoo 19, no XML-RPC. Su contrato se
verifico leyendo el codebase de Odoo 19 en
`/home/oscar-gonzalez/Documents/docker_volumes/FullOdoo19/`, en los archivos
`odoo19ce/addons/rpc/controllers/json2.py` y `odoo19ce/odoo/http.py`.
Puntos que no se adivinan:

- `POST /json/2/<modelo>/<metodo>`. No hay login: no existe `authenticate()`
  ni `uid`.
- Autentica solo con API Key en `Authorization: Bearer <clave>`. La contraseña
  del usuario **no** funciona (la ruta usa `auth='bearer'`).
- La base de datos va en el encabezado `X-Odoo-Database`.
- **Los metodos se llaman solo con argumentos con nombre.** El controlador hace
  `signature.bind(records, **kwargs)` y responde 422 si no encaja. Se manda
  `{"domain": [...]}`, nunca `[dominio]` posicional como en XML-RPC.
- `ids` y `context` son llaves reservadas del cuerpo; el resto pasa tal cual al
  metodo del ORM.
- Los errores llegan como status HTTP con cuerpo JSON (llave `message`), no como
  un Fault de XML-RPC. 404 en un modelo suele significar modulo no instalado.
