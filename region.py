import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from PIL import Image

# Datos
regiones = [
    "América del Norte", "Centroamérica", "Europa",
    "Asia", "Caribe"
]
crecimiento_trimestral_2025 = [
-3.3,
-1.7,
-10.5,
-8.0,
-17.6,
]

crecimiento_anual_2024 = [
 0.8 ,
 1.1 ,
-16.0 ,
-17.8, 
-12.3
]
media_trimestral = sum(crecimiento_trimestral_2025) / len(crecimiento_trimestral_2025)

# Cargar imágenes
image_paths = {
    "América del Norte": "norte_america.png",
    "Centroamérica": "ca.png",
    "Europa": "europa.png",
    "Asia": "asia.png",
    "Caribe": "caribe.png"
}
imagenes = {k: Image.open(path) for k, path in image_paths.items()}

# Crear figura
fig, ax = plt.subplots(figsize=(12, 8))

# Rango de ejes
xmin = min(crecimiento_trimestral_2025) - 10
xmax = max(crecimiento_trimestral_2025) + 10
ymin = min(crecimiento_anual_2024) - 30
ymax = max(crecimiento_anual_2024) + 10

# Líneas guía
ax.axvline(media_trimestral, color='black', linestyle='--', linewidth=1)
ax.axhline(0, color='black', linewidth=1)

# Agregar imágenes y nombres
for region, x, y in zip(regiones, crecimiento_trimestral_2025, crecimiento_anual_2024):
    img = OffsetImage(imagenes[region], zoom=0.15)
    ab = AnnotationBbox(img, (x, y), frameon=False)
    ax.add_artist(ab)
    ax.text(x, y - 10, region, fontsize=15, ha='center')

# Títulos y etiquetas
ax.set_title("Crecimiento de exportaciones por región\n4T 2024 vs Anual 2023", fontsize=16)
ax.set_xlabel("Crecimiento trimestral de exportaciones (4T 2024, %)", fontsize=12)
ax.set_ylabel("Crecimiento anual de exportaciones (2023, %)", fontsize=12)
ax.set_xlim([xmin, xmax])
ax.set_ylim([ymin, ymax])
ax.grid(True, linestyle='--', alpha=0.5)

plt.tight_layout()
plt.show()
