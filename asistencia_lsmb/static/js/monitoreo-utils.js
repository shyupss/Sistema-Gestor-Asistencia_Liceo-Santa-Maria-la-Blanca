const PALETA = {
    azulPrimario: '#1B5FA8',
    azulMedio: '#5B9BD9',
    azulFondo: '#D4EAFF',
    grisClaro: '#E5E7EB',
    grisTexto: '#6B7280',
    verde: '#2F9E58',
    amarillo: '#E3A72E',
    rojo: '#D9453D',
};


// -----------------------------------------
//  Scroll horizontal en gráficos
// -----------------------------------------
function _prepararScroll(canvasId, nPuntos, minPx) {
    const canvas = document.getElementById(canvasId);
    const lienzo = canvas && canvas.closest('[data-lienzo]');
    if (!lienzo) return null;
    // El lienzo mide el 100% de la tarjeta, pero nunca menos que puntos * minPx.
    lienzo.style.minWidth = `${nPuntos * minPx}px`;
    return {
        lienzo,
        scroller: lienzo.closest('[data-scroller]'),
        eje: document.getElementById(`${canvasId}-eje`),
    };
}

// Plugin de Chart.js que copia la franja del eje Y al canvas fijo
function _pluginEjeFijo(eje) {
    return {
        id: 'ejeYFijo',
        afterRender(chart) {
            const area = chart.chartArea;
            if (!area || !eje) return;
            const dpr = chart.currentDevicePixelRatio || window.devicePixelRatio || 1;
            const ancho = Math.ceil(area.left);
            const anchoPx = Math.max(1, Math.round(ancho * dpr));
            const altoPx = chart.canvas.height;

            eje.width = anchoPx;
            eje.height = altoPx;
            eje.style.width = `${ancho}px`;
            eje.style.height = `${altoPx / dpr}px`;
            eje.getContext('2d').drawImage(chart.canvas, 0, 0, anchoPx, altoPx, 0, 0, anchoPx, altoPx);

            // Permite a los degradados y flechas posicionarse después del eje.
            if (eje.parentElement) eje.parentElement.style.setProperty('--eje-ancho', `${ancho}px`);
        },
    };
}

// Posición inicial del scroll
function _scrollInicial(scroll, nPuntos, donde) {
    if (!scroll || !scroll.scroller || donde === 'inicio') return;
    requestAnimationFrame(() => {
        const { scroller, lienzo } = scroll;
        if (donde === 'fin') {
            scroller.scrollLeft = scroller.scrollWidth;
        } else if (Number.isInteger(donde) && donde >= 0) {
            const centro = ((donde + 0.5) / nPuntos) * lienzo.offsetWidth;
            scroller.scrollLeft = centro - scroller.clientWidth / 2;
        }
    });
}


// -----------
//  Gráficos
// -----------


