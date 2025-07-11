

# ==========================================================
#      CELDA 4:TABLA Y MAPA
# ==========================================================
print("--- 1. PRUEBA ANALÍTICA: TABLA DE RIESGOS ETIQUETADOS ---\n")

# Extraer un ejemplo de cada tipo de riesgo encontrado para la tabla
# Esto nos ayuda a verificar que nuestra lógica funcionó para cada regla.
tipos_encontrados = pd.Series([d['tipo_de_riesgo'] for u,v,d in G.edges(data=True)]).unique()
lista_de_ejemplos = []
for tipo in tipos_encontrados:
    # Buscamos el primer arco que coincida con este tipo de riesgo
    for u, v, data in G.edges(data=True):
        if data['tipo_de_riesgo'] == tipo:
            lista_de_ejemplos.append({
                "Tipo de Riesgo Identificado": tipo,
                "μ (Tiempo Esperado) [s]": f"{data['mu']:.2f}",
                "σ (Incertidumbre) [s]": f"{data['sigma']:.2f}"
            })
            break # Una vez encontrado, pasamos al siguiente tipo

# Creamos el DataFrame y lo ordenamos por sigma para ver los más riesgosos primero
df_riesgos = pd.DataFrame(lista_de_ejemplos)
display(df_riesgos.sort_values(by='σ (Incertidumbre) [s]', key=lambda col: col.astype(float), ascending=False))
print("\nLa tabla anterior demuestra cómo cada tipo de riesgo tiene valores de 'mu' y 'sigma' distintos, según las reglas del documento.")

# --- 2. PRUEBA VISUAL: MAPA DETALLADO DE RIESGOS ---
print("\n--- 2. PRUEBA VISUAL: GENERANDO MAPA FINAL DE RIESGOS ---\n")

# Paleta de colores para cada tipo de riesgo, diseñada para ser clara y visualmente atractiva
color_palette = {
    "Zona Escolar": "#FF5733",      # Naranja Fuerte (Alto Riesgo, alta visibilidad)
    "Vía en Mal Estado": "#8B4513", # Marrón (Riesgo físico)
    "Mercado/Comercio": "#9B59B6",  # Morado (Riesgo por congestión de personas)
    "Paradero Informal": "#F1C40F", # Amarillo (Riesgo por detenciones súbitas)
    "Cruce sin Semáforo": "#3498DB",# Azul (Riesgo por negociación de paso)
    "Zona Hospitalaria": "#E74C3C", # Rojo (Riesgo por flujo constante y ambulancias)
    "Calle Angosta": "#7F8C8D",     # Gris Oscuro (Riesgo por maniobrabilidad)
    "Ninguno": "#D5D8DC"            # Gris claro (Bajo riesgo / línea base)
}

# Asignar un color a cada arco del grafo según su tipo de riesgo
edge_colors = [color_palette.get(data['tipo_de_riesgo'], 'black') for u, v, data in G.edges(data=True)]

# Dibujar el grafo
fig, ax = ox.plot_graph(
    G,
    node_size=0,
    edge_color=edge_colors,
    edge_linewidth=1, # Grosor de línea uniforme para claridad
    figsize=(20, 20),
    show=False,
    close=False
)

# Crear y añadir la leyenda al mapa
import matplotlib.patches as mpatches
legend_patches = [mpatches.Patch(color=c, label=l) for l, c in color_palette.items() if l in tipos_encontrados and l != "Ninguno"]
ax.legend(handles=legend_patches, loc='lower right', fontsize='large', title='Tipos de Riesgo', frameon=True, facecolor='white', framealpha=0.9)
ax.set_title('Mapa Detallado de Riesgos y Puntos de Incertidumbre en Tacna', fontsize=20)

# Mostrar el mapa final
plt.show()

print("\n--- ¡TRABAJO DE LUZ COMPLETADO Y DEMOSTRADO! ---")

