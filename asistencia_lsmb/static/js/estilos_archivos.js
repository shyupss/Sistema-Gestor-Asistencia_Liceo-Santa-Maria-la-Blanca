function tipoArchivo(nombre) {
    const ext = nombre.split('.').pop().toLowerCase();
    const mapa = {
        jpg: { icono: 'file-image', bg: 'bg-celeste-claro', color: 'text-azul-medio' },
        jpeg: { icono: 'file-image', bg: 'bg-celeste-claro', color: 'text-azul-medio' },
        jpe: { icono: 'file-image', bg: 'bg-celeste-claro', color: 'text-azul-medio' },
        png: { icono: 'file-image', bg: 'bg-celeste-claro', color: 'text-azul-medio' },
        gif: { icono: 'file-image', bg: 'bg-celeste-claro', color: 'text-azul-medio' },
        webp: { icono: 'file-image', bg: 'bg-celeste-claro', color: 'text-azul-medio' },
        svg: { icono: 'file-image', bg: 'bg-celeste-claro', color: 'text-azul-medio' },
        pdf: { icono: 'file-text', bg: 'bg-rojo-fondo', color: 'text-rojo-oscuro' },
        doc: { icono: 'file-text', bg: 'bg-azul-fondo', color: 'text-azul-primario' },
        docx: { icono: 'file-text', bg: 'bg-azul-fondo', color: 'text-azul-primario' },
        xls: { icono: 'file-spreadsheet', bg: 'bg-verde-fondo', color: 'text-verde-oscuro' },
        xlsx: { icono: 'file-spreadsheet', bg: 'bg-verde-fondo', color: 'text-verde-oscuro' },
        csv: { icono: 'file-spreadsheet', bg: 'bg-verde-fondo', color: 'text-verde-oscuro' },
        ppt: { icono: 'presentation', bg: 'bg-amarillo-fondo', color: 'text-amarillo-oscuro' },
        pptx: { icono: 'presentation', bg: 'bg-amarillo-fondo', color: 'text-amarillo-oscuro' },
    };
    return mapa[ext] || { icono: 'file', bg: 'bg-gris-ultraclaro', color: 'text-gris-texto' };
}

// Formatea tamaño de archivo a B/KB/MB
function formatearTamano(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

async function descargarArchivo(url, nombre) {
    try {
        const respuesta = await fetch(url);
        if (!respuesta.ok) throw new Error('Error al obtener el archivo');
        const blob = await respuesta.blob();
        const blobUrl = window.URL.createObjectURL(blob);
        const enlace = document.createElement('a');
        enlace.style.display = 'none';
        enlace.href = blobUrl;
        enlace.download = nombre || 'archivo';
        document.body.appendChild(enlace);
        enlace.click();
        document.body.removeChild(enlace);
        window.URL.revokeObjectURL(blobUrl);
    } catch (error) {
        const enlace = document.createElement('a');
        enlace.href = url;
        enlace.download = nombre || '';
        enlace.target = '_blank';
        enlace.rel = 'noopener noreferrer';
        document.body.appendChild(enlace);
        enlace.click();
        document.body.removeChild(enlace);
    }
}

document.addEventListener('alpine:init', () => {
    Alpine.data('gestorArchivos', () => ({
        archivos: [],
        archivosInvalidos: [],
        arrastrando: false,
        contadorArrastre: 0,
        extensionesPermitidas: ['jpg', 'jpeg', 'jpe', 'png', 'gif', 'webp', 'svg', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'ppt', 'pptx'],
        tipoArchivo,
        formatearTamano,

        // Validar, desduplicar y acumular archivos (input o drag & drop)
        agregarArchivos(listaArchivos) {
            this.archivosInvalidos = [];
            const nuevosValidos = [];

            Array.from(listaArchivos).forEach(f => {
                const ext = f.name.split('.').pop().toLowerCase();
                if (!this.extensionesPermitidas.includes(ext)) {
                    this.archivosInvalidos.push(f.name);
                    return;
                }
                // Evitar duplicados por nombre + tamaño
                if (!this.archivos.some(a => a.name === f.name && a.size === f.size)) {
                    nuevosValidos.push(f);
                }
            });

            if (nuevosValidos.length > 0) {
                this.archivos = [...this.archivos, ...nuevosValidos];
                this.sincronizarInput();
            }

            // Invocar Lucide una sola vez tras el ciclo de Alpine, no en cada <li>
            this.$nextTick(() => lucide.createIcons());
        },

        actualizarArchivos(event) {
            if (event.target.files && event.target.files.length > 0) {
                this.agregarArchivos(event.target.files);
            }
            // Limpiar el input para que volver a abrir el mismo archivo no quede en conflicto
            event.target.value = '';
        },

        soltarArchivos(event) {
            this.arrastrando = false;
            this.contadorArrastre = 0;
            if (event.dataTransfer && event.dataTransfer.files) {
                this.agregarArchivos(event.dataTransfer.files);
            }
        },

        quitarArchivo(index) {
            this.archivos.splice(index, 1);
            this.sincronizarInput();
            this.$nextTick(() => lucide.createIcons());
        },

        sincronizarInput() {
            const dt = new DataTransfer();
            this.archivos.forEach(f => dt.items.add(f));
            if (this.$refs.inputArchivos) {
                this.$refs.inputArchivos.files = dt.files;
            }
        }
    }));
});