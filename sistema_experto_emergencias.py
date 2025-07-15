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

# --- Funciones de Cache y Carga del Grafo (Tarea de Luz) ---
@st.cache_data
def cargar_grafo_tacna():
    """
    Carga un grafo enriquecido de Tacna con atributos estáticos para el modelo probabilístico.
    Implementa las especificaciones del proyecto para variables aleatorias N(μ, σ).
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
        
        # Enriquecimiento del grafo con atributos estáticos (Responsabilidad de Luz)
        for u, v, key, data in G.edges(data=True, keys=True):
            # Calcular longitud geodésica si no existe
            if 'length' not in data:
                node_u = G.nodes[u]
                node_v = G.nodes[v]
                data['length'] = geodesic((node_u['y'], node_u['x']), (node_v['y'], node_v['x'])).meters
            
            # Clasificar tipo de vía
            highway = data.get('highway', 'residential')
            if isinstance(highway, list):
                highway = highway[0]

            # Asignación de atributos estáticos según especificaciones del proyecto
            if highway in ['motorway', 'trunk', 'primary']:
                data['tipo_via'] = 'avenida_principal'
                data['velocidad_base'] = 60  # km/h
                data['sigma_base'] = 5       # Baja incertidumbre
                data['factor_calidad'] = 1.0 # Buena calidad
            elif highway in ['secondary', 'tertiary']:
                data['tipo_via'] = 'calle_colectora'
                data['velocidad_base'] = 40
                data['sigma_base'] = 10      # Incertidumbre moderada
                data['factor_calidad'] = 1.2
            elif highway in ['residential', 'unclassified']:
                data['tipo_via'] = 'calle_residencial'
                data['velocidad_base'] = 25
                data['sigma_base'] = 12
                data['factor_calidad'] = 1.3
            else:
                data['tipo_via'] = 'jiron_comercial'
                data['velocidad_base'] = 30
                data['sigma_base'] = 15      # Alta incertidumbre
                data['factor_calidad'] = 1.4

            # Aplicar multiplicadores de riesgo según tabla del proyecto
            if random.random() < 0.15:  # 15% de calles tienen factores de alta incertidumbre
                zona_problema = random.choice(['mercado', 'paradero', 'centro_historico', 'zona_escolar', 'via_mala'])
                if zona_problema == 'mercado':
                    data['sigma_base'] *= 2.0  # Factor 1.70-2.50 del proyecto
                    data['factor_calidad'] *= 1.8
                elif zona_problema == 'paradero':
                    data['sigma_base'] *= 1.5  # Factor 1.40-1.60
                    data['factor_calidad'] *= 1.4
                elif zona_problema == 'centro_historico':
                    data['sigma_base'] *= 1.4  # Factor 1.30-1.50
                    data['factor_calidad'] *= 1.3
                elif zona_problema == 'zona_escolar':
                    data['sigma_base'] *= 2.5  # Factor 2.00-3.50 en horas pico
                    data['factor_calidad'] *= 2.0
                elif zona_problema == 'via_mala':
                    data['sigma_base'] *= 2.2  # Factor 1.80-3.00
                    data['factor_calidad'] *= 2.5

        st.success(f"✅ Grafo de Tacna cargado: {G.number_of_nodes()} nodos, {G.number_of_edges()} arcos")
        st.info(f"📊 Red fuertemente conectada con {len(list(nx.strongly_connected_components(G)))} componente(s)")
        return G
        
    except Exception as e:
        st.error(f"❌ Error al cargar el grafo: {e}")
        return None

# --- Interfaz de Usuario (Sidebar) - Responsabilidad de Noemí ---
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
- 🛡️ Segura: Costo(e) = μ(e) + k×σ(e)

**Heurística A*:**
h(n) = Distancia_Geodésica / Velocidad_Máxima
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
            'id': f"U-{i+1:02d}",  # Unidad-01, Unidad-02, etc.
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
                <div style="margin-top: 3px;"><b>Intersecciones:</b></div>
                <div>� Super hubs (8+ conexiones)</div>
                <div>🟠 Hubs importantes (6+ conexiones)</div>
                <div>🔵 Intersecciones (4+ conexiones)</div>
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

            // Variables globales para marcadores, rutas y visualización del grafo
            let marcadorIncidente, rutaRapidaLayer, rutaSeguraLayer, grafoLayer;
            let mostrarGrafo = false;

            // --- Visualización del Grafo de Red ---
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
                }} else {{
                    // Mostrar grafo
                    mostrarGrafo = true;
                    document.getElementById('btn-grafo').innerHTML = '🗺️ Ocultar Grafo';
                    document.getElementById('btn-grafo').style.background = '#dc3545';
                    
                    // Crear grupo de capas para el grafo
                    grafoLayer = L.layerGroup();
                    
                    console.log(`🗺️ Iniciando visualización del grafo: ${{edges.length}} aristas disponibles`);
                    
                    // Mostrar TODAS las aristas del grafo (red vial completa)
                    let aristasVisibles = 0;
                    const maxAristas = Math.min(edges.length, 2000); // Limite para rendimiento
                    
                    for (let i = 0; i < maxAristas; i++) {{
                        const edge = edges[i];
                        const sourceNode = nodes[edge.source];
                        const targetNode = nodes[edge.target];
                        
                        if (sourceNode && targetNode) {{
                            // Color y grosor según tipo de vía
                            let color, weight, opacity;
                            
                            switch(edge.tipo_via) {{
                                case 'avenida_principal':
                                    color = '#FF6B35'; // Naranja fuerte para avenidas
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
                                    color = '#3498DB'; // Azul para jirones comerciales
                                    weight = 2;
                                    opacity = 0.6;
                                    break;
                                default:
                                    color = '#95A5A6'; // Gris para otros tipos
                                    weight = 1;
                                    opacity = 0.5;
                            }}
                            
                            // Crear la línea (arista) del grafo
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
                                <b>Desde:</b> Nodo ${{edge.source}}<br>
                                <b>Hacia:</b> Nodo ${{edge.target}}<br>
                                <b>Tipo:</b> ${{edge.tipo_via}}<br>
                                <b>Longitud:</b> ${{edge.length.toFixed(1)}}m<br>
                                <b>Velocidad:</b> ${{edge.velocidad_base}} km/h<br>
                                <b>Factor calidad:</b> ${{edge.factor_calidad}}<br>
                                <b>Sigma base:</b> ${{edge.sigma_base}}
                            `).addTo(grafoLayer);
                            
                            aristasVisibles++;
                        }}
                    }}
                    
                    // Solo agregar algunos nodos clave como puntos de referencia (intersecciones importantes)
                    let nodosImportantes = 0;
                    Object.keys(nodes).forEach(nodeId => {{
                        const node = nodes[nodeId];
                        if (node && nodosImportantes < 50) {{ // Solo 50 nodos más importantes
                            // Calcular el grado del nodo (número de conexiones)
                            const conexiones = edges.filter(e => e.source == nodeId || e.target == nodeId).length;
                            
                            // Solo mostrar nodos con muchas conexiones (intersecciones importantes)
                            if (conexiones >= 4) {{
                                let color, radius;
                                if (conexiones >= 8) {{
                                    color = '#E74C3C'; radius = 6; // Rojo para super hubs
                                }} else if (conexiones >= 6) {{
                                    color = '#F39C12'; radius = 4; // Naranja para hubs importantes
                                }} else {{
                                    color = '#3498DB'; radius = 3; // Azul para intersecciones normales
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
                                    <b>Conexiones:</b> ${{conexiones}}<br>
                                    <b>Coordenadas:</b> [${{node.lat.toFixed(4)}}, ${{node.lon.toFixed(4)}}]
                                `).addTo(grafoLayer);
                                
                                nodosImportantes++;
                            }}
                        }}
                    }});
                    
                    // Agregar al mapa
                    grafoLayer.addTo(map);
                    
                    console.log(`✅ Grafo visualizado: ${{aristasVisibles}} aristas, ${{nodosImportantes}} intersecciones importantes`);
                    
                    // Actualizar información en pantalla
                    const infoDiv = document.createElement('div');
                    infoDiv.id = 'info-grafo';
                    infoDiv.style.cssText = `
                        position: absolute; 
                        bottom: 10px; 
                        left: 10px; 
                        background: rgba(255, 255, 255, 0.95); 
                        padding: 10px; 
                        border-radius: 5px; 
                        font-size: 11px; 
                        box-shadow: 0 2px 5px rgba(0,0,0,0.2);
                        z-index: 1000;
                    `;
                    infoDiv.innerHTML = `
                        <b>📊 Grafo Visualizado</b><br>
                        🛣️ Aristas: ${{aristasVisibles}}<br>
                        🏛️ Intersecciones: ${{nodosImportantes}}
                    `;
                    document.body.appendChild(infoDiv);
                    
                    // Limpiar info anterior si existe
                    const infoAnterior = document.getElementById('info-grafo');
                    if (infoAnterior && infoAnterior !== infoDiv) {{
                        infoAnterior.remove();
                    }}
                }} else {{
                    // Limpiar info del grafo cuando se oculta
                    const infoGrafo = document.getElementById('info-grafo');
                    if (infoGrafo) {{
                        infoGrafo.remove();
                    }}
                }}
            }}

            // --- Construcción de Lista de Adyacencia ---
            const listaAdyacencia = {{}};
            edges.forEach(edge => {{
                if (!listaAdyacencia[edge.source]) listaAdyacencia[edge.source] = [];
                
                // Calcular factores dinámicos según especificaciones
                let factorCongestion = 1.0;
                if (PERFIL_HORARIO === "punta") {{
                    switch(edge.tipo_via) {{
                        case "avenida_principal": factorCongestion = 3.0; break;
                        case "calle_colectora": factorCongestion = 2.2; break;
                        case "calle_residencial": factorCongestion = 1.5; break;
                        default: factorCongestion = 1.8;
                    }}
                }} else if (PERFIL_HORARIO === "noche") {{
                    factorCongestion = 0.8; // Menos tráfico nocturno
                }}
                
                const factorClima = (CONDICION_CLIMA === "lluvia") ? 1.3 : 1.0;
                
                // Modelo probabilístico: calcular μ y σ dinámicos
                const tiempoBase = edge.length / (edge.velocidad_base * 1000 / 3600); // segundos
                const muDinamico = tiempoBase * edge.factor_calidad * factorCongestion * factorClima;
                const sigmaDinamico = edge.sigma_base * Math.sqrt(factorCongestion) * factorClima;

                listaAdyacencia[edge.source].push({{
                    node: edge.target,
                    length: edge.length,
                    costo_rapido: muDinamico,                                           // Costo_Rápido(e) = μ(e)
                    costo_seguro: muDinamico + (FACTOR_RIESGO_K * sigmaDinamico)      // Costo_Seguro(e) = μ(e) + k×σ(e)
                }});
            }});

            // --- Algoritmo A* Optimizado para Largas Distancias ---
            function aStar(inicio, destino, tipoCosto) {{
                const tiempoInicio = performance.now();
                console.log(`🔍 A* iniciado: ${{inicio}} → ${{destino}} [${{tipoCosto}}]`);
                
                // Validaciones básicas
                if (!nodes[inicio] || !nodes[destino]) {{
                    console.error(`❌ Nodos inválidos: inicio=${{inicio}}, destino=${{destino}}`);
                    return null;
                }}
                
                if (inicio === destino) {{
                    console.log(`✅ Origen y destino son iguales`);
                    return {{ path: [inicio], cost: 0, nodesExplored: 1 }};
                }}
                
                // Verificar conectividad básica
                if (!listaAdyacencia[inicio] || listaAdyacencia[inicio].length === 0) {{
                    console.warn(`⚠️ Nodo inicio ${{inicio}} tiene ${{listaAdyacencia[inicio]?.length || 0}} vecinos`);
                    // Intentar encontrar el nodo más cercano conectado
                    const nodoAlternativo = encontrarNodoConectadoCercano(inicio);
                    if (nodoAlternativo && nodoAlternativo !== inicio) {{
                        console.log(`🔄 Usando nodo alternativo ${{nodoAlternativo}} en lugar de ${{inicio}}`);
                        inicio = nodoAlternativo;
                    }} else {{
                        console.error(`❌ No hay nodos conectados cerca de ${{inicio}}`);
                        return null;
                    }}
                }}
                
                // Heurística admisible optimizada para largas distancias
                function heuristica(nodoA, nodoB) {{
                    const pA = nodes[nodoA];
                    const pB = nodes[nodoB];
                    if (!pA || !pB) return Infinity;
                    
                    // Distancia euclidiana simplificada pero más precisa
                    const lat1 = pA.lat * Math.PI / 180;
                    const lat2 = pB.lat * Math.PI / 180;
                    const deltaLat = lat2 - lat1;
                    const deltaLon = (pB.lon - pA.lon) * Math.PI / 180;
                    
                    // Fórmula de Haversine simplificada para mejor precisión en largas distancias
                    const a = Math.sin(deltaLat/2) * Math.sin(deltaLat/2) +
                            Math.cos(lat1) * Math.cos(lat2) *
                            Math.sin(deltaLon/2) * Math.sin(deltaLon/2);
                    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
                    const distancia = 6371000 * c; // Radio de la Tierra en metros
                    
                    // Velocidad máxima conservadora para mantener admisibilidad
                    const velocidadMaxMs = 20; // 72 km/h en m/s (más conservador)
                    return distancia / velocidadMaxMs;
                }}
                
                // Función auxiliar para encontrar nodos conectados cercanos
                function encontrarNodoConectadoCercano(nodoProblema) {{
                    let mejorNodo = null;
                    let menorDistancia = Infinity;
                    
                    Object.keys(listaAdyacencia).forEach(nodoId => {{
                        if (listaAdyacencia[nodoId].length > 0) {{
                            const dist = calcularDistanciaSimple(parseInt(nodoId), nodoProblema);
                            if (dist < menorDistancia) {{
                                menorDistancia = dist;
                                mejorNodo = parseInt(nodoId);
                            }}
                        }}
                    }});
                    
                    return mejorNodo;
                }}
                
                function calcularDistanciaSimple(nodo1, nodo2) {{
                    const p1 = nodes[nodo1];
                    const p2 = nodes[nodo2];
                    if (!p1 || !p2) return Infinity;
                    const dx = p2.lon - p1.lon;
                    const dy = p2.lat - p1.lat;
                    return Math.sqrt(dx * dx + dy * dy);
                }}
                
                // Estructuras de datos optimizadas
                const openSet = new Set([inicio]);
                const closedSet = new Set();
                const cameFrom = new Map();
                const gScore = new Map([[inicio, 0]]);
                const fScore = new Map([[inicio, heuristica(inicio, destino)]]);
                
                let nodosExplorados = 0;
                const maxIteraciones = 8000; // Aumentado para largas distancias
                const maxTiempo = 8000; // Aumentado a 8 segundos
                
                while (openSet.size > 0 && nodosExplorados < maxIteraciones) {{
                    // Control de tiempo para evitar congelamiento
                    if (performance.now() - tiempoInicio > maxTiempo) {{
                        console.warn(`⏰ Timeout alcanzado después de ${{(performance.now() - tiempoInicio).toFixed(0)}}ms`);
                        // Intentar devolver la mejor ruta parcial encontrada
                        const rutaParcial = construirMejorRutaParcial(cameFrom, gScore, inicio, destino);
                        if (rutaParcial) {{
                            console.log(`🔄 Devolviendo ruta parcial con ${{rutaParcial.length}} nodos`);
                            return {{ 
                                path: rutaParcial, 
                                cost: gScore.get(rutaParcial[rutaParcial.length - 1]) || 0, 
                                nodesExplored: nodosExplorados,
                                timeMs: performance.now() - tiempoInicio,
                                isPartial: true
                            }};
                        }}
                        break;
                    }}
                    
                    // Encontrar nodo con menor f(n) usando heap simplificado
                    let actual = null;
                    let menorF = Infinity;
                    for (let nodo of openSet) {{
                        const f = fScore.get(nodo) || Infinity;
                        if (f < menorF) {{
                            menorF = f;
                            actual = nodo;
                        }}
                    }}
                    
                    if (!actual) {{
                        console.error(`❌ No se encontró nodo actual válido en iteración ${{nodosExplorados}}`);
                        break;
                    }}
                    
                    nodosExplorados++;
                    
                    // Verificar si llegamos al destino
                    if (actual === destino) {{
                        const ruta = [];
                        let temp = actual;
                        while (temp !== undefined) {{
                            ruta.unshift(temp);
                            temp = cameFrom.get(temp);
                        }}
                        const tiempoTotal = performance.now() - tiempoInicio;
                        console.log(`✅ Ruta completa encontrada en ${{tiempoTotal.toFixed(0)}}ms: ${{ruta.length}} nodos, costo ${{gScore.get(destino).toFixed(2)}}s, explorados ${{nodosExplorados}}`);
                        return {{ 
                            path: ruta, 
                            cost: gScore.get(destino), 
                            nodesExplored: nodosExplorados,
                            timeMs: tiempoTotal,
                            isPartial: false
                        }};
                    }}
                    
                    openSet.delete(actual);
                    closedSet.add(actual);
                    
                    // Explorar vecinos con optimización
                    const vecinos = listaAdyacencia[actual] || [];
                    for (let i = 0; i < vecinos.length; i++) {{
                        const vecino = vecinos[i];
                        const nodoVecino = vecino.node;
                        
                        // Saltar si ya está en el conjunto cerrado
                        if (closedSet.has(nodoVecino)) continue;
                        
                        const costoTentativo = gScore.get(actual) + vecino[tipoCosto];
                        
                        // Verificar si este camino es mejor
                        const costoActual = gScore.get(nodoVecino);
                        if (costoActual === undefined || costoTentativo < costoActual) {{
                            // Este es el mejor camino hasta ahora
                            cameFrom.set(nodoVecino, actual);
                            gScore.set(nodoVecino, costoTentativo);
                            fScore.set(nodoVecino, costoTentativo + heuristica(nodoVecino, destino));
                            
                            if (!openSet.has(nodoVecino)) {{
                                openSet.add(nodoVecino);
                            }}
                        }}
                    }}
                    
                    // Feedback cada 200 iteraciones para debugging
                    if (nodosExplorados % 200 === 0) {{
                        const progreso = ((performance.now() - tiempoInicio) / maxTiempo * 100).toFixed(1);
                        console.log(`🔄 Progreso: ${{nodosExplorados}} nodos, openSet: ${{openSet.size}}, tiempo: ${{progreso}}%`);
                    }}
                }}
                
                // Función para construir la mejor ruta parcial
                function construirMejorRutaParcial(cameFrom, gScore, inicio, destino) {{
                    let mejorNodo = null;
                    let menorDistanciaAlDestino = Infinity;
                    
                    // Encontrar el nodo explorado más cercano al destino
                    for (let [nodo, ] of gScore) {{
                        const distancia = calcularDistanciaSimple(nodo, destino);
                        if (distancia < menorDistanciaAlDestino) {{
                            menorDistanciaAlDestino = distancia;
                            mejorNodo = nodo;
                        }}
                    }}
                    
                    if (!mejorNodo || mejorNodo === inicio) return null;
                    
                    // Construir ruta hasta el mejor nodo encontrado
                    const ruta = [];
                    let temp = mejorNodo;
                    while (temp !== undefined) {{
                        ruta.unshift(temp);
                        temp = cameFrom.get(temp);
                    }}
                    
                    return ruta.length > 1 ? ruta : null;
                }}
                
                const tiempoTotal = performance.now() - tiempoInicio;
                console.log(`❌ No se encontró ruta después de ${{nodosExplorados}} nodos en ${{tiempoTotal.toFixed(0)}}ms`);
                
                // Intentar devolver ruta parcial como último recurso
                const rutaParcial = construirMejorRutaParcial(cameFrom, gScore, inicio, destino);
                if (rutaParcial && rutaParcial.length > 1) {{
                    console.log(`🔄 Devolviendo ruta parcial de emergencia con ${{rutaParcial.length}} nodos`);
                    return {{ 
                        path: rutaParcial, 
                        cost: gScore.get(rutaParcial[rutaParcial.length - 1]) || 0, 
                        nodesExplored: nodosExplorados,
                        timeMs: tiempoTotal,
                        isPartial: true
                    }};
                }}
                
                return null;
            }}

            // --- Manejo de Eventos de Emergencia con Procesamiento Asíncrono ---
            map.on('click', function(e) {{
                if (!MODO_EMERGENCIA) return;
                
                const coordsIncidente = e.latlng;
                console.log(`🚨 Emergencia reportada en: [${{coordsIncidente.lat.toFixed(6)}}, ${{coordsIncidente.lng.toFixed(6)}}]`);
                
                // Mostrar indicador de carga inmediatamente
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
                
                // Procesar de forma asíncrona para evitar congelamiento
                setTimeout(() => {{
                    procesarEmergencia(coordsIncidente);
                }}, 100);
            }});
            
            // --- Función de Procesamiento de Emergencia Asíncrona ---
            function procesarEmergencia(coordsIncidente) {{
                try {{
                    // Encontrar nodo más cercano
                    let nodoDestino = null;
                    let distanciaMinima = Infinity;
                    const nodosArray = Object.keys(nodes);
                    
                    for (let i = 0; i < nodosArray.length; i++) {{
                        const nodeId = nodosArray[i];
                        const posNodo = L.latLng(nodes[nodeId].lat, nodes[nodeId].lon);
                        const distancia = posNodo.distanceTo(coordsIncidente);
                        if (distancia < distanciaMinima) {{
                            distanciaMinima = distancia;
                            nodoDestino = parseInt(nodeId);
                        }}
                    }}
                    
                    if (!nodoDestino) {{
                        document.getElementById('contenido-recomendaciones').innerHTML = 
                            "<div style='color: #dc3545; font-weight: bold; padding: 15px;'>❌ Error: Ubicación no accesible en la red vial.</div>";
                        return;
                    }}
                    
                    console.log(`📍 Nodo destino: ${{nodoDestino}}, distancia: ${{distanciaMinima.toFixed(1)}}m`);
                    
                    // Evaluar patrullas disponibles
                    const patrullasDisponibles = patrullas.filter(p => p.status === 'disponible');
                    
                    if (patrullasDisponibles.length === 0) {{
                        document.getElementById('contenido-recomendaciones').innerHTML = 
                            "<div style='color: #dc3545; font-weight: bold; padding: 15px;'>⚠️ No hay patrullas disponibles en este momento.</div>";
                        return;
                    }}
                    
                    // Actualizar estado de procesamiento
                    document.getElementById('contenido-recomendaciones').innerHTML += `
                        <p style="color: #666; margin: 10px 0;">
                            📊 Evaluando ${{patrullasDisponibles.length}} patrullas disponibles...
                        </p>`;
                    
                    // Calcular rutas para todas las patrullas (mejorado para largas distancias)
                    let candidatos = [];
                    let patrullasEvaluadas = 0;
                    
                    // Pre-calcular distancia euclidiana para priorizar patrullas más cercanas
                    const patrullasConDistancia = patrullasDisponibles.map(p => {{
                        const distEuclidiana = calcularDistanciaEuclidiana(p.nodo_actual, nodoDestino);
                        return {{ patrulla: p, distanciaEuclidiana: distEuclidiana }};
                    }}).sort((a, b) => a.distanciaEuclidiana - b.distanciaEuclidiana);
                    
                    console.log(`📊 Patrullas ordenadas por distancia:`);
                    patrullasConDistancia.forEach((item, idx) => {{
                        console.log(`  ${{idx + 1}}. ${{item.patrulla.id}}: ${{item.distanciaEuclidiana.toFixed(0)}}m`);
                    }});
                    
                    function calcularDistanciaEuclidiana(nodo1, nodo2) {{
                        const p1 = nodes[nodo1];
                        const p2 = nodes[nodo2];
                        if (!p1 || !p2) return Infinity;
                        
                        const dx = (p2.lon - p1.lon) * 111320 * Math.cos(p1.lat * Math.PI / 180);
                        const dy = (p2.lat - p1.lat) * 110540;
                        return Math.sqrt(dx * dx + dy * dy);
                    }}
                    
                    for (let i = 0; i < patrullasConDistancia.length; i++) {{
                        const {{ patrulla: p, distanciaEuclidiana }} = patrullasConDistancia[i];
                        console.log(`🔍 Evaluando patrulla ${{p.id}} desde nodo ${{p.nodo_actual}} (dist: ${{distanciaEuclidiana.toFixed(0)}}m)`);
                        
                        const resultado = aStar(p.nodo_actual, nodoDestino, 'costo_rapido');
                        patrullasEvaluadas++;
                        
                        if (resultado && resultado.path && resultado.path.length > 0) {{
                            const estado = resultado.isPartial ? "parcial" : "completa";
                            candidatos.push({{ 
                                patrulla: p, 
                                tiempo: resultado.cost,
                                nodosExplorados: resultado.nodesExplored,
                                tiempoCalculo: resultado.timeMs || 0,
                                distanciaEuclidiana: distanciaEuclidiana,
                                rutaParcial: resultado.isPartial || false
                            }});
                            console.log(`✅ Ruta ${{estado}} para ${{p.id}}: ${{resultado.cost.toFixed(2)}}s (${{resultado.timeMs?.toFixed(0) || 0}}ms, ${{resultado.path.length}} nodos)`);
                        }} else {{
                            console.log(`❌ Sin ruta válida para ${{p.id}}`);
                        }}
                        
                        // Actualizar progreso
                        if (patrullasEvaluadas < patrullasConDistancia.length) {{
                            const progreso = Math.round((patrullasEvaluadas / patrullasConDistancia.length) * 100);
                            document.getElementById('contenido-recomendaciones').innerHTML = `
                                <div style="text-align: center; padding: 20px;">
                                    <h5>🚨 Procesando Emergencia</h5>
                                    <p>Evaluando patrulla ${{p.id}}... (${{patrullasEvaluadas}}/${{patrullasConDistancia.length}})</p>
                                    <div style="width: 100%; background: #f0f0f0; border-radius: 10px; margin: 10px 0;">
                                        <div style="width: ${{progreso}}%; background: #3498db; height: 20px; border-radius: 10px; transition: width 0.3s;"></div>
                                    </div>
                                    <small>Progreso: ${{progreso}}%</small>
                                </div>`;
                        }}
                        
                        // Si encontramos al menos una ruta completa cercana, podemos parar la búsqueda temprana
                        // para optimizar el tiempo de respuesta
                        if (candidatos.length > 0 && 
                            !candidatos[candidatos.length - 1].rutaParcial && 
                            distanciaEuclidiana < 2000 && // Menos de 2km
                            candidatos.length >= Math.min(3, patrullasConDistancia.length)) {{
                            console.log(`⚡ Búsqueda temprana completada con ${{candidatos.length}} candidatos válidos`);
                            break;
                        }}
                    }}
                    
                    if (candidatos.length === 0) {{
                        console.log("❌ No se encontró ninguna ruta válida después de evaluar todas las patrullas");
                        document.getElementById('contenido-recomendaciones').innerHTML = `
                            <div style="background: #f8d7da; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #dc3545;">
                                <h5>❌ No se encontró una ruta válida</h5>
                                <p>El sistema no pudo calcular una ruta para ninguna patrulla disponible.</p>
                                <p><strong>📊 Resumen del análisis:</strong></p>
                                <ul>
                                    <li>🚔 Patrullas evaluadas: ${{patrullasEvaluadas}}/${{patrullasDisponibles.length}}</li>
                                    <li>📍 Ubicación objetivo: [${{lat.toFixed(6)}}, ${{lon.toFixed(6)}}]</li>
                                    <li>🗺️ Nodo más cercano: ${{nodoDestino}}</li>
                                    <li>⏱️ Tiempo límite de cálculo: 8 segundos por patrulla</li>
                                    <li>🔍 Iteraciones máximas: 8,000 por búsqueda</li>
                                </ul>
                                <p><strong>🔍 Posibles causas:</strong></p>
                                <ul>
                                    <li>📍 Ubicación muy alejada de la red de carreteras</li>
                                    <li>🚧 Zona sin conectividad en el mapa vial</li>
                                    <li>⏰ Limitaciones de tiempo de cálculo para distancias muy largas</li>
                                    <li>🗺️ Área fuera de la cobertura del mapa de Tacna</li>
                                </ul>
                                <p><strong>💡 Sugerencias:</strong></p>
                                <ul>
                                    <li>📌 Intente con una ubicación más cercana a calles principales</li>
                                    <li>🏙️ Verifique que la zona esté dentro del área urbana de Tacna</li>
                                    <li>🔄 Considere redistribuir las patrullas a posiciones más estratégicas</li>
                                    <li>📞 Para emergencias en zonas remotas, coordine con otras unidades disponibles</li>
                                </ul>
                            </div>`;
                        return;
                    }}
                    
                    // Mostrar resumen de candidatos encontrados antes de procesar
                    const rutasCompletas = candidatos.filter(c => !c.rutaParcial).length;
                    const rutasParciales = candidatos.filter(c => c.rutaParcial).length;
                    
                    console.log(`✅ Análisis completado: ${{rutasCompletas}} rutas completas, ${{rutasParciales}} rutas parciales`);
                    
                    document.getElementById('contenido-recomendaciones').innerHTML = `
                        <div style="background: #d1ecf1; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #bee5eb;">
                            <h5>📊 Análisis completado</h5>
                            <p>✅ Rutas completas encontradas: <strong>${{rutasCompletas}}</strong></p>
                            <p>⚠️ Rutas parciales encontradas: <strong>${{rutasParciales}}</strong></p>
                            <p>🎯 Seleccionando la mejor opción...</p>
                        </div>`;
                    
                    // Seleccionar mejor patrulla (priorizar rutas completas)
                    candidatos.sort((a, b) => {{
                        // Priorizar rutas completas sobre parciales
                        if (a.rutaParcial !== b.rutaParcial) {{
                            return a.rutaParcial ? 1 : -1;
                        }}
                        // Luego por tiempo de llegada
                        return a.tiempo - b.tiempo;
                    }});
                    
                    const mejorPatrulla = candidatos[0].patrulla;
                    const esRutaParcial = candidatos[0].rutaParcial;
                    
                    console.log(`🏆 Mejor patrulla: ${{mejorPatrulla.id}} con tiempo: ${{candidatos[0].tiempo.toFixed(2)}}s ${{esRutaParcial ? '(RUTA PARCIAL)' : '(RUTA COMPLETA)'}}`);
                    
                    // Mostrar advertencia si es ruta parcial
                    if (esRutaParcial) {{
                        document.getElementById('contenido-recomendaciones').innerHTML += `
                            <div style="background: #fff3cd; padding: 10px; border-radius: 6px; margin: 10px 0; border-left: 4px solid #ffc107;">
                                <strong>⚠️ Advertencia:</strong> La mejor ruta disponible es parcial. 
                                La patrulla podría no llegar exactamente al destino especificado.
                            </div>`;
                    }}
                    
                    // Procesar rutas duales de forma asíncrona
                    setTimeout(() => {{
                        calcularRutasDuales(mejorPatrulla, nodoDestino);
                    }}, 100);
                    
                }} catch (error) {{
                    console.error('❌ Error en procesarEmergencia:', error);
                    document.getElementById('contenido-recomendaciones').innerHTML = 
                        `<div style='color: #dc3545; font-weight: bold; padding: 15px;'>
                            ❌ Error interno del sistema<br>
                            <small>${{error.message}}</small>
                        </div>`;
                }}
            }}
            
            // --- Función para Calcular Rutas Duales ---
            function calcularRutasDuales(mejorPatrulla, nodoDestino) {{
                try {{
                    document.getElementById('contenido-recomendaciones').innerHTML = `
                        <div style="text-align: center; padding: 15px;">
                            <h5>🎯 Calculando rutas para ${{mejorPatrulla.id}}</h5>
                            <p>Generando recomendaciones del sistema experto...</p>
                        </div>`;
                    
                    // Calcular ambas rutas
                    const rutaRapida = aStar(mejorPatrulla.nodo_actual, nodoDestino, 'costo_rapido');
                    const rutaSegura = aStar(mejorPatrulla.nodo_actual, nodoDestino, 'costo_seguro');
                    
                    if (!rutaRapida) {{
                        document.getElementById('contenido-recomendaciones').innerHTML = 
                            "<div style='color: #dc3545; font-weight: bold; padding: 15px;'>❌ Error: No se pudo calcular la ruta rápida</div>";
                        return;
                    }}
                    
                    // Formatear tiempo
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
                            ⚡ Cálculo: ${{rutaRapida.timeMs?.toFixed(0) || 0}}ms<br>
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
                            ⚡ Cálculo: ${{rutaSegura.timeMs?.toFixed(0) || 0}}ms<br>
                            📊 Diferencia: +${{formatearTiempo(diferencia)}} (+${{porcentaje}}%)<br>
                            🧮 Función: μ(e) + ${{FACTOR_RIESGO_K}}×σ(e)
                        </div>`;
                    }} else {{
                        htmlRecomendaciones += `
                        <div style="border-left: 5px solid #f39c12; padding: 12px; margin: 8px 0; background: #fef9e7; border-radius: 5px;">
                            <b>⚠️ Ruta Segura</b><br>
                            No se pudo calcular una ruta alternativa segura.<br>
                            <small>Recomendamos usar la ruta rápida con precaución.</small>
                        </div>`;
                    }}
                    
                    // Panel de decisión
                    htmlRecomendaciones += `
                    <div style="background: #f8f9fa; padding: 12px; border-radius: 5px; margin: 10px 0;">
                        <h6>🤖 Recomendación del Sistema:</h6>
                        <p style="font-size: 0.9em;">
                            ${{rutaSegura && (rutaSegura.cost - rutaRapida.cost) / rutaRapida.cost < 0.3 ? 
                                "🛡️ Se recomienda la ruta segura por su bajo costo adicional." : 
                                "⚡ Se recomienda la ruta rápida para respuesta urgente."}}
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
                    document.getElementById('contenido-recomendaciones').innerHTML = 
                        `<div style='color: #dc3545; font-weight: bold; padding: 15px;'>
                            ❌ Error al calcular rutas duales<br>
                            <small>${{error.message}}</small>
                        </div>`;
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
                    
                    // Actualizar popup
                    const statusElement = document.getElementById(`status-${{patrulla.id}}`);
                    if (statusElement) statusElement.innerText = 'en_ruta';
                    
                    const tipoTexto = tipoRuta === 'rapida' ? 'Rápida ⚡' : 'Segura 🛡️';
                    const mensaje = `✅ ${{patrulla.id}} despachada<br>📍 Ruta: ${{tipoTexto}}<br>🚀 Estado: En camino`;
                    
                    document.getElementById('contenido-recomendaciones').innerHTML = `
                        <div style="color: #28a745; font-weight: bold; padding: 20px; background: #d4edda; border-radius: 8px; border: 2px solid #c3e6cb; text-align: center;">
                            ${{mensaje}}
                        </div>
                        <div style="text-align: center; margin-top: 15px;">
                            <small style="color: #6c757d;">Sistema monitoreando progreso...</small>
                        </div>`;
                }} else {{
                    console.error(`Patrulla ${{idPatrulla}} no encontrada`);
                }}
            }}

            // --- Hacer función global para el botón ---
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
        **⚡ Modelo de Costos:**
        - Ruta Rápida: `Costo(e) = μ(e)`
        - Ruta Segura: `Costo(e) = μ(e) + {factor_riesgo_k}×σ(e)`
        - Perfil horario: **{perfil_horario}**
        - Condición climática: **{condicion_clima}**
        """)
    
    with col2:
        st.markdown("""
        **🎯 Algoritmo A*:**
        - Heurística: `h(n) = Distancia/Velocidad_Máx`
        - Límite tiempo: 8 segundos por búsqueda
        - Límite iteraciones: 8,000 nodos
        - Rutas parciales habilitadas
        """)

    # Estado actual del sistema
    st.markdown("### 🔄 Estado Actual")
    estado_df = pd.DataFrame(patrullas_data)
    st.dataframe(estado_df, hide_index=True)