# ========================================================== #
# MÓDULO DE RUTEO (EDITH) - VERSIÓN CORREGIDA Y COMPLETA      #
# ASEGÚRATE DE EJECUTAR ESTA CELDA PRIMERO                   #
# ========================================================== #

from queue import PriorityQueue
from geopy.distance import geodesic
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# --- Funciones Auxiliares y de Costo ---

def formatear_tiempo(segundos):
    if segundos == float('inf'):
        return "Inalcanzable"
    minutos = int(segundos // 60)
    resto_segundos = int(segundos % 60)
    return f"{minutos} min {resto_segundos} s"

def heuristica_geodesica(nodo_actual, nodo_destino, G, velocidad_max_kmh=50):
    velocidad_max_mps = velocidad_max_kmh * 1000 / 3600
    coord1 = (G.nodes[nodo_actual]['y'], G.nodes[nodo_actual]['x'])
    coord2 = (G.nodes[nodo_destino]['y'], G.nodes[nodo_destino]['x'])
    distancia_m = geodesic(coord1, coord2).meters
    return distancia_m / velocidad_max_mps

def costo_rapido(mu):
    return mu

def costo_seguro(mu, sigma, k):
    return mu + k * sigma

# --- Algoritmo A* Adaptado ---

def a_estrella_ruteo(G, origen, destino, tipo='rapido', k=1.5):
    frontera = PriorityQueue()
    frontera.put((0, origen))
    came_from = {origen: None}
    costo_acumulado = {origen: 0}

    while not frontera.empty():
        _, actual = frontera.get()
        if actual == destino:
            break
        for vecino in G.neighbors(actual):
            datos_arco = G.get_edge_data(actual, vecino)[0]
            mu = datos_arco.get('mu', 1)
            sigma = datos_arco.get('sigma', 0.1)
            costo_paso = costo_rapido(mu) if tipo == 'rapido' else costo_seguro(mu, sigma, k)
            nuevo_costo = costo_acumulado[actual] + costo_paso
            if vecino not in costo_acumulado or nuevo_costo < costo_acumulado[vecino]:
                costo_acumulado[vecino] = nuevo_costo
                h = heuristica_geodesica(vecino, destino, G)
                prioridad = nuevo_costo + h
                frontera.put((prioridad, vecino))
                came_from[vecino] = actual

    if destino not in came_from:
        return [], float('inf')
    ruta = []
    nodo = destino
    while nodo is not None:
        ruta.append(nodo)
        nodo = came_from.get(nodo)
    ruta.reverse()
    return ruta, costo_acumulado.get(destino, float('inf'))

# --- Función para Calcular Tiempo Real (LA QUE FALTABA) ---

def calcular_tiempo_real_ruta(G, ruta):
    tiempo_total = 0
    if not ruta:
        return 0
    for i in range(len(ruta) - 1):
        nodo_origen = ruta[i]
        nodo_destino = ruta[i+1]
        try:
            mu_arco = G.get_edge_data(nodo_origen, nodo_destino)[0]['mu']
            tiempo_total += mu_arco
        except (KeyError, IndexError):
            pass
    return tiempo_total

print("✅ Módulo de ruteo (EDITH) definido y listo.")

# ========================================================== #
# INTERFAZ INTERACTIVA DE NOEMÍ - SIMULACIÓN EN COLAB        #
# EJECUTA ESTA CELDA DESPUÉS DE LA ANTERIOR                  #
# ========================================================== #

import ipywidgets as widgets
from IPython.display import display, clear_output
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# --- 1. Creación de los Componentes de la Interfaz (Widgets) ---
print("Preparando UI interactiva...")

nodo_ids = list(G.nodes)
nodo_opciones = [(f"Nodo {i} ({nodo})", nodo) for i, nodo in enumerate(nodo_ids[:200])]

origen_widget = widgets.Dropdown(options=nodo_opciones, value=nodo_ids[10], description='Origen:', style={'description_width': 'initial'}, layout={'width': '400px'})
destino_widget = widgets.Dropdown(options=nodo_opciones, value=nodo_ids[150], description='Destino:', style={'description_width': 'initial'}, layout={'width': '400px'})
k_widget = widgets.FloatSlider(value=3.0, min=0.0, max=10.0, step=0.5, description='Aversión al Riesgo (k):', style={'description_width': 'initial'}, readout_format='.1f', continuous_update=False)
calculate_button = widgets.Button(description="Calcular Rutas", button_style='success', tooltip='Haz clic para encontrar la ruta rápida y la segura', icon='road')
output_area = widgets.Output()

# --- 2. Lógica de Ejecución que se activa con el botón ---
def on_calculate_button_clicked(b):
    with output_area:
        clear_output(wait=True)
        origen = origen_widget.value
        destino = destino_widget.value
        k_riesgo = k_widget.value

        if origen == destino:
            print("❌ Error: El origen y el destino no pueden ser el mismo.")
            return

        print(f"Buscando rutas desde el nodo {origen} al {destino} con k={k_riesgo}...")

        # Calcular ambas rutas
        ruta_rapida, costo_rapida = a_estrella_ruteo(G, origen, destino, tipo='rapido')
        ruta_segura, costo_abstracto_segura = a_estrella_ruteo(G, origen, destino, tipo='seguro', k=k_riesgo)

        # Usar la función que ahora sí está definida
        tiempo_real_rapida = costo_rapida
        tiempo_real_segura = calcular_tiempo_real_ruta(G, ruta_segura)

        print("\n--- RESULTADOS DE LA SIMULACIÓN ---")
        print(f"🟢 RUTA RÁPIDA: {len(ruta_rapida)} nodos, Tiempo estimado: {formatear_tiempo(tiempo_real_rapida)}")
        print(f"🔴 RUTA SEGURA:  {len(ruta_segura)} nodos, Tiempo estimado: {formatear_tiempo(tiempo_real_segura)}")

        if ruta_rapida != ruta_segura:
            print("\n✅ Las rutas son diferentes.")
        else:
            print("\nℹ️ Ambas rutas son idénticas con la configuración actual.")

        # Generar visualización
        fig, ax = ox.plot_graph(G, node_size=0, edge_color='lightgray', edge_linewidth=0.5, show=False, close=False, figsize=(14, 14))
        if ruta_segura:
            ox.plot_graph_route(G, route=ruta_segura, route_color='red', route_linewidth=3, ax=ax, show=False, close=False)
        if ruta_rapida:
            ox.plot_graph_route(G, route=ruta_rapida, route_color='lime', route_linewidth=4.5, ax=ax, show=False, close=False)

        ax.set_title(f'Comparación de Rutas (k={k_riesgo})', fontsize=20)
        leyenda_handles = [Line2D([0], [0], color='lime', lw=4, label='Ruta Rápida'), Line2D([0], [0], color='red', lw=3, label='Ruta Segura')]
        ax.legend(handles=leyenda_handles, loc='best', fontsize='large', frameon=True)
        plt.show()

# --- 3. Conectar el botón a la función y mostrar la interfaz ---
calculate_button.on_click(on_calculate_button_clicked)
print("\nControles de Simulación:")
display(origen_widget, destino_widget, k_widget, calculate_button, output_area)

# Opcional: Ejecutar un cálculo inicial al cargar la celda
on_calculate_button_clicked(None)

# ====================================================================== #
# INTERFAZ INTERACTIVA DE NOEMÍ - VERSIÓN FINAL Y ROBUSTA CON FOLIUM    #
# ====================================================================== #

import ipywidgets as widgets
from IPython.display import display, clear_output
import folium

# --- 1. Creación de los Componentes de la Interfaz (Widgets) ---
print("Preparando UI interactiva con mapa Folium...")

nodo_ids = list(G.nodes)
nodo_opciones = [(f"Nodo {i} ({nodo})", nodo) for i, nodo in enumerate(nodo_ids[:200])]

origen_widget = widgets.Dropdown(options=nodo_opciones, value=nodo_ids[2], description='Origen:', style={'description_width': 'initial'}, layout={'width': '400px'})
destino_widget = widgets.Dropdown(options=nodo_opciones, value=nodo_ids[150], description='Destino:', style={'description_width': 'initial'}, layout={'width': '400px'})
k_widget = widgets.FloatSlider(value=3.0, min=0.0, max=10.0, step=0.5, description='Aversión al Riesgo (k):', style={'description_width': 'initial'}, readout_format='.1f', continuous_update=False)
calculate_button = widgets.Button(description="Calcular Rutas", button_style='success', tooltip='Haz clic para encontrar la ruta rápida y la segura', icon='road')
output_area = widgets.Output()


# --- 2. Lógica de Ejecución que se activa con el botón ---
def on_calculate_button_clicked(b):
    with output_area:
        clear_output(wait=True)
        origen = origen_widget.value
        destino = destino_widget.value
        k_riesgo = k_widget.value

        if origen == destino:
            print("❌ Error: El origen y el destino no pueden ser el mismo.")
            return

        print(f"Buscando rutas desde el nodo {origen} al {destino} con k={k_riesgo}...")

        ruta_rapida, costo_rapida = a_estrella_ruteo(G, origen, destino, tipo='rapido')
        ruta_segura, costo_abstracto_segura = a_estrella_ruteo(G, origen, destino, tipo='seguro', k=k_riesgo)

        tiempo_real_rapida = costo_rapida
        tiempo_real_segura = calcular_tiempo_real_ruta(G, ruta_segura)

        print("\n--- RESULTADOS DE LA SIMULACIÓN ---")
        print(f"🟢 RUTA RÁPIDA: {len(ruta_rapida)} nodos, Tiempo estimado: {formatear_tiempo(tiempo_real_rapida)}")
        print(f"🔴 RUTA SEGURA:  {len(ruta_segura)} nodos, Tiempo estimado: {formatear_tiempo(tiempo_real_segura)}")

        if ruta_rapida != ruta_segura:
            print("\n✅ Las rutas son diferentes.")
        else:
            print("\nℹ️ Ambas rutas son idénticas con la configuración actual.")

        # =========================================================================
        # --- BLOQUE DE VISUALIZACIÓN CORREGIDO PARA EVITAR EL ERROR DE ASSERTION ---
        # =========================================================================

        if not ruta_rapida and not ruta_segura:
            print("\nNo se encontraron rutas, no se puede generar el mapa.")
            return

        # 1. Crear el mapa base, centrado en el origen
        location = (G.nodes[origen]['y'], G.nodes[origen]['x'])
        m = folium.Map(location=location, zoom_start=14, tiles="cartodbpositron")

        # 2. Dibujar la ruta segura (rojo) si existe
        if ruta_segura:
            gdf_segura = ox.routing.route_to_gdf(G, ruta_segura)
            folium.GeoJson(
                gdf_segura,
                style_function=lambda x: {'color': 'red', 'weight': 6, 'opacity': 0.8},
                tooltip=f"<b>Ruta Segura</b><br>Tiempo: {formatear_tiempo(tiempo_real_segura)}"
            ).add_to(m)

        # 3. Dibujar la ruta rápida (verde) si existe
        if ruta_rapida:
            gdf_rapida = ox.routing.route_to_gdf(G, ruta_rapida)
            folium.GeoJson(
                gdf_rapida,
                style_function=lambda x: {'color': 'lime', 'weight': 6, 'opacity': 0.8},
                tooltip=f"<b>Ruta Rápida</b><br>Tiempo: {formatear_tiempo(tiempo_real_rapida)}"
            ).add_to(m)

        # 4. Añadir marcadores para el origen y el destino
        folium.Marker(
            location=(G.nodes[origen]['y'], G.nodes[origen]['x']),
            popup=f"<b>Origen</b><br>Nodo: {origen}",
            icon=folium.Icon(color='green', icon='play', prefix='fa')
        ).add_to(m)

        folium.Marker(
            location=(G.nodes[destino]['y'], G.nodes[destino]['x']),
            popup=f"<b>Destino</b><br>Nodo: {destino}",
            icon=folium.Icon(color='red', icon='stop-circle', prefix='fa')
        ).add_to(m)

        # 5. Muestra el mapa interactivo
        display(m)


# --- 3. Conectar el botón a la función y mostrar la interfaz ---
calculate_button.on_click(on_calculate_button_clicked)
print("\nControles de Simulación:")
display(origen_widget, destino_widget, k_widget, calculate_button, output_area)

# Opcional: Ejecutar un cálculo inicial al cargar la celda
on_calculate_button_clicked(None)

# ============================
# INTERFAZ DE NOEMÍ – SIMULACIÓN EN COLAB
# ============================

import ipywidgets as widgets
from IPython.display import display, clear_output

# Dropdown para seleccionar origen y destino
print("Preparando UI interactiva...")

nodo_ids = list(G.nodes)
nodo_opciones = [(f"Nodo {i}", nodo) for i, nodo in enumerate(nodo_ids[:100])]

origen_widget = widgets.Dropdown(
    options=nodo_opciones,
    description='Origen:',
    value=nodo_ids[10]
)

destino_widget = widgets.Dropdown(
    options=nodo_opciones,
    description='Destino:',
    value=nodo_ids[30]
)

# Slider para parámetro de riesgo k
k_widget = widgets.FloatSlider(
    value=1.5,
    min=3.0,
    max=15.0,
    step=1.1,
    description='Riesgo (k):',
    continuous_update=False
)

# Selector de tipo de ruta
tipo_widget = widgets.ToggleButtons(
    options=[('Rápida', 'rapido'), ('Segura', 'seguro')],
    description='Tipo de Ruta:'
)

# Botón para ejecutar ruteo
boton_ejecutar = widgets.Button(description="Calcular Ruta", button_style='success')

# Output para mostrar resultados
salida = widgets.Output()

# Lógica de ejecución
def ejecutar_ruteo(b):
    with salida:
        clear_output()
        origen = origen_widget.value
        destino = destino_widget.value
        tipo = tipo_widget.value
        k = k_widget.value

        print(f"\nCalculando ruta tipo: {tipo} (k={k})...")
        ruta, costo_total = a_estrella_ruteo(G, origen, destino, tipo=tipo, k=k)

        print(f"Ruta con {len(ruta)} nodos.")
        print(f"Tiempo total estimado: {formatear_tiempo(costo_total)}")

        # Visualizar la ruta
        fig, ax = ox.plot_graph(
            G,
            node_size=0,
            edge_color='lightgray',
            edge_linewidth=0.5,
            show=False,
            close=False,
            figsize=(14, 14)
        )
        ox.plot_graph_route(
            G,
            route=ruta,
            route_color='blue',
            route_linewidth=4,
            ax=ax,
            show=False,
            close=False
        )
        titulo = f"Ruta {tipo.capitalize()} (k={k}) – {formatear_tiempo(costo_total)}"
        ax.set_title(titulo, fontsize=14)
        plt.show()

# Conectar botón a función
boton_ejecutar.on_click(ejecutar_ruteo)

ax.set_title('Comparación: Ruta Rápida (verde) vs Segura (rojo)', fontsize=16)
leyenda = [
    Line2D([0], [0], color='green', lw=4, label='Ruta rápida'),
    Line2D([0], [0], color='red', lw=2.5, label='Ruta segura')
]
ax.legend(handles=leyenda, loc='lower right')

# Mostrar interfaz
display(origen_widget, destino_widget, k_widget, tipo_widget, boton_ejecutar, salida)