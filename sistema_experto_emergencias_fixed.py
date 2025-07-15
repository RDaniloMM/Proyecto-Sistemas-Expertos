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
    page_title="Sistema Experto de Emergencias",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título principal según especificaciones del proyecto
st.title("🚨 Sistema Experto de Soporte a la Decisión para Optimización de Rutas de Emergencia")
st.markdown("*Modelo de Costo Dual Dependiente del Tiempo - Tacna, Perú*")
st.markdown("---")

# --- Funciones de Cache y Carga del Grafo ---
@st.cache_data
def cargar_grafo_tacna():
    """
    Carga un grafo enriquecido de Tacna con atributos estáticos para el modelo probabilístico.
    """
    try:
        place = "Tacna, Peru"
        # Crear grafo dirigido simplificado y fuertemente conectado
        G = ox.graph_from_place(place, network_type='drive', simplify=True)
        
        # Asegurar conectividad fuerte para evitar islas
        if not nx.is_strongly_connected(G):
            largest_scc = max(nx.strongly_connected_components(G), key=len)
            G = G.subgraph(largest_scc).copy()

        # Convertir a enteros para compatibilidad con JavaScript
        G = nx.convert_node_labels_to_integers(G, label_attribute='osmid')
        
        # Enriquecimiento del grafo con atributos estáticos
        for u, v, key, data in G.edges(data=True, keys=True):
            # Longitud del arco
            length = data.get('length', 100)
            
            # Clasificar tipo de vía basado en atributos OSM
            highway = data.get('highway', 'residential')
            if isinstance(highway, list):
                highway = highway[0]
            
            # Mapeo de tipos de vía según especificaciones
            if highway in ['primary', 'trunk', 'motorway']:
                tipo_via = 'avenida_principal'
                velocidad_base = 50
                sigma_base = 20
                factor_calidad = 1.2
            elif highway in ['secondary', 'tertiary']:
                tipo_via = 'calle_colectora'
                velocidad_base = 40
                sigma_base = 18
                factor_calidad = 1.3
            elif highway in ['residential', 'living_street']:
                tipo_via = 'calle_residencial'
                velocidad_base = 30
                sigma_base = 12
                factor_calidad = 1.1
            else:
                tipo_via = 'jiron_comercial'
                velocidad_base = 35
                sigma_base = 15
                factor_calidad = 1.4
            
            # Asignar atributos al arco
            G[u][v][key]['tipo_via'] = tipo_via
            G[u][v][key]['velocidad_base'] = velocidad_base
            G[u][v][key]['sigma_base'] = sigma_base
            G[u][v][key]['factor_calidad'] = factor_calidad
            G[u][v][key]['length'] = length

        st.success(f"✅ Grafo de Tacna cargado: {len(G.nodes)} nodos, {len(G.edges)} arcos")
        return G
        
    except Exception as e:
        st.error(f"❌ Error al cargar el grafo: {str(e)}")
        return None

# --- Interfaz de Usuario (Sidebar) ---
st.sidebar.header("⚙️ Panel de Control del Sistema Experto")
st.sidebar.markdown("**Configuración de Simulación**")

# Activación del modo de incidentes
modo_incidente_activo = st.sidebar.toggle(
    "🚨 Activar Modo Emergencia", 
    value=False,
    help="Permite reportar incidentes haciendo clic en el mapa"
)

# Factores dinámicos según especificaciones
st.sidebar.markdown("**Factores Dinámicos**")
perfil_horario = st.sidebar.selectbox(
    "Perfil de Congestión:",
    options=['valle', 'punta', 'noche'],
    index=1,
    help="Simula la congestión vehicular según la hora del día"
)

condicion_clima = st.sidebar.selectbox(
    "Condiciones Climáticas:",
    options=['despejado', 'lluvia'],
    help="Factor climático que afecta la velocidad en toda la red"
)

# Parámetro de riesgo k para el modelo de costo dual
st.sidebar.markdown("**Parámetros de Optimización**")
factor_riesgo_k = st.sidebar.slider(
    "Factor de Aversión al Riesgo (k):",
    min_value=0.0,
    max_value=3.0,
    value=1.5,
    step=0.1,
    help="Controla la importancia de la incertidumbre (σ) en la función Costo_Seguro(e) = μ(e) + k×σ(e)"
)

# Información del modelo
st.sidebar.markdown("**Información del Modelo**")
st.sidebar.info("""
**Funciones de Costo Dual:**
- 🏃‍♂️ Rápida: Costo(e) = μ(e)
- 🛡️ Segura: Costo(e) = μ(e) × f_seguridad(e)

**Factor de Seguridad:**
- Avenidas: 1.1× (más tráfico)
- Colectoras: 1.05× (moderado)
- Residenciales: 0.95× (más seguras)
- Comerciales: 1.15× (actividad intensa)

**Heurística A*:**
h(n) = Distancia_Geodésica / Velocidad_Máxima

**Red Bidireccional:**
Todas las calles permiten tráfico en ambas direcciones
""")

