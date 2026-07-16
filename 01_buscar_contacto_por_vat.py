"""
Ejemplo del API "External JSON-2" de Odoo 19: buscar un contacto por vat.

QUE ES EL JSON-2 API
--------------------
Odoo 19 agrega un endpoint nuevo, mas simple que el XML-RPC de siempre:

    POST /json/2/<modelo>/<metodo>

Diferencias importantes contra XML-RPC:

    1. NO hay paso de login. No existe authenticate() ni uid. Se manda una
       API Key en el encabezado 'Authorization: Bearer <clave>' y Odoo resuelve
       solo que usuario es.
    2. La base de datos va en el encabezado 'X-Odoo-Database'. 
    3. La contraseña del usuario NO sirve aqui, solo la API Key.
    4. Los metodos se llaman SOLO con argumentos con nombre (kwargs). Se manda
       {"domain": [...]}. Esto es una regla del controlador, no un detalle:
       el servidor valida la firma del metodo y rechaza lo que no encaje.
    5. Los errores llegan como codigo HTTP (401, 404, 422...) con un cuerpo
       JSON.

El cuerpo de la peticion admite tres cosas:

    {
      "ids":     [1, 2],        <- registros sobre los que aplica el metodo: En sistemas externos se puede guardar como Odoo_id, y asi no hay que buscar por vat cada vez.
      "context": {"lang": "es_MX"},
      ...                       <- el resto son los kwargs del metodo
    }

'ids' y 'context' son nombres reservados; cualquier otra llave se pasa tal cual
al metodo del ORM.

CASO DE USO
-----------
Un sistema externo (por ejemplo un CRM propio) guarda contactos identificados
por vat. Este script consulta Odoo por ese vat y reporta que campos cambiaron
respecto a la ultima copia local, que es el patron tipico de una sincronizacion:
no se trae todo, solo se detecta la diferencia.

EJECUCION
---------
    python3 01_buscar_contacto_por_vat.py                 (usa un vat de ejemplo)
    python3 01_buscar_contacto_por_vat.py XAXX010101000

Solo usa la libreria estandar de Python.
"""

import json
import os
import sys
import urllib.error
import urllib.request

import configuracion

# Campos que este sistema externo mantiene sincronizados.
# El identificador fiscal del contacto vive en el campo 'vat' de res.partner.
# Se le llama vat porque es el nombre internacional y el nombre tecnico real del
# campo; cada localizacion solo cambia la etiqueta que ve el usuario (en Mexico
# aparece como RFC, en España como NIF).
# Para registros especificos proporcionaremos la estructura de datos especifica
CAMPOS_SINCRONIZADOS = ["name", "street", "email", "website", "phone"]

# Archivo donde se guarda la ultima copia conocida de cada contacto, para poder
# comparar en la siguiente corrida. En un sistema real esto seria la base de
# datos del sistema externo.
ARCHIVO_COPIA_LOCAL = "copia_contactos.json"


def llamar_odoo(modelo, metodo, **kwargs):
    """Ejecuta un metodo del ORM por el endpoint JSON-2 y devuelve el resultado.

    Esta es la unica funcion que habla por red. Construye la peticion, agrega la
    API Key y traduce los errores HTTP a excepciones de Python entendibles.

    :param modelo: nombre tecnico del modelo, por ejemplo 'res.partner'.
    :param metodo: metodo publico del ORM, por ejemplo 'search_read'.
    :param kwargs: argumentos con nombre del metodo (domain, fields, limit...).
                   Tambien acepta las llaves reservadas 'ids' y 'context'.
    :return: la respuesta ya convertida a tipos de Python.
    :raises ConnectionError: si el servidor no responde.
    :raises PermissionError: si la API Key es invalida o no tiene permisos.
    :raises RuntimeError: si Odoo rechaza la llamada (modelo o campo incorrecto).
    """
    url = f"{configuracion.URL}/json/2/{modelo}/{metodo}"

    peticion = urllib.request.Request(
        url,
        data=json.dumps(kwargs).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            # Aqui va toda la autenticacion: sin usuario, sin contraseña.
            "Authorization": f"Bearer {configuracion.CLAVE_API}",
            # Sin este encabezado Odoo no sabe a que base de datos entrar,
            # salvo que el servidor tenga una sola y la resuelva por dominio.
            "X-Odoo-Database": configuracion.BASE_DATOS,
        },
    )

    try:
        with urllib.request.urlopen(peticion, timeout=30) as respuesta:
            return json.loads(respuesta.read())

    except urllib.error.HTTPError as error:
        # Odoo responde el detalle del error en el cuerpo, no solo en el status.
        detalle = error.read().decode("utf-8", errors="replace")
        try:
            mensaje = json.loads(detalle).get("message", detalle)
        except json.JSONDecodeError:
            mensaje = detalle

        if error.code in (401, 403):
            raise PermissionError(
                f"La API Key fue rechazada o no tiene permisos sobre "
                f"'{modelo}': {mensaje}"
            )
        raise RuntimeError(f"Odoo respondio HTTP {error.code}: {mensaje}")

    except urllib.error.URLError as error:
        raise ConnectionError(
            f"No se pudo contactar el servidor {configuracion.URL}: {error.reason}"
        )


