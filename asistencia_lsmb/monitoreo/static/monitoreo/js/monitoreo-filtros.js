const PARAMS_FILTROS = {
    curso: {
        ag: ['ag_curso'],
        evo: ['evo_curso'],
        apn: ['apn_curso', 'alerta_nivel_curso'],
        ten: ['ten_curso', 'tendencia_curso'],
        just: ['just_curso', 'jp_curso'],
        act: ['act_curso', 'curso'],
    },
    nivel: {
        ag: ['ag_nivel'],
        evo: ['evo_nivel'],
        apn: ['apn_nivel', 'alerta_nivel_nivel'],
        ten: ['ten_nivel', 'tendencia_nivel'],
        just: ['just_nivel', 'jp_nivel'],
    },
};

const NIVELES_ROMANOS = { 1: 'I', 2: 'II', 3: 'III', 4: 'IV' };
const CLAVE_ESTADO_SESION = 'monitoreo:estado';

function _borrarClaves(params, grupos) {
    grupos.flat().forEach(clave => {
        params.delete(clave);
    });
}

function construirParamsGlobales(paramsActuales, tipo, valor) {
    const params = new URLSearchParams(paramsActuales);

    _borrarClaves(params, [...Object.values(PARAMS_FILTROS.curso), ...Object.values(PARAMS_FILTROS.nivel)]);
    if (valor !== null && valor !== undefined && valor !== ''){
        Object.values(PARAMS_FILTROS[tipo]).forEach(claves => params.set(claves[0], valor))
    }

    return params;
}


document.addEventListener(
    'alpine:init', () => {
        Alpine.store('filtros', {
            catalogo: { cursos: [], niveles: [], meses: [], tipos_actividad: [], actores_actividad: [], activos: [] },
            sheetAbierto: false, // Mobile
            init() {
                const nodo = document.getElementById('datos-filtros-monitoreo');
                if (nodo) this.catalogo = JSON.parse(nodo.textContent);
            },

            get activos() { return this.catalogo.activos || {}; },
            get cursoGlobal() { return (this.activos.ag || {}).curso ?? null },
            get nivelGlobal() { return (this.activos.ag || {}).nivel ?? null },
            get cantidadGlobal() { return this.cursoGlobal !== null || this.nivelGlobal !== null ? 1 : 0 },

            etiquetaCurso(id) {
                const curso = this.catalogo.cursos.find( c => c.id === id );
                return curso ? `${NIVELES_ROMANOS[curso.nivel] || curso.nivel}°${curso.grupo}` : '';
            },

            tituloFiltrado(componente) {
                const activo = this.activos[componente] || {};
                if (activo.curso) {
                    const etiqueta = this.etiquetaCurso(activo.curso);
                    return etiqueta ? ` · ${etiqueta}` : '';
                }
                if (activo.nivel)
                    return ` · ${NIVELES_ROMANOS[activo.nivel] || activo.nivel}° Medio`;

                return '';
            },

            leerParams() { return new URLSearchParams(window.location.search); },
            navegar(params) {
                const nuevo = params.toString();
                if (nuevo === this.leerParams().toString()) return; // nada cambió
    
                const raiz = document.getElementById('monitoreo-root');
                try {
                    sessionStorage.setItem(CLAVE_ESTADO_SESION, JSON.stringify({
                        seccion: raiz ? Alpine.$data(raiz).seccionActiva : null,
                        scroll: window.scrollY,
                    }));
                } 
                catch (_) { /* sessionStorage puede no estar disponible */ }
    
                window.location.assign(window.location.pathname + (nuevo ? `?${nuevo}` : ''));
            },
            fijarGlobal(tipo, valor) {
                this.navegar(construirParamsGlobales(this.leerParams(), tipo, valor));
            },

            limpiarGlobales() {
                this.navegar(construirParamsGlobales(this.leerParams(), 'curso', ''));
            }
        });
    }
);