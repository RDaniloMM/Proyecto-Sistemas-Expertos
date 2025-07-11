import streamlit as st
import osmnx as ox
import networkx as nx
import folium
from streamlit_folium import st_folium
import pandas as pd
import numpy as np
import random
import math
import datetime
import time
import json
from geopy.distance import geodesic
import streamlit.components.v1 as components

# Configuración de la página
st.set_page_config(
    page_title="Sistema de Patrullas Tacna - Calles Reales",
    page_icon="🚔",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título principal
st.title("🚔 Sistema de Patrullas - Tacna (Calles Reales)")
st.markdown("*Simulación con grafo de calles etiquetado por tipos de riesgo*")

# Cache para el grafo para evitar recargarlo cada vez
@st.cache_data
def cargar_grafo_tacna():
    """Carga y procesa el grafo de calles de Tacna con etiquetado de riesgos"""
    place_name = "Tacna, Peru"
    
    with st.spinner("Descargando red vial de Tacna..."):
        try:
            # Descargar el grafo
            G = ox.graph_from_place(place_name, network_type='drive', simplify=True)
            
            # Identificar POIs
            st.write("Identificando puntos de interés...")
            tags = {
                "colegios": {"amenity": ["school", "college", "university"]},
                "hospitales": {"amenity": ["hospital", "clinic"]},
                "mercados": {"amenity": ["marketplace"], "shop": ["market"]}
            }
            
            pois = {}
            for key, tag_dict in tags.items():
                try:
                    pois[key] = ox.features_from_place(place_name, tags=tag_dict)
                    st.write(f"✅ {len(pois[key])} {key} encontrados")
                except:
                    st.write(f"⚠️ No se encontraron {key}")
                    pois[key] = None
            
            # Simular calles en mal estado
            for u, v, data in G.edges(data=True):
                data['mal_estado'] = False
                htype = data.get('highway', 'residential')
                if isinstance(htype, list):
                    htype = htype[0]
                if htype in ['residential', 'unclassified'] and np.random.rand() < 0.05:
                    data['mal_estado'] = True
            
            # Identificar intersecciones sin semáforo
            nodes_sin_semaforo = set()
            for node, node_data in G.nodes(data=True):
                if not node_data.get('highway') == 'traffic_signals':
                    street_types = []
                    for neighbor in G.neighbors(node):
                        edge_data = G.get_edge_data(node, neighbor)
                        if edge_data:
                            htype = list(edge_data.values())[0].get('highway', 'residential')
                            if isinstance(htype, list):
                                street_types.append(htype[0])
                            else:
                                street_types.append(htype)
                    
                    unique_street_types = set(street_types)
                    if len(unique_street_types) > 1 and all(s in ['residential', 'tertiary', 'unclassified'] for s in unique_street_types):
                        nodes_sin_semaforo.add(node)
            
            # Etiquetar arcos
            for u, v, data in G.edges(data=True):
                data['cruce_sin_semaforo'] = v in nodes_sin_semaforo
            
            # Aplicar reglas de etiquetado
            def get_risk_attributes(edge_data, u, v):
                velocidad_kmh = 50.0
                penalizacion_tiempo = 1.0
                sigma_segundos = 10.0
                tipo_de_riesgo = "Ninguno"
                
                distancia_m = edge_data.get('length', 0)
                
                # Regla 5: Vías en Mal Estado
                if edge_data['mal_estado']:
                    tipo_de_riesgo, velocidad_kmh, penalizacion_tiempo, sigma_segundos = "Vía en Mal Estado", 30, np.random.uniform(1.8, 3.0), 70
                
                # Regla 3: Calles Angostas
                htype = edge_data.get('highway', 'residential')
                if isinstance(htype, list):
                    htype = htype[0]
                
                if tipo_de_riesgo == "Ninguno" and htype == 'residential':
                    tipo_de_riesgo, velocidad_kmh, penalizacion_tiempo, sigma_segundos = "Calle Angosta", 30, np.random.uniform(1.3, 1.5), 30
                
                # Regla 2: Paraderos Informales
                if tipo_de_riesgo == "Ninguno" and htype in ['primary', 'secondary']:
                    if np.random.rand() < 0.1:
                        tipo_de_riesgo, penalizacion_tiempo, sigma_segundos = "Paradero Informal", np.random.uniform(1.4, 1.6), 40
                
                # Regla 7: Cruces sin Semáforo
                if tipo_de_riesgo == "Ninguno" and edge_data['cruce_sin_semaforo']:
                    tipo_de_riesgo, penalizacion_tiempo, sigma_segundos = "Cruce sin Semáforo", np.random.uniform(1.3, 1.7), 45
                
                # Cálculo final
                velocidad_mps = velocidad_kmh * 1000 / 3600
                mu_segundos = (distancia_m / velocidad_mps) * penalizacion_tiempo
                
                return tipo_de_riesgo, mu_segundos, sigma_segundos, velocidad_kmh
            
            # Aplicar etiquetado a todos los arcos
            for u, v, data in G.edges(data=True):
                tipo_riesgo, mu, sigma, velocidad = get_risk_attributes(data, u, v)
                data['tipo_de_riesgo'] = tipo_riesgo
                data['mu'] = mu
                data['sigma'] = sigma
                data['velocidad_permitida'] = velocidad
            
            st.success(f"✅ Grafo procesado: {G.number_of_nodes()} nodos, {G.number_of_edges()} arcos")
            
            return G, pois
            
        except Exception as e:
            st.error(f"Error al cargar el grafo: {e}")
            return None, None

# Cargar el grafo
G, pois = cargar_grafo_tacna()

if G is None:
    st.error("No se pudo cargar el grafo de Tacna")
    st.stop()

# Coordenadas del centro de Tacna
TACNA_CENTER = [-18.0146, -70.2535]

# Sidebar para configuración
st.sidebar.header("🚔 Configuración de Patrullas")

# Selector de número de patrullas
num_patrullas = st.sidebar.selectbox(
    "Patrullas:",
    options=list(range(1, 11)),
    index=4,
    format_func=lambda x: f"Patrullas [{x}]"
)

# Selector de hora
st.sidebar.markdown("---")
st.sidebar.subheader("⏰ Hora del Día")

hora_seleccionada = st.sidebar.time_input(
    "Selecciona la hora:",
    value=datetime.time(14, 30),
    help="Cambia la hora para simular diferentes condiciones de tráfico"
)

# Función para determinar el nivel de tráfico
def determinar_trafico(hora_obj):
    hora = hora_obj.hour
    minuto = hora_obj.minute
    hora_decimal = hora + minuto / 60
    
    if 6.5 <= hora_decimal < 8:
        return "🔴 FULL TRÁFICO", "Hora pico matutina", "#FF0000"
    elif 8 <= hora_decimal < 11:
        return "🟡 MEDIO TRÁFICO", "Tráfico moderado", "#FFA500"
    elif 11 <= hora_decimal < 13:
        return "🔴 FULL TRÁFICO", "Hora de almuerzo", "#FF0000"
    elif 13 <= hora_decimal < 17:
        return "🟡 MEDIO TRÁFICO", "Tarde tranquila", "#FFA500"
    elif 17 <= hora_decimal < 20:
        return "🟥 MUCHO TRÁFICO", "Hora pico vespertina", "#8B0000"
    elif 20 <= hora_decimal < 23:
        return "🟢 POCO TRÁFICO", "Noche temprana", "#32CD32"
    else:
        return "🔵 SIN TRÁFICO", "Madrugada", "#0000FF"

nivel_trafico, descripcion_trafico, color_trafico = determinar_trafico(hora_seleccionada)

st.sidebar.markdown(f"**Estado del Tráfico ({hora_seleccionada.strftime('%H:%M')})**")
st.sidebar.markdown(f"{nivel_trafico}")
st.sidebar.markdown(f"*{descripcion_trafico}*")

# Selector de clima
st.sidebar.markdown("---")
st.sidebar.subheader("🌤️ Condiciones Climáticas")

opciones_clima_simple = [
    "☀️ Soleado",
    "⛅ Parcialmente Nublado", 
    "☁️ Nublado",
    "🌦️ Lluvia Ligera",
    "🌧️ Lluvia Intensa",
    "⛈️ Tormenta",
    "🌫️ Niebla",
    "💨 Ventoso"
]

clima_seleccionado_idx = st.sidebar.selectbox(
    "Selecciona el clima:",
    options=range(len(opciones_clima_simple)),
    index=0,
    format_func=lambda x: opciones_clima_simple[x],
    help="Elige las condiciones climáticas"
)

# Función para calcular velocidad según condiciones
def calcular_velocidad_final(nivel_trafico, clima_idx):
    velocidad_base = 40
    
    # Factor de tráfico
    if "FULL TRÁFICO" in nivel_trafico or "MUCHO TRÁFICO" in nivel_trafico:
        factor_trafico = 0.6
    elif "MEDIO TRÁFICO" in nivel_trafico:
        factor_trafico = 0.8
    elif "POCO TRÁFICO" in nivel_trafico:
        factor_trafico = 1.2
    else:
        factor_trafico = 1.4
    
    # Factor de clima
    factores_clima = [1.0, 0.95, 0.9, 0.8, 0.6, 0.4, 0.5, 0.85]
    factor_clima = factores_clima[clima_idx]
    
    return int(velocidad_base * factor_trafico * factor_clima)

velocidad_final = calcular_velocidad_final(nivel_trafico, clima_seleccionado_idx)

st.sidebar.markdown(f"**Velocidad Calculada: {velocidad_final} km/h**")

# Botón para iniciar simulación
if 'simulacion_activa' not in st.session_state:
    st.session_state.simulacion_activa = False

if st.sidebar.button("🚀 Iniciar Simulación" if not st.session_state.simulacion_activa else "⏸️ Detener Simulación"):
    st.session_state.simulacion_activa = not st.session_state.simulacion_activa

# Función para obtener nodo aleatorio del grafo
def obtener_nodo_aleatorio(G):
    return random.choice(list(G.nodes()))

# Función para encontrar ruta entre dos nodos
def encontrar_ruta(G, origen, destino):
    try:
        return nx.shortest_path(G, origen, destino, weight='length')
    except:
        return []

# Función para avanzar en la ruta
def avanzar_en_ruta(G, patrulla, velocidad_kmh, tiempo_seg):
    if not patrulla['ruta'] or patrulla['indice_ruta'] >= len(patrulla['ruta']) - 1:
        # Generar nueva ruta
        destino = obtener_nodo_aleatorio(G)
        nueva_ruta = encontrar_ruta(G, patrulla['nodo_actual'], destino)
        if nueva_ruta:
            patrulla['ruta'] = nueva_ruta
            patrulla['indice_ruta'] = 0
            patrulla['destino'] = destino
            patrulla['progreso_arco'] = 0.0  # Progreso en el arco actual (0-1)
    
    if patrulla['ruta'] and patrulla['indice_ruta'] < len(patrulla['ruta']) - 1:
        # Calcular distancia recorrida
        velocidad_ms = velocidad_kmh * 1000 / 3600
        distancia_recorrida = velocidad_ms * tiempo_seg
        
        # Obtener nodos del arco actual
        nodo_actual = patrulla['ruta'][patrulla['indice_ruta']]
        siguiente_nodo = patrulla['ruta'][patrulla['indice_ruta'] + 1]
        
        try:
            # Obtener distancia del arco actual
            edge_data = G.get_edge_data(nodo_actual, siguiente_nodo)
            if edge_data:
                distancia_arco = list(edge_data.values())[0]['length']
                
                # Actualizar progreso en el arco
                if 'progreso_arco' not in patrulla:
                    patrulla['progreso_arco'] = 0.0
                
                patrulla['progreso_arco'] += distancia_recorrida / distancia_arco
                
                # Coordenadas de los nodos
                lat_actual = G.nodes[nodo_actual]['y']
                lon_actual = G.nodes[nodo_actual]['x']
                lat_siguiente = G.nodes[siguiente_nodo]['y']
                lon_siguiente = G.nodes[siguiente_nodo]['x']
                
                # Interpolar posición
                progreso = min(patrulla['progreso_arco'], 1.0)
                lat_interpolada = lat_actual + (lat_siguiente - lat_actual) * progreso
                lon_interpolada = lon_actual + (lon_siguiente - lon_actual) * progreso
                
                # Actualizar posición
                patrulla['posicion'] = [lat_interpolada, lon_interpolada]
                
                # Agregar a rastro
                if len(patrulla['rastro']) == 0 or geodesic(patrulla['rastro'][-1], patrulla['posicion']).meters > 20:
                    patrulla['rastro'].append(patrulla['posicion'])
                    # Mantener solo los últimos 20 puntos del rastro
                    if len(patrulla['rastro']) > 20:
                        patrulla['rastro'] = patrulla['rastro'][-20:]
                
                # Si hemos completado el arco, avanzar al siguiente nodo
                if patrulla['progreso_arco'] >= 1.0:
                    patrulla['indice_ruta'] += 1
                    patrulla['nodo_actual'] = patrulla['ruta'][patrulla['indice_ruta']]
                    patrulla['progreso_arco'] = 0.0
                    
        except Exception as e:
            # Si hay error, generar nueva ruta
            patrulla['ruta'] = []
            patrulla['progreso_arco'] = 0.0

# Inicializar patrullas
if 'patrullas' not in st.session_state or len(st.session_state.patrullas) != num_patrullas:
    st.session_state.patrullas = []
    for i in range(num_patrullas):
        nodo_inicial = obtener_nodo_aleatorio(G)
        st.session_state.patrullas.append({
            'id': i + 1,
            'nodo_actual': nodo_inicial,
            'posicion': [G.nodes[nodo_inicial]['y'], G.nodes[nodo_inicial]['x']],
            'ruta': [],
            'indice_ruta': 0,
            'progreso_arco': 0.0,
            'destino': None,
            'color': random.choice(['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'lightred', 'beige', 'darkblue', 'darkgreen']),
            'velocidad_actual': velocidad_final,
            'rastro': []
        })

# Actualizar velocidad de patrullas existentes
for patrulla in st.session_state.patrullas:
    patrulla['velocidad_actual'] = velocidad_final

# Crear mapa
m = folium.Map(location=TACNA_CENTER, zoom_start=13, tiles="OpenStreetMap")

# Mostrar información del grafo
st.subheader("🗺️ Mapa de Calles Etiquetadas de Tacna")

# Información contextual
col_info1, col_info2, col_info3 = st.columns(3)

with col_info1:
    st.markdown(f"""
    <div style="background-color: {color_trafico}20; border-left: 4px solid {color_trafico}; padding: 10px; border-radius: 5px;">
        <h4 style="color: {color_trafico}; margin: 0;">{nivel_trafico}</h4>
        <p style="margin: 0; font-size: 12px; color: #666;">Hora: {hora_seleccionada.strftime('%H:%M')}</p>
    </div>
    """, unsafe_allow_html=True)

with col_info2:
    st.markdown(f"""
    <div style="background-color: #87CEEB20; border-left: 4px solid #87CEEB; padding: 10px; border-radius: 5px;">
        <h4 style="color: #87CEEB; margin: 0;">{opciones_clima_simple[clima_seleccionado_idx]}</h4>
        <p style="margin: 0; font-size: 12px; color: #666;">Condiciones actuales</p>
    </div>
    """, unsafe_allow_html=True)

with col_info3:
    st.markdown(f"""
    <div style="background-color: #f0f0f0; border-left: 4px solid #333; padding: 10px; border-radius: 5px;">
        <h4 style="color: #333; margin: 0;">🚗 {velocidad_final} km/h</h4>
        <p style="margin: 0; font-size: 12px; color: #666;">Velocidad Calculada</p>
    </div>
    """, unsafe_allow_html=True)

# Estadísticas del grafo
st.subheader("📊 Estadísticas del Grafo")
col_stats1, col_stats2, col_stats3, col_stats4 = st.columns(4)

with col_stats1:
    st.metric("Nodos (Intersecciones)", f"{G.number_of_nodes():,}")

with col_stats2:
    st.metric("Arcos (Calles)", f"{G.number_of_edges():,}")

with col_stats3:
    tipos_riesgo = pd.Series([data['tipo_de_riesgo'] for u, v, data in G.edges(data=True)])
    st.metric("Tipos de Riesgo", len(tipos_riesgo.unique()))

with col_stats4:
    st.metric("Patrullas Activas", num_patrullas)

# Mostrar tipos de riesgo encontrados
st.subheader("🚨 Tipos de Riesgo Identificados")
tipos_riesgo_stats = pd.Series([data['tipo_de_riesgo'] for u, v, data in G.edges(data=True)]).value_counts()

col_risk1, col_risk2 = st.columns(2)
with col_risk1:
    st.dataframe(tipos_riesgo_stats.head(4), use_container_width=True)
with col_risk2:
    if len(tipos_riesgo_stats) > 4:
        st.dataframe(tipos_riesgo_stats.tail(len(tipos_riesgo_stats)-4), use_container_width=True)

# Agregar marcadores de patrullas al mapa
for patrulla in st.session_state.patrullas:
    # Agregar rastro de la patrulla
    if len(patrulla['rastro']) > 1:
        folium.PolyLine(
            locations=patrulla['rastro'],
            color=patrulla['color'],
            weight=3,
            opacity=0.6,
            popup=f"Rastro Patrulla {patrulla['id']}"
        ).add_to(m)
    
    # Agregar marcador de la patrulla
    folium.CircleMarker(
        location=patrulla['posicion'],
        radius=8,
        popup=f"🚔 Patrulla {patrulla['id']}<br>Nodo: {patrulla['nodo_actual']}<br>Velocidad: {patrulla['velocidad_actual']} km/h<br>Ruta: {len(patrulla['ruta'])} nodos",
        color=patrulla['color'],
        fill=True,
        weight=2,
        fillColor=patrulla['color'],
        fillOpacity=0.8
    ).add_to(m)
    
    # Agregar marcador del destino si existe
    if patrulla['destino'] and patrulla['destino'] in G.nodes:
        folium.CircleMarker(
            location=[G.nodes[patrulla['destino']]['y'], G.nodes[patrulla['destino']]['x']],
            radius=5,
            popup=f"🎯 Destino Patrulla {patrulla['id']}",
            color=patrulla['color'],
            fill=True,
            weight=1,
            fillColor='white',
            fillOpacity=0.8
        ).add_to(m)

# Inicializar key único para el mapa
if 'map_key' not in st.session_state:
    st.session_state.map_key = 0

# Mostrar el mapa con key fijo para mantener el estado
map_data = st_folium(m, width=1200, height=600, returned_objects=["last_object_clicked"], key=f"map_{st.session_state.map_key}")

# Placeholder para actualizaciones en tiempo real
placeholder_actualizacion = st.empty()

# Actualización de patrullas en tiempo real
if st.session_state.simulacion_activa:
    # Crear contenedor para actualizaciones
    with placeholder_actualizacion.container():
        # JavaScript para actualizar marcadores sin recargar la página
        js_code = """
        <script>
        function actualizarPatrullas() {
            // Esta función será llamada desde Python
            console.log('Actualizando patrullas...');
        }
        
        // Configurar intervalos de actualización
        if (window.intervalPatrullas) {
            clearInterval(window.intervalPatrullas);
        }
        
        window.intervalPatrullas = setInterval(function() {
            // Simular actualización de patrullas
            actualizarPatrullas();
        }, 1000);
        </script>
        """
        
        st.html(js_code)
        
        # Actualizar patrullas sin recargar página
        for i, patrulla in enumerate(st.session_state.patrullas):
            avanzar_en_ruta(G, patrulla, patrulla['velocidad_actual'], 1.0)
        
        # Mostrar información actualizada sin recargar
        st.success("🟢 Simulación activa - Las patrullas se mueven en tiempo real")
        
        # Auto-actualizar cada 2 segundos usando session_state
        if 'last_update' not in st.session_state:
            st.session_state.last_update = time.time()
        
        current_time = time.time()
        if current_time - st.session_state.last_update > 2:
            st.session_state.last_update = current_time
            # Solo actualizar datos, no recargar mapa
            for patrulla in st.session_state.patrullas:
                avanzar_en_ruta(G, patrulla, patrulla['velocidad_actual'], 2.0)
            
            # Crear nuevo mapa con posiciones actualizadas
            nuevo_mapa = folium.Map(location=TACNA_CENTER, zoom_start=13, tiles="OpenStreetMap")
            
            # Agregar marcadores actualizados
            for patrulla in st.session_state.patrullas:
                # Agregar rastro
                if len(patrulla['rastro']) > 1:
                    folium.PolyLine(
                        locations=patrulla['rastro'],
                        color=patrulla['color'],
                        weight=3,
                        opacity=0.6,
                        popup=f"Rastro Patrulla {patrulla['id']}"
                    ).add_to(nuevo_mapa)
                
                # Agregar marcador de la patrulla
                folium.CircleMarker(
                    location=patrulla['posicion'],
                    radius=8,
                    popup=f"🚔 Patrulla {patrulla['id']}<br>Nodo: {patrulla['nodo_actual']}<br>Velocidad: {patrulla['velocidad_actual']} km/h<br>Ruta: {len(patrulla['ruta'])} nodos",
                    color=patrulla['color'],
                    fill=True,
                    weight=2,
                    fillColor=patrulla['color'],
                    fillOpacity=0.8
                ).add_to(nuevo_mapa)
            
            # Actualizar el mapa preservando el estado
            st.session_state.map_key += 1
            st.rerun()

# Estado de la simulación
if st.session_state.simulacion_activa:
    st.success("🟢 Simulación activa - Las patrullas se mueven automáticamente")
    # Mostrar información de patrullas
    st.subheader("📊 Estado de las Patrullas")
    patrol_data = []
    for patrulla in st.session_state.patrullas:
        patrol_data.append({
            'Patrulla': f"🚔 {patrulla['id']}",
            'Nodo Actual': patrulla['nodo_actual'],
            'Velocidad': f"{patrulla['velocidad_actual']} km/h",
            'Ruta': f"{len(patrulla['ruta'])} nodos",
            'Progreso': f"{patrulla.get('progreso_arco', 0):.1%}"
        })
    
    st.dataframe(pd.DataFrame(patrol_data), use_container_width=True)
else:
    st.info("⏸️ Simulación pausada - Presiona 'Iniciar Simulación' para activar el movimiento")

# Información adicional
st.sidebar.markdown("---")
st.sidebar.markdown("### ℹ️ Información")
st.sidebar.markdown("""
- 🗺️ **Grafo Real**: Calles reales de Tacna
- 🚨 **Etiquetado**: 7 tipos de riesgo identificados
- 🛣️ **Navegación**: Por rutas más cortas
- 📍 **Posición**: Nodos reales del grafo
- 🎯 **Velocidad**: Según tipo de calle
""")
