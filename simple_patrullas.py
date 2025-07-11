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
    page_title="Patrullas Simple - Tacna",
    page_icon="🚔",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título principal
st.title("🚔 Sistema de Patrullas Simple - Tacna")
st.markdown("*Versión simplificada para debug*")

# Cache para el grafo
@st.cache_data
def cargar_grafo_simple():
    """Carga un grafo simple de Tacna"""
    try:
        # Cargar el grafo de calles de Tacna
        place = "Tacna, Peru"
        G = ox.graph_from_place(place, network_type='drive', simplify=True)
        
        # Convertir a no dirigido
        G_undirected = G.to_undirected()
        
        # Agregar información básica
        for u, v, data in G.edges(data=True):
            if 'length' not in data:
                start_coords = (G.nodes[u]['y'], G.nodes[u]['x'])
                end_coords = (G.nodes[v]['y'], G.nodes[v]['x'])
                data['length'] = geodesic(start_coords, end_coords).meters
        
        return G, G_undirected
    except Exception as e:
        st.error(f"Error al cargar el grafo: {e}")
        return None, None

# Función para generar HTML simple
def generar_html_simple(G, num_patrullas):
    """Genera HTML con movimiento simple garantizado"""
    
    # Obtener algunos nodos para las patrullas
    nodes_list = list(G.nodes())
    patrol_nodes = random.sample(nodes_list, min(num_patrullas, len(nodes_list)))
    
    # Datos para JavaScript
    nodes_data = {}
    for node, data in G.nodes(data=True):
        nodes_data[node] = {
            'lat': data['y'],
            'lon': data['x']
        }
    
    # Edges simples
    edges_data = []
    for u, v, data in G.edges(data=True):
        edges_data.append({
            'source': u,
            'target': v,
            'length': data.get('length', 100)
        })
    
    # Patrullas iniciales
    patrullas_data = []
    for i, node in enumerate(patrol_nodes):
        patrullas_data.append({
            'id': i,
            'current_node': node,
            'lat': G.nodes[node]['y'],
            'lon': G.nodes[node]['x'],
            'target_node': random.choice(nodes_list),
            'path': [],
            'pathIndex': 0,
            'progress': 0
        })
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Patrullas Simple</title>
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
            <h4>🚔 Estado de Patrullas</h4>
            <div id="patrol-info"></div>
        </div>
        
        <script>
            // Datos
            const nodes = {json.dumps(nodes_data)};
            const edges = {json.dumps(edges_data)};
            const patrullas = {json.dumps(patrullas_data)};
            
            console.log('Datos cargados:', {{
                nodes: Object.keys(nodes).length,
                edges: edges.length,
                patrullas: patrullas.length
            }});
            
            // Crear mapa
            const map = L.map('map').setView([-18.0137, -70.2500], 13);
            
            // Agregar capa base
            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                attribution: '© OpenStreetMap contributors'
            }}).addTo(map);
            
            // Dibujar algunas calles principales
            edges.slice(0, 500).forEach(edge => {{
                const start = nodes[edge.source];
                const end = nodes[edge.target];
                if (start && end) {{
                    L.polyline([
                        [start.lat, start.lon],
                        [end.lat, end.lon]
                    ], {{
                        color: 'blue',
                        weight: 2,
                        opacity: 0.5
                    }}).addTo(map);
                }}
            }});
            
            // Marcadores de patrullas
            const patrolMarkers = {{}};
            const patrolPaths = {{}};
            
            patrullas.forEach(patrulla => {{
                // Marcador visible
                patrolMarkers[patrulla.id] = L.marker([patrulla.lat, patrulla.lon], {{
                    icon: L.divIcon({{
                        html: `<div style="background: red; color: white; border-radius: 50%; width: 25px; height: 25px; display: flex; align-items: center; justify-content: center; font-size: 14px; border: 2px solid white; box-shadow: 0 0 5px rgba(0,0,0,0.5);">P${{patrulla.id}}</div>`,
                        iconSize: [25, 25],
                        className: 'patrol-marker'
                    }})
                }}).addTo(map);
                
                // Línea de trayectoria
                patrolPaths[patrulla.id] = L.polyline([], {{
                    color: 'red',
                    weight: 3,
                    opacity: 0.8
                }}).addTo(map);
            }});
            
            // Crear mapa de adyacencia
            const adjacencyList = {{}};
            edges.forEach(edge => {{
                if (!adjacencyList[edge.source]) adjacencyList[edge.source] = [];
                if (!adjacencyList[edge.target]) adjacencyList[edge.target] = [];
                
                adjacencyList[edge.source].push(edge.target);
                adjacencyList[edge.target].push(edge.source);
            }});
            
            // Función simple para encontrar camino
            function findSimplePath(start, end) {{
                const visited = new Set();
                const queue = [[start]];
                
                while (queue.length > 0) {{
                    const path = queue.shift();
                    const node = path[path.length - 1];
                    
                    if (node === end) {{
                        return path;
                    }}
                    
                    if (visited.has(node)) continue;
                    visited.add(node);
                    
                    const neighbors = adjacencyList[node] || [];
                    neighbors.forEach(neighbor => {{
                        if (!visited.has(neighbor)) {{
                            queue.push([...path, neighbor]);
                        }}
                    }});
                    
                    // Limitar búsqueda para evitar loops infinitos
                    if (visited.size > 100) break;
                }}
                
                return [start, end]; // Path directo como fallback
            }}
            
            // Función de movimiento simple
            function movePatrols() {{
                patrullas.forEach(patrulla => {{
                    // Si no tiene path, crear uno nuevo
                    if (!patrulla.path || patrulla.path.length === 0) {{
                        const allNodes = Object.keys(nodes);
                        const randomTarget = allNodes[Math.floor(Math.random() * allNodes.length)];
                        patrulla.path = findSimplePath(patrulla.current_node, randomTarget);
                        patrulla.pathIndex = 0;
                        patrulla.progress = 0;
                        console.log(`Patrulla ${{patrulla.id}} nueva ruta: ${{patrulla.path.length}} nodos`);
                    }}
                    
                    // Mover por el path
                    if (patrulla.path.length > 1) {{
                        const currentIdx = patrulla.pathIndex;
                        const nextIdx = currentIdx + 1;
                        
                        if (nextIdx < patrulla.path.length) {{
                            const currentNode = patrulla.path[currentIdx];
                            const nextNode = patrulla.path[nextIdx];
                            
                            const currentPos = nodes[currentNode];
                            const nextPos = nodes[nextNode];
                            
                            if (currentPos && nextPos) {{
                                // Incrementar progreso
                                patrulla.progress += 0.05; // Velocidad fija
                                
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
                                    if (pathCoords.length > 30) {{
                                        pathCoords.shift();
                                    }}
                                    patrolPaths[patrulla.id].setLatLngs(pathCoords);
                                }}
                            }}
                        }} else {{
                            // Reiniciar path
                            patrulla.path = [];
                        }}
                    }}
                }});
            }}
            
            // Función para actualizar información
            function updateInfo() {{
                const infoDiv = document.getElementById('patrol-info');
                infoDiv.innerHTML = `
                    <div>Patrullas: ${{patrullas.length}}</div>
                    <div>Nodos: ${{Object.keys(nodes).length}}</div>
                    <div>Calles: ${{edges.length}}</div>
                    <div>Tiempo: ${{new Date().toLocaleTimeString()}}</div>
                `;
            }}
            
            // Iniciar sistema
            console.log('Iniciando sistema simple...');
            
            // Ejecutar movimiento cada 200ms para movimiento fluido
            setInterval(movePatrols, 200);
            setInterval(updateInfo, 1000);
            
            // Inicializar info
            updateInfo();
            
            console.log('Sistema iniciado correctamente');
        </script>
    </body>
    </html>
    """
    
    return html_content

# Sidebar
st.sidebar.header("⚙️ Configuración Simple")
num_patrullas = st.sidebar.slider("Número de patrullas", 1, 5, 3)

# Cargar grafo
G, G_undirected = cargar_grafo_simple()

if G is not None:
    # Estadísticas
    st.metric("Nodos", len(G.nodes()))
    st.metric("Aristas", len(G.edges()))
    
    # Generar y mostrar mapa
    html_content = generar_html_simple(G, num_patrullas)
    components.html(html_content, height=650)
    
    st.success("✅ Sistema simple funcionando - Las patrullas deberían moverse")
else:
    st.error("❌ Error al cargar el grafo")