else:
    st.error("❌ No se pudo cargar el grafo de Tacna. Verifique la conexión a internet y reinicie la aplicación.")
    st.info("💡 **Sugerencia:** Asegúrese de tener una conexión estable a internet para descargar los datos de OpenStreetMap.")

# --- Función para Visualizar el Grafo ---
def mostrar_estadisticas_grafo(_G):
    """
    Muestra estadísticas del grafo sin cacheo para evitar problemas de hash.
    """
    try:
        # Estadísticas básicas del grafo
        num_nodos = _G.number_of_nodes()
        num_arcos = _G.number_of_edges()
        componentes_conectados = list(nx.strongly_connected_components(_G))
        num_componentes = len(componentes_conectados)
        
        # Análisis de conectividad
        grados_entrada = dict(_G.in_degree())
        grados_salida = dict(_G.out_degree())
        nodos_aislados = [n for n in _G.nodes() if grados_entrada[n] == 0 and grados_salida[n] == 0]
        nodos_sin_entrada = [n for n in _G.nodes() if grados_entrada[n] == 0 and grados_salida[n] > 0]
        nodos_sin_salida = [n for n in _G.nodes() if grados_entrada[n] > 0 and grados_salida[n] == 0]
        
        # Mostrar estadísticas
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("🔵 Nodos Totales", num_nodos)
            st.metric("⚫ Nodos Aislados", len(nodos_aislados))
        
        with col2:
            st.metric("🛣️ Arcos Totales", num_arcos)
            st.metric("⬆️ Sin Entrada", len(nodos_sin_entrada))
        
        with col3:
            st.metric("🔗 Componentes", num_componentes)
            st.metric("⬇️ Sin Salida", len(nodos_sin_salida))
        
        with col4:
            componente_principal = len(componentes_conectados[0]) if componentes_conectados else 0
            st.metric("🎯 Comp. Principal", componente_principal)
            densidad = nx.density(_G)
            st.metric("📊 Densidad", f"{densidad:.4f}")
        
        # Análisis de conectividad
        st.markdown("#### 🔍 Diagnóstico de Conectividad")
        
        if num_componentes > 1:
            st.warning(f"⚠️ **Problema de Conectividad:** El grafo tiene {num_componentes} componentes separados. Esto puede causar fallas en el cálculo de rutas entre componentes diferentes.")
            
            # Mostrar tamaños de componentes
            tamaños_componentes = [len(comp) for comp in componentes_conectados]
            st.write(f"**Tamaños de componentes:** {tamaños_componentes[:10]}" + (" ..." if len(tamaños_componentes) > 10 else ""))
            
            # Información detallada sobre componentes
            st.info(f"📊 **Análisis de componentes:** El componente principal tiene {componente_principal} nodos ({componente_principal/num_nodos*100:.1f}% del total).")
            
            if num_componentes > 10:
                st.warning(f"🚨 **Fragmentación Alta:** Hay {num_componentes} componentes separados, indicando una red muy fragmentada.")
        else:
            st.success("✅ **Grafo Fuertemente Conectado:** Todas las rutas son teóricamente posibles.")
        
        if len(nodos_aislados) > 0:
            st.error(f"❌ **Nodos Aislados:** {len(nodos_aislados)} nodos ({len(nodos_aislados)/num_nodos*100:.1f}%) no tienen conexiones. Estos nodos son completamente inaccesibles.")
            if len(nodos_aislados) <= 10:
                st.write(f"**Nodos aislados:** {nodos_aislados}")
            else:
                st.write(f"**Primeros 10 nodos aislados:** {nodos_aislados[:10]}...")
        
        if len(nodos_sin_entrada) > 0 or len(nodos_sin_salida) > 0:
            st.warning(f"⚠️ **Conectividad Parcial:** {len(nodos_sin_entrada)} nodos sin entrada y {len(nodos_sin_salida)} sin salida pueden limitar las rutas.")
            
            if len(nodos_sin_entrada) > 0:
                st.write(f"   - **Nodos sin entrada (solo destino):** {len(nodos_sin_entrada)} nodos")
            if len(nodos_sin_salida) > 0:
                st.write(f"   - **Nodos sin salida (solo origen):** {len(nodos_sin_salida)} nodos")
        
        # Análisis de grados
        grados = [grados_entrada[n] + grados_salida[n] for n in _G.nodes()]
        grado_promedio = sum(grados) / len(grados) if grados else 0
        grado_max = max(grados) if grados else 0
        grado_min = min(grados) if grados else 0
        
        st.markdown("#### 📈 Estadísticas de Grados")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📊 Grado Promedio", f"{grado_promedio:.2f}")
        with col2:
            st.metric("📈 Grado Máximo", grado_max)
        with col3:
            st.metric("📉 Grado Mínimo", grado_min)
        
        # Análisis de distribución de grados
        if grados:
            nodos_alta_conectividad = len([g for g in grados if g >= 6])
            nodos_baja_conectividad = len([g for g in grados if g <= 2])
            
            st.write(f"**Distribución de conectividad:**")
            st.write(f"   - Alta conectividad (≥6 conexiones): {nodos_alta_conectividad} nodos ({nodos_alta_conectividad/len(grados)*100:.1f}%)")
            st.write(f"   - Baja conectividad (≤2 conexiones): {nodos_baja_conectividad} nodos ({nodos_baja_conectividad/len(grados)*100:.1f}%)")
        
        # Crear mapa simple de distribución de nodos
        st.markdown("#### 🗺️ Mapa de Distribución de Nodos")
        
        # Calcular centro del grafo
        lats = [data['y'] for _, data in _G.nodes(data=True) if 'y' in data]
        lons = [data['x'] for _, data in _G.nodes(data=True) if 'x' in data]
        
        if lats and lons:
            centro_lat = sum(lats) / len(lats)
            centro_lon = sum(lons) / len(lons)
            
            # Crear mapa simple
            mapa_simple = folium.Map(
                location=[centro_lat, centro_lon], 
                zoom_start=12,
                tiles='OpenStreetMap'
            )
            
            # Agregar muestra de nodos (máximo 200 para rendimiento)
            nodos_muestra = list(_G.nodes())[:200]
            
            # Contadores para la leyenda
            contadores = {"aislados": 0, "hubs": 0, "normales": 0, "bajos": 0}
            
            for nodo in nodos_muestra:
                node_data = _G.nodes[nodo]
                if 'y' in node_data and 'x' in node_data:
                    grado_total = grados_entrada[nodo] + grados_salida[nodo]
                    
                    # Color según tipo de nodo
                    if nodo in nodos_aislados:
                        color = 'black'
                        icono = '⚫'
                        tipo = 'AISLADO'
                        contadores["aislados"] += 1
                    elif grado_total >= 6:
                        color = 'red'
                        icono = '🔴'
                        tipo = 'HUB'
                        contadores["hubs"] += 1
                    elif grado_total >= 3:
                        color = 'blue'
                        icono = '🔵'
                        tipo = 'NORMAL'
                        contadores["normales"] += 1
                    else:
                        color = 'gray'
                        icono = '⚪'
                        tipo = 'BAJA CONECTIVIDAD'
                        contadores["bajos"] += 1
                    
                    folium.CircleMarker(
                        location=[node_data['y'], node_data['x']],
                        radius=4,
                        popup=f"<b>Nodo: {nodo}</b><br>Tipo: {tipo}<br>Grado total: {grado_total}<br>Entrada: {grados_entrada[nodo]}<br>Salida: {grados_salida[nodo]}",
                        tooltip=f"Nodo {nodo}: {tipo} (Grado: {grado_total})",
                        color=color,
                        fill=True,
                        weight=2,
                        fillOpacity=0.7
                    ).add_to(mapa_simple)
            
            # Agregar leyenda al mapa
            leyenda_html = f'''
            <div style="position: fixed; 
                        top: 10px; right: 10px; width: 200px; height: 150px; 
                        background-color: white; border:2px solid grey; z-index:9999; 
                        font-size:11px; padding: 10px">
            <h4>🎨 Tipos de Nodos</h4>
            <ul style="margin: 5px; padding-left: 15px;">
                <li>🔴 Hubs ({contadores["hubs"]}): ≥6 conexiones</li>
                <li>🔵 Normales ({contadores["normales"]}): 3-5 conexiones</li>
                <li>⚪ Baja conectividad ({contadores["bajos"]}): ≤2 conexiones</li>
                <li>⚫ Aislados ({contadores["aislados"]}): 0 conexiones</li>
            </ul>
            <small>Muestra: {len(nodos_muestra)}/{num_nodos} nodos</small>
            </div>
            '''
            mapa_simple.get_root().html.add_child(folium.Element(leyenda_html))
            
            # Mostrar el mapa
            components.html(mapa_simple._repr_html_(), height=500)
            
            st.caption(f"📍 **Mapa de diagnóstico:** Mostrando {len(nodos_muestra)} de {num_nodos} nodos para mejor rendimiento. Centro del grafo: [{centro_lat:.4f}, {centro_lon:.4f}]")
            
            # Información sobre la muestra
            st.info(f"📊 **En la muestra mostrada:** {contadores['hubs']} hubs, {contadores['normales']} normales, {contadores['bajos']} baja conectividad, {contadores['aislados']} aislados")
        else:
            st.error("❌ No se pudieron obtener las coordenadas de los nodos para crear el mapa.")
        
        # Recomendaciones específicas
        st.markdown("#### 💡 Recomendaciones para Mejorar el Sistema")
        
        if len(nodos_aislados) > 5:
            st.info("🔧 **Limpieza del Grafo:** Considere filtrar nodos aislados durante la carga para mejorar el rendimiento del algoritmo A*.")
        
        if num_componentes > 1:
            st.info(f"🔗 **Conectividad:** Use solo el componente fuertemente conectado más grande ({componente_principal} nodos) para garantizar que todas las rutas sean factibles.")
        
        if densidad < 0.001:
            st.info("📈 **Densidad Baja:** La red tiene muy baja densidad. Considere aumentar los límites de tiempo y iteraciones en el algoritmo A* para rutas largas.")
        
        if grado_promedio < 2.5:
            st.warning("🛣️ **Conectividad Local Baja:** El grado promedio es bajo, lo que puede crear cuellos de botella en la red vial.")
        
        if nodos_alta_conectividad < num_nodos * 0.05:
            st.warning("🎯 **Pocos Hubs:** Menos del 5% de los nodos son hubs importantes. Esto puede limitar las opciones de rutas eficientes.")
        
        # Resumen del análisis
        st.markdown("#### 📋 Resumen del Diagnóstico")
        
        if num_componentes == 1 and len(nodos_aislados) == 0:
            st.success("✅ **Grafo Óptimo:** Red completamente conectada sin nodos aislados.")
        elif num_componentes == 1 and len(nodos_aislados) < num_nodos * 0.05:
            st.success("✅ **Grafo Bueno:** Red principalmente conectada con pocos nodos aislados.")
        elif num_componentes <= 5:
            st.warning("⚠️ **Grafo Regular:** Red con fragmentación moderada que puede afectar algunas rutas.")
        else:
            st.error("❌ **Grafo Problemático:** Red muy fragmentada que puede causar muchos fallos en el cálculo de rutas.")
        
        return {
            "num_nodos": num_nodos,
            "num_arcos": num_arcos,
            "num_componentes": num_componentes,
            "nodos_aislados": len(nodos_aislados),
            "densidad": densidad,
            "grado_promedio": grado_promedio
        }
        
    except Exception as e:
        st.error(f"❌ Error al analizar el grafo: {e}")
        return None
    try:
        # Estadísticas básicas del grafo
        num_nodos = _G.number_of_nodes()
        num_arcos = _G.number_of_edges()
        componentes_conectados = list(nx.strongly_connected_components(_G))
        num_componentes = len(componentes_conectados)
        
        # Análisis de conectividad
        grados_entrada = dict(_G.in_degree())
        grados_salida = dict(_G.out_degree())
        nodos_aislados = [n for n in _G.nodes() if grados_entrada[n] == 0 and grados_salida[n] == 0]
        nodos_sin_entrada = [n for n in _G.nodes() if grados_entrada[n] == 0 and grados_salida[n] > 0]
        nodos_sin_salida = [n for n in _G.nodes() if grados_entrada[n] > 0 and grados_salida[n] == 0]
        
        # Crear mapa de visualización del grafo
        # Calcular centro del grafo
        lats = [data['y'] for _, data in _G.nodes(data=True) if 'y' in data]
        lons = [data['x'] for _, data in G.nodes(data=True) if 'x' in data]
        
        if not lats or not lons:
            return None, {"error": "No se encontraron coordenadas válidas"}
        
        centro_lat = sum(lats) / len(lats)
        centro_lon = sum(lons) / len(lons)
        
        # Crear mapa base
        mapa_grafo = folium.Map(
            location=[centro_lat, centro_lon], 
            zoom_start=13,
            tiles='CartoDB positron'
        )
        
        # Colorear componentes conectados
        colores_componentes = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'lightred', 
                              'beige', 'darkblue', 'darkgreen', 'cadetblue', 'darkpurple', 
                              'white', 'pink', 'lightblue', 'lightgreen', 'gray', 'black', 'lightgray']
        
        # Visualizar nodos por componente
        for i, componente in enumerate(componentes_conectados[:len(colores_componentes)]):
            tamaño_componente = len(componente)
            
            for nodo in componente:
                node_data = G.nodes[nodo]
                if 'y' in node_data and 'x' in node_data:
                    # Determinar tipo de nodo
                    grado_total = grados_entrada[nodo] + grados_salida[nodo]
                    
                    if nodo in nodos_aislados:
                        icono = "⚫"  # Nodo aislado
                        tooltip = f"Nodo {nodo}: AISLADO"
                    elif nodo in nodos_sin_entrada:
                        icono = "⬆️"  # Solo salida
                        tooltip = f"Nodo {nodo}: Solo salida ({grados_salida[nodo]})"
                    elif nodo in nodos_sin_salida:
                        icono = "⬇️"  # Solo entrada
                        tooltip = f"Nodo {nodo}: Solo entrada ({grados_entrada[nodo]})"
                    elif grado_total >= 6:
                        icono = "🔴"  # Nodo importante (alta conectividad)
                        tooltip = f"Nodo {nodo}: Hub (E:{grados_entrada[nodo]}, S:{grados_salida[nodo]})"
                    else:
                        icono = "🔵"  # Nodo normal
                        tooltip = f"Nodo {nodo}: Normal (E:{grados_entrada[nodo]}, S:{grados_salida[nodo]})"
                    
                    folium.Marker(
                        location=[node_data['y'], node_data['x']],
                        popup=f"Nodo: {nodo}<br>Componente: {i+1}/{num_componentes}<br>Tamaño componente: {tamaño_componente}<br>Entrada: {grados_entrada[nodo]}<br>Salida: {grados_salida[nodo]}",
                        tooltip=tooltip,
                        icon=folium.DivIcon(
                            html=f'<div style="font-size: 8px; text-align: center;">{icono}</div>',
                            icon_size=(15, 15),
                            icon_anchor=(7, 7)
                        )
                    ).add_to(mapa_grafo)
        
        # Agregar algunas aristas para mostrar conectividad (muestra limitada para no sobrecargar)
        aristas_mostradas = 0
        max_aristas_mostrar = min(500, num_arcos // 4)  # Mostrar máximo 500 aristas o 1/4 del total
        
        for u, v, data in G.edges(data=True):
            if aristas_mostradas >= max_aristas_mostrar:
                break
                
            node_u = G.nodes[u]
            node_v = G.nodes[v]
            
            if 'y' in node_u and 'x' in node_u and 'y' in node_v and 'x' in node_v:
                # Color según tipo de vía
                tipo_via = data.get('tipo_via', 'jiron_comercial')
                if tipo_via == 'avenida_principal':
                    color = '#e74c3c'  # Rojo para avenidas principales
                    peso = 3
                elif tipo_via == 'calle_colectora':
                    color = '#f39c12'  # Naranja para colectoras
                    peso = 2
                else:
                    color = '#95a5a6'  # Gris para calles menores
                    peso = 1
                
                folium.PolyLine(
                    locations=[[node_u['y'], node_u['x']], [node_v['y'], node_v['x']]],
                    color=color,
                    weight=peso,
                    opacity=0.6,
                    popup=f"Arista: {u}→{v}<br>Tipo: {tipo_via}<br>Longitud: {data.get('length', 0):.1f}m"
                ).add_to(mapa_grafo)
                
                aristas_mostradas += 1
        
        # Agregar leyenda
        leyenda_html = f'''
        <div style="position: fixed; 
                    top: 10px; left: 50px; width: 300px; height: 200px; 
                    background-color: white; border:2px solid grey; z-index:9999; 
                    font-size:10px; padding: 10px">
        <h4>🗺️ Análisis del Grafo de Tacna</h4>
        <p><b>📊 Estadísticas:</b></p>
        <ul style="margin: 5px; padding-left: 15px;">
            <li>Nodos: {num_nodos}</li>
            <li>Arcos: {num_arcos}</li>
            <li>Componentes conectados: {num_componentes}</li>
            <li>Nodos aislados: {len(nodos_aislados)}</li>
            <li>Sin entrada: {len(nodos_sin_entrada)}</li>
            <li>Sin salida: {len(nodos_sin_salida)}</li>
        </ul>
        <p><b>🎨 Leyenda:</b></p>
        <ul style="margin: 5px; padding-left: 15px;">
            <li>🔴 Hub importante (≥6 conexiones)</li>
            <li>🔵 Nodo normal</li>
            <li>⚫ Nodo aislado</li>
            <li>⬆️ Solo salida</li>
            <li>⬇️ Solo entrada</li>
        </ul>
        </div>
        '''
        mapa_grafo.get_root().html.add_child(folium.Element(leyenda_html))
        
        # Estadísticas detalladas
        estadisticas = {
            "nodos_totales": num_nodos,
            "arcos_totales": num_arcos,
            "componentes_conectados": num_componentes,
            "componente_principal": len(componentes_conectados[0]) if componentes_conectados else 0,
            "nodos_aislados": len(nodos_aislados),
            "nodos_sin_entrada": len(nodos_sin_entrada),
            "nodos_sin_salida": len(nodos_sin_salida),
            "densidad": nx.density(G),
            "grado_promedio": sum(dict(G.degree()).values()) / num_nodos if num_nodos > 0 else 0,
            "aristas_mostradas": aristas_mostradas,
            "centro": [centro_lat, centro_lon]
        }
        
        return mapa_grafo, estadisticas
        
    except Exception as e:
        st.error(f"❌ Error al crear visualización del grafo: {e}")
        return None, {"error": str(e)}

# --- Información sobre Visualización del Grafo ---
if G is not None:
    st.markdown("### �️ Visualización del Grafo de Red Vial")
    
    st.info("""
    � **Visualización del Grafo Integrada:** 
    
    Puede activar la visualización del grafo de conectividad directamente en el mapa principal usando el botón **"🗺️ Mostrar Grafo"** en la esquina superior izquierda del mapa.
    
    **Leyenda de la visualización:**
    - 🔴 **Hubs importantes:** Nodos con 6 o más conexiones (intersecciones principales)
    - � **Intersecciones:** Nodos con 3-5 conexiones (cruces normales)  
    - 🟢 **Conexión básica:** Nodos con 1-2 conexiones (calles simples)
    - ⚫ **Nodos aislados:** Sin conexiones (posibles problemas de datos)
    
    **Colores de las aristas (calles):**
    - 🟠 **Avenidas principales:** Vías rápidas urbanas
    - 🟣 **Calles colectoras:** Vías de distribución
    - 🟢 **Calles residenciales:** Vías locales
    - ⚫ **Otros tipos:** Jirones, pasajes, etc.
    
    Esta visualización ayuda a identificar problemas de conectividad que pueden causar fallas en el cálculo de rutas.
    """)

else:
    st.error("❌ No se pudo cargar el grafo de Tacna. Verifique la conexión a internet y reinicie la aplicación.")
    st.info("💡 **Sugerencia:** Asegúrese de tener una conexión estable a internet para descargar los datos de OpenStreetMap.")
