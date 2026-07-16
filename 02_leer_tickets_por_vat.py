"""
Ejemplo del API JSON-2 de Odoo 19: leer los tickets de soporte de un cliente.

CASO DE USO
-----------
Un sistema externo identifica a sus clientes por vat, no por el id de Odoo.
Este script recibe un vat y devuelve los tickets de soporte (helpdesk.ticket)
cuyo cliente (partner_id) tenga ese vat.

LO NUEVO DE ESTE EJEMPLO: DOMINIOS CON PUNTO
--------------------------------------------
El dato del filtro (el vat) NO vive en helpdesk.ticket: vive en res.partner.
La forma ingenua de resolverlo son dos llamadas:

    1. buscar en res.partner los ids que tengan ese vat
    2. buscar en helpdesk.ticket con partner_id in [esos ids]

Pero el dominio de Odoo permite cruzar la relacion con un punto:

    [("partner_id.vat", "=ilike", vat)]

Odoo traduce eso a un JOIN en SQL y resuelve todo en UNA peticion. Menos viajes
de red y menos codigo. Se puede usar en cualquier campo relacional
(partner_id.country_id.code tambien es valido).

NOTA SOBRE HELPDESK
-------------------
helpdesk.ticket pertenece a Odoo Enterprise y el modulo "Soporte al cliente"
debe estar instalado. Si no lo esta, Odoo responde 404 indicando que el modelo
no existe; el script lo detecta y lo explica.

EJECUCION
---------
    python3 02_leer_tickets_por_vat.py                 (usa un vat de ejemplo)
    python3 02_leer_tickets_por_vat.py XAXX010101000

Solo usa la libreria estandar de Python.
"""

import json
import sys
import urllib.error
import urllib.request

import configuracion

# Campos del ticket que interesan al sistema externo.
CAMPOS_TICKET = [
    "id",
    "name",           # Asunto del ticket
    "ticket_ref",     # Referencia visible para el cliente
    "stage_id",       # Etapa: Nuevo, En progreso, Resuelto...
    "priority",       # Prioridad, llega como '0'...'3'
    "user_id",        # Responsable asignado
    "partner_id",     # Cliente
    "create_date",    # Fecha de creacion
]

# Traduccion de la prioridad. Odoo guarda un texto ('0', '1'...) porque el campo
# es Selection; el numero por si solo no le dice nada a quien lee el reporte.
# Los valores salen de TICKET_PRIORITY en helpdesk/models/helpdesk_ticket.py.
PRIORIDADES = {
    "0": "Baja",
    "1": "Media",
    "2": "Alta",
    "3": "Urgente",
}