def buscar_contacto_por_vat(vat):
    """Devuelve el contacto que tenga ese vat, o None si no existe.

    Se usa search_read para resolver busqueda y lectura en una sola peticion.
    El limite de 2 es intencional: permite detectar vat duplicados (un problema
    real de datos) sin traer una lista completa si la base esta sucia.

    :param vat: vat a buscar, por ejemplo 'XAXX010101000'.
    :return: diccionario con los campos del contacto, o None.
    :raises RuntimeError: si el vat esta registrado en mas de un contacto.
    """
    contactos = llamar_odoo(
        "res.partner",
        "search_read",
        # '=ilike' compara sin distinguir mayusculas, util porque el vat se
        # captura de formas distintas segun quien lo dio de alta.
        domain=[("vat", "=ilike", vat)],
        fields=["id", "vat"] + CAMPOS_SINCRONIZADOS,
        limit=2,
    )

    if not contactos:
        return None

    if len(contactos) > 1:
        identificadores = [contacto["id"] for contacto in contactos]
        raise RuntimeError(
            f"El vat '{vat}' esta registrado en mas de un contacto {identificadores}. "
            f"Debe corregirse en Odoo antes de sincronizar."
        )

    return contactos[0]


def leer_copia_local():
    """Carga la ultima copia conocida de los contactos.

    :return: diccionario {vat: {campo: valor}}. Vacio si aun no hay archivo.
    """
    if not os.path.exists(ARCHIVO_COPIA_LOCAL):
        return {}

    with open(ARCHIVO_COPIA_LOCAL, encoding="utf-8") as archivo:
        return json.load(archivo)


def guardar_copia_local(copia):
    """Guarda la copia de contactos para comparar en la siguiente corrida."""
    with open(ARCHIVO_COPIA_LOCAL, "w", encoding="utf-8") as archivo:
        json.dump(copia, archivo, indent=2, ensure_ascii=False)


def normalizar(contacto):
    """Deja solo los campos sincronizados y convierte los vacios a cadena.

    Odoo devuelve False cuando un campo de texto esta vacio. Si no se normaliza,
    la comparacion marcaria un cambio falso entre False y "" cada vez que el
    sistema externo guarde un campo vacio.

    :param contacto: diccionario tal como lo devuelve Odoo.
    :return: diccionario con los campos de CAMPOS_SINCRONIZADOS.
    """
    return {campo: contacto[campo] or "" for campo in CAMPOS_SINCRONIZADOS}


def comparar(actual, anterior):
    """Compara dos versiones del contacto y devuelve los campos que cambiaron.

    :param actual: datos recien traidos de Odoo, ya normalizados.
    :param anterior: datos de la copia local, ya normalizados.
    :return: diccionario {campo: (valor_anterior, valor_actual)}.
    """
    return {
        campo: (anterior.get(campo, ""), actual[campo])
        for campo in CAMPOS_SINCRONIZADOS
        if anterior.get(campo, "") != actual[campo]
    }


def main():
    """Punto de entrada: busca el contacto por vat y reporta los cambios."""
    # XAXX010101000 es el vat generico de publico en general en Mexico (el RFC
    # generico); sirve como valor de prueba porque suele existir en bases con
    # la localizacion mexicana instalada.
    vat = sys.argv[1] if len(sys.argv) > 1 else "XAXX010101000"

    print(f"Buscando contacto con vat '{vat}' en {configuracion.URL}")

    contacto = buscar_contacto_por_vat(vat)

    if contacto is None:
        print("No existe ningun contacto con ese vat.")
        return

    print(f"Encontrado: [{contacto['id']}] {contacto['name']}\n")

    datos_actuales = normalizar(contacto)
    copia = leer_copia_local()
    datos_anteriores = copia.get(vat)

    if datos_anteriores is None:
        print("Primera sincronizacion de este vat, se guardan los datos:")
        for campo, valor in datos_actuales.items():
            print(f"  {campo}: {valor or '(vacio)'}")
    else:
        cambios = comparar(datos_actuales, datos_anteriores)

        if not cambios:
            print("Sin cambios desde la ultima sincronizacion.")
        else:
            print(f"Se detectaron {len(cambios)} cambios:")
            for campo, (antes, ahora) in cambios.items():
                print(f"  {campo}: '{antes or '(vacio)'}' -> '{ahora or '(vacio)'}'")

    copia[vat] = datos_actuales
    guardar_copia_local(copia)
    print(f"\nCopia local actualizada en '{ARCHIVO_COPIA_LOCAL}'")


if __name__ == "__main__":
    try:
        main()
    except (ConnectionError, PermissionError, RuntimeError) as error:
        print(f"\nError: {error}")
