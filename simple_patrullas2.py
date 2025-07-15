import streamlit as st
import osmnx as ox
import networkx as nx
import json
import random
from geopy.distance import geodesic
import streamlit.components.v1 as components

# --- Configuración de la Página ---
st.set_page_config(
    page_title="Sistema de Despacho de Emergencia",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Título y Descripción ---
st.title("🚨 Sistema Experto de Soporte a la Decisión para Rutas de Emergencia")
st.markdown("*Modelo Híbrido: Grafo de Ruteo + Grafo Geométrico - Tacna, Perú*")

# --- Lógica de Carga de Grafos (Tarea de Luz) ---
@st.cache_data
def cargar_grafos():
    """
    Carga DOS grafos con una estrategia robusta para garantizar el ruteo.
    """
    try:
        place = "Tacna, Peru"
        
        # 1. Grafo para RUTEAR: simplificado y garantizado como conectado.
        G_ruta_base = ox.graph_from_place(place, network_type='drive', simplify=True)
        # FIX DEFINITIVO: Tomar el componente conectado más grande de la versión NO DIRIGIDA
        # para asegurar que no haya islas, y luego convertirlo de nuevo a dirigido.
        G_undirected = G_ruta_base.to_undirected()
        largest_cc = max(nx.connected_components(G_undirected), key=len)
        G_ruta = G_ruta_base.subgraph(largest_cc).copy()

        # 2. Grafo para VISUALIZAR: denso, con toda la geometría
        G_geom = ox.graph_from_place(place, network_type='drive', simplify=False)
        
        def anadir_atributos(G):
            for u, v, data in G.edges(data=True):
                data['length'] = data.get('length', geodesic((G.nodes[u]['y'], G.nodes[u]['x']), (G.nodes[v]['y'], G.nodes[v]['x'])).meters)
                highway = data.get('highway', 'residential')
                if isinstance(highway, list): highway = highway[0]
                if highway in ['motorway', 'trunk', 'primary']:
                    data.update({'tipo_via': 'avenida_principal', 'velocidad_base': 60, 'sigma_base': 5, 'factor_calidad': 1.0})
                elif highway in ['secondary', 'tertiary']:
                    data.update({'tipo_via': 'calle_colectora', 'velocidad_base': 40, 'sigma_base': 10, 'factor_calidad': 1.2})
                else: 
                    data.update({'tipo_via': 'jiron_comercial', 'velocidad_base': 30, 'sigma_base': 15, 'factor_calidad': 1.4})
            return G
        
        G_ruta = anadir_atributos(G_ruta)
        G_geom = anadir_atributos(G_geom)
        
        return G_ruta, G_geom
    except Exception as e:
        st.error(f"Error al cargar los grafos: {e}")
        return None, None

# --- Interfaz y Lógica Principal ---
st.sidebar.header("⚙️ Panel de Control de Simulación")

modo_incidente_activo = st.sidebar.toggle( "Activar Modo 'Añadir Incidente'", value=True)
st.sidebar.markdown("**Factores Dinámicos**")
perfil_horario = st.sidebar.selectbox("Perfil Horario:", ['valle', 'punta', 'noche'], index=1)
condicion_clima = st.sidebar.selectbox("Clima:", ['despejado', 'lluvia'])
st.sidebar.markdown("**Parámetros de Optimización**")
factor_riesgo_k = st.sidebar.slider("Aversión al Riesgo (k):", 0.0, 3.0, 1.5, 0.1)

G_ruta, G_geom = cargar_grafos()

if G_ruta and G_geom:
    # Preparar datos para JS
    def preparar_datos_grafo(G):
        nodes = {node: {'lat': data['y'], 'lon': data['x']} for node, data in G.nodes(data=True)}
        edges = [{'source': u, 'target': v, **data} for u, v, data in G.edges(data=True)]
        return nodes, edges

    nodes_ruta_data, edges_ruta_data = preparar_datos_grafo(G_ruta)
    nodes_geom_data, edges_geom_data = preparar_datos_grafo(G_geom)

    # Las patrullas DEBEN existir en el grafo de ruteo
    patrol_nodes = random.sample(list(G_ruta.nodes()), 5)
    patrullas_data = [{'id': f"P-{i+1}", 'nodo_actual': node, 'status': 'disponible'} for i, node in enumerate(patrol_nodes)]

    if modo_incidente_activo:
        st.info("ℹ️ **Modo Incidente Activado:** Haz clic en el mapa para reportar una emergencia.")
    else:
        st.warning("⚠️ **Modo Incidente Desactivado:** Activa el interruptor para reportar un incidente.")

    # --- HTML y JavaScript ---
    with st.container():
        html_content = f"""
        <!DOCTYPE html><html><head>
            <title>Sistema de Despacho</title><meta charset="utf-8" />
            <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css" />
            <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
            <style>
                #map {{ height: 600px; width: 100%; cursor: {'crosshair' if modo_incidente_activo else 'default'}; }}
                .recommendations-panel {{ position: absolute; bottom: 10px; right: 10px; z-index: 1000; background: rgba(255, 255, 255, 0.95); padding: 10px; border-radius: 5px; box-shadow: 0 2px 10px rgba(0,0,0,0.2); max-width: 450px; max-height: 400px; overflow-y: auto; }}
                .patrol-marker-disponible {{ background: linear-gradient(135deg, #1e90ff, #00BFFF); color: white; border-radius: 50%; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: bold; border: 2px solid white; box-shadow: 0 0 8px rgba(0,0,0,0.5); }}
                .patrol-marker-en_ruta {{ background: linear-gradient(135deg, #ff4e50, #f9d423); color: white; border-radius: 50%; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: bold; border: 2px solid white; box-shadow: 0 0 8px rgba(0,0,0,0.5); animation: pulse 1.5s infinite; }}
                @keyframes pulse {{ 0% {{ box-shadow: 0 0 8px rgba(255, 78, 80, 0.7); }} 50% {{ box-shadow: 0 0 14px 4px rgba(255, 78, 80, 0.3); }} 100% {{ box-shadow: 0 0 8px rgba(255, 78, 80, 0.7); }} }}
            </style>
        </head><body>
            <div id="map"></div>
            <div class="recommendations-panel" id="recommendations-container"><h4>📋 Panel de Recomendaciones</h4><div id="recommendations">Esperando incidente...</div></div>
            <script>
                // --- ARQUITECTURA DE DOS GRAFOS ---
                const nodosRuta = {json.dumps(nodes_ruta_data)};
                const aristasRuta = {json.dumps(edges_ruta_data)};
                const nodosGeom = {json.dumps(nodes_geom_data)};
                const aristasGeom = {json.dumps(edges_geom_data)};
                
                const MODO_INCIDENTE_ACTIVO = {str(modo_incidente_activo).lower()};
                const PERFIL_HORARIO = "{perfil_horario}";
                const CONDICION_CLIMA = "{condicion_clima}";
                const FACTOR_RIESGO_K = {factor_riesgo_k};
                
                const patrullas = {json.dumps(patrullas_data)};

                const map = L.map('map').setView([-18.0137, -70.2500], 14);
                L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ attribution: '© OpenStreetMap' }}).addTo(map);

                patrullas.forEach(p => {{
                    p.marker = L.marker([nodosRuta[p.nodo_actual].lat, nodosRuta[p.nodo_actual].lon], {{
                        icon: L.divIcon({{ html: `<div class="patrol-marker-${{p.status}}">${{p.id}}</div>`, iconSize: [30, 30], className: '' }})
                    }}).addTo(map).bindPopup(`<b>Patrulla ${{{'p.id'}}}</b><br>Estado: <span id="status-${{{'p.id'}}}">${{{'p.status'}}}</span>`);
                }});

                let incidentMarker, rutaRapidaLayer, rutaSeguraLayer;

                function crearListaAdyacencia(aristas) {{
                    const adjList = {{}};
                    aristas.forEach(edge => {{
                        if (!adjList[edge.source]) adjList[edge.source] = [];
                        adjList[edge.source].push({{...edge, node: edge.target}});
                    }});
                    return adjList;
                }}

                const adjRuta = crearListaAdyacencia(aristasRuta);
                const adjGeom = crearListaAdyacencia(aristasGeom);

                // Pre-cálculo de costos para el grafo de ruteo
                Object.values(adjRuta).forEach(neighbors => {{
                    neighbors.forEach(edge => {{
                        let factorCongestion = 1.0;
                        if (PERFIL_HORARIO === "punta") {{
                            if (edge.tipo_via === "avenida_principal") factorCongestion = 3.0; else if (edge.tipo_via === "calle_colectora") factorCongestion = 2.2; else factorCongestion = 1.8;
                        }}
                        let factorClima = (CONDICION_CLIMA === "lluvia") ? 1.3 : 1.0;
                        const tiempo_base = edge.length / (edge.velocidad_base * 1000 / 3600);
                        const mu_dinamico = tiempo_base * edge.factor_calidad * factorCongestion * factorClima;
                        const sigma_dinamico = edge.sigma_base * Math.sqrt(factorCongestion);
                        edge.costo_rapido = mu_dinamico;
                        edge.costo_seguro = mu_dinamico + (FACTOR_RIESGO_K * sigma_dinamico);
                    }});
                }});

                // Algoritmo A* (optimizado para JS)
                function aStar(start, end, cost_type, adjacencyList, nodeSet) {{
                    function heuristic(nodeA, nodeB) {{
                        const pA = nodeSet[nodeA]; const pB = nodeSet[nodeB]; if (!pA || !pB) return Infinity;
                        const dist = L.latLng(pA.lat, pA.lon).distanceTo(L.latLng(pB.lat, pB.lon));
                        const maxSpeedKmh = 90; const maxSpeedMs = maxSpeedKmh * 1000 / 3600;
                        return dist / maxSpeedMs; 
                    }}
                    
                    let openSet = new Map([[start, heuristic(start, end)]]); // Mapa de nodo -> fScore
                    let cameFrom = new Map();
                    let gScore = new Map([[start, 0]]);

                    while (openSet.size > 0) {{
                        let current = null; let lowestFScore = Infinity;
                        for (let [node, score] of openSet) {{
                            if (score < lowestFScore) {{ lowestFScore = score; current = node; }}
                        }}

                        if (current === end) {{
                            let path = []; let temp = current;
                            while(temp) {{ path.unshift(temp); temp = cameFrom.get(temp); }}
                            return {{ path, cost: gScore.get(end) }};
                        }}

                        openSet.delete(current);
                        
                        (adjacencyList[current] || []).forEach(neighbor => {{
                            let tentativeGScore = gScore.get(current) + neighbor[cost_type];
                            if (tentativeGScore < (gScore.get(neighbor.node) || Infinity)) {{
                                cameFrom.set(neighbor.node, current);
                                gScore.set(neighbor.node, tentativeGScore);
                                openSet.set(neighbor.node, gScore.get(neighbor.node) + heuristic(neighbor.node, end));
                            }}
                        }});
                    }}
                    return null;
                }}
                
                // NUEVO: Función para reconstruir la ruta con geometría fiel
                function reconstruirRutaGeometrica(rutaIntersecciones, adjGeom) {{
                    if (!rutaIntersecciones || rutaIntersecciones.length < 2) return rutaIntersecciones;
                    let rutaCompleta = [rutaIntersecciones[0]];
                    for (let i = 0; i < rutaIntersecciones.length - 1; i++) {{
                        let startNode = rutaIntersecciones[i];
                        let endNode = rutaIntersecciones[i+1];
                        
                        // Búsqueda simple (BFS) en el grafo geométrico para encontrar el subtramo
                        let queue = [[startNode]];
                        let visited = new Set([startNode]);
                        let foundSubPath = null;

                        while(queue.length > 0) {{
                            let path = queue.shift();
                            let lastNode = path[path.length - 1];
                            if (lastNode === endNode) {{
                                foundSubPath = path;
                                break;
                            }}
                            (adjGeom[lastNode] || []).forEach(neighbor => {{
                                if (!visited.has(neighbor.node)) {{
                                    visited.add(neighbor.node);
                                    let newPath = [...path, neighbor.node];
                                    queue.push(newPath);
                                }}
                            }});
                        }}

                        if(foundSubPath) {{
                            rutaCompleta = rutaCompleta.concat(foundSubPath.slice(1));
                        }} else {{ // Fallback si el subtramo no se encuentra (no debería pasar)
                            rutaCompleta.push(endNode);
                        }}
                    }}
                    return rutaCompleta;
                }}

                map.on('click', function(e) {{
                    if (!MODO_INCIDENTE_ACTIVO) return;
                    const destCoords = e.latlng;
                    if (incidentMarker) map.removeLayer(incidentMarker);
                    incidentMarker = L.marker(destCoords, {{ icon: L.divIcon({{ html: '💥', className: '', iconSize: [30, 30] }}) }}).addTo(map).bindPopup("<b>Incidente</b>").openPopup();
                    
                    // FIX DEFINITIVO: Buscar el nodo más cercano en el grafo de RUTEO
                    let destNode = Object.keys(nodosRuta).reduce((a, b) =>
                         L.latLng(nodosRuta[a].lat, nodosRuta[a].lon).distanceTo(destCoords) < L.latLng(nodosRuta[b].lat, nodosRuta[b].lon).distanceTo(destCoords) ? a : b
                    );

                    const patrullasDisponibles = patrullas.filter(p => p.status === 'disponible');
                    if (patrullasDisponibles.length === 0) {{
                        document.getElementById('recommendations').innerHTML = "<p>⚠️ No hay patrullas disponibles.</p>"; return;
                    }}
                    
                    let candidates = [];
                    patrullasDisponibles.forEach(p => {{
                        const result = aStar(p.nodo_actual, destNode, 'costo_rapido', adjRuta, nodosRuta);
                        if (result) candidates.push({{ patrol: p, time: result.cost }});
                    }});

                    if (candidates.length === 0) {{
                         document.getElementById('recommendations').innerHTML = "<p>❌ No se encontró una ruta válida. Intente con otro punto.</p>"; return;
                    }}
                    
                    candidates.sort((a, b) => a.time - b.time);
                    const bestPatrol = candidates[0].patrol;
                    
                    // Se calculan ambas rutas usando el grafo de ruteo
                    const resultInterseccionesRapido = aStar(bestPatrol.nodo_actual, destNode, 'costo_rapido', adjRuta, nodosRuta);
                    const resultInterseccionesSeguro = aStar(bestPatrol.nodo_actual, destNode, 'costo_seguro', adjRuta, nodosRuta);
                    
                    if (rutaRapidaLayer) map.removeLayer(rutaRapidaLayer);
                    if (rutaSeguraLayer) map.removeLayer(rutaSeguraLayer);

                    let recommendationsHTML = `<h5>Recomendaciones para ${{{'bestPatrol.id'}}}:</h5>`;
                    const formatTime = (seconds) => {{
                        if (!seconds || seconds === Infinity) return "Inalcanzable";
                        return `${{Math.floor(seconds / 60)}} min ${{Math.round(seconds % 60)}} seg`;
                    }};

                    // Se reconstruyen y dibujan usando el grafo geométrico
                    if (resultInterseccionesRapido) {{
                        const rutaGeometrica = reconstruirRutaGeometrica(resultInterseccionesRapido.path, adjGeom);
                        const rutaCoords = rutaGeometrica.map(n => [nodosGeom[n].lat, nodosGeom[n].lon]);
                        rutaRapidaLayer = L.polyline(rutaCoords, {{ color: '#d9534f', weight: 5, opacity: 0.9 }}).addTo(map);
                        recommendationsHTML += `<div style="border-left: 5px solid #d9534f; padding-left: 10px; margin-bottom: 10px;"><b>1. Ruta Rápida</b><br>⏱️ Tiempo: ${{{'formatTime(resultInterseccionesRapido.cost)'}}}</div>`;
                    }}
                    
                    if (resultInterseccionesSeguro) {{
                         const rutaGeometrica = reconstruirRutaGeometrica(resultInterseccionesSeguro.path, adjGeom);
                         const rutaCoords = rutaGeometrica.map(n => [nodosGeom[n].lat, nodosGeom[n].lon]);
                         rutaSeguraLayer = L.polyline(rutaCoords, {{ color: '#0275d8', weight: 5, opacity: 0.9, dashArray: '10, 5' }}).addTo(map);
                         recommendationsHTML += `<div style="border-left: 5px solid #0275d8; padding-left: 10px;"><b>2. Ruta Segura</b><br>⏱️ Tiempo: ${{{'formatTime(resultInterseccionesSeguro.cost)'}}}</div>`;
                    }}
                    
                    document.getElementById('recommendations').innerHTML = recommendationsHTML;
                }});
            </script>
        </body></html>
        """
        components.html(html_content, height=620)
else:
    st.error("❌ No se pudieron cargar los grafos. Por favor, revisa la conexión a internet o los permisos de red.")