def llamar_odoo(modelo, metodo, **kwargs):
    """Ejecuta un metodo del ORM por el endpoint JSON-2 y devuelve el resultado.

    Esta es la unica funcion que habla por red. Construye la peticion, agrega la
    API Key y traduce los errores HTTP a excepciones de Python entendibles.

    :param modelo: nombre tecnico del modelo, por ejemplo 'helpdesk.ticket'.
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
        if error.code == 404:
            raise RuntimeError(
                f"Odoo no reconoce '{modelo}'. Si es un modelo de Enterprise, "
                f"revisar que el modulo este instalado: {mensaje}"
            )
        raise RuntimeError(f"Odoo respondio HTTP {error.code}: {mensaje}")

    except urllib.error.URLError as error:
        raise ConnectionError(
            f"No se pudo contactar el servidor {configuracion.URL}: {error.reason}"
        )


def leer_tickets_por_vat(vat, solo_abiertos=False, limite=20):
    """Devuelve los tickets cuyo cliente tenga el vat indicado.

    El cruce hacia res.partner se hace con 'partner_id.vat' dentro del dominio,
    asi se resuelve en una sola peticion en lugar de buscar primero el contacto.

    :param vat: vat del cliente, por ejemplo 'XAXX010101000'.
    :param solo_abiertos: si es True, omite los tickets ya cerrados.
    :param limite: maximo de tickets a devolver.
    :return: lista de diccionarios, uno por ticket.
    """
    # '=ilike' compara sin distinguir mayusculas, porque el vat se captura de
    # formas distintas segun quien dio de alta al contacto.
    dominio = [("partner_id.vat", "=ilike", vat)]

    if solo_abiertos:
        # 'fold' marca las etapas que en la vista kanban aparecen plegadas, que
        # son las de cierre (Resuelto, Cancelado). Es el criterio que usa el
        # propio Odoo para considerar un ticket terminado.
        dominio.append(("stage_id.fold", "=", False))

    return llamar_odoo(
        "helpdesk.ticket",
        "search_read",
        domain=dominio,
        fields=CAMPOS_TICKET,
        limit=limite,
        # Los mas recientes primero, que es lo que interesa en un tablero.
        order="create_date desc",
    )


def contar_tickets_por_vat(vat):
    """Devuelve cuantos tickets tiene el cliente, sin traer los registros.

    search_count es mucho mas barato que traer todo y contarlo en Python.

    :param vat: vat del cliente.
    :return: numero entero de tickets.
    """
    return llamar_odoo(
        "helpdesk.ticket",
        "search_count",
        domain=[("partner_id.vat", "=ilike", vat)],
    )


def describir_ticket(ticket):
    """Convierte un ticket crudo de Odoo en lineas de texto legibles.

    Los campos Many2one llegan como [id, nombre] o como False si estan vacios,
    y los Char vacios llegan como False. Por eso cada valor se protege antes
    de imprimirse.

    :param ticket: diccionario tal como lo devuelve Odoo.
    :return: cadena de texto lista para imprimir.
    """
    referencia = ticket["ticket_ref"] or ticket["id"]
    etapa = ticket["stage_id"][1] if ticket["stage_id"] else "sin etapa"
    responsable = ticket["user_id"][1] if ticket["user_id"] else "sin asignar"
    prioridad = PRIORIDADES.get(ticket["priority"], "desconocida")

    # create_date llega como texto 'YYYY-MM-DD HH:MM:SS' en horario UTC.
    # Se corta la hora porque para un listado la fecha es suficiente.
    fecha = ticket["create_date"][:10] if ticket["create_date"] else "sin fecha"

    return (
        f"  [{referencia}] {ticket['name']}\n"
        f"      Etapa: {etapa} | Prioridad: {prioridad}\n"
        f"      Responsable: {responsable} | Creado: {fecha}"
    )


def main():
    """Punto de entrada: busca los tickets del vat recibido y los muestra."""
    # XAXX010101000 es el vat generico de publico en general en Mexico; sirve
    # como valor de prueba porque suele existir en bases con localizacion.
    vat = sys.argv[1] if len(sys.argv) > 1 else "XAXX010101000"

    print(f"Buscando tickets del cliente con vat '{vat}'")
    print(f"Servidor: {configuracion.URL}\n")

    total = contar_tickets_por_vat(vat)

    if not total:
        # Sin tickets pueden pasar dos cosas: el cliente no existe, o existe
        # pero nunca abrio uno. Se distingue para no dejar al usuario a ciegas.
        contactos = llamar_odoo(
            "res.partner",
            "search_read",
            domain=[("vat", "=ilike", vat)],
            fields=["name"],
            limit=1,
        )
        if contactos:
            print(f"El cliente '{contactos[0]['name']}' no tiene tickets.")
        else:
            print("No existe ningun contacto con ese vat.")
        return

    tickets = leer_tickets_por_vat(vat, limite=20)

    # Todos los tickets son del mismo cliente, asi que basta leer el primero.
    cliente = tickets[0]["partner_id"][1] if tickets[0]["partner_id"] else vat
    print(f"Cliente: {cliente}")
    print(f"Tickets en total: {total}, mostrando {len(tickets)}\n")

    for ticket in tickets:
        print(describir_ticket(ticket))


if __name__ == "__main__":
    try:
        main()
    except (ConnectionError, PermissionError, RuntimeError) as error:
        print(f"\nError: {error}")