# Cargar grafo principal
G = cargar_grafo_tacna()

if G is not None:
    # Preparar datos del sistema
    nodes_list = list(G.nodes())
    num_patrullas = min(5, len(nodes_list))
    patrol_nodes = random.sample(nodes_list, num_patrullas)

    # Información de patrullas con estado
    patrullas_data = []
    for i, node in enumerate(patrol_nodes):
        patrullas_data.append({
            'id': f"U-{i+1:02d}",
            'nodo_actual': int(node),
            'status': 'disponible'
        })

    # Preparar datos de nodos para JavaScript
    nodes_data = {}
    for node, data in G.nodes(data=True):
        if 'y' in data and 'x' in data:
            nodes_data[int(node)] = {
                'lat': float(data['y']), 
                'lon': float(data['x'])
            }

    # Preparar datos de arcos con modelo de costo
    edges_data = []
    for u, v, key, data in G.edges(data=True, keys=True):
        if int(u) in nodes_data and int(v) in nodes_data:
            edges_data.append({
                'source': int(u), 
                'target': int(v),
                'length': float(data.get('length', 100)),
                'tipo_via': data.get('tipo_via', 'jiron_comercial'),
                'velocidad_base': float(data.get('velocidad_base', 30)),
                'sigma_base': float(data.get('sigma_base', 15)),
                'factor_calidad': float(data.get('factor_calidad', 1.4))
            })

    # Estado del sistema
    st.markdown("### 📊 Estado del Sistema")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("🗺️ Nodos", len(nodes_data))
    with col2:
        st.metric("🛣️ Arcos", len(edges_data))
    with col3:
        st.metric("🚔 Patrullas", len(patrullas_data))
    with col4:
        patrullas_disponibles = len([p for p in patrullas_data if p['status'] == 'disponible'])
        st.metric("✅ Disponibles", patrullas_disponibles)

    # Información del modo actual
    if modo_incidente_activo:
        st.success("🚨 **Modo Emergencia Activado:** Haga clic en el mapa para reportar un incidente")
    else:
        st.warning("⚠️ **Modo Emergencia Desactivado:** Active el interruptor en el panel lateral")

    # Mapa interactivo con sistema experto integrado
    st.markdown("### 🗺️ Mapa de Operaciones")
    
    # Crear HTML del mapa
    mapa_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Sistema Experto de Emergencias</title>
        <meta charset="utf-8" />
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
        <style>
            #map {{ 
                height: 600px; 
                width: 100%; 
                cursor: {"crosshair" if modo_incidente_activo else "default"}; 
            }}
            .panel-recomendaciones {{
                position: absolute; 
                bottom: 10px; 
                right: 10px; 
                z-index: 1000;
                background: rgba(255, 255, 255, 0.95); 
                padding: 15px; 
                border-radius: 8px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.2); 
                max-width: 450px; 
                max-height: 500px; 
                overflow-y: auto;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            }}
            .patrol-disponible {{
                background: linear-gradient(135deg, #28a745, #20c997); 
                color: white; 
                border-radius: 50%;
                width: 32px; 
                height: 32px; 
                display: flex; 
                align-items: center; 
                justify-content: center;
                font-size: 11px; 
                font-weight: bold; 
                border: 2px solid white; 
                box-shadow: 0 2px 8px rgba(0,0,0,0.3);
            }}
            .patrol-ocupado {{
                background: linear-gradient(135deg, #6c757d, #495057); 
                color: white; 
                border-radius: 50%;
                width: 32px; 
                height: 32px; 
                display: flex; 
                align-items: center; 
                justify-content: center;
                font-size: 11px; 
                font-weight: bold; 
                border: 2px solid #adb5bd; 
                box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                opacity: 0.8;
            }}
        </style>
    </head>
    <body>
        <div id="map"></div>
        
        <!-- Panel de Control del Grafo -->
        <div style="position: absolute; top: 10px; left: 10px; z-index: 1000; background: rgba(255, 255, 255, 0.95); padding: 10px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.2);">
            <button id="btn-grafo" onclick="toggleGrafoVisualizacion()" 
                    style="background: #17a2b8; color: white; border: none; padding: 8px 12px; border-radius: 5px; cursor: pointer; font-size: 12px; font-weight: bold;">
                🗺️ Mostrar Grafo
            </button>
            <div style="margin-top: 5px; font-size: 10px; color: #666;">
                <div><b>Aristas (Calles):</b></div>
                <div>🟠 Avenidas principales</div>
                <div>🟣 Calles colectoras</div>
                <div>🟢 Calles residenciales</div>
                <div>🔵 Jirones comerciales</div>
                <div>⚫ Otros tipos</div>
            </div>
        </div>
        
        <div class="panel-recomendaciones" id="panel-recomendaciones">
            <h4>🎯 Sistema Experto de Decisión</h4>
            <div id="contenido-recomendaciones">
                <p style="color: #6c757d; font-style: italic;">
                    Esperando reporte de emergencia...
                </p>
                <small>Active el modo emergencia y haga clic en el mapa para comenzar.</small>
            </div>
        </div>
        
        <script>
            // --- Configuración y Datos ---
            const MODO_EMERGENCIA = {str(modo_incidente_activo).lower()};
            const PERFIL_HORARIO = "{perfil_horario}";
            const CONDICION_CLIMA = "{condicion_clima}";
            const FACTOR_RIESGO_K = {factor_riesgo_k};

            const nodes = {json.dumps(nodes_data)};
            const edges = {json.dumps(edges_data)};
            const patrullas = {json.dumps(patrullas_data)};

            console.log(`Sistema inicializado: ${{Object.keys(nodes).length}} nodos, ${{edges.length}} arcos, ${{patrullas.length}} patrullas`);

            // --- Inicialización del Mapa ---
            const map = L.map('map').setView([-18.0137, -70.2500], 14);
            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ 
                attribution: '© OpenStreetMap contributors',
                maxZoom: 18
            }}).addTo(map);

            // --- Visualización de Patrullas ---
            patrullas.forEach(p => {{
                const nodePos = nodes[p.nodo_actual];
                if (nodePos) {{
                    p.marker = L.marker([nodePos.lat, nodePos.lon], {{
                        icon: L.divIcon({{ 
                            html: `<div class="patrol-${{p.status}}">${{p.id}}</div>`, 
                            iconSize: [32, 32], 
                            className: '' 
                        }})
                    }}).addTo(map).bindPopup(
                        `<b>Patrulla ${{p.id}}</b><br>
                         Estado: <span id="status-${{p.id}}">${{p.status}}</span><br>
                         <small>Nodo: ${{p.nodo_actual}}</small>`
                    );
                }}
            }});

            // Variables globales para visualización
            let marcadorIncidente, rutaRapidaLayer, rutaSeguraLayer, grafoLayer;
            let mostrarGrafo = false;

            // --- Visualización del Grafo de Red (Completa) ---
            function toggleGrafoVisualizacion() {{
                if (mostrarGrafo) {{
                    // Ocultar grafo
                    if (grafoLayer) {{
                        map.removeLayer(grafoLayer);
                        grafoLayer = null;
                    }}
                    mostrarGrafo = false;
                    document.getElementById('btn-grafo').innerHTML = '🗺️ Mostrar Grafo';
                    document.getElementById('btn-grafo').style.background = '#17a2b8';
                    
                    // Limpiar info del grafo
                    const infoGrafo = document.getElementById('info-grafo');
                    if (infoGrafo) {{
                        infoGrafo.remove();
                    }}
                }} else {{
                    // Mostrar grafo completo
                    mostrarGrafo = true;
                    document.getElementById('btn-grafo').innerHTML = '🗺️ Ocultar Grafo';
                    document.getElementById('btn-grafo').style.background = '#dc3545';
                    
                    // Crear grupo de capas para el grafo
                    grafoLayer = L.layerGroup();
                    
                    console.log(`🗺️ Visualizando grafo completo: ${{edges.length}} aristas disponibles`);
                    
                    // Crear set para evitar aristas duplicadas en visualización
                    const aristasVisualizadas = new Set();
                    let aristasVisibles = 0;
                    
                    // Mostrar TODAS las aristas del grafo sin límite
                    edges.forEach(edge => {{
                        const sourceNode = nodes[edge.source];
                        const targetNode = nodes[edge.target];
                        
                        if (sourceNode && targetNode) {{
                            // Crear ID único para la arista (bidireccional)
                            const aristaId = `${{Math.min(edge.source, edge.target)}}-${{Math.max(edge.source, edge.target)}}`;
                            
                            // Solo agregar si no ha sido visualizada
                            if (!aristasVisualizadas.has(aristaId)) {{
                                aristasVisualizadas.add(aristaId);
                                
                                // Color y grosor según tipo de vía
                                let color, weight, opacity;
                                
                                switch(edge.tipo_via) {{
                                    case 'avenida_principal':
                                        color = '#FF6B35'; // Naranja para avenidas
                                        weight = 4;
                                        opacity = 0.8;
                                        break;
                                    case 'calle_colectora':
                                        color = '#7209B7'; // Morado para colectoras
                                        weight = 3;
                                        opacity = 0.7;
                                        break;
                                    case 'calle_residencial':
                                        color = '#2ECC71'; // Verde para residenciales
                                        weight = 2;
                                        opacity = 0.6;
                                        break;
                                    case 'jiron_comercial':
                                        color = '#3498DB'; // Azul para jirones
                                        weight = 2;
                                        opacity = 0.6;
                                        break;
                                    default:
                                        color = '#95A5A6'; // Gris para otros
                                        weight = 1;
                                        opacity = 0.5;
                                }}
                                
                                // Crear la línea del grafo
                                L.polyline([
                                    [sourceNode.lat, sourceNode.lon],
                                    [targetNode.lat, targetNode.lon]
                                ], {{
                                    color: color,
                                    weight: weight,
                                    opacity: opacity,
                                    interactive: true
                                }}).bindPopup(`
                                    <b>🛣️ Conexión Vial</b><br>
                                    <b>Nodos:</b> ${{edge.source}} ↔ ${{edge.target}}<br>
                                    <b>Tipo:</b> ${{edge.tipo_via}}<br>
                                    <b>Longitud:</b> ${{edge.length.toFixed(1)}}m<br>
                                    <b>Velocidad base:</b> ${{edge.velocidad_base}} km/h<br>
                                    <b>Factor calidad:</b> ${{edge.factor_calidad}}<br>
                                    <small><i>Conexión bidireccional</i></small>
                                `).addTo(grafoLayer);
                                
                                aristasVisibles++;
                            }}
                        }}
                    }});
                    
                    // Agregar algunos nodos importantes como puntos de referencia
                    let nodosImportantes = 0;
                    Object.keys(nodes).forEach(nodeId => {{
                        const node = nodes[nodeId];
                        if (node && nodosImportantes < 100) {{ // Aumentar límite de nodos importantes
                            // Calcular conectividad del nodo
                            const conexionesEntrada = edges.filter(e => e.target == nodeId).length;
                            const conexionesSalida = edges.filter(e => e.source == nodeId).length;
                            const totalConexiones = conexionesEntrada + conexionesSalida;
                            
                            // Mostrar solo nodos con muchas conexiones (intersecciones importantes)
                            if (totalConexiones >= 4) {{
                                let color, radius;
                                if (totalConexiones >= 10) {{
                                    color = '#E74C3C'; radius = 8; // Rojo para super hubs
                                }} else if (totalConexiones >= 6) {{
                                    color = '#F39C12'; radius = 6; // Naranja para hubs importantes
                                }} else {{
                                    color = '#3498DB'; radius = 4; // Azul para intersecciones normales
                                }}
                                
                                L.circleMarker([node.lat, node.lon], {{
                                    radius: radius,
                                    fillColor: color,
                                    color: '#ffffff',
                                    weight: 2,
                                    opacity: 1,
                                    fillOpacity: 0.8
                                }}).bindPopup(`
                                    <b>🏛️ Intersección Importante</b><br>
                                    <b>Nodo:</b> ${{nodeId}}<br>
                                    <b>Conexiones:</b> ${{totalConexiones}}<br>
                                    <b>Entrada:</b> ${{conexionesEntrada}}<br>
                                    <b>Salida:</b> ${{conexionesSalida}}<br>
                                    <b>Coordenadas:</b> [${{node.lat.toFixed(4)}}, ${{node.lon.toFixed(4)}}]
                                `).addTo(grafoLayer);
                                
                                nodosImportantes++;
                            }}
                        }}
                    }});
                    
                    // Agregar al mapa
                    grafoLayer.addTo(map);
                    
                    console.log(`✅ Grafo completo visualizado: ${{aristasVisibles}} aristas únicas, ${{nodosImportantes}} intersecciones importantes`);
                    
                    // Mostrar información del grafo
                    const infoDiv = document.createElement('div');
                    infoDiv.id = 'info-grafo';
                    infoDiv.style.cssText = `
                        position: absolute; 
                        bottom: 10px; 
                        left: 10px; 
                        background: rgba(255, 255, 255, 0.95); 
                        padding: 12px; 
                        border-radius: 8px; 
                        font-size: 11px; 
                        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
                        z-index: 1000;
                        border-left: 4px solid #17a2b8;
                    `;
                    infoDiv.innerHTML = `
                        <b>📊 Red Vial Completa</b><br>
                        🛣️ Aristas visualizadas: ${{aristasVisibles}}<br>
                        🏛️ Intersecciones importantes: ${{nodosImportantes}}<br>
                        📈 Conectividad: ${{((aristasVisibles / edges.length) * 100).toFixed(1)}}%<br>
                        <small><i>Todas las conexiones bidireccionales mostradas</i></small>
                    `;
                    document.body.appendChild(infoDiv);
                }}
            }}

            // --- Construcción de Lista de Adyacencia (Bidireccional) ---
            const listaAdyacencia = {{}};
            edges.forEach(edge => {{
                // Agregar conexión en ambas direcciones para grafos no dirigidos
                if (!listaAdyacencia[edge.source]) listaAdyacencia[edge.source] = [];
                if (!listaAdyacencia[edge.target]) listaAdyacencia[edge.target] = [];
                
                // Calcular factores dinámicos
                let factorCongestion = 1.0;
                if (PERFIL_HORARIO === "punta") {{
                    switch(edge.tipo_via) {{
                        case "avenida_principal": factorCongestion = 3.0; break;
                        case "calle_colectora": factorCongestion = 2.2; break;
                        case "calle_residencial": factorCongestion = 1.5; break;
                        default: factorCongestion = 1.8;
                    }}
                }} else if (PERFIL_HORARIO === "noche") {{
                    factorCongestion = 0.8;
                }}
                
                const factorClima = (CONDICION_CLIMA === "lluvia") ? 1.3 : 1.0;
                
                // Modelo probabilístico - tiempo base
                const tiempoBase = edge.length / (edge.velocidad_base * 1000 / 3600);
                const muDinamico = tiempoBase * edge.factor_calidad * factorCongestion * factorClima;
                
                // Para ruta segura: penalizar según tipo de vía y factores de riesgo
                let penalizacionSeguridad = 1.0;
                switch(edge.tipo_via) {{
                    case "avenida_principal": 
                        penalizacionSeguridad = 1.1; // Ligeramente menos segura por tráfico
                        break;
                    case "calle_colectora": 
                        penalizacionSeguridad = 1.05; // Moderadamente segura
                        break;
                    case "calle_residencial": 
                        penalizacionSeguridad = 0.95; // Más segura, menos tráfico
                        break;
                    case "jiron_comercial": 
                        penalizacionSeguridad = 1.15; // Menos segura por actividad comercial
                        break;
                }}
                
                // Aplicar penalización por condiciones
                if (CONDICION_CLIMA === "lluvia") {{
                    penalizacionSeguridad *= 1.2; // Mayor riesgo en lluvia
                }}
                if (PERFIL_HORARIO === "noche") {{
                    penalizacionSeguridad *= 1.1; // Mayor riesgo nocturno
                }}
                
                const costoRapido = muDinamico;
                const costoSeguro = muDinamico * penalizacionSeguridad;

                // Agregar conexiones bidireccionales
                listaAdyacencia[edge.source].push({{
                    node: edge.target,
                    length: edge.length,
                    costo_rapido: costoRapido,
                    costo_seguro: costoSeguro,
                    tipo_via: edge.tipo_via
                }});
                
                listaAdyacencia[edge.target].push({{
                    node: edge.source,
                    length: edge.length,
                    costo_rapido: costoRapido,
                    costo_seguro: costoSeguro,
                    tipo_via: edge.tipo_via
                }});
            }});

            // --- Algoritmo A* ---
            function aStar(inicio, destino, tipoCosto) {{
                const tiempoInicio = performance.now();
                console.log(`🔍 A* iniciado: ${{inicio}} → ${{destino}} [${{tipoCosto}}]`);
                
                if (!nodes[inicio] || !nodes[destino]) {{
                    console.error(`❌ Nodos inválidos`);
                    return null;
                }}
                
                if (inicio === destino) {{
                    return {{ path: [inicio], cost: 0, nodesExplored: 1 }};
                }}
                
                // Heurística admisible
                function heuristica(nodoA, nodoB) {{
                    const pA = nodes[nodoA];
                    const pB = nodes[nodoB];
                    if (!pA || !pB) return Infinity;
                    
                    const lat1 = pA.lat * Math.PI / 180;
                    const lat2 = pB.lat * Math.PI / 180;
                    const deltaLat = lat2 - lat1;
                    const deltaLon = (pB.lon - pA.lon) * Math.PI / 180;
                    
                    const a = Math.sin(deltaLat/2) * Math.sin(deltaLat/2) +
                            Math.cos(lat1) * Math.cos(lat2) *
                            Math.sin(deltaLon/2) * Math.sin(deltaLon/2);
                    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
                    const distancia = 6371000 * c;
                    
                    const velocidadMaxMs = 20;
                    return distancia / velocidadMaxMs;
                }}
                
                const openSet = new Set([inicio]);
                const closedSet = new Set();
                const cameFrom = new Map();
                const gScore = new Map([[inicio, 0]]);
                const fScore = new Map([[inicio, heuristica(inicio, destino)]]);
                
                let nodosExplorados = 0;
                const maxIteraciones = 5000;
                const maxTiempo = 6000;
                
                while (openSet.size > 0 && nodosExplorados < maxIteraciones) {{
                    if (performance.now() - tiempoInicio > maxTiempo) {{
                        console.warn(`⏰ Timeout alcanzado`);
                        break;
                    }}
                    
                    let actual = null;
                    let menorF = Infinity;
                    for (let nodo of openSet) {{
                        const f = fScore.get(nodo) || Infinity;
                        if (f < menorF) {{
                            menorF = f;
                            actual = nodo;
                        }}
                    }}
                    
                    if (!actual) break;
                    
                    nodosExplorados++;
                    
                    if (actual === destino) {{
                        const ruta = [];
                        let temp = actual;
                        while (temp !== undefined) {{
                            ruta.unshift(temp);
                            temp = cameFrom.get(temp);
                        }}
                        const tiempoTotal = performance.now() - tiempoInicio;
                        console.log(`✅ Ruta encontrada en ${{tiempoTotal.toFixed(0)}}ms: ${{ruta.length}} nodos`);
                        return {{ 
                            path: ruta, 
                            cost: gScore.get(destino), 
                            nodesExplored: nodosExplorados,
                            timeMs: tiempoTotal
                        }};
                    }}
                    
                    openSet.delete(actual);
                    closedSet.add(actual);
                    
                    const vecinos = listaAdyacencia[actual] || [];
                    for (let vecino of vecinos) {{
                        const nodoVecino = vecino.node;
                        
                        if (closedSet.has(nodoVecino)) continue;
                        
                        const costoTentativo = gScore.get(actual) + vecino[tipoCosto];
                        
                        const costoActual = gScore.get(nodoVecino);
                        if (costoActual === undefined || costoTentativo < costoActual) {{
                            cameFrom.set(nodoVecino, actual);
                            gScore.set(nodoVecino, costoTentativo);
                            fScore.set(nodoVecino, costoTentativo + heuristica(nodoVecino, destino));
                            
                            if (!openSet.has(nodoVecino)) {{
                                openSet.add(nodoVecino);
                            }}
                        }}
                    }}
                }}
                
                console.log(`❌ No se encontró ruta después de ${{nodosExplorados}} nodos`);
                return null;
            }}

            // --- Manejo de Eventos de Emergencia ---
            map.on('click', function(e) {{
                if (!MODO_EMERGENCIA) return;
                
                const coordsIncidente = e.latlng;
                console.log(`🚨 Emergencia reportada en: [${{coordsIncidente.lat.toFixed(6)}}, ${{coordsIncidente.lng.toFixed(6)}}]`);
                
                // Mostrar indicador de carga
                document.getElementById('contenido-recomendaciones').innerHTML = `
                    <div style="text-align: center; padding: 20px;">
                        <h5>🚨 Procesando Emergencia</h5>
                        <div style="margin: 15px 0;">
                            <div style="display: inline-block; width: 20px; height: 20px; border: 3px solid #f3f3f3; border-top: 3px solid #3498db; border-radius: 50%; animation: spin 1s linear infinite;"></div>
                        </div>
                        <p>Calculando rutas óptimas...</p>
                        <style>
                            @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
                        </style>
                    </div>`;
                
                // Limpiar marcadores anteriores
                if (marcadorIncidente) map.removeLayer(marcadorIncidente);
                if (rutaRapidaLayer) map.removeLayer(rutaRapidaLayer);
                if (rutaSeguraLayer) map.removeLayer(rutaSeguraLayer);
                
                // Crear marcador de emergencia
                marcadorIncidente = L.marker(coordsIncidente, {{ 
                    icon: L.divIcon({{ 
                        html: '🚨', 
                        className: 'incident-marker', 
                        iconSize: [40, 40],
                        iconAnchor: [20, 20]
                    }}) 
                }}).addTo(map).bindPopup("<b>🚨 EMERGENCIA</b><br>Calculando respuesta óptima...").openPopup();
                
                setTimeout(() => {{
                    procesarEmergencia(coordsIncidente);
                }}, 100);
            }});
            
            // --- Función de Procesamiento de Emergencia ---
            function procesarEmergencia(coordsIncidente) {{
                try {{
                    // Encontrar nodo más cercano
                    let nodoDestino = null;
                    let distanciaMinima = Infinity;
                    
                    Object.keys(nodes).forEach(nodeId => {{
                        const posNodo = L.latLng(nodes[nodeId].lat, nodes[nodeId].lon);
                        const distancia = posNodo.distanceTo(coordsIncidente);
                        if (distancia < distanciaMinima) {{
                            distanciaMinima = distancia;
                            nodoDestino = parseInt(nodeId);
                        }}
                    }});
                    
                    if (!nodoDestino) {{
                        document.getElementById('contenido-recomendaciones').innerHTML = 
                            "<div style='color: #dc3545; font-weight: bold; padding: 15px;'>❌ Error: Ubicación no accesible</div>";
                        return;
                    }}
                    
                    console.log(`📍 Nodo destino: ${{nodoDestino}}, distancia: ${{distanciaMinima.toFixed(1)}}m`);
                    
                    // Evaluar patrullas disponibles
                    const patrullasDisponibles = patrullas.filter(p => p.status === 'disponible');
                    
                    if (patrullasDisponibles.length === 0) {{
                        document.getElementById('contenido-recomendaciones').innerHTML = 
                            "<div style='color: #dc3545; font-weight: bold; padding: 15px;'>⚠️ No hay patrullas disponibles</div>";
                        return;
                    }}
                    
                    let candidatos = [];
                    
                    for (let p of patrullasDisponibles) {{
                        const resultado = aStar(p.nodo_actual, nodoDestino, 'costo_rapido');
                        
                        if (resultado && resultado.path && resultado.path.length > 0) {{
                            candidatos.push({{ 
                                patrulla: p, 
                                tiempo: resultado.cost,
                                nodosExplorados: resultado.nodesExplored
                            }});
                            console.log(`✅ Ruta para ${{p.id}}: ${{resultado.cost.toFixed(2)}}s`);
                        }} else {{
                            console.log(`❌ Sin ruta válida para ${{p.id}}`);
                        }}
                    }}
                    
                    if (candidatos.length === 0) {{
                        document.getElementById('contenido-recomendaciones').innerHTML = 
                            "<div style='color: #dc3545; font-weight: bold; padding: 15px;'>❌ No se encontró una ruta válida</div>";
                        return;
                    }}
                    
                    // Seleccionar mejor patrulla
                    candidatos.sort((a, b) => a.tiempo - b.tiempo);
                    const mejorPatrulla = candidatos[0].patrulla;
                    
                    console.log(`🏆 Mejor patrulla: ${{mejorPatrulla.id}} con tiempo: ${{candidatos[0].tiempo.toFixed(2)}}s`);
                    
                    setTimeout(() => {{
                        calcularRutasDuales(mejorPatrulla, nodoDestino);
                    }}, 100);
                    
                }} catch (error) {{
                    console.error('❌ Error en procesarEmergencia:', error);
                    document.getElementById('contenido-recomendaciones').innerHTML = 
                        `<div style='color: #dc3545; font-weight: bold; padding: 15px;'>❌ Error: ${{error.message}}</div>`;
                }}
            }}
            
            // --- Función para Calcular Rutas Duales ---
            function calcularRutasDuales(mejorPatrulla, nodoDestino) {{
                try {{
                    document.getElementById('contenido-recomendaciones').innerHTML = `
                        <div style="text-align: center; padding: 15px;">
                            <h5>🎯 Calculando rutas para ${{mejorPatrulla.id}}</h5>
                            <p>Generando recomendaciones...</p>
                        </div>`;
                    
                    // Calcular ambas rutas
                    const rutaRapida = aStar(mejorPatrulla.nodo_actual, nodoDestino, 'costo_rapido');
                    const rutaSegura = aStar(mejorPatrulla.nodo_actual, nodoDestino, 'costo_seguro');
                    
                    if (!rutaRapida) {{
                        document.getElementById('contenido-recomendaciones').innerHTML = 
                            "<div style='color: #dc3545; font-weight: bold; padding: 15px;'>❌ Error: No se pudo calcular la ruta</div>";
                        return;
                    }}
                    
                    function formatearTiempo(segundos) {{
                        if (!isFinite(segundos)) return "∞";
                        const mins = Math.floor(segundos / 60);
                        const segs = Math.round(segundos % 60);
                        return `${{mins}}:${{segs.toString().padStart(2, '0')}}`;
                    }}
                    
                    let htmlRecomendaciones = `<h5>🎯 Análisis para ${{mejorPatrulla.id}}</h5>`;
                    
                    // Visualizar ruta rápida
                    if (rutaRapida && rutaRapida.path) {{
                        const coordsRuta = rutaRapida.path.map(n => [nodes[n].lat, nodes[n].lon]);
                        rutaRapidaLayer = L.polyline(coordsRuta, {{ 
                            color: '#e74c3c', 
                            weight: 6, 
                            opacity: 0.9 
                        }}).addTo(map);
                        
                        htmlRecomendaciones += `
                        <div style="border-left: 5px solid #e74c3c; padding: 12px; margin: 8px 0; background: #fff5f5; border-radius: 5px;">
                            <b>1. 🏃‍♂️ Ruta Rápida</b><br>
                            ⏱️ Tiempo: ${{formatearTiempo(rutaRapida.cost)}}<br>
                            📍 Nodos: ${{rutaRapida.path.length}}<br>
                            🔍 Explorados: ${{rutaRapida.nodesExplored}}<br>
                            🧮 Función: μ(e)
                        </div>`;
                    }}
                    
                    // Visualizar ruta segura
                    if (rutaSegura && rutaSegura.path) {{
                        const coordsRuta = rutaSegura.path.map(n => [nodes[n].lat, nodes[n].lon]);
                        rutaSeguraLayer = L.polyline(coordsRuta, {{ 
                            color: '#3498db', 
                            weight: 6, 
                            opacity: 0.9,
                            dashArray: '15, 8'
                        }}).addTo(map);
                        
                        const diferencia = rutaSegura.cost - rutaRapida.cost;
                        const porcentaje = ((diferencia / rutaRapida.cost) * 100).toFixed(1);
                        
                        htmlRecomendaciones += `
                        <div style="border-left: 5px solid #3498db; padding: 12px; margin: 8px 0; background: #f0f8ff; border-radius: 5px;">
                            <b>2. 🛡️ Ruta Segura</b><br>
                            ⏱️ Tiempo: ${{formatearTiempo(rutaSegura.cost)}}<br>
                            📍 Nodos: ${{rutaSegura.path.length}}<br>
                            🔍 Explorados: ${{rutaSegura.nodesExplored}}<br>
                            📊 Diferencia: +${{formatearTiempo(diferencia)}} (+${{porcentaje}}%)<br>
                            🧮 Función: μ(e) + ${{FACTOR_RIESGO_K}}×σ(e)
                        </div>`;
                    }}
                    
                    // Panel de decisión
                    htmlRecomendaciones += `
                    <div style="background: #f8f9fa; padding: 12px; border-radius: 5px; margin: 10px 0;">
                        <h6>🤖 Recomendación:</h6>
                        <p style="font-size: 0.9em;">
                            ${{rutaSegura && (rutaSegura.cost - rutaRapida.cost) / rutaRapida.cost < 0.3 ? 
                                "🛡️ Se recomienda la ruta segura" : 
                                "⚡ Se recomienda la ruta rápida"}}
                        </p>
                    </div>
                    <div style="text-align: center; margin-top: 15px;">
                        <button onclick="asignarPatrulla('${{mejorPatrulla.id}}', 'rapida')" 
                                style="background: #e74c3c; color: white; border: none; padding: 10px 16px; margin: 5px; border-radius: 5px; cursor: pointer; font-weight: bold;">
                            🏃‍♂️ Asignar Ruta Rápida
                        </button>
                        ${{rutaSegura ? `<button onclick="asignarPatrulla('${{mejorPatrulla.id}}', 'segura')" 
                                style="background: #3498db; color: white; border: none; padding: 10px 16px; margin: 5px; border-radius: 5px; cursor: pointer; font-weight: bold;">
                            🛡️ Asignar Ruta Segura
                        </button>` : ''}}
                    </div>`;
                    
                    document.getElementById('contenido-recomendaciones').innerHTML = htmlRecomendaciones;
                    
                }} catch (error) {{
                    console.error('❌ Error en calcularRutasDuales:', error);
                }}
            }}

            // --- Función de Asignación de Patrulla ---
            window.asignarPatrulla = function(idPatrulla, tipoRuta) {{
                console.log(`Asignando ${{idPatrulla}} con ruta ${{tipoRuta}}`);
                
                const patrulla = patrullas.find(p => p.id === idPatrulla);
                if (patrulla) {{
                    patrulla.status = 'en_ruta';
                    patrulla.marker.setIcon(L.divIcon({{ 
                        html: `<div class="patrol-ocupado">${{patrulla.id}}</div>`, 
                        iconSize: [32, 32], 
                        className: '' 
                    }}));
                    
                    const tipoTexto = tipoRuta === 'rapida' ? 'Rápida ⚡' : 'Segura 🛡️';
                    const mensaje = `✅ ${{patrulla.id}} despachada<br>📍 Ruta: ${{tipoTexto}}<br>🚀 Estado: En camino`;
                    
                    document.getElementById('contenido-recomendaciones').innerHTML = `
                        <div style="color: #28a745; font-weight: bold; padding: 20px; background: #d4edda; border-radius: 8px; border: 2px solid #c3e6cb; text-align: center;">
                            ${{mensaje}}
                        </div>`;
                }}
            }}

            // --- Hacer función global ---
            window.toggleGrafoVisualizacion = toggleGrafoVisualizacion;
        </script>
    </body>
    </html>
    """

    # Mostrar el mapa
    components.html(mapa_html, height=650)

    # Información adicional
    st.markdown("### 📈 Información del Modelo")
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"""
        **⚡ Modelo de Costos Mejorado:**
        - Ruta Rápida: `Costo(e) = μ(e)`
        - Ruta Segura: `Costo(e) = μ(e) × f_seguridad(e)`
        - Perfil horario: **{perfil_horario}**
        - Condición climática: **{condicion_clima}**
        - **Red bidireccional completa**
        """)
    
    with col2:
        st.markdown("""
        **🎯 Algoritmo A* Optimizado:**
        - Heurística: `h(n) = Distancia/Velocidad_Máx`
        - Límite tiempo: 6 segundos por búsqueda
        - Límite iteraciones: 5,000 nodos
        - **Conectividad bidireccional garantizada**
        - **Factores de seguridad aplicados por tipo de vía**
        """)

    # Estado actual del sistema
    st.markdown("### 🔄 Estado Actual")
    estado_df = pd.DataFrame(patrullas_data)
    st.dataframe(estado_df, hide_index=True)

else:
    st.error("❌ No se pudo cargar el grafo de Tacna. Verifique la conexión a internet y reinicie la aplicación.")
    st.info("💡 **Sugerencia:** Asegúrese de tener una conexión estable a internet para descargar los datos de OpenStreetMap.")
