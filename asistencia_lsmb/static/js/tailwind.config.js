tailwind.config = {
    theme: {
        extend: {
            fontFamily: {
                sans: ['Inter', 'sans-serif'],
                serif: ['Lora', 'serif']
            },
            colors: {
                azul: {
                    profundo: "#0F3A66",
                    primario: "#1B5FA8",
                    medio: "#5B9BD9",
                    claro: "#5EB0FF",
                    fondo: "#D4EAFF",
                },
                celeste: {
                    claro: "#EAF4FC",
                },
                negro: {
                    texto: "#1F2937",
                },
                gris: {
                    texto: "#6B7280",
                    iconos: "#B1B1B1",
                    claro: "#E5E7EB",
                    ultraclaro: "#F3F3F3",
                },
                blanco: {
                    DEFAULT: "#FFFFFF",
                    fondo: "#F3F4F6",
                    tarjeta: "#FFFFFF",
                },
                verde: {
                    oscuro: "#1A6035",
                    DEFAULT: "#2F9E58",
                    suave: "#6CAF84",
                    fondo: "#DEFFEA",
                    claro: "#EDFAF3",
                },
                amarillo: {
                    oscuro: "#7A540F",
                    DEFAULT: "#E3A72E",
                    suave: "#DEB155",
                    fondo: "#FFF2D8",
                    claro: "#FEF7E8",
                },
                rojo: {
                    oscuro: "#791F1F",
                    DEFAULT: "#D9453D",
                    suave: "#DA6862",
                    fondo: "#FFDCDA",
                    claro: "#FCEBEB",
                }
            }
        }
    }
}