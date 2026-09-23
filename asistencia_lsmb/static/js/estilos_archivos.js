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
        xls: { icono: 'file-spreadsheet', bg: 'bg-verde-fondo',color: 'text-verde-oscuro' },
        xlsx: { icono: 'file-spreadsheet', bg: 'bg-verde-fondo',color: 'text-verde-oscuro' },
        csv: { icono: 'file-spreadsheet', bg: 'bg-verde-fondo',color: 'text-verde-oscuro' },
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
        tipoArchivo,
        formatearTamano,
        
        actualizarArchivos(event) {
            this.archivos = Array.from(event.target.files);
            this.$nextTick(() => lucide.createIcons());
        },
        
        quitarArchivo(index) {
            this.archivos.splice(index, 1);
            const dt = new DataTransfer();
            this.archivos.forEach(f => dt.items.add(f));
            this.$refs.inputArchivos.files = dt.files;
            this.$nextTick(() => lucide.createIcons());
        }
    }));
});