// Gráfico de dona
function crearDonut(canvasId, porcentaje, color = PALETA.azulPrimario) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const sinDatos = porcentaje === null || porcentaje === undefined;
    const valor = sinDatos ? 0 : porcentaje;

    return new Chart(canvas, {
        type: 'doughnut',
        data: {
            datasets: [{
                data: [valor, 100 - valor],
                backgroundColor: [sinDatos ? PALETA.grisClaro : color, PALETA.grisClaro],
                borderWidth: 0,
                borderRadius: '999px',
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '72%',
            plugins: {
                legend: { display: false },
                tooltip: { enabled: false },
            },
        },
    });
}


// Gráfico de barras
function crearBarras(canvasId, labels, valores, opciones = {}) {
    if (typeof opciones === 'string') opciones = { color: opciones };
    const {
        color = PALETA.azulPrimario,
        colorHover = null,
        max = 100,
        sufijo = '%',
        minPx = null,
        scrollInicial = 'inicio',
        ticksX = null,
        titulos = null,
        pie = null,
        onClickIndice = null,
        colorPorUmbral = false,
    } = opciones;

    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const scroll = minPx ? _prepararScroll(canvasId, labels.length, minPx) : null;

    // Colores por barra según umbral de asistencia o color fijo
    const colorFinal = colorPorUmbral
        ? valores.map((v) => (typeof nivelAsistencia === 'function' ? nivelAsistencia(v).hex : color))
        : color;

    const hoverFinal = colorHover
        || (Array.isArray(colorFinal)
            ? colorFinal.map((c) => `${c}CC`)
            : `${colorFinal}CC`);

    const callbacksTooltip = {
        title: (items) => (titulos ? titulos[items[0].dataIndex] : items[0].label),
        label: (ctx) => {
            const v = ctx.parsed.y;
            if (v === null || v === undefined || isNaN(v)) return 'Sin registros';
            return `${v}${sufijo}`;
        },
    };
    if (pie) callbacksTooltip.footer = () => pie;

    const chart = new Chart(canvas, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                data: valores,
                backgroundColor: colorFinal,
                hoverBackgroundColor: hoverFinal,
                borderRadius: 4,
                maxBarThickness: 36,
            }],
        },
        plugins: scroll && scroll.eje ? [_pluginEjeFijo(scroll.eje)] : [],
        options: {
            responsive: true,
            maintainAspectRatio: false,

            onHover: (evento, elementos) => {
                if (evento.native) evento.native.target.style.cursor = onClickIndice && elementos.length ? 'pointer' : '';
            },

            onClick: (_evento, elementos) => {
                if (!onClickIndice || !elementos.length) return;
                if (scroll && scroll.scroller && scroll.scroller.dataset.arrastre === '1') return;
                onClickIndice(elementos[0].index);
            },

            plugins: {
                legend: { display: false },
                tooltip: { callbacks: callbacksTooltip },
            },

            scales: {
                y: {
                    beginAtZero: true,
                    ...(max !== null && { max }),
                    ticks: { callback: (valor) => valor + sufijo },
                    grid: { color: PALETA.grisClaro },
                },
                x: {
                    grid: { display: false },
                    ticks: ticksX
                        ? { callback(valor) { return ticksX(this.getLabelForValue(valor), valor); } }
                        : {},
                },
            },
        },
    });

    _scrollInicial(scroll, labels.length, scrollInicial);
    return chart;
}


function crearDonutSegmentos(canvasId, valores, colores) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const total = valores.reduce((acc, val) => acc + (Number(val) || 0), 0);
    const esVacio = total === 0;

    return new Chart(canvas, {
        type: 'doughnut',

        data: {
            datasets: [{
                data: esVacio ? [1] : valores,
                backgroundColor: esVacio ? [PALETA.grisClaro] : colores,
                borderWidth: 0,
            }],
        },
        
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '65%',
            plugins: {
                legend: { display: false },
                tooltip: { enabled: false },
            },
            ...(esVacio && { events: [] }),
        },
    });
}


// Gráfico de línea
function crearLinea(canvasId, labels, valores, opciones = {}) {
    const { color = PALETA.rojo, sufijo = '', minPx = null, scrollInicial = 'inicio' } = opciones;
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const scroll = minPx ? _prepararScroll(canvasId, labels.length, minPx) : null;

    const chart = new Chart(canvas, {
        type: 'line',

        data: {
            labels,
            datasets: [{
                data: valores,
                borderColor: color,
                backgroundColor: color + '22',
                fill: true,
                tension: 0.3,
                pointRadius: 3,
                pointHoverRadius: 5,
                pointBackgroundColor: color,
            }],
        },

        plugins: scroll && scroll.eje ? [_pluginEjeFijo(scroll.eje)] : [],

        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { precision: 0, callback: (valor) => valor + sufijo },
                    grid: { color: PALETA.grisClaro },
                },
                x: {
                    grid: { display: false },
                },
            },
        },
    });

    _scrollInicial(scroll, labels.length, scrollInicial);
    return chart;
}