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
 

function crearDonut(canvasId, porcentaje, color = PALETA.azulPrimario) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
 
    return new Chart(canvas, {
        type: 'doughnut',
        data: {
            datasets: [{
                data: [porcentaje, 100 - porcentaje],
                backgroundColor: [color, PALETA.grisClaro],
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


function crearBarras(canvasId, labels, valores, color = PALETA.azulPrimario) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
 
    return new Chart(canvas, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                data: valores,
                backgroundColor: color,
                borderRadius: 4,
                maxBarThickness: 36,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    ticks: { callback: (valor) => valor + '%' },
                    grid: { color: PALETA.grisClaro },
                },
                x: {
                    grid: { display: false },
                },
            },
        },
    });
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

function crearLinea(canvasId, labels, valores, opciones = {}) {
    const { color = PALETA.rojo, sufijo = '' } = opciones;
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
 
    return new Chart(canvas, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                data: valores,
                borderColor: color,
                backgroundColor: color + '22', // relleno semi-transparente bajo la línea
                fill: true,
                tension: 0.3,
                pointRadius: 3,
                pointBackgroundColor: color,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { callback: (valor) => valor + sufijo },
                    grid: { color: PALETA.grisClaro },
                },
                x: {
                    grid: { display: false },
                },
            },
        },
    });
}