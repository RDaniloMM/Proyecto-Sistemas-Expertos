import streamlit as st
import osmnx as ox
import networkx as nx
import folium
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
    page_title="Patrullas en Tiempo Real - Tacna",
    page_icon="🚔",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título principal
st.title("🚔 Sistema de Patrullas en Tiempo Real - Tacna")
st.markdown("*Movimiento en tiempo real sin recargar la página*")

# Cache para el grafo
@st.cache_data
def cargar_grafo_tacna():
    """Carga el grafo de calles de Tacna usando OSMnx"""
    try:
        # Cargar el grafo de calles de Tacna con geometrías detalladas
        place = "Tacna, Peru"
        G = ox.graph_from_place(place, network_type='drive', simplify=False)
        
        # Convertir a no dirigido para calcular caminos
        G_undirected = G.to_undirected()
        
        # Agregar información de longitud a los edges
        for u, v, data in G.edges(data=True):
            if 'length' not in data:
                # Calcular longitud usando coordenadas
                start_coords = (G.nodes[u]['y'], G.nodes[u]['x'])
                end_coords = (G.nodes[v]['y'], G.nodes[v]['x'])
                data['length'] = geodesic(start_coords, end_coords).meters
        
        # Procesar geometrías de las aristas
        for u, v, data in G.edges(data=True):
            if 'geometry' in data:
                # Convertir geometría a lista de coordenadas [lat, lon]
                geometry = data['geometry']
                if hasattr(geometry, 'coords'):
                    coords = list(geometry.coords)
                    # Convertir de (lon, lat) a [lat, lon]
                    data['geometry_coords'] = [[lat, lon] for lon, lat in coords]
                else:
                    # Si no hay geometría, usar nodos extremos
                    start_node = G.nodes[u]
                    end_node = G.nodes[v]
                    data['geometry_coords'] = [
                        [start_node['y'], start_node['x']],
                        [end_node['y'], end_node['x']]
                    ]
            else:
                # Si no hay geometría, usar nodos extremos
                start_node = G.nodes[u]
                end_node = G.nodes[v]
                data['geometry_coords'] = [
                    [start_node['y'], start_node['x']],
                    [end_node['y'], end_node['x']]
                ]
        
        # Etiquetar calles con riesgos
        for u, v, data in G.edges(data=True):
            # Lógica simplificada de etiquetado
            if 'highway' in data:
                highway_type = data['highway']
                if highway_type in ['primary', 'secondary']:
                    data['risk_type'] = 'accidentes'
                elif highway_type in ['residential', 'living_street']:
                    data['risk_type'] = 'robos'
                elif highway_type in ['tertiary', 'unclassified']:
                    data['risk_type'] = 'vandalismo'
                else:
                    data['risk_type'] = 'otros'
            else:
                data['risk_type'] = 'otros'
        
        return G, G_undirected
    except Exception as e:
        st.error(f"Error al cargar el grafo: {e}")
        return None, None

# Función para obtener nodos aleatorios
def obtener_nodos_aleatorios(G, n):
    """Obtiene n nodos aleatorios del grafo"""
    nodes = list(G.nodes())
    return random.sample(nodes, min(n, len(nodes)))

# Función para calcular velocidad basada en tiempo y clima
def calcular_velocidad_base(time_of_day, weather):
    """Calcula velocidad base en km/h según hora y clima"""
    # Velocidad base en km/h
    base_speed = 40.0
    
    # Factor de tráfico según hora
    if 6 <= time_of_day <= 8 or 17 <= time_of_day <= 19:
        traffic_factor = 0.5  # Hora pico
    elif 22 <= time_of_day or time_of_day <= 5:
        traffic_factor = 1.2  # Madrugada
    else:
        traffic_factor = 1.0  # Normal
    
    # Factor climático
    weather_factors = {
        'soleado': 1.0,
        'nublado': 0.9,
        'lluvioso': 0.6,
        'neblina': 0.7
    }
    
    return base_speed * traffic_factor * weather_factors.get(weather, 1.0)

# Función para crear el mapa base
def crear_mapa_base(G, center_lat=-18.0137, center_lon=-70.2500):
    """Crea el mapa base con las calles de Tacna"""
    # Crear mapa
    m = folium.Map(location=[center_lat, center_lon], zoom_start=14)
    
    # Agregar calles coloreadas por tipo de riesgo
    colors = {
        'accidentes': 'red',
        'robos': 'orange',
        'vandalismo': 'yellow',
        'otros': 'blue'
    }
    
    for u, v, data in G.edges(data=True):
        start_coords = [G.nodes[u]['y'], G.nodes[u]['x']]
        end_coords = [G.nodes[v]['y'], G.nodes[v]['x']]
        risk_type = data.get('risk_type', 'otros')
        
        folium.PolyLine(
            locations=[start_coords, end_coords],
            color=colors.get(risk_type, 'blue'),
            weight=2,
            opacity=0.6
        ).add_to(m)
    
    return m

# Función para generar HTML con JavaScript personalizado
def generar_html_realtime(G, num_patrullas, velocidad_base):
    """Genera HTML con JavaScript para movimiento en tiempo real"""
    
    # Obtener nodos aleatorios para patrullas
    nodos_patrullas = obtener_nodos_aleatorios(G, num_patrullas)
    
    # Convertir grafo a formato JSON para JavaScript
    edges_data = []
    for u, v, data in G.edges(data=True):
        # Obtener geometría real de la calle
        geometry = data.get('geometry_coords', [])
        if not geometry:
            # Fallback: usar nodos extremos
            start_coords = [G.nodes[u]['y'], G.nodes[u]['x']]
            end_coords = [G.nodes[v]['y'], G.nodes[v]['x']]
            geometry = [start_coords, end_coords]
        
        edges_data.append({
            'source': u,
            'target': v,
            'length': data.get('length', 100),
            'risk_type': data.get('risk_type', 'otros'),
            'geometry': geometry  # Geometría real de la calle
        })
    
    nodes_data = {}
    for node, data in G.nodes(data=True):
        nodes_data[node] = {
            'lat': data['y'],
            'lon': data['x']
        }
    
    # Crear patrullas iniciales
    patrullas_data = []
    for i, node in enumerate(nodos_patrullas):
        patrullas_data.append({
            'id': i,
            'current_node': node,
            'target_node': random.choice(list(G.nodes())),
            'lat': G.nodes[node]['y'],
            'lon': G.nodes[node]['x'],
            'path': []
        })
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Patrullas en Tiempo Real</title>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
        <style>
            #map {{ height: 600px; width: 100%; }}
            .info-panel {{ 
                position: absolute; 
                top: 10px; 
                right: 10px; 
                background: white; 
                padding: 10px; 
                border-radius: 5px; 
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                z-index: 1000;
            }}
        </style>
    </head>
    <body>
        <div id="map"></div>
        <div class="info-panel">
            <h4>Estado de Patrullas</h4>
            <div id="patrol-info"></div>
            <div>Velocidad: {velocidad_base:.1f} km/h</div>
        </div>
        
        <script>
            // Datos del grafo
            const nodes = {json.dumps(nodes_data)};
            const edges = {json.dumps(edges_data)};
            const patrullas = {json.dumps(patrullas_data)};
            const velocidad = {velocidad_base};
            
            // Crear mapa
            const map = L.map('map').setView([-18.0137, -70.2500], 14);
            
            // Agregar capa base
            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                attribution: '© OpenStreetMap contributors'
            }}).addTo(map);
            
            // Colores por tipo de riesgo
            const colors = {{
                'accidentes': 'red',
                'robos': 'orange',
                'vandalismo': 'yellow',
                'otros': 'blue'
            }};
            
            // Dibujar calles con geometrías reales
            edges.forEach(edge => {{
                if (edge.geometry && edge.geometry.length > 0) {{
                    // Usar geometría real de la calle
                    L.polyline(edge.geometry, {{
                        color: colors[edge.risk_type] || 'blue',
                        weight: 2,
                        opacity: 0.6
                    }}).addTo(map);
                }} else {{
                    // Fallback: línea directa entre nodos
                    const start = nodes[edge.source];
                    const end = nodes[edge.target];
                    if (start && end) {{
                        L.polyline([
                            [start.lat, start.lon],
                            [end.lat, end.lon]
                        ], {{
                            color: colors[edge.risk_type] || 'blue',
                            weight: 2,
                            opacity: 0.6
                        }}).addTo(map);
                    }}
                }}
            }});
            
            // Crear marcadores de patrullas
            const patrolMarkers = {{}};
            const patrolPaths = {{}};
            
            patrullas.forEach(patrulla => {{
                // Marcador de patrulla más visible
                patrolMarkers[patrulla.id] = L.marker([patrulla.lat, patrulla.lon], {{
                    icon: L.divIcon({{
                        html: `<div style="background: red; color: white; border-radius: 50%; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; font-size: 18px; border: 2px solid white; box-shadow: 0 0 10px rgba(0,0,0,0.5);">🚔</div>`,
                        iconSize: [30, 30],
                        className: 'patrol-marker'
                    }})
                }}).addTo(map)
                .bindTooltip(`Patrulla ${{patrulla.id}}`, {{permanent: true, offset: [0, -20]}});
                
                // Línea de trayectoria más visible
                patrolPaths[patrulla.id] = L.polyline([], {{
                    color: 'red',
                    weight: 4,
                    opacity: 0.8,
                    dashArray: '10, 5'
                }}).addTo(map);
            }});
            
            // Crear índice de adyacencia para navegación rápida
            const adjacencyList = {{}};
            edges.forEach(edge => {{
                if (!adjacencyList[edge.source]) adjacencyList[edge.source] = [];
                if (!adjacencyList[edge.target]) adjacencyList[edge.target] = [];
                
                adjacencyList[edge.source].push({{
                    node: edge.target,
                    length: edge.length,
                    risk_type: edge.risk_type
                }});
                adjacencyList[edge.target].push({{
                    node: edge.source,
                    length: edge.length,
                    risk_type: edge.risk_type
                }});
            }});
            
            // Función para encontrar camino más corto usando Dijkstra
            function findShortestPath(start, end) {{
                const distances = {{}};
                const previous = {{}};
                const unvisited = new Set();
                
                // Inicializar distancias
                Object.keys(nodes).forEach(node => {{
                    distances[node] = node === start ? 0 : Infinity;
                    unvisited.add(node);
                }});
                
                while (unvisited.size > 0) {{
                    // Encontrar nodo no visitado con menor distancia
                    let current = null;
                    let minDistance = Infinity;
                    
                    for (const node of unvisited) {{
                        if (distances[node] < minDistance) {{
                            minDistance = distances[node];
                            current = node;
                        }}
                    }}
                    
                    if (current === null || distances[current] === Infinity) break;
                    
                    unvisited.delete(current);
                    
                    if (current === end) {{
                        // Reconstruir camino
                        const path = [];
                        let temp = end;
                        while (temp !== undefined) {{
                            path.unshift(temp);
                            temp = previous[temp];
                        }}
                        return path;
                    }}
                    
                    // Actualizar distancias de vecinos
                    if (adjacencyList[current]) {{
                        adjacencyList[current].forEach(neighbor => {{
                            const alt = distances[current] + neighbor.length;
                            if (alt < distances[neighbor.node]) {{
                                distances[neighbor.node] = alt;
                                previous[neighbor.node] = current;
                            }}
                        }});
                    }}
                }}
                
                return [start]; // Si no hay camino, quedarse en el lugar
            }}
            
            // Actualizar posiciones de patrullas (versión simplificada que funciona)
            function updatePatrols() {{
                patrullas.forEach(patrulla => {{
                    // Si no tiene camino, calcular nuevo destino
                    if (!patrulla.path || patrulla.path.length === 0) {{
                        const allNodes = Object.keys(nodes);
                        const randomTarget = allNodes[Math.floor(Math.random() * allNodes.length)];
                        patrulla.target_node = randomTarget;
                        patrulla.path = findShortestPath(patrulla.current_node, patrulla.target_node);
                        patrulla.pathIndex = 0;
                        patrulla.progress = 0;
                        console.log(`Patrulla ${{patrulla.id}} nueva ruta: ${{patrulla.path.length}} nodos`);
                    }}
                    
                    // Mover a lo largo del camino (algoritmo simple que funciona)
                    if (patrulla.path && patrulla.path.length > 1) {{
                        const currentIdx = patrulla.pathIndex || 0;
                        const nextIdx = currentIdx + 1;
                        
                        if (nextIdx < patrulla.path.length) {{
                            const currentNode = patrulla.path[currentIdx];
                            const nextNode = patrulla.path[nextIdx];
                            
                            const currentPos = nodes[currentNode];
                            const nextPos = nodes[nextNode];
                            
                            if (currentPos && nextPos) {{
                                // Incrementar progreso con velocidad fija
                                patrulla.progress = (patrulla.progress || 0) + 0.03; // Velocidad fija
                                
                                if (patrulla.progress >= 1) {{
                                    // Avanzar al siguiente nodo
                                    patrulla.pathIndex = nextIdx;
                                    patrulla.progress = 0;
                                    patrulla.current_node = nextNode;
                                    
                                    // Si llegó al final, reiniciar
                                    if (patrulla.pathIndex >= patrulla.path.length - 1) {{
                                        patrulla.path = [];
                                    }}
                                }} else {{
                                    // Interpolar posición
                                    const lat = currentPos.lat + (nextPos.lat - currentPos.lat) * patrulla.progress;
                                    const lon = currentPos.lon + (nextPos.lon - currentPos.lon) * patrulla.progress;
                                    
                                    // Actualizar marcador
                                    patrolMarkers[patrulla.id].setLatLng([lat, lon]);
                                    
                                    // Actualizar trayectoria
                                    const pathCoords = patrolPaths[patrulla.id].getLatLngs();
                                    pathCoords.push([lat, lon]);
                                    if (pathCoords.length > 50) {{
                                        pathCoords.shift();
                                    }}
                                    patrolPaths[patrulla.id].setLatLngs(pathCoords);
                                }}
                            }}
                        }} else {{
                            // Reiniciar camino
                            patrulla.path = [];
                        }}
                    }}
                }});
                
                // Actualizar información
                updatePatrolInfo();
            }}
            
            // Mover patrulla a lo largo de la geometría real del edge
            function moveAlongGeometry(patrulla, edge) {{
                const geometry = edge.geometry;
                
                // Inicializar variables de geometría
                if (patrulla.geometryProgress === undefined) {{
                    patrulla.geometryProgress = 0;
                    patrulla.geometryIndex = 0;
                    
                    // Decidir dirección de la geometría
                    if (edge.source === patrulla.path[patrulla.pathIndex + 1]) {{
                        patrulla.currentGeometry = [...geometry].reverse();
                    }} else {{
                        patrulla.currentGeometry = geometry;
                    }}
                }}
                
                const currentGeometry = patrulla.currentGeometry;
                
                // Velocidad ajustada (más lenta para ver el movimiento)
                const speedFactor = 0.02; // Ajustar para controlar velocidad
                
                // Calcular progreso en el segmento actual
                const geometryIndex = Math.floor(patrulla.geometryIndex || 0);
                const nextGeometryIndex = geometryIndex + 1;
                
                if (nextGeometryIndex < currentGeometry.length) {{
                    const point1 = currentGeometry[geometryIndex];
                    const point2 = currentGeometry[nextGeometryIndex];
                    
                    // Incrementar progreso
                    patrulla.geometryProgress += speedFactor;
                    
                    if (patrulla.geometryProgress >= 1) {{
                        // Avanzar al siguiente segmento
                        patrulla.geometryIndex = nextGeometryIndex;
                        patrulla.geometryProgress = 0;
                        
                        // Si completamos toda la geometría, avanzar al siguiente nodo
                        if (patrulla.geometryIndex >= currentGeometry.length - 1) {{
                            patrulla.pathIndex += 1;
                            patrulla.progress = 0;
                            patrulla.geometryProgress = undefined;
                            patrulla.geometryIndex = undefined;
                            patrulla.currentGeometry = undefined;
                            patrulla.current_node = patrulla.path[patrulla.pathIndex];
                            return;
                        }}
                    }}
                    
                    // Interpolar posición en el segmento actual
                    const lat = point1[0] + (point2[0] - point1[0]) * patrulla.geometryProgress;
                    const lon = point1[1] + (point2[1] - point1[1]) * patrulla.geometryProgress;
                    
                    // Actualizar marcador
                    patrolMarkers[patrulla.id].setLatLng([lat, lon]);
                    
                    // Actualizar trayectoria
                    updatePatrolPath(patrulla, lat, lon);
                }} else {{
                    // Completar el edge
                    patrulla.pathIndex += 1;
                    patrulla.progress = 0;
                    patrulla.geometryProgress = undefined;
                    patrulla.geometryIndex = undefined;
                    patrulla.currentGeometry = undefined;
                    patrulla.current_node = patrulla.path[patrulla.pathIndex];
                }}
            }}
            
            // Movimiento simple (fallback)
            function moveAlongSimplePath(patrulla, currentNode, nextNode) {{
                const currentPos = nodes[currentNode];
                const nextPos = nodes[nextNode];
                
                // Velocidad ajustada
                const speedFactor = 0.02;
                
                patrulla.progress = (patrulla.progress || 0) + speedFactor;
                
                if (patrulla.progress >= 1) {{
                    // Avanzar al siguiente nodo
                    patrulla.pathIndex += 1;
                    patrulla.progress = 0;
                    patrulla.current_node = nextNode;
                }} else {{
                    // Interpolar posición
                    const lat = currentPos.lat + (nextPos.lat - currentPos.lat) * patrulla.progress;
                    const lon = currentPos.lon + (nextPos.lon - currentPos.lon) * patrulla.progress;
                    
                    // Actualizar marcador
                    patrolMarkers[patrulla.id].setLatLng([lat, lon]);
                    
                    // Actualizar trayectoria
                    updatePatrolPath(patrulla, lat, lon);
                }}
            }}
            
            // Actualizar trayectoria de patrulla
            function updatePatrolPath(patrulla, lat, lon) {{
                const pathCoords = patrolPaths[patrulla.id].getLatLngs();
                pathCoords.push([lat, lon]);
                if (pathCoords.length > 50) {{ // Limitar longitud de trayectoria
                    pathCoords.shift();
                }}
                patrolPaths[patrulla.id].setLatLngs(pathCoords);
            }}
            
            // Función para calcular distancia
            function calculateDistance(pos1, pos2) {{
                const R = 6371e3; // Radio de la Tierra en metros
                const φ1 = pos1.lat * Math.PI/180;
                const φ2 = pos2.lat * Math.PI/180;
                const Δφ = (pos2.lat-pos1.lat) * Math.PI/180;
                const Δλ = (pos2.lon-pos1.lon) * Math.PI/180;
                
                const a = Math.sin(Δφ/2) * Math.sin(Δφ/2) +
                          Math.cos(φ1) * Math.cos(φ2) *
                          Math.sin(Δλ/2) * Math.sin(Δλ/2);
                const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
                
                return R * c;
            }}
            
            // Inicializar patrullas con rutas válidas
            function initializePatrols() {{
                console.log('Inicializando patrullas...', patrullas.length);
                
                patrullas.forEach(patrulla => {{
                    // Asegurar que cada patrulla tenga una ruta
                    if (!patrulla.path || patrulla.path.length === 0) {{
                        const allNodes = Object.keys(nodes);
                        const randomTarget = allNodes[Math.floor(Math.random() * allNodes.length)];
                        patrulla.target_node = randomTarget;
                        patrulla.path = findShortestPath(patrulla.current_node, patrulla.target_node);
                        patrulla.pathIndex = 0;
                        patrulla.progress = 0;
                        
                        console.log(`Patrulla ${{patrulla.id}} inicializada con ruta de ${{patrulla.path.length}} nodos`);
                    }}
                }});
            }}
            
            // Actualizar información de patrullas
            function updatePatrolInfo() {{
                const infoDiv = document.getElementById('patrol-info');
                infoDiv.innerHTML = `
                    <div>Patrullas activas: ${{patrullas.length}}</div>
                    <div>Última actualización: ${{new Date().toLocaleTimeString()}}</div>
                    <div>Nodos disponibles: ${{Object.keys(nodes).length}}</div>
                    <div>Edges disponibles: ${{edges.length}}</div>
                `;
            }}
            
            // Iniciar animación
            console.log('Iniciando sistema de patrullas...');
            initializePatrols();
            
            // Actualizar más frecuentemente para mejor visualización
            setInterval(updatePatrols, 500); // Actualizar cada 0.5 segundos
            updatePatrolInfo();
            
            // Log inicial
            console.log('Sistema iniciado con:', {{
                patrullas: patrullas.length,
                nodos: Object.keys(nodes).length,
                edges: edges.length
            }});
        </script>
    </body>
    </html>
    """
    
    return html_content

# Sidebar para controles
st.sidebar.header("⚙️ Configuración")

# Selector de número de patrullas
num_patrullas = st.sidebar.slider("Número de patrullas", 1, 10, 5)

# Selector de hora del día
time_of_day = st.sidebar.selectbox(
    "Hora del día",
    options=list(range(24)),
    index=12,
    format_func=lambda x: f"{x}:00"
)

# Selector de clima
weather = st.sidebar.selectbox(
    "Condiciones climáticas",
    options=['soleado', 'nublado', 'lluvioso', 'neblina'],
    index=0
)

# Mostrar información contextual
st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 Información Contextual")

# Información de tráfico
if 6 <= time_of_day <= 8 or 17 <= time_of_day <= 19:
    traffic_status = "🔴 Hora pico - Tráfico pesado"
elif 22 <= time_of_day or time_of_day <= 5:
    traffic_status = "🟢 Madrugada - Tráfico ligero"
else:
    traffic_status = "🟡 Normal"

st.sidebar.markdown(f"**Tráfico:** {traffic_status}")

# Información climática
weather_info = {
    'soleado': "☀️ Condiciones ideales",
    'nublado': "☁️ Visibilidad reducida",
    'lluvioso': "🌧️ Precaución - Calles mojadas",
    'neblina': "🌫️ Visibilidad muy reducida"
}
st.sidebar.markdown(f"**Clima:** {weather_info[weather]}")

# Botón para recargar el grafo
if st.sidebar.button("🔄 Recargar Grafo"):
    st.cache_data.clear()
    st.rerun()

# Cargar el grafo
G, G_undirected = cargar_grafo_tacna()

if G is not None:
    # Calcular velocidad basada en condiciones
    velocidad_base = calcular_velocidad_base(time_of_day, weather)
    
    # Mostrar estadísticas
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Nodos (Intersecciones)", len(G.nodes()))
    
    with col2:
        st.metric("Aristas (Calles)", len(G.edges()))
    
    with col3:
        st.metric("Velocidad Base", f"{velocidad_base:.1f} km/h")
    
    # Generar y mostrar el mapa en tiempo real
    st.markdown("### 🗺️ Mapa en Tiempo Real")
    
    # Generar HTML personalizado
    html_content = generar_html_realtime(G, num_patrullas, velocidad_base)
    
    # Mostrar el mapa usando components.html
    components.html(html_content, height=650)
    
    # Información adicional
    st.markdown("### 📈 Estadísticas de Riesgo")
    
    # Contar tipos de riesgo
    risk_counts = {}
    for u, v, data in G.edges(data=True):
        risk_type = data.get('risk_type', 'otros')
        risk_counts[risk_type] = risk_counts.get(risk_type, 0) + 1
    
    # Mostrar en columnas
    cols = st.columns(len(risk_counts))
    for i, (risk_type, count) in enumerate(risk_counts.items()):
        with cols[i]:
            st.metric(f"Calles - {risk_type.title()}", count)
    
    st.markdown("---")
    st.markdown("**🎯 Características del Sistema:**")
    st.markdown("- ✅ Movimiento en tiempo real sin recargar la página")
    st.markdown("- ✅ Patrullas siguen calles reales de Tacna")
    st.markdown("- ✅ Velocidad afectada por hora y clima")
    st.markdown("- ✅ Calles etiquetadas por tipo de riesgo")
    st.markdown("- ✅ Trayectorias visibles en el mapa")
    
else:
    st.error("❌ No se pudo cargar el grafo de Tacna. Verifica tu conexión a internet.")
