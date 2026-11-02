/*
    Configuración global de /monitoreo.
    Todo parámetro o umbral que se pueda querer ajustar sin tocar templates HTML vive aquí.
*/

const UMBRALES_ASISTENCIA = [
    { id: 'optimo',   etiqueta: 'Óptimo',   desde: 95, hex: PALETA.verde,        fondo: 'bg-verde-fondo',    texto: 'text-verde-oscuro' },
    { id: 'adecuado', etiqueta: 'Adecuado', desde: 85, hex: PALETA.azulPrimario, fondo: 'bg-azul-fondo',     texto: 'text-azul-profundo' },
    { id: 'atencion', etiqueta: 'Atención', desde: 75, hex: PALETA.amarillo,     fondo: 'bg-amarillo-fondo', texto: 'text-amarillo-oscuro' },
    { id: 'critico',  etiqueta: 'Crítico',  desde: 0,  hex: PALETA.rojo,         fondo: 'bg-rojo-fondo',     texto: 'text-rojo-oscuro' },
];

// Estado visual cuando no hay datos que clasificar (curso sin registros)
const NIVEL_SIN_DATOS = {
    id: 'sin-datos',
    etiqueta: 'Sin registros',
    hex: PALETA.grisClaro,
    fondo: 'bg-gris-ultraclaro',
    texto: 'text-gris-texto',
};

// Ancho mínimo en pixeles que ocupa cada punto de un gráfico que tiene scroll horizontal
const GRAFICOS_SCROLL = {
    barrasMes: 56,    // Evolución de asistencia (vista mensual)
    barrasDia: 36,    // Evolución de asistencia (vista diaria)
    barrasCurso: 56,  // Porcentaje de alertas por curso
    lineaMes: 64,     // Tendencia de alertas activas
};

// Devuelve el objeto de UMBRALES_ASISTENCIA que corresponde a un porcentaje
function nivelAsistencia(porcentaje) {
    if (porcentaje === null || porcentaje === undefined || porcentaje === '') return NIVEL_SIN_DATOS;
    const valor = Number(porcentaje);
    if (Number.isNaN(valor)) return NIVEL_SIN_DATOS;
    const ordenados = [...UMBRALES_ASISTENCIA].sort((a, b) => b.desde - a.desde);

    return ordenados.find((nivel) => valor >= nivel.desde) ?? ordenados[ordenados.length - 1];
}

// Pinta cada elemento de la leyenda [data-nivel-asistencia="<porcentaje>"] según los umbrales
// sobre la métrica de nivel de asistencia por curso
function aplicarNivelesAsistencia(raiz = document) {
    raiz.querySelectorAll('[data-nivel-asistencia]').forEach((el) => {
        const nivel = nivelAsistencia(el.dataset.nivelAsistencia);
        el.classList.add(nivel.fondo);
        el.querySelectorAll('[data-nivel-texto]').forEach((texto) => texto.classList.add(nivel.texto));
        el.title = nivel.etiqueta;
    });
}

// Dibuja la leyenda de umbrales dentro de cada [data-leyenda-asistencia]
function renderLeyendaAsistencia(raiz = document) {
    const ordenados = [...UMBRALES_ASISTENCIA].sort((a, b) => b.desde - a.desde);
    raiz.querySelectorAll('[data-leyenda-asistencia]').forEach((contenedor) => {
        contenedor.replaceChildren(...ordenados.map((nivel, i) => {
            const mayor = ordenados[i - 1];
            const rango = i === 0 ? `≥ ${nivel.desde}%`
                : i === ordenados.length - 1 ? `< ${mayor.desde}%`
                : `${nivel.desde}-${mayor.desde - 1}%`;

            const item = document.createElement('span');
            item.className = 'inline-flex items-center gap-1.5 text-xs text-gris-texto';
            const punto = document.createElement('span');
            punto.className = 'h-2.5 w-2.5 shrink-0 rounded-full';
            punto.style.backgroundColor = nivel.hex;
            item.append(punto, `${nivel.etiqueta} ${rango}`);

            return item;
        }));
    });
}