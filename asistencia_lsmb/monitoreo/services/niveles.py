def nivel_alerta(estado):
    """Clasifica un Estado en 'critico' o 'atencion' según su codigo.

    Solo debe llamarse con estados que tienen es_no_ideal=True. Cualquier
    estado sin código reconocido cae en 'atencion'.
    """
    if estado is not None and estado.codigo == "critico":
        return "critico"
    return "atencion